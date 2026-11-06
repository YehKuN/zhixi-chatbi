from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class AdminSessionRead(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: datetime


class AdminOverviewRead(BaseModel):
    """平台级总览：只暴露聚合计数，不返回企业业务数据。"""

    enterprise_count: int
    active_enterprise_count: int
    user_count: int
    active_user_count: int
    datasource_count: int
    session_count: int
    run_count: int
    usage_input_tokens: int
    usage_output_tokens: int
    usage_total_tokens: int
    usage_model_calls: int
    recent_30d_tokens: int
    tracked_usage_runs: int


class AdminEnterpriseRow(BaseModel):
    id: str
    code: str
    name: str
    industry: str | None
    company_size: str | None
    status: str
    created_at: datetime
    user_count: int
    active_user_count: int
    admin_count: int
    datasource_count: int
    session_count: int
    run_count: int
    usage_input_tokens: int
    usage_output_tokens: int
    usage_total_tokens: int
    last_run_at: datetime | None


class AdminEnterpriseListRead(BaseModel):
    items: list[AdminEnterpriseRow]
    total: int


class AdminUserRow(BaseModel):
    id: str
    enterprise_id: str
    enterprise_code: str
    enterprise_name: str
    username: str
    display_name: str
    role: Literal["enterprise_admin", "employee"]
    status: str
    created_at: datetime
    last_login_at: datetime | None


class AdminUserStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "disabled"]


class AdminPasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=8, max_length=64)
