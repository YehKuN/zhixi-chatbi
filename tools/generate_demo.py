from __future__ import annotations

import csv
import datetime as dt
import random
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "demo"
    root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20261029)
    regions = ["华东", "华北", "华南", "西南", "华中"]
    products = [
        ("企业智能分析", 1.35),
        ("数据治理服务", 0.92),
        ("销售预测模块", 0.74),
        ("基础版订阅", 0.46),
    ]
    channels = ["直销", "渠道", "客户续费", "线上推广"]
    segments = ["企业客户", "成长客户", "标准客户"]
    cities = {
        "华东": ["上海", "杭州", "苏州", "南京", "宁波", "合肥"],
        "华北": ["北京", "天津", "青岛", "石家庄", "济南"],
        "华南": ["深圳", "广州", "厦门", "福州", "南宁"],
        "西南": ["成都", "重庆", "昆明", "贵阳"],
        "华中": ["武汉", "郑州", "长沙", "南昌"],
    }
    reps = ["林安", "周宁", "沈言", "顾晨", "白露", "许衡"]
    customer_book = []
    customer_id = 1
    for region in regions:
        for _ in range(36):
            customer_book.append({
                "id": f"CUST-{customer_id:04d}",
                "name": f"{region}示例企业{customer_id:03d}",
                "region": region,
                "city": cities[region][rng.randrange(len(cities[region]))],
                "segment": rng.choices(segments, weights=[0.22, 0.38, 0.40], k=1)[0],
                "rep": reps[rng.randrange(len(reps))],
            })
            customer_id += 1
    rows: list[list[object]] = []
    day = dt.date(2026, 1, 1)
    end = dt.date(2026, 10, 29)
    order_id = 1
    while day <= end:
        month_factor = 1.0 + ((day.month - 1) * 0.018)
        for _ in range(3):
            region = regions[rng.randrange(len(regions))]
            customer = customer_book[rng.randrange(len(customer_book))]
            while customer["region"] != region:
                customer = customer_book[rng.randrange(len(customer_book))]
            product, base = products[rng.randrange(len(products))]
            channel = channels[rng.randrange(len(channels))]
            segment_factor = {
                "企业客户": 1.28,
                "成长客户": 1.0,
                "标准客户": 0.76,
            }[customer["segment"]]
            amount = round(
                base * 10000 * month_factor * segment_factor * rng.uniform(0.72, 1.34),
                2,
            )
            cost = round(amount * rng.uniform(0.48, 0.72), 2)
            status = "已回款" if rng.random() > 0.08 else "待回款"
            rows.append([
                f"ORD-{day:%Y%m%d}-{order_id:04d}",
                day.isoformat(),
                region,
                customer["city"],
                customer["id"],
                customer["name"],
                product,
                customer["segment"],
                channel,
                f"{rng.randrange(9, 19):02d}:{rng.randrange(0, 60):02d}",
                amount,
                cost,
                round(amount - cost, 2),
                status,
                customer["rep"],
            ])
            order_id += 1
        day += dt.timedelta(days=1)
    path = root / "chatbi_sales.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "order_id", "order_date", "region", "city", "customer_id", "customer_name",
            "product", "customer_segment", "channel", "order_time", "order_amount",
            "cost_amount", "gross_profit", "payment_status", "sales_rep",
        ])
        writer.writerows(rows)
    print(f"rows={len(rows)} path={path}")


if __name__ == "__main__":
    main()
