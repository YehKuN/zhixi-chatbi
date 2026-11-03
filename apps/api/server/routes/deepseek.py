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
    if not rows:
        return "演示数据为空。"

    revenue = sum(float(row["order_amount"]) for row in rows)
    profit = sum(float(row["gross_profit"]) for row in rows)
    customers = {row["customer_id"] for row in rows}
    dates = sorted(row["order_date"] for row in rows)
    by_region: defaultdict[str, float] = defaultdict(float)
    by_product: defaultdict[str, float] = defaultdict(float)
    by_channel: defaultdict[str, float] = defaultdict(float)
    by_month_channel: defaultdict[tuple[str, str], float] = defaultdict(float)
    by_month_region: defaultdict[tuple[str, str], float] = defaultdict(float)
    by_month_product: defaultdict[tuple[str, str], float] = defaultdict(float)
    month_stats: defaultdict[str, dict[str, float]] = defaultdict(
        lambda: {"orders": 0.0, "revenue": 0.0, "profit": 0.0, "customers": 0.0,
                 "unpaid_orders": 0.0, "unpaid": 0.0}
    )
    for row in rows:
        amount = float(row["order_amount"])
        gain = float(row["gross_profit"])
        month = row["order_date"][:7]
        by_region[row["region"]] += amount
        by_product[row["product"]] += amount
        by_channel[row["channel"]] += amount
        by_month_channel[(month, row["channel"])] += amount
        by_month_region[(month, row["region"])] += amount
        by_month_product[(month, row["product"])] += amount
        stats = month_stats[month]
        stats["orders"] += 1
        stats["revenue"] += amount
        stats["profit"] += gain
        if row["payment_status"] != "已回款":
            stats["unpaid_orders"] += 1
            stats["unpaid"] += amount
    for month in month_stats:
        month_stats[month]["customers"] = len(
            {row["customer_id"] for row in rows if row["order_date"][:7] == month}
        )

    def wan(value: float) -> str:
        return f"{value / 10000:.1f}"

    channel_lines = "；".join(
        f"{name} {wan(value)}万元（{value / revenue * 100:.1f}%）"
        for name, value in sorted(by_channel.items(), key=lambda item: item[1], reverse=True)
    )
    region_lines = "；".join(
        f"{name} {wan(value)}万元（{value / revenue * 100:.1f}%）"
        for name, value in sorted(by_region.items(), key=lambda item: item[1], reverse=True)
    )
    product_lines = "；".join(
        f"{name} {wan(value)}万元（{value / revenue * 100:.1f}%）"
        for name, value in sorted(by_product.items(), key=lambda item: item[1], reverse=True)
    )

    detail_rows = [
        "月份|订单数|销售额万元|毛利万元|毛利率%|活跃客户|客单价元|待回款笔数|待回款万元"
    ]
    for month, stats in sorted(month_stats.items()):
        margin = stats["profit"] / stats["revenue"] * 100 if stats["revenue"] else 0
        avg = stats["revenue"] / stats["orders"] if stats["orders"] else 0
        detail_rows.append(
            f"{month}|{int(stats['orders'])}|{wan(stats['revenue'])}|{wan(stats['profit'])}|"
            f"{margin:.1f}|{int(stats['customers'])}|{avg:.0f}|"
            f"{int(stats['unpaid_orders'])}|{wan(stats['unpaid'])}"
        )

    def grouped_lines(pairs: dict[tuple[str, str], float]) -> list[str]:
        lines = []
        for month in sorted({key[0] for key in pairs}):
            parts = "、".join(
                f"{name} {wan(value)}万"
                for (item_month, name), value in sorted(
                    pairs.items(), key=lambda item: item[1], reverse=True
                )
                if item_month == month
            )
            lines.append(f"{month}：{parts}")
        return lines

    segments: defaultdict[str, float] = defaultdict(float)
    payments: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        segments[row["customer_segment"]] += float(row["order_amount"])
        payments[row["payment_status"]] += float(row["order_amount"])

    return (
        f"数据集 chatbi_sales.csv，共 {len(rows)} 条订单，{len(customers)} 家客户，"
        f"覆盖 {dates[0]} 至 {dates[-1]}。累计订单金额 {wan(revenue)} 万元，"
        f"累计毛利 {wan(profit)} 万元，整体毛利率 {profit / revenue * 100:.1f}%。\n"
        f"累计渠道结构：{channel_lines}。\n"
        f"累计区域结构：{region_lines}。\n"
        f"累计产品结构：{product_lines}。\n"
        f"客户分层：{'；'.join(f'{k} {wan(v)}万元' for k, v in segments.items())}。\n"
        f"回款状态：{'；'.join(f'{k} {wan(v)}万元' for k, v in payments.items())}。\n"
        f"月度明细：\n" + "\n".join(detail_rows) + "\n"
        "各月渠道销售额（万元）：\n" + "\n".join(grouped_lines(dict(by_month_channel))) + "\n"
        "各月区域销售额（万元）：\n" + "\n".join(grouped_lines(dict(by_month_region))) + "\n"
        "各月产品销售额（万元）：\n" + "\n".join(grouped_lines(dict(by_month_product)))
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
        max_output_tokens=settings.deepseek_max_output_tokens,
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
