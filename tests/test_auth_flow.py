import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.config import TEST_TOKENS

client = TestClient(app)

def test_login_page_renders():
    res = client.get("/login")
    assert res.status_code == 200
    assert "Sign in to Veritas" in res.text

def test_successful_login_participant():
    res = client.post("/api/auth/login", json={
        "email": "participant@example.org",
        "password": "password123"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["redirect_url"] == "/participant/dashboard"
    assert data["user"]["role"] == "participant"

def test_successful_login_judge():
    res = client.post("/api/auth/login", json={
        "email": "ada@example.org",
        "password": "password123"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["redirect_url"] == "/judge"
    assert data["user"]["role"] == "judge"

def test_successful_login_organizer():
    res = client.post("/api/auth/login", json={
        "email": "organizer@dogfood.local",
        "password": "password123"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["redirect_url"] == "/war-room"
    assert data["user"]["role"] == "organizer"

def test_failed_login_invalid_password():
    res = client.post("/api/auth/login", json={
        "email": "organizer@dogfood.local",
        "password": "wrongpassword"
    })
    assert res.status_code == 401

def test_participant_dashboard_access():
    client.cookies.clear()
    # Unauthenticated should redirect to /login
    res = client.get("/participant/dashboard", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/login"

    # Authenticated participant should get 200 OK
    res = client.get("/participant/dashboard", headers={"Cookie": f"session={TEST_TOKENS['participant']}"})
    assert res.status_code == 200
    assert "Participant Workspace" in res.text or "Welcome" in res.text

def test_logout_clears_session():
    res = client.get("/logout", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/login"
    assert "session=" in res.headers.get("set-cookie", "")

def test_signup_page_renders():
    res = client.get("/signup")
    assert res.status_code == 200
    assert "Join Veritas" in res.text or "Registration" in res.text

def test_participant_signup_flow():
    import uuid
    rand_email = f"user_{uuid.uuid4().hex[:8]}@builder.test"
    res = client.post("/api/auth/signup", json={
        "name": "Jane Developer",
        "email": rand_email,
        "password": "secretpassword",
        "join_code": "RAPTOR-2026"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["user"]["role"] == "participant"
    assert data["user"]["email"] == rand_email
    assert "session=" in res.headers.get("set-cookie", "")

    # Duplicate should fail
    dup = client.post("/api/auth/signup", json={
        "name": "Jane Developer",
        "email": rand_email,
        "password": "secretpassword"
    })
    assert dup.status_code == 400
