from __future__ import annotations

from tests.test_datasources_and_gateway import unwrap, upload_csv

_MONTHLY_ORDERS = (
    b"order_date,region,revenue,order_id\n"
    b"2026-09-03,East,100,o1\n"
    b"2026-09-10,South,50,o2\n"
    b"2026-10-02,East,160,o3\n"
    b"2026-10-08,South,20,o4\n"
)


def _ready_datasource(client, content: bytes, *, name: str = "Diagnosis fixture") -> str:
    uploaded = upload_csv(client, content, name=name)
    datasource_id = str(uploaded["id"])
    unwrap(client.patch(f"/datasources/{datasource_id}/mask-fields", json={"mask_fields": []}))
    return datasource_id


def _run(client, datasource_id: str, **overrides):
    payload = {
        "metric": "revenue",
        "time_column": "order_date",
        "dimension": "region",
        "top_n": 6,
    }
    payload.update(overrides)
    return client.post(f"/datasources/{datasource_id}/diagnosis/runs", json=payload)


def test_diagnosis_capabilities_detects_measure_time_and_dimension(client) -> None:
    datasource_id = _ready_datasource(client, _MONTHLY_ORDERS)

    capabilities = unwrap(
        client.get(f"/datasources/{datasource_id}/diagnosis/capabilities")
    )

    assert capabilities["ready"] is True
    assert capabilities["default_measure"] == "revenue"
    assert capabilities["default_time_column"] == "order_date"
    assert capabilities["default_dimension"] == "region"
    assert [item["name"] for item in capabilities["measures"]] == ["revenue"]
    assert [item["name"] for item in capabilities["dimensions"]] == ["region"]
    assert [item["name"] for item in capabilities["time_columns"]] == ["order_date"]
    assert capabilities["masked_fields"] == []


def test_diagnosis_decomposes_contributions_and_verifies_invariants(client) -> None:
    datasource_id = _ready_datasource(client, _MONTHLY_ORDERS)

    result = unwrap(_run(client, datasource_id))

    assert result["period"]["current_total"] == 180.0
    assert result["period"]["baseline_total"] == 150.0
    assert result["period"]["delta"] == 30.0
    assert [item["group"] for item in result["contributions"]] == ["East", "South"]
    assert result["contributions"][0]["delta"] == 60.0
    assert result["contributions"][0]["share_pct"] == 200.0
    assert result["contributions"][1]["delta"] == -30.0
    assert result["chart"]["type"] == "waterfall"
    assert result["chart"]["deltas"] == [60.0, -30.0]
    assert result["verification"]["status"] == "valid"
    assert result["verification"]["passed"] == result["verification"]["total"]
    assert result["hypotheses"][0]["status"] == "leading"
    assert result["evidence"][0]["method"] == "additive_decomposition"
    assert result["recipe"]["comparison"] == "previous_period"
    assert result["recipe_hash"]
    assert result["recipe_id"].startswith("diag_recipe_")
    assert "## 结论" in result["narrative"]
    assert "不构成因果证明" in result["narrative"]


def test_diagnosis_requires_two_comparable_periods(client) -> None:
    datasource_id = _ready_datasource(
        client,
        b"order_date,region,revenue\n2026-10-02,East,160\n2026-10-08,South,20\n",
        name="Single period fixture",
    )

    response = _run(client, datasource_id)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"]["period_count"] == 1


def test_diagnosis_aggregates_daily_rows_into_months(client) -> None:
    lines = ["order_date,region,revenue"]
    for month, amount in (("09", 10), ("10", 20)):
        for region in ("East", "South", "North", "West"):
            for day in range(1, 16):
                lines.append(f"2026-{month}-{day:02d},{region},{amount}")
    datasource_id = _ready_datasource(
        client,
        ("\n".join(lines) + "\n").encode(),
        name="Daily rows fixture",
    )

    result = unwrap(_run(client, datasource_id))

    assert result["period"]["current_total"] == 1200.0
    assert result["period"]["baseline_total"] == 600.0
    assert result["quality"]["sampled_rows"] == 120
    assert sum(item["delta"] for item in result["contributions"]) == 600.0
    assert result["verification"]["status"] == "valid"


def test_diagnosis_verification_tolerates_repeating_shares(client) -> None:
    datasource_id = _ready_datasource(
        client,
        (
            b"order_date,region,revenue\n"
            b"2026-09-05,A,10\n2026-09-06,B,10\n2026-09-07,C,10\n"
            b"2026-10-05,A,11\n2026-10-06,B,11\n2026-10-07,C,11\n"
        ),
        name="Repeating shares fixture",
    )

    result = unwrap(_run(client, datasource_id))

    assert result["period"]["delta"] == 3.0
    assert result["verification"]["status"] == "valid"
    assert all(item["passed"] for item in result["verification"]["checks"])
    assert abs(sum(item["share_pct"] for item in result["contributions"]) - 100) < 1e-3


def test_diagnosis_orders_month_names_by_month_num(client) -> None:
    datasource_id = _ready_datasource(
        client,
        (
            b"month,month_num,job,balance\n"
            b"Aug,8,admin.,100\nAug,8,blue-collar,100\n"
            b"Sep,9,admin.,120\nSep,9,blue-collar,80\n"
            b"Oct,10,admin.,150\nOct,10,blue-collar,60\n"
        ),
        name="Month names fixture",
    )

    result = unwrap(
        _run(
            client,
            datasource_id,
            metric="balance",
            time_column="month",
            dimension="job",
        )
    )

    assert result["period"]["current_label"] == "10月"
    assert result["period"]["baseline_label"] == "9月"
    assert result["period"]["current_total"] == 210.0
    assert result["period"]["baseline_total"] == 200.0


def test_diagnosis_intent_parses_chinese_question(client) -> None:
    datasource_id = _ready_datasource(client, _MONTHLY_ORDERS)

    intent = unwrap(
        client.post(
            f"/datasources/{datasource_id}/diagnosis/intent",
            json={"question": "本月营收为什么下降？按区域看看"},
        )
    )

    assert intent["understood"] is True
    assert intent["source"] == "rules"
    assert intent["metric"] == "revenue"
    assert intent["dimension"] == "region"
    assert intent["time_column"] == "order_date"
    assert "营收" in intent["explanation"]
    assert "区域" in intent["explanation"]
    assert intent["confidence"] >= 0.9


def test_diagnosis_intent_uses_defaults_for_vague_question(client) -> None:
    datasource_id = _ready_datasource(client, _MONTHLY_ORDERS)

    intent = unwrap(
        client.post(
            f"/datasources/{datasource_id}/diagnosis/intent",
            json={"question": "为什么下降了"},
        )
    )

    assert intent["understood"] is True
    assert intent["metric"] == "revenue"
    assert intent["dimension"] == "region"
    assert "默认项" in intent["explanation"]
    assert intent["confidence"] < 0.9


def test_diagnosis_intent_rejects_unrelated_question(client) -> None:
    datasource_id = _ready_datasource(client, _MONTHLY_ORDERS)

    intent = unwrap(
        client.post(
            f"/datasources/{datasource_id}/diagnosis/intent",
            json={"question": "今天天气怎么样"},
        )
    )

    assert intent["understood"] is False
    assert intent["clarification"]


def test_diagnosis_intent_rejects_unready_datasource(client) -> None:
    uploaded = upload_csv(client, _MONTHLY_ORDERS, name="Unready intent fixture")
    datasource_id = str(uploaded["id"])

    response = client.post(
        f"/datasources/{datasource_id}/diagnosis/intent",
        json={"question": "营收为什么下降"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DATASOURCE_NOT_READY"


def test_diagnosis_rejects_masked_metric(client) -> None:
    uploaded = upload_csv(client, _MONTHLY_ORDERS, name="Masked metric fixture")
    datasource_id = str(uploaded["id"])
    unwrap(
        client.patch(
            f"/datasources/{datasource_id}/mask-fields",
            json={"mask_fields": ["revenue"]},
        )
    )

    capabilities = unwrap(
        client.get(f"/datasources/{datasource_id}/diagnosis/capabilities")
    )
    response = _run(client, datasource_id)

    assert capabilities["ready"] is False
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_diagnosis_rejects_high_cardinality_dimension(client) -> None:
    rows = "\n".join(
        f"2026-09-01,item-{index},{index + 1}\n2026-10-01,item-{index},{index + 2}"
        for index in range(70)
    )
    datasource_id = _ready_datasource(
        client,
        ("order_date,customer,revenue\n" + rows + "\n").encode(),
        name="High cardinality fixture",
    )

    response = _run(client, datasource_id, dimension="customer")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"]["limit"] == 60
