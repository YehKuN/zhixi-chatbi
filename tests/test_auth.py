from __future__ import annotations

import re

from fastapi.testclient import TestClient

ENTERPRISE_CODE_PATTERN = re.compile(r"^ZX-[A-Z0-9]{6}$")


def _admin_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "company_name": "智析测试科技有限公司",
        "industry": "企业服务",
        "company_size": "51-200 人",
        "contact_name": "叶锦豪",
        "contact_phone": "13800000000",
        "contact_email": "admin@zhixi.test",
        "username": "zhixi_admin",
        "display_name": "叶锦豪",
        "password": "AdminPass123",
    }
    payload.update(overrides)
    return payload


def _register_admin(client: TestClient, **overrides: object):
    return client.post("/auth/enterprises/register", json=_admin_payload(**overrides))


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_enterprise_creates_admin_and_returns_enterprise_code(
    client: TestClient,
) -> None:
    response = _register_admin(client)

    assert response.status_code == 201
    data = response.json()["data"]
    assert ENTERPRISE_CODE_PATTERN.fullmatch(data["enterprise"]["code"])
    assert data["enterprise"]["name"] == "智析测试科技有限公司"
    assert data["user"]["role"] == "enterprise_admin"
    assert data["user"]["username"] == "zhixi_admin"
    assert data["token_type"] == "bearer"
    assert data["token"]

    me = client.get("/auth/me", headers=_bearer(data["token"]))
    assert me.status_code == 200
    assert me.json()["data"]["enterprise"]["code"] == data["enterprise"]["code"]


def test_duplicate_company_name_is_rejected(client: TestClient) -> None:
    assert _register_admin(client).status_code == 201

    response = _register_admin(client, username="another_admin")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ENTERPRISE_ALREADY_REGISTERED"


def test_duplicate_username_is_rejected(client: TestClient) -> None:
    assert _register_admin(client).status_code == 201

    response = _register_admin(
        client,
        company_name="另一家测试有限公司",
        username="zhixi_admin",
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "USERNAME_TAKEN"


def test_employee_joins_with_enterprise_code(client: TestClient) -> None:
    admin = _register_admin(client)
    assert admin.status_code == 201
    admin_data = admin.json()["data"]

    response = client.post(
        "/auth/employees/register",
        json={
            "enterprise_code": admin_data["enterprise"]["code"].lower(),
            "username": "employee_01",
            "display_name": "洪富凯",
            "password": "EmployeePass123",
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["user"]["role"] == "employee"
    assert data["user"]["username"] == "employee_01"
    assert data["enterprise"]["code"] == admin_data["enterprise"]["code"]

    me = client.get("/auth/me", headers=_bearer(data["token"]))
    assert me.status_code == 200
    assert me.json()["data"]["user"]["display_name"] == "洪富凯"


def test_unknown_enterprise_code_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/auth/employees/register",
        json={
            "enterprise_code": "ZX-AAAAAA",
            "username": "employee_02",
            "display_name": "测试职工",
            "password": "EmployeePass123",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INVALID_ENTERPRISE_CODE"


def test_malformed_enterprise_code_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/auth/employees/register",
        json={
            "enterprise_code": "not-a-code",
            "username": "employee_03",
            "display_name": "测试职工",
            "password": "EmployeePass123",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INVALID_ENTERPRISE_CODE"


def test_weak_password_and_invalid_username_are_validation_errors(
    client: TestClient,
) -> None:
    weak = client.post("/auth/enterprises/register", json=_admin_payload(password="short"))
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "VALIDATION_ERROR"

    bad_username = client.post(
        "/auth/enterprises/register", json=_admin_payload(username="中文账号")
    )
    assert bad_username.status_code == 422
    assert bad_username.json()["error"]["code"] == "VALIDATION_ERROR"


def test_login_is_case_insensitive_and_rejects_wrong_password(
    client: TestClient,
) -> None:
    registered = _register_admin(client)
    assert registered.status_code == 201

    success = client.post(
        "/auth/login",
        json={"username": "ZHIXI_ADMIN", "password": "AdminPass123"},
    )
    assert success.status_code == 200
    assert success.json()["data"]["user"]["username"] == "zhixi_admin"

    wrong = client.post(
        "/auth/login",
        json={"username": "zhixi_admin", "password": "WrongPass123"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_requires_valid_bearer_token(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401
    response = client.get("/auth/me", headers=_bearer("not-a-real-token"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_logout_revokes_token_and_is_idempotent(client: TestClient) -> None:
    registered = _register_admin(client)
    token = registered.json()["data"]["token"]

    assert client.post("/auth/logout", headers=_bearer(token)).json()["data"]["logged_out"] is True
    assert client.get("/auth/me", headers=_bearer(token)).status_code == 401

    again = client.post("/auth/logout", headers=_bearer(token))
    assert again.status_code == 200
    assert again.json()["data"]["logged_out"] is True
