from __future__ import annotations

from typing import Annotated

from application.admin_service import AdminService
from contracts.admin import (
    AdminEnterpriseListRead,
    AdminLoginRequest,
    AdminOverviewRead,
    AdminPasswordResetRequest,
    AdminSessionRead,
    AdminUserRow,
    AdminUserStatusUpdate,
)
from contracts.api import ApiEnvelope, DeleteResult, Page, PageResult
from fastapi import APIRouter, Depends, Query, Request

from server.dependencies import get_admin_service, get_admin_token
from server.responses import success_response

router = APIRouter(prefix="/admin", tags=["admin"])
AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]
AdminTokenDep = Annotated[str, Depends(get_admin_token)]


@router.post("/login", response_model=ApiEnvelope[AdminSessionRead])
async def admin_login(
    request: Request,
    payload: AdminLoginRequest,
    service: AdminServiceDep,
):
    """平台管理员登录；凭据只来自服务器环境变量，与入驻企业账号完全分离。"""

    return success_response(request, service.login(payload.username, payload.password))


@router.get("/overview", response_model=ApiEnvelope[AdminOverviewRead])
async def admin_overview(
    request: Request,
    service: AdminServiceDep,
    token: AdminTokenDep,
):
    service.verify_token(token)
    return success_response(request, await service.overview())


@router.get("/enterprises", response_model=ApiEnvelope[AdminEnterpriseListRead])
async def admin_enterprises(
    request: Request,
    service: AdminServiceDep,
    token: AdminTokenDep,
    q: str | None = Query(default=None, max_length=200),
):
    service.verify_token(token)
    return success_response(request, await service.list_enterprises(q=q))


@router.get("/users", response_model=ApiEnvelope[PageResult[AdminUserRow]])
async def admin_users(
    request: Request,
    service: AdminServiceDep,
    token: AdminTokenDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, max_length=200),
    enterprise_id: str | None = Query(default=None, max_length=120),
):
    service.verify_token(token)
    return success_response(
        request,
        await service.list_users(
            Page(page=page, page_size=page_size), q=q, enterprise_id=enterprise_id
        ),
    )


@router.patch("/users/{user_id}/status", response_model=ApiEnvelope[AdminUserRow])
async def admin_update_user_status(
    request: Request,
    user_id: str,
    payload: AdminUserStatusUpdate,
    service: AdminServiceDep,
    token: AdminTokenDep,
):
    service.verify_token(token)
    return success_response(request, await service.set_user_status(user_id, payload))


@router.post("/users/{user_id}/reset-password", response_model=ApiEnvelope[DeleteResult])
async def admin_reset_password(
    request: Request,
    user_id: str,
    payload: AdminPasswordResetRequest,
    service: AdminServiceDep,
    token: AdminTokenDep,
):
    """重置成员密码并撤销其现有登录会话，强制使用新密码重新登录。"""

    service.verify_token(token)
    await service.reset_password(user_id, payload.password)
    return success_response(request, {"deleted": True})
