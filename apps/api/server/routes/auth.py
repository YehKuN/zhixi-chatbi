from __future__ import annotations

from typing import Annotated

from application.auth_service import (
    AuthContext,
    AuthService,
    enterprise_read,
    user_read,
)
from contracts.api import ApiEnvelope
from contracts.auth import (
    AuthProfileRead,
    AuthSessionRead,
    EmployeeRegisterRequest,
    EnterpriseRegisterRequest,
    LoginRequest,
    LogoutResult,
)
from fastapi import APIRouter, Depends, Request

from server.dependencies import get_auth_context, get_auth_service, get_bearer_token
from server.responses import success_response

router = APIRouter(prefix="/auth", tags=["auth"])
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
AuthContextDep = Annotated[AuthContext, Depends(get_auth_context)]
BearerTokenDep = Annotated[str, Depends(get_bearer_token)]


@router.post(
    "/enterprises/register",
    status_code=201,
    response_model=ApiEnvelope[AuthSessionRead],
)
async def register_enterprise(
    request: Request,
    payload: EnterpriseRegisterRequest,
    service: AuthServiceDep,
):
    """企业首次入驻并创建管理员账号，成功后立即返回登录令牌。"""

    return success_response(
        request,
        await service.register_enterprise(payload),
        status_code=201,
    )


@router.post(
    "/employees/register",
    status_code=201,
    response_model=ApiEnvelope[AuthSessionRead],
)
async def register_employee(
    request: Request,
    payload: EmployeeRegisterRequest,
    service: AuthServiceDep,
):
    """职工凭公开企业 ID 注册并自动挂接到所属企业。"""

    return success_response(
        request,
        await service.register_employee(payload),
        status_code=201,
    )


@router.post("/login", response_model=ApiEnvelope[AuthSessionRead])
async def login(
    request: Request,
    payload: LoginRequest,
    service: AuthServiceDep,
):
    """账号密码登录，返回新的 Bearer 令牌。"""

    return success_response(request, await service.login(payload))


@router.get("/me", response_model=ApiEnvelope[AuthProfileRead])
async def read_me(request: Request, context: AuthContextDep):
    """返回当前令牌对应的用户与企业公开信息。"""

    return success_response(
        request,
        AuthProfileRead(
            user=user_read(context.user),
            enterprise=enterprise_read(context.enterprise),
        ),
    )


@router.post("/logout", response_model=ApiEnvelope[LogoutResult])
async def logout(
    request: Request,
    token: BearerTokenDep,
    service: AuthServiceDep,
):
    """撤销当前令牌；重复调用保持幂等。"""

    revoked = await service.logout(token)
    return success_response(request, LogoutResult(logged_out=revoked))
