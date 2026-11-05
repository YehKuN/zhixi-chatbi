from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AuthRole = Literal["enterprise_admin", "employee"]

_USERNAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$"


class EnterpriseRegisterRequest(BaseModel):
    """企业首次入驻申请：公司信息 + 管理员账号。"""

    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(min_length=2, max_length=200)
    industry: str | None = Field(default=None, max_length=100)
    company_size: str | None = Field(default=None, max_length=50)
    contact_name: str = Field(min_length=1, max_length=80)
    contact_phone: str = Field(min_length=5, max_length=40)
    contact_email: str | None = Field(default=None, max_length=200)
    username: str = Field(pattern=_USERNAME_PATTERN)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=64)


class EmployeeRegisterRequest(BaseModel):
    """一般职工注册：凭公开企业 ID 挂接到所属企业。"""

    model_config = ConfigDict(extra="forbid")

    enterprise_code: str = Field(min_length=4, max_length=20)
    username: str = Field(pattern=_USERNAME_PATTERN)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=64)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=64)


class EnterpriseRead(BaseModel):
    """企业公开信息；code 即用户看到的企业 ID。"""

    code: str
    name: str
    industry: str | None
    company_size: str | None


class UserRead(BaseModel):
    id: str
    username: str
    display_name: str
    role: AuthRole
    created_at: datetime


class AuthSessionRead(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserRead
    enterprise: EnterpriseRead


class AuthProfileRead(BaseModel):
    user: UserRead
    enterprise: EnterpriseRead


class LogoutResult(BaseModel):
    logged_out: bool
