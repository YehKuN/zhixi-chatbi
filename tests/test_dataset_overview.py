from __future__ import annotations

from tests.test_datasources_and_gateway import unwrap, upload_csv


def _ready_datasource(client, content: bytes, *, name: str = "Overview fixture") -> str:
    uploaded = upload_csv(client, content, name=name)
    datasource_id = str(uploaded["id"])
    unwrap(client.patch(f"/datasources/{datasource_id}/mask-fields", json={"mask_fields": []}))
    return datasource_id


def test_overview_aggregates_real_rows(client) -> None:
    datasource_id = _ready_datasource(
        client,
        (
            b"month,month_num,segment,converted_flag,amount\n"
            b"Jan,1,A,0,10\n"
            b"Jan,1,B,1,20\n"
            b"Feb,2,A,1,30\n"
            b"Feb,2,A,0,40\n"
            b"Mar,3,B,1,50\n"
        ),
    )
    overview = unwrap(client.get(f"/datasources/{datasource_id}/overview"))

    assert overview["datasource_id"] == datasource_id
    assert overview["row_count"] == 5
    assert overview["conversion_pct"] == 60.0
    assert overview["target_column"] == "converted_flag"
    assert overview["target_label"] == "转化率"
    assert [metric["key"] for metric in overview["metrics"]][0] == "rows"
    assert [metric["value"] for metric in overview["metrics"]][:2] == ["5", "60.0%"]
    assert overview["trend"]["labels"] == ["1月", "2月", "3月"]
    assert overview["trend"]["series"][0]["values"] == [2.0, 2.0, 1.0]
    assert overview["distribution"]["column"] == "segment"
    assert overview["distribution"]["items"][0]["name"] == "A"
    assert overview["ranking"]["items"][0]["name"] == "B"
    assert overview["quality"]["non_null_pct"] == 100.0
    assert overview["prompts"]
    assert "5 条记录" in overview["briefing"]


def test_overview_merges_categories_beyond_the_visible_four(client) -> None:
    rows = "\n".join(
        f"Jan,1,{segment},1" for segment in ("A", "B", "C", "D", "E", "F")
    )
    datasource_id = _ready_datasource(
        client,
        ("month,month_num,segment,converted_flag\n" + rows + "\n").encode(),
        name="Category fixture",
    )
    overview = unwrap(client.get(f"/datasources/{datasource_id}/overview"))

    items = overview["distribution"]["items"]
    assert len(items) == 5
    assert items[-1]["name"] == "其他"
    assert sum(item["count"] for item in items) == overview["row_count"]
    assert 99.9 <= round(sum(item["share_pct"] for item in items), 1) <= 100.1


def test_overview_is_cached_until_refresh(client) -> None:
    datasource_id = _ready_datasource(
        client,
        b"month,month_num,segment,converted_flag\nJan,1,A,0\nFeb,2,B,1\n",
        name="Cached fixture",
    )
    first = unwrap(client.get(f"/datasources/{datasource_id}/overview"))
    again = unwrap(client.get(f"/datasources/{datasource_id}/overview"))
    refreshed = unwrap(client.get(f"/datasources/{datasource_id}/overview?refresh=true"))

    assert first["row_count"] == 2
    assert again["row_count"] == 2
    assert refreshed["row_count"] == 2
    assert first["updated_at"] == again["updated_at"]
    assert refreshed["updated_at"] == first["updated_at"]


def test_overview_rejects_unconfirmed_datasource(client) -> None:
    uploaded = upload_csv(client, b"month,segment,converted_flag\nJan,A,1\n")
    datasource_id = str(uploaded["id"])

    response = client.get(f"/datasources/{datasource_id}/overview")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DATASOURCE_NOT_READY"
