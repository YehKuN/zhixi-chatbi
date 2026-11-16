from __future__ import annotations

from typing import Annotated

from application.diagnosis_intent import DiagnosisIntentService
from application.diagnosis_service import DiagnosisService
from contracts.api import ApiEnvelope
from contracts.diagnosis import (
    DiagnosisCapabilitiesRead,
    DiagnosisIntentRead,
    DiagnosisQuestionRequest,
    DiagnosisRequest,
    DiagnosisResultRead,
)
from fastapi import APIRouter, Depends, Request

from server.dependencies import get_diagnosis_intent_service, get_diagnosis_service
from server.responses import success_response

router = APIRouter(tags=["diagnosis"])
DiagnosisServiceDep = Annotated[DiagnosisService, Depends(get_diagnosis_service)]
DiagnosisIntentDep = Annotated[DiagnosisIntentService, Depends(get_diagnosis_intent_service)]


@router.get(
    "/datasources/{datasource_id}/diagnosis/capabilities",
    response_model=ApiEnvelope[DiagnosisCapabilitiesRead],
)
async def get_diagnosis_capabilities(
    request: Request,
    datasource_id: str,
    service: DiagnosisServiceDep,
):
    """返回当前数据源可诊断的指标、时间字段与维度。"""

    return success_response(request, await service.capabilities(datasource_id))


@router.post(
    "/datasources/{datasource_id}/diagnosis/intent",
    response_model=ApiEnvelope[DiagnosisIntentRead],
)
async def parse_diagnosis_question(
    request: Request,
    datasource_id: str,
    payload: DiagnosisQuestionRequest,
    service: DiagnosisIntentDep,
):
    """把一句中文问题解析成当前数据源可执行的诊断意图。"""

    return success_response(request, await service.parse(datasource_id, payload.question))


@router.post(
    "/datasources/{datasource_id}/diagnosis/runs",
    response_model=ApiEnvelope[DiagnosisResultRead],
)
async def create_diagnosis_run(
    request: Request,
    datasource_id: str,
    payload: DiagnosisRequest,
    service: DiagnosisServiceDep,
):
    """执行一次确定性经营诊断，返回贡献分解、假设-证据图与不变量验证。"""

    return success_response(request, await service.run(datasource_id, payload))


__all__ = ["router"]
