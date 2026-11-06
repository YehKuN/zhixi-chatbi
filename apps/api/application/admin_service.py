from __future__ import annotations

import base64
import hashlib
import hmac
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from contracts.admin import (
    AdminEnterpriseListRead,
    AdminEnterpriseRow,
    AdminOverviewRead,
    AdminSessionRead,
    AdminUserRow,
    AdminUserStatusUpdate,
)
from contracts.api import Page, PageResult
from contracts.errors import AppError, ErrorCode
from metadata.models import (
    AuthSessionModel,
    DataSourceModel,
    EnterpriseModel,
    RunModel,
    SessionModel,
    UserModel,
)
from server.config import Settings
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from application.auth_service import PasswordHasher, _ensure_aware


class AdminService:
    """平台运营管理：管理员鉴权、入驻企业总览、账号管理与 Token 用量统计。"""

    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    @property
    def configured(self) -> bool:
        password = self.settings.admin_password
        return password is not None and bool(password.get_secret_value())

    def _signing_key(self) -> bytes:
        return self.settings.secret_master_key.encode("utf-8")

    def _issue_token(self) -> AdminSessionRead:
        expires_at = datetime.now(UTC) + timedelta(hours=self.settings.admin_token_ttl_hours)
        expires_ts = int(expires_at.timestamp())
        payload = base64.urlsafe_b64encode(str(expires_ts).encode("ascii")).decode("ascii")
        signature = hmac.new(
            self._signing_key(), f"admin:{expires_ts}".encode("ascii"), hashlib.sha256
        ).hexdigest()
        return AdminSessionRead(token=f"{payload}.{signature}", expires_at=expires_at)

    def verify_token(self, token: str) -> None:
        """校验管理员 Bearer；签名或有效期不通过统一视为未登录。"""

        payload, _, signature = token.partition(".")
        try:
            expires_ts = int(base64.urlsafe_b64decode(payload.encode("ascii")).decode("ascii"))
        except (ValueError, UnicodeError):
            raise self._unauthorized() from None
        expected = hmac.new(
            self._signing_key(), f"admin:{expires_ts}".encode("ascii"), hashlib.sha256
        ).hexdigest()
        if not signature or not hmac.compare_digest(signature, expected):
            raise self._unauthorized()
        if expires_ts <= int(time.time()):
            raise self._unauthorized()

    @staticmethod
    def _unauthorized() -> AppError:
        return AppError(ErrorCode.AUTH_REQUIRED, "管理员登录状态已失效", status_code=401)

    def login(self, username: str, password: str) -> AdminSessionRead:
        if not self.configured:
            raise AppError(
                ErrorCode.CONFIGURATION_ERROR,
                "未配置管理员密码，请在服务器环境变量中设置 ADMIN_PASSWORD",
                status_code=503,
            )
        expected_password = self.settings.admin_password
        assert expected_password is not None
        username_ok = hmac.compare_digest(username, self.settings.admin_username)
        password_ok = hmac.compare_digest(password, expected_password.get_secret_value())
        if not (username_ok and password_ok):
            raise AppError(ErrorCode.INVALID_CREDENTIALS, "管理员账号或密码错误", status_code=401)
        return self._issue_token()

    async def overview(self) -> AdminOverviewRead:
        enterprise_count = await self._scalar(select(func.count()).select_from(EnterpriseModel))
        active_enterprise_count = await self._scalar(
            select(func.count())
            .select_from(EnterpriseModel)
            .where(EnterpriseModel.status == "active")
        )
        user_count = await self._scalar(select(func.count()).select_from(UserModel))
        active_user_count = await self._scalar(
            select(func.count()).select_from(UserModel).where(UserModel.status == "active")
        )
        datasource_count = await self._scalar(
            select(func.count())
            .select_from(DataSourceModel)
            .where(DataSourceModel.status != "deleted")
        )
        session_count = await self._scalar(select(func.count()).select_from(SessionModel))
        run_count = await self._scalar(select(func.count()).select_from(RunModel))
        totals = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(RunModel.usage_input_tokens), 0),
                    func.coalesce(func.sum(RunModel.usage_output_tokens), 0),
                    func.coalesce(func.sum(RunModel.usage_total_tokens), 0),
                    func.coalesce(func.sum(RunModel.usage_model_calls), 0),
                    func.count(RunModel.usage_total_tokens),
                )
            )
        ).one()
        since = datetime.now(UTC) - timedelta(days=30)
        recent = await self._scalar(
            select(func.coalesce(func.sum(RunModel.usage_total_tokens), 0)).where(
                RunModel.finished_at >= since
            )
        )
        return AdminOverviewRead(
            enterprise_count=enterprise_count,
            active_enterprise_count=active_enterprise_count,
            user_count=user_count,
            active_user_count=active_user_count,
            datasource_count=datasource_count,
            session_count=session_count,
            run_count=run_count,
            usage_input_tokens=int(totals[0] or 0),
            usage_output_tokens=int(totals[1] or 0),
            usage_total_tokens=int(totals[2] or 0),
            usage_model_calls=int(totals[3] or 0),
            recent_30d_tokens=int(recent),
            tracked_usage_runs=int(totals[4] or 0),
        )

    async def list_enterprises(self, *, q: str | None = None) -> AdminEnterpriseListRead:
        stmt = select(EnterpriseModel).order_by(EnterpriseModel.created_at.desc())
        cleaned = (q or "").strip()
        if cleaned:
            pattern = f"%{cleaned}%"
            stmt = stmt.where(
                or_(EnterpriseModel.name.ilike(pattern), EnterpriseModel.code.ilike(pattern))
            )
        enterprises = list(await self.db.scalars(stmt))
        if not enterprises:
            return AdminEnterpriseListRead(items=[], total=0)

        users = await self._grouped(
            select(
                UserModel.enterprise_id,
                func.count(UserModel.id),
                func.coalesce(func.sum(case((UserModel.status == "active", 1), else_=0)), 0),
                func.coalesce(
                    func.sum(case((UserModel.role == "enterprise_admin", 1), else_=0)), 0
                ),
            ).group_by(UserModel.enterprise_id)
        )
        datasources = await self._grouped(
            select(DataSourceModel.enterprise_id, func.count(DataSourceModel.id))
            .where(DataSourceModel.status != "deleted")
            .group_by(DataSourceModel.enterprise_id)
        )
        sessions = await self._grouped(
            select(SessionModel.enterprise_id, func.count(SessionModel.id)).group_by(
                SessionModel.enterprise_id
            )
        )
        runs = await self._grouped(
            select(
                SessionModel.enterprise_id,
                func.count(RunModel.id),
                func.coalesce(func.sum(RunModel.usage_input_tokens), 0),
                func.coalesce(func.sum(RunModel.usage_output_tokens), 0),
                func.coalesce(func.sum(RunModel.usage_total_tokens), 0),
                func.max(RunModel.finished_at),
            )
            .join(SessionModel, RunModel.session_id == SessionModel.id)
            .group_by(SessionModel.enterprise_id)
        )

        items: list[AdminEnterpriseRow] = []
        for enterprise in enterprises:
            user_stats = users.get(enterprise.id, (0, 0, 0))
            usage = runs.get(enterprise.id, (0, 0, 0, 0, None))
            items.append(
                AdminEnterpriseRow(
                    id=enterprise.id,
                    code=enterprise.code,
                    name=enterprise.name,
                    industry=enterprise.industry,
                    company_size=enterprise.company_size,
                    status=enterprise.status,
                    created_at=_ensure_aware(enterprise.created_at),
                    user_count=int(user_stats[0] or 0),
                    active_user_count=int(user_stats[1] or 0),
                    admin_count=int(user_stats[2] or 0),
                    datasource_count=int(datasources.get(enterprise.id, 0) or 0),
                    session_count=int(sessions.get(enterprise.id, 0) or 0),
                    run_count=int(usage[0] or 0),
                    usage_input_tokens=int(usage[1] or 0),
                    usage_output_tokens=int(usage[2] or 0),
                    usage_total_tokens=int(usage[3] or 0),
                    last_run_at=(
                        _ensure_aware(usage[4]) if usage[4] is not None else None
                    ),
                )
            )
        return AdminEnterpriseListRead(items=items, total=len(items))

    async def list_users(
        self,
        page: Page,
        *,
        q: str | None = None,
        enterprise_id: str | None = None,
    ) -> PageResult[AdminUserRow]:
        conditions: list[Any] = []
        cleaned = (q or "").strip()
        if cleaned:
            pattern = f"%{cleaned}%"
            conditions.append(
                or_(
                    UserModel.username.ilike(pattern),
                    UserModel.display_name.ilike(pattern),
                    EnterpriseModel.name.ilike(pattern),
                    EnterpriseModel.code.ilike(pattern),
                )
            )
        if enterprise_id:
            conditions.append(UserModel.enterprise_id == enterprise_id)

        base = select(UserModel, EnterpriseModel).join(
            EnterpriseModel, UserModel.enterprise_id == EnterpriseModel.id
        )
        count_stmt = (
            select(func.count())
            .select_from(UserModel)
            .join(EnterpriseModel, UserModel.enterprise_id == EnterpriseModel.id)
        )
        for condition in conditions:
            base = base.where(condition)
            count_stmt = count_stmt.where(condition)
        total = await self._scalar(count_stmt)
        rows = list(
            await self.db.execute(
                base.order_by(UserModel.created_at.desc())
                .offset(page.offset)
                .limit(page.page_size)
            )
        )
        user_ids = [user.id for user, _ in rows]
        last_logins: dict[str, datetime] = {}
        if user_ids:
            sessions = await self.db.execute(
                select(AuthSessionModel.user_id, func.max(AuthSessionModel.created_at))
                .where(AuthSessionModel.user_id.in_(user_ids))
                .group_by(AuthSessionModel.user_id)
            )
            last_logins = {
                str(user_id): _ensure_aware(created_at)
                for user_id, created_at in sessions
                if created_at is not None
            }
        items = [
            AdminUserRow(
                id=user.id,
                enterprise_id=enterprise.id,
                enterprise_code=enterprise.code,
                enterprise_name=enterprise.name,
                username=user.username,
                display_name=user.display_name,
                role="enterprise_admin" if user.role == "enterprise_admin" else "employee",
                status=user.status,
                created_at=_ensure_aware(user.created_at),
                last_login_at=last_logins.get(user.id),
            )
            for user, enterprise in rows
        ]
        return PageResult(items=items, total=total, page=page.page, page_size=page.page_size)

    async def set_user_status(
        self, user_id: str, payload: AdminUserStatusUpdate
    ) -> AdminUserRow:
        user = await self.db.get(UserModel, user_id)
        if user is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, "账号不存在", status_code=404)
        if payload.status == "disabled" and user.role == "enterprise_admin":
            others = await self._scalar(
                select(func.count())
                .select_from(UserModel)
                .where(
                    UserModel.enterprise_id == user.enterprise_id,
                    UserModel.role == "enterprise_admin",
                    UserModel.status == "active",
                    UserModel.id != user.id,
                )
            )
            if others == 0:
                raise AppError(
                    ErrorCode.ADMIN_ACTION_REJECTED,
                    "该企业仅剩一名可用管理员，不能停用",
                    status_code=409,
                )
        user.status = payload.status
        if payload.status == "disabled":
            await self.db.execute(
                update(AuthSessionModel)
                .where(
                    AuthSessionModel.user_id == user.id,
                    AuthSessionModel.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )
            await self.db.flush()
        enterprise = await self.db.get(EnterpriseModel, user.enterprise_id)
        assert enterprise is not None
        return AdminUserRow(
            id=user.id,
            enterprise_id=enterprise.id,
            enterprise_code=enterprise.code,
            enterprise_name=enterprise.name,
            username=user.username,
            display_name=user.display_name,
            role="enterprise_admin" if user.role == "enterprise_admin" else "employee",
            status=user.status,
            created_at=_ensure_aware(user.created_at),
            last_login_at=None,
        )

    async def reset_password(self, user_id: str, password: str) -> None:
        user = await self.db.get(UserModel, user_id)
        if user is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, "账号不存在", status_code=404)
        user.password_hash = PasswordHasher.hash(password)
        await self.db.execute(
            update(AuthSessionModel)
            .where(
                AuthSessionModel.user_id == user.id,
                AuthSessionModel.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await self.db.flush()

    async def _scalar(self, statement: Any) -> int:
        value = await self.db.scalar(statement)
        return int(value or 0)

    async def _grouped(self, statement: Any) -> dict[str, Any]:
        """单列聚合直接返回值，多列聚合返回元组，便于调用方按列读取。"""

        rows = await self.db.execute(statement)
        grouped: dict[str, Any] = {}
        for row in rows:
            if row[0] is None:
                continue
            values = tuple(row[1:])
            grouped[str(row[0])] = values[0] if len(values) == 1 else values
        return grouped
