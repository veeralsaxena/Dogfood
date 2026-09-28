import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.config import TEST_TOKENS

client = TestClient(app)

def test_organizer_create_judge_invite():
    headers = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}
    res = client.post("/api/organizer/invites", headers=headers, json={
        "role": "judge",
        "tracks": ["trk_01", "trk_02"]
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "inv_" in data["invite_token"]
    assert data["role"] == "judge"
    assert "/onboard/" in data["invite_url"]

def test_unauthorized_cannot_create_invite():
    headers = {"Authorization": f"Token {TEST_TOKENS['participant']}"}
    res = client.post("/api/organizer/invites", headers=headers, json={
        "role": "judge"
    })
    assert res.status_code in (401, 403)

def test_full_onboarding_and_authentication_flow():
    # 1. Organizer creates invite
    headers = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}
    res = client.post("/api/organizer/invites", headers=headers, json={
        "role": "judge",
        "tracks": ["trk_03"]
    })
    assert res.status_code == 200
    token = res.json()["invite_token"]

    # 2. View onboarding page
    page_res = client.get(f"/onboard/{token}")
    assert page_res.status_code == 200
    assert "Activate Your Account" in page_res.text

    # 3. User submits onboarding form
    email = f"invited_{token[:8]}@example.org"
    onboard_res = client.post("/api/auth/onboard", json={
        "token": token,
        "name": "Dr. Sarah Connor",
        "email": email,
        "password": "mypassword456"
    })
    assert onboard_res.status_code == 200
    user_data = onboard_res.json()
    assert user_data["status"] == "success"
    assert user_data["user"]["role"] == "judge"
    assert user_data["redirect_url"] == "/judge"

    # 4. Attempting to use the same token again must fail
    reuse_res = client.post("/api/auth/onboard", json={
        "token": token,
        "name": "Intruder",
        "email": "intruder@example.org",
        "password": "mypassword456"
    })
    assert reuse_res.status_code == 400

    # 5. User can log in with new credentials
    login_res = client.post("/api/auth/login", json={
        "email": email,
        "password": "mypassword456"
    })
    assert login_res.status_code == 200
    assert login_res.json()["user"]["email"] == email

def test_self_service_password_change():
    client.cookies.clear()
    headers = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}
    inv_res = client.post("/api/organizer/invites", headers=headers, json={"role": "participant"})
    token = inv_res.json()["invite_token"]
    email = f"part_{token[:8]}@example.org"

    onb_res = client.post("/api/auth/onboard", json={
        "token": token,
        "name": "Alex Vance",
        "email": email,
        "password": "initialpassword"
    })
    user_token = onb_res.json()["token"]
    auth_header = {"Authorization": f"Token {user_token}"}

    # Change password
    chg_res = client.post("/api/auth/change-password", headers=auth_header, json={
        "old_password": "initialpassword",
        "new_password": "newsecretpassword"
    })
    assert chg_res.status_code == 200
    assert chg_res.json()["status"] == "success"

    # Verify old password fails
    fail_res = client.post("/api/auth/login", json={
        "email": email,
        "password": "initialpassword"
    })
    assert fail_res.status_code == 401

    # Verify new password succeeds
    ok_res = client.post("/api/auth/login", json={
        "email": email,
        "password": "newsecretpassword"
    })
    assert ok_res.status_code == 200

def test_organizer_user_list_and_password_reset():
    headers = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}
    users_res = client.get("/api/organizer/users", headers=headers)
    assert users_res.status_code == 200
    users = users_res.json()["users"]
    assert len(users) > 0

    first_user = users[0]
    reset_res = client.post(f"/api/organizer/users/{first_user['id']}/reset-password", headers=headers, json={
        "new_password": "password123"
    })
    assert reset_res.status_code == 200
    assert reset_res.json()["status"] == "success"
