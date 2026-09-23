from sqlalchemy import select

from app.database import SessionLocal
from app.models import User


def test_registration_password_hash_and_login_returns_usable_jwt(client) -> None:
    registered = client.post(
        "/api/auth/register",
        json={
            "full_name": "Test Applicant",
            "email": "new.applicant@example.com",
            "password": "SecurePassphrase2026!",
            "company_name": "Test Manufacturing Ltd",
        },
    )
    assert registered.status_code == 201
    assert registered.json()["role"] == "APPLICANT"
    assert "password" not in registered.json()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "new.applicant@example.com"))
        assert user is not None
        assert user.password_hash != "SecurePassphrase2026!"

    login = client.post(
        "/api/auth/login",
        json={"email": "new.applicant@example.com", "password": "SecurePassphrase2026!"},
    )
    assert login.status_code == 200
    token_data = login.json()
    assert token_data["token_type"] == "bearer"
    assert token_data["user"]["role"] == "APPLICANT"

    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "new.applicant@example.com"
    assert client.get("/api/applicant/dashboard", headers=headers).status_code == 200


def test_role_guard_rejects_other_roles_and_anonymous_requests(client) -> None:
    assert client.get("/api/applicant/dashboard").status_code == 401

    officer_login = client.post(
        "/api/auth/login",
        json={"email": "officer@example.com", "password": "TestPassphrase2026!"},
    )
    assert officer_login.status_code == 200
    headers = {"Authorization": f"Bearer {officer_login.json()['access_token']}"}
    assert client.get("/api/officer/department", headers=headers).status_code == 200
    assert client.get("/api/applicant/dashboard", headers=headers).status_code == 403
    assert client.get("/api/admin/overview", headers=headers).status_code == 403
    assert client.get("/api/applications", headers=headers).status_code == 403

    admin_login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "TestPassphrase2026!"},
    )
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    assert client.get("/api/admin/overview", headers=admin_headers).status_code == 200
    assert client.get("/api/officer/department", headers=admin_headers).status_code == 403


def test_registration_cannot_select_a_privileged_role_and_duplicate_email_fails(client) -> None:
    payload = {
        "full_name": "Public Applicant",
        "email": "public@example.com",
        "password": "SecurePassphrase2026!",
        "role": "ADMIN",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 422
    payload.pop("role")
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    assert response.json()["role"] == "APPLICANT"
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_invalid_password_and_invalid_token_are_rejected(client) -> None:
    bad_login = client.post(
        "/api/auth/login",
        json={"email": "officer@example.com", "password": "wrong-password-value"},
    )
    assert bad_login.status_code == 401
    bad_token = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad_token.status_code == 401
