from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from application.deepseek_client import DeepSeekResponsesClient
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/ai/deepseek", tags=["deepseek"])


class DeepSeekAnalysisRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def _dataset_context(request: Request) -> str:
    path = Path(request.app.state.settings.datasource_root).parent / "demo" / "chatbi_sales.csv"
    if not path.exists():
        path = Path(__file__).resolve().parents[4] / "data" / "demo" / "chatbi_sales.csv"
    if not path.exists():
        return "演示数据文件暂不可用。"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    revenue = sum(float(row["order_amount"]) for row in rows)
    profit = sum(float(row["gross_profit"]) for row in rows)
    by_region: defaultdict[str, float] = defaultdict(float)
    by_product: defaultdict[str, float] = defaultdict(float)
    by_month: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        amount = float(row["order_amount"])
        by_region[row["region"]] += amount
        by_product[row["product"]] += amount
        by_month[row["order_date"][:7]] += amount
    region_lines = "；".join(
        f"{name} {value / 10000:.1f}万元"
        for name, value in sorted(by_region.items(), key=lambda item: item[1], reverse=True)
    )
    product_lines = "；".join(
        f"{name} {value / 10000:.1f}万元"
        for name, value in sorted(by_product.items(), key=lambda item: item[1], reverse=True)
    )
    month_lines = "；".join(
        f"{name} {value / 10000:.1f}万元" for name, value in sorted(by_month.items())
    )
    return (
        f"数据集 chatbi_sales.csv，共 {len(rows)} 条订单，覆盖 2026-01-01 至 2026-10-29。"
        f"累计订单金额 {revenue / 10000:.1f} 万元，累计毛利 {profit / 10000:.1f} 万元，"
        f"整体毛利率 {profit / revenue * 100:.1f}%。"
        f"区域销售额：{region_lines}。产品销售额：{product_lines}。"
        f"月度销售额：{month_lines}。"
    )


@router.post("/analyze", response_model=None)
async def analyze(request: Request, payload: DeepSeekAnalysisRequest) -> StreamingResponse:
    settings = request.app.state.settings
    key = settings.deepseek_api_key.get_secret_value() if settings.deepseek_api_key else None
    client = DeepSeekResponsesClient(
        api_key=key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        timeout_seconds=settings.deepseek_timeout_seconds,
        max_retries=settings.deepseek_max_retries,
    )
    context = _dataset_context(request)

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
