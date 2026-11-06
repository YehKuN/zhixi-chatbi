from __future__ import annotations

from fastapi.testclient import TestClient

ADMIN_PASSWORD = "AdminPass123"


def _register_enterprise(
    client: TestClient,
    *,
    company_name: str,
    username: str,
) -> tuple[str, dict[str, str]]:
    response = client.post(
        "/auth/enterprises/register",
        json={
            "company_name": company_name,
            "industry": "企业服务",
            "company_size": "51-200 人",
            "contact_name": "测试联系人",
            "contact_phone": "13800000000",
            "contact_email": None,
            "username": username,
            "display_name": "测试管理员",
            "password": ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    return data["enterprise"]["code"], {
        "Authorization": f"Bearer {data['token']}"
    }


def _upload_csv(client: TestClient, headers: dict[str, str], name: str) -> str:
    response = client.post(
        "/datasources/upload",
        headers=headers,
        data={"type": "csv", "name": name},
        files={"file": (f"{name}.csv", b"order_id,amount\n1,10.20\n2,20.30\n", "text/csv")},
    )
    assert response.status_code == 202, response.text
    return str(response.json()["data"]["id"])


def _create_session(client: TestClient, headers: dict[str, str], title: str) -> str:
    response = client.post("/sessions", headers=headers, json={"title": title})
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


def test_sessions_are_isolated_by_enterprise(client: TestClient) -> None:
    _, enterprise_a = _register_enterprise(
        client, company_name="甲方数据科技有限公司", username="scope_admin_a"
    )
    _, enterprise_b = _register_enterprise(
        client, company_name="乙方数据科技有限公司", username="scope_admin_b"
    )

    session_a = _create_session(client, enterprise_a, "甲方的分析会话")

    listed_a = client.get("/sessions", headers=enterprise_a)
    assert listed_a.status_code == 200
    assert [item["id"] for item in listed_a.json()["data"]["items"]] == [session_a]

    listed_b = client.get("/sessions", headers=enterprise_b)
    assert listed_b.status_code == 200
    assert listed_b.json()["data"]["items"] == []

    assert client.get(f"/sessions/{session_a}", headers=enterprise_b).status_code == 404
    assert client.delete(f"/sessions/{session_a}", headers=enterprise_b).status_code == 404
    assert client.post(
        f"/sessions/{session_a}/runs",
        headers=enterprise_b,
        json={"question": "乙方尝试分析甲方会话", "idempotency_key": "scope-cross-run"},
    ).status_code == 404


def test_datasources_are_isolated_and_cross_binding_is_rejected(
    client: TestClient,
) -> None:
    _, enterprise_a = _register_enterprise(
        client, company_name="甲方数据科技有限公司", username="scope_admin_a"
    )
    _, enterprise_b = _register_enterprise(
        client, company_name="乙方数据科技有限公司", username="scope_admin_b"
    )

    datasource_a = _upload_csv(client, enterprise_a, "甲方订单数据")

    listed_a = client.get("/datasources", headers=enterprise_a)
    assert listed_a.status_code == 200
    assert [item["id"] for item in listed_a.json()["data"]["items"]] == [datasource_a]

    listed_b = client.get("/datasources", headers=enterprise_b)
    assert listed_b.status_code == 200
    assert listed_b.json()["data"]["items"] == []

    assert client.get(f"/datasources/{datasource_a}", headers=enterprise_b).status_code == 404
    assert client.patch(
        f"/datasources/{datasource_a}/description",
        headers=enterprise_b,
        json={"description": "越权修改"},
    ).status_code == 404

    cross_binding = client.post(
        "/sessions",
        headers=enterprise_b,
        json={"title": "越权绑定", "selected_datasource_id": datasource_a},
    )
    assert cross_binding.status_code == 404
    assert cross_binding.json()["error"]["code"] == "DATASOURCE_NOT_FOUND"


def test_model_profiles_are_isolated_by_enterprise(client: TestClient) -> None:
    _, enterprise_a = _register_enterprise(
        client, company_name="甲方数据科技有限公司", username="scope_admin_a"
    )
    _, enterprise_b = _register_enterprise(
        client, company_name="乙方数据科技有限公司", username="scope_admin_b"
    )

    created = client.post(
        "/model-profiles",
        headers=enterprise_a,
        json={
            "name": "甲方专属模型",
            "provider": "openai-compatible",
            "model_name": "demo-model",
            "base_url": "https://model.example/v1",
            "api_key": "test-api-key",
        },
    )
    assert created.status_code == 201, created.text
    profile_id = created.json()["data"]["id"]

    listed_a = client.get("/model-profiles", headers=enterprise_a)
    assert [item["id"] for item in listed_a.json()["data"]["items"]] == [profile_id]

    listed_b = client.get("/model-profiles", headers=enterprise_b)
    assert listed_b.json()["data"]["items"] == []
    assert client.get(f"/model-profiles/{profile_id}", headers=enterprise_b).status_code == 404
    assert client.post(
        f"/model-profiles/{profile_id}/activate", headers=enterprise_b
    ).status_code == 404
