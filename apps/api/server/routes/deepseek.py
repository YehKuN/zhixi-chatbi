from __future__ import annotations

import json
from typing import Annotated

from application.dataset_overview import DatasetOverviewService
from application.deepseek_client import DeepSeekResponsesClient
from contracts.datasources import DatasetOverviewRead
from contracts.errors import AppError, ErrorCode
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from server.dependencies import get_dataset_overview_service

router = APIRouter(prefix="/ai/deepseek", tags=["deepseek"])


class DeepSeekAnalysisRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    datasource_id: str = Field(min_length=1, max_length=120)


def _dataset_context(overview: DatasetOverviewRead) -> str:
    """仅使用当前真实数据源的聚合结果，作为快速分析的真实上下文。"""

    lines = [
        f"数据源：{overview.datasource_name}（{overview.datasource_type}），"
        f"共 {overview.row_count:,} 条记录、{overview.column_count} 个字段，"
        f"{overview.period_label}。",
        f"字段完整度：{overview.quality.non_null_pct:.1f}%；"
        f"数值字段 {overview.quality.numeric_columns} 个、"
        f"分类字段 {overview.quality.categorical_columns} 个。",
    ]
    if overview.target_label and overview.conversion_pct is not None:
        lines.append(f"整体{overview.target_label}：{overview.conversion_pct:.1f}%。")
    if overview.trend:
        counts = overview.trend.series[0].values
        rates = overview.trend.series[1].values if len(overview.trend.series) > 1 else []
        parts = [
            f"{label} {counts[index]:.0f} 条"
            + (f"、{rates[index]:.1f}%" if index < len(rates) else "")
            for index, label in enumerate(overview.trend.labels)
            if index < len(counts)
        ]
        lines.append("月度趋势：" + "；".join(parts))
    if overview.distribution:
        lines.append(
            overview.distribution.title + "："
            + "；".join(
                f"{item.name} {item.count:,} 条（{item.share_pct:.1f}%）"
                for item in overview.distribution.items
            )
        )
    if overview.ranking:
        lines.append(
            overview.ranking.title + "："
            + "；".join(
                f"{item.name} "
                f"{item.conversion_pct if item.conversion_pct is not None else item.share_pct}%"
                for item in overview.ranking.items
            )
        )
    lines.append(
        "以上是平台对当前数据源生成的实时聚合结果，任何结论都必须使用这些真实数字。"
    )
    return "\n".join(lines)


@router.post("/analyze", response_model=None)
async def analyze(
    request: Request,
    payload: DeepSeekAnalysisRequest,
    service: Annotated[DatasetOverviewService, Depends(get_dataset_overview_service)],
) -> StreamingResponse:
    settings = request.app.state.settings
    key = settings.deepseek_api_key.get_secret_value() if settings.deepseek_api_key else None
    if key is None:
        raise AppError(
            ErrorCode.MODEL_CONFIG_INVALID,
            "DeepSeek API Key 未配置，无法执行快速分析",
            status_code=503,
        )
    overview = await service.get(payload.datasource_id)
    client = DeepSeekResponsesClient(
        api_key=key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        timeout_seconds=settings.deepseek_timeout_seconds,
        max_retries=settings.deepseek_max_retries,
        max_output_tokens=settings.deepseek_max_output_tokens,
    )
    context = _dataset_context(overview)

    async def events():
        yield (
            "event: status\ndata: " + json.dumps({"status": "started"}, ensure_ascii=False) + "\n\n"
        )
        async for kind, value in client.stream_analysis(
            question=payload.question, dataset_context=context
        ):
            if kind == "delta":
                yield (
                    "event: delta\ndata: "
                    + json.dumps({"text": value}, ensure_ascii=False)
                    + "\n\n"
                )
            elif kind == "error":
                yield (
                    "event: error\ndata: "
                    + json.dumps({"message": value}, ensure_ascii=False)
                    + "\n\n"
                )
                return
            elif kind == "done":
                yield (
                    "event: done\ndata: "
                    + json.dumps({"status": "completed"}, ensure_ascii=False)
                    + "\n\n"
                )
                return

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
