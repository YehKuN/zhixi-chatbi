from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from contracts.ids import make_id
from fastapi.testclient import TestClient
from metadata.database import create_session_factory, create_sqlite_engine
from metadata.models import EnterpriseModel, RunModel, SessionModel
from server.config import Settings
from sqlalchemy import select

ADMIN = {"username": "admin", "password": "AdminConsolePass123"}


def _admin_login(client: TestClient) -> dict[str, str]:
    response = client.post("/admin/login", json=ADMIN)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['token']}"}


def _register_enterprise(
    client: TestClient, company_name: str, username: str
) -> dict[str, object]:
    response = client.post(
        "/auth/enterprises/register",
        json={
            "company_name": company_name,
            "contact_name": "管理员",
            "contact_phone": "13800000000",
            "username": username,
            "display_name": "管理员",
            "password": "AdminPass123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_admin_login_and_overview_counts(client: TestClient) -> None:
    first = _register_enterprise(client, "平台总览甲企业", "overview_admin_a")
    _register_enterprise(client, "平台总览乙企业", "overview_admin_b")
    client.post(
        "/auth/employees/register",
        json={
            "enterprise_code": first["enterprise"]["code"],
            "username": "overview_staff",
            "display_name": "职工",
            "password": "EmployeePass123",
        },
    )

    headers = _admin_login(client)
    overview = client.get("/admin/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    data = overview.json()["data"]
    assert data["enterprise_count"] == 2
    assert data["user_count"] == 3
    assert data["active_user_count"] == 3

    enterprises = client.get("/admin/enterprises", headers=headers)
    assert enterprises.status_code == 200
    rows = enterprises.json()["data"]["items"]
    assert {row["name"] for row in rows} == {"平台总览甲企业", "平台总览乙企业"}
    first_row = next(row for row in rows if row["name"] == "平台总览甲企业")
    assert first_row["user_count"] == 2
    assert first_row["admin_count"] == 1


def test_admin_login_rejects_wrong_password_and_unconfigured_password(
    client: TestClient, migrated_settings: Settings
) -> None:
    wrong = client.post("/admin/login", json={"username": "admin", "password": "wrong"})
    assert wrong.status_code == 401

    from server.app import create_app

    unconfigured = migrated_settings.model_copy(update={"admin_password": None})
    with TestClient(create_app(unconfigured)) as other_client:
        response = other_client.post("/admin/login", json=ADMIN)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CONFIGURATION_ERROR"


def test_admin_endpoints_reject_enterprise_token(client: TestClient) -> None:
    session = _register_enterprise(client, "越权校验企业", "scope_admin_check")
    headers = {"Authorization": f"Bearer {session['token']}"}

    assert client.get("/admin/overview", headers=headers).status_code == 401
    assert client.get("/admin/users", headers=headers).status_code == 401
    assert client.get("/admin/overview").status_code == 401


def test_account_management_disable_and_password_reset(client: TestClient) -> None:
    enterprise = _register_enterprise(client, "账号管理企业", "account_admin")
    client.post(
        "/auth/employees/register",
        json={
            "enterprise_code": enterprise["enterprise"]["code"],
            "username": "managed_staff",
            "display_name": "被管理职工",
            "password": "EmployeePass123",
        },
    )

    headers = _admin_login(client)
    users = client.get("/admin/users", headers=headers, params={"q": "managed_staff"})
    assert users.status_code == 200
    row = users.json()["data"]["items"][0]
    assert row["enterprise_name"] == "账号管理企业"

    disabled = client.patch(
        f"/admin/users/{row['id']}/status",
        headers=headers,
        json={"status": "disabled"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["data"]["status"] == "disabled"

    blocked = client.post(
        "/auth/login",
        json={"username": "managed_staff", "password": "EmployeePass123"},
    )
    assert blocked.status_code == 401

    reset = client.post(
        f"/admin/users/{row['id']}/reset-password",
        headers=headers,
        json={"password": "NewEmployeePass123"},
    )
    assert reset.status_code == 200

    enabled = client.patch(
        f"/admin/users/{row['id']}/status",
        headers=headers,
        json={"status": "active"},
    )
    assert enabled.status_code == 200

    old_password = client.post(
        "/auth/login",
        json={"username": "managed_staff", "password": "EmployeePass123"},
    )
    assert old_password.status_code == 401
    new_password = client.post(
        "/auth/login",
        json={"username": "managed_staff", "password": "NewEmployeePass123"},
    )
    assert new_password.status_code == 200


def test_cannot_disable_last_enterprise_admin(client: TestClient) -> None:
    enterprise = _register_enterprise(client, "唯一管理员企业", "lonely_admin")
    headers = _admin_login(client)

    users = client.get("/admin/users", headers=headers, params={"q": "lonely_admin"})
    admin_row = users.json()["data"]["items"][0]

    response = client.patch(
        f"/admin/users/{admin_row['id']}/status",
        headers=headers,
        json={"status": "disabled"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ADMIN_ACTION_REJECTED"
    assert enterprise["user"]["id"] == admin_row["id"]


def test_overview_aggregates_persisted_token_usage(
    client: TestClient, migrated_settings: Settings
) -> None:
    enterprise = _register_enterprise(client, "Token 统计企业", "token_admin")

    async def seed() -> None:
        engine = create_sqlite_engine(migrated_settings.metadata_database_url)
        factory = create_session_factory(engine)
        try:
            async with factory() as db:
                enterprise_model = await db.scalar(
                    select(EnterpriseModel).where(
                        EnterpriseModel.code == enterprise["enterprise"]["code"]
                    )
                )
                assert enterprise_model is not None
                session = SessionModel(
                    id=make_id("session"),
                    title="Token 统计会话",
                    enterprise_id=enterprise_model.id,
                )
                db.add(session)
                await db.flush()
                db.add(
                    RunModel(
                        id=make_id("run"),
                        session_id=session.id,
                        question="统计 token",
                        status="succeeded",
                        usage_input_tokens=900,
                        usage_output_tokens=100,
                        usage_total_tokens=1000,
                        usage_model_calls=3,
                        finished_at=datetime.now(UTC),
                    )
                )
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(seed())

    headers = _admin_login(client)
    overview = client.get("/admin/overview", headers=headers).json()["data"]
    assert overview["usage_total_tokens"] == 1000
    assert overview["usage_input_tokens"] == 900
    assert overview["usage_model_calls"] == 3
    assert overview["tracked_usage_runs"] == 1

    rows = client.get("/admin/enterprises", headers=headers).json()["data"]["items"]
    row = next(item for item in rows if item["name"] == "Token 统计企业")
    assert row["usage_total_tokens"] == 1000
    assert row["run_count"] == 1
