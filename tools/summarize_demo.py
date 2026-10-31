from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "demo" / "chatbi_sales.csv"
OUTPUT = ROOT / "data" / "demo" / "chatbi_sales_summary.json"
WEB_OUTPUT = ROOT / "apps" / "web" / "src" / "data" / "demoSummary.json"


def main() -> None:
    with SOURCE.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    totals = {
        "order_count": len(rows),
        "customer_count": len({row["customer_id"] for row in rows}),
        "unpaid_order_count": sum(row["payment_status"] == "待回款" for row in rows),
        "revenue": round(sum(float(row["order_amount"]) for row in rows), 2),
        "cost": round(sum(float(row["cost_amount"]) for row in rows), 2),
        "gross_profit": round(sum(float(row["gross_profit"]) for row in rows), 2),
        "paid_revenue": round(
            sum(float(row["order_amount"]) for row in rows if row["payment_status"] == "已回款"), 2
        ),
        "open_receivables": round(
            sum(float(row["order_amount"]) for row in rows if row["payment_status"] == "待回款"), 2
        ),
        "avg_order_value": round(sum(float(row["order_amount"]) for row in rows) / len(rows), 2),
    }
    totals["gross_margin_pct"] = round(totals["gross_profit"] / totals["revenue"] * 100, 2)
    region: defaultdict[str, float] = defaultdict(float)
    channel: defaultdict[str, float] = defaultdict(float)
    product: defaultdict[str, float] = defaultdict(float)
    month: defaultdict[str, float] = defaultdict(float)
    monthly_profit: defaultdict[str, float] = defaultdict(float)
    paid_by_region: defaultdict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for row in rows:
        amount = float(row["order_amount"])
        region[row["region"]] += amount
        channel[row["channel"]] += amount
        product[row["product"]] += amount
        month[row["order_date"][:7]] += amount
        monthly_profit[row["order_date"][:7]] += float(row["gross_profit"])
        paid_by_region[row["region"]][1] += amount
        if row["payment_status"] == "已回款":
            paid_by_region[row["region"]][0] += amount
    latest_month = max(month)
    previous_month_key = "2026-09"
    latest_mtd_rows = [row for row in rows if row["order_date"].startswith(latest_month)]
    mtd_day = max(int(row["order_date"][-2:]) for row in latest_mtd_rows)
    previous_mtd_rows = [
        row
        for row in rows
        if row["order_date"].startswith(previous_month_key)
        and int(row["order_date"][-2:]) <= mtd_day
    ]
    latest_revenue = sum(float(row["order_amount"]) for row in latest_mtd_rows)
    previous_revenue = sum(float(row["order_amount"]) for row in previous_mtd_rows)
    latest_paid_revenue = sum(
        float(row["order_amount"]) for row in latest_mtd_rows if row["payment_status"] == "已回款"
    )
    latest_gross_profit = sum(float(row["gross_profit"]) for row in latest_mtd_rows)
    latest_cost = sum(float(row["cost_amount"]) for row in latest_mtd_rows)
    previous_gross_profit = sum(float(row["gross_profit"]) for row in previous_mtd_rows)
    latest_regions: defaultdict[str, float] = defaultdict(float)
    for row in latest_mtd_rows:
        latest_regions[row["region"]] += float(row["order_amount"])
    latest_channels: defaultdict[str, float] = defaultdict(float)
    for row in latest_mtd_rows:
        latest_channels[row["channel"]] += float(row["order_amount"])
    latest_channel_total = sum(latest_channels.values())
    summary = {
        "period": {"start": "2026-01-01", "end": "2026-10-29", "latest_month": latest_month},
        "totals": totals,
        "latest_month": {
            "revenue": round(latest_revenue, 2),
            "previous_month_revenue": round(previous_revenue, 2),
            "growth_pct": round((latest_revenue / previous_revenue - 1) * 100, 2),
            "order_count": sum(row["order_date"].startswith(latest_month) for row in rows),
            "active_customers": len({row["customer_id"] for row in latest_mtd_rows}),
            "avg_order_value": round(
                latest_revenue / sum(row["order_date"].startswith(latest_month) for row in rows),
                2,
            ),
            "gross_profit": round(latest_gross_profit, 2),
            "cost": round(latest_cost, 2),
            "gross_margin_pct": round(latest_gross_profit / latest_revenue * 100, 2),
            "paid_revenue": round(latest_paid_revenue, 2),
            "collection_pct": round(latest_paid_revenue / latest_revenue * 100, 2),
            "gross_profit_change_pct": (
                round((latest_gross_profit / previous_gross_profit - 1) * 100, 2)
                if previous_gross_profit
                else None
            ),
            "regions": [
                {
                    "name": name,
                    "revenue": round(amount, 2),
                    "share_pct": round(amount / latest_revenue * 100, 2),
                }
                for name, amount in sorted(
                    latest_regions.items(), key=lambda item: item[1], reverse=True
                )
            ],
            "channels": [
                {
                    "name": name,
                    "revenue": round(amount, 2),
                    "share_pct": round(amount / latest_channel_total * 100, 2),
                }
                for name, amount in sorted(
                    latest_channels.items(), key=lambda item: item[1], reverse=True
                )
            ],
            "as_of_day": mtd_day,
        },
        "regions": [
            {
                "name": name,
                "revenue": round(value, 2),
                "share_pct": round(value / totals["revenue"] * 100, 2),
                "paid_pct": round(paid_by_region[name][0] / paid_by_region[name][1] * 100, 2),
            }
            for name, value in sorted(region.items(), key=lambda item: item[1], reverse=True)
        ],
        "channels": [
            {
                "name": name,
                "revenue": round(value, 2),
                "share_pct": round(value / totals["revenue"] * 100, 2),
            }
            for name, value in sorted(channel.items(), key=lambda item: item[1], reverse=True)
        ],
        "products": [
            {
                "name": name,
                "revenue": round(value, 2),
                "share_pct": round(value / totals["revenue"] * 100, 2),
            }
            for name, value in sorted(product.items(), key=lambda item: item[1], reverse=True)
        ],
        "months": [
            {
                "month": name,
                "revenue": round(value, 2),
                "gross_profit": round(monthly_profit[name], 2),
            }
            for name, value in sorted(month.items())
        ],
        "recent_transactions": [
            {
                "order_id": row["order_id"],
                "date": row["order_date"],
                "time": row["order_time"],
                "customer": row["customer_name"],
                "region": row["region"],
                "product": row["product"],
                "channel": row["channel"],
                "amount": round(float(row["order_amount"]), 2),
                "cost": round(float(row["cost_amount"]), 2),
                "payment_status": row["payment_status"],
            }
            for row in sorted(
                rows, key=lambda row: (row["order_date"], row["order_time"]), reverse=True
            )[:8]
        ],
    }
    OUTPUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    WEB_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    WEB_OUTPUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
