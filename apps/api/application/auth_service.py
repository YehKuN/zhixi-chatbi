from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from contracts.auth import (
    AuthSessionRead,
    EmployeeRegisterRequest,
    EnterpriseRead,
    EnterpriseRegisterRequest,
    LoginRequest,
    UserRead,
)
from contracts.errors import AppError, ErrorCode
from metadata.models import AuthSessionModel, EnterpriseModel, UserModel
from metadata.repositories import AuthRepository

_ENTERPRISE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_ENTERPRISE_CODE_PATTERN = re.compile(r"^ZX-[A-Z0-9]{6}$")
_USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
_SESSION_TTL = timedelta(days=7)


class PasswordHasher:
    """标准库 scrypt 密码哈希；不引入 passlib/bcrypt 依赖。"""

    n = 2**14
    r = 8
    p = 1
    dklen = 32

    @classmethod
    def hash(cls, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=cls.n,
            r=cls.r,
            p=cls.p,
            dklen=cls.dklen,
        )
        return f"scrypt${cls.n}${cls.r}${cls.p}${salt.hex()}${digest.hex()}"

    @classmethod
    def verify(cls, password: str, encoded: str) -> bool:
        try:
            scheme, n_text, r_text, p_text, salt_hex, hash_hex = encoded.split("$")
            if scheme != "scrypt":
                return False
            digest = hashlib.scrypt(
                password.encode("utf-8"),
                salt=bytes.fromhex(salt_hex),
                n=int(n_text),
                r=int(r_text),
                p=int(p_text),
                dklen=len(bytes.fromhex(hash_hex)),
            )
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(digest.hex(), hash_hex)


@dataclass(frozen=True)
class AuthContext:
    """一次已鉴权请求的最小身份上下文。"""

    user: UserModel
    enterprise: EnterpriseModel
    session: AuthSessionModel


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not _USERNAME_PATTERN.fullmatch(normalized):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "用户名需为 3-32 位字母、数字或 _ . -，且以字母或数字开头",
            status_code=422,
        )
    return normalized


def _normalize_enterprise_code(code: str) -> str:
    normalized = code.strip().upper()
    if not _ENTERPRISE_CODE_PATTERN.fullmatch(normalized):
        raise AppError(
            ErrorCode.INVALID_ENTERPRISE_CODE,
            "企业 ID 格式不正确，应形如 ZX-ABCDEF",
            status_code=404,
        )
    return normalized


def _ensure_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def enterprise_read(model: EnterpriseModel) -> EnterpriseRead:
    return EnterpriseRead(
        code=model.code,
        name=model.name,
        industry=model.industry,
        company_size=model.company_size,
    )


def user_read(model: UserModel) -> UserRead:
    return UserRead(
        id=model.id,
        username=model.username,
        display_name=model.display_name,
        role=model.role,  # type: ignore[arg-type]
        created_at=_ensure_aware(model.created_at),
    )


class AuthService:
    """企业入驻、职工加入、登录与令牌校验。"""

    def __init__(self, repository: AuthRepository) -> None:
        self.repository = repository

    async def _issue_session(
        self,
        user: UserModel,
        enterprise: EnterpriseModel,
    ) -> AuthSessionRead:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + _SESSION_TTL
        await self.repository.create_session(
            token_hash=_hash_token(token),
            user_id=user.id,
            expires_at=expires_at,
        )
        return AuthSessionRead(
            token=token,
            expires_at=expires_at,
            user=user_read(user),
            enterprise=enterprise_read(enterprise),
        )

    async def _generate_enterprise_code(self) -> str:
        for _ in range(10):
            suffix = "".join(
                secrets.choice(_ENTERPRISE_CODE_ALPHABET) for _ in range(6)
            )
            code = f"ZX-{suffix}"
            if await self.repository.get_enterprise_by_code(code) is None:
                return code
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            "企业 ID 生成失败，请稍后重试",
            status_code=500,
        )

    async def register_enterprise(
        self, payload: EnterpriseRegisterRequest
    ) -> AuthSessionRead:
        company_name = payload.company_name.strip()
        username = _normalize_username(payload.username)
        if await self.repository.get_enterprise_by_name(company_name) is not None:
            raise AppError(
                ErrorCode.ENTERPRISE_ALREADY_REGISTERED,
                "该公司全称已完成注册，请联系企业管理员获取企业 ID",
                status_code=409,
            )
        if await self.repository.get_user_by_username(username) is not None:
            raise AppError(ErrorCode.USERNAME_TAKEN, "该用户名已被占用", status_code=409)

        enterprise = await self.repository.create_enterprise(
            code=await self._generate_enterprise_code(),
            name=company_name,
            industry=(payload.industry or "").strip() or None,
            company_size=(payload.company_size or "").strip() or None,
            contact_name=payload.contact_name.strip(),
            contact_phone=payload.contact_phone.strip(),
            contact_email=(payload.contact_email or "").strip() or None,
        )
        user = await self.repository.create_user(
            enterprise_id=enterprise.id,
            username=username,
            display_name=payload.display_name.strip(),
            role="enterprise_admin",
            password_hash=PasswordHasher.hash(payload.password),
        )
        return await self._issue_session(user, enterprise)

    async def register_employee(
        self, payload: EmployeeRegisterRequest
    ) -> AuthSessionRead:
        code = _normalize_enterprise_code(payload.enterprise_code)
        username = _normalize_username(payload.username)
        enterprise = await self.repository.get_enterprise_by_code(code)
        if enterprise is None or enterprise.status != "active":
            raise AppError(
                ErrorCode.INVALID_ENTERPRISE_CODE,
                "企业 ID 不存在或企业已停用，请向企业管理员确认",
                status_code=404,
            )
        if await self.repository.get_user_by_username(username) is not None:
            raise AppError(ErrorCode.USERNAME_TAKEN, "该用户名已被占用", status_code=409)

        user = await self.repository.create_user(
            enterprise_id=enterprise.id,
            username=username,
            display_name=payload.display_name.strip(),
            role="employee",
            password_hash=PasswordHasher.hash(payload.password),
        )
        return await self._issue_session(user, enterprise)

    async def login(self, payload: LoginRequest) -> AuthSessionRead:
        username = payload.username.strip().lower()
        user = await self.repository.get_user_by_username(username)
        if (
            user is None
            or user.status != "active"
            or not PasswordHasher.verify(payload.password, user.password_hash)
        ):
            raise AppError(
                ErrorCode.INVALID_CREDENTIALS, "用户名或密码错误", status_code=401
            )
        enterprise = await self.repository.get_enterprise(user.enterprise_id)
        if enterprise is None or enterprise.status != "active":
            raise AppError(
                ErrorCode.INVALID_CREDENTIALS, "所属企业不可用", status_code=401
            )
        return await self._issue_session(user, enterprise)

    async def authenticate(self, token: str) -> AuthContext:
        session = await self.repository.get_session_by_token_hash(_hash_token(token))
        now = datetime.now(UTC)
        if (
            session is None
            or session.revoked_at is not None
            or _ensure_aware(session.expires_at) <= now
        ):
            raise AppError(
                ErrorCode.AUTH_REQUIRED, "登录状态已失效，请重新登录", status_code=401
            )
        user = await self.repository.get_user(session.user_id)
        if user is None or user.status != "active":
            raise AppError(ErrorCode.AUTH_REQUIRED, "账号不可用", status_code=401)
        enterprise = await self.repository.get_enterprise(user.enterprise_id)
        if enterprise is None or enterprise.status != "active":
            raise AppError(ErrorCode.AUTH_REQUIRED, "所属企业不可用", status_code=401)
        return AuthContext(user=user, enterprise=enterprise, session=session)

    async def logout(self, token: str) -> bool:
        session = await self.repository.get_session_by_token_hash(_hash_token(token))
        if session is None:
            return False
        await self.repository.revoke_session(session)
        return True
