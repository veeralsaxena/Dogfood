import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.config import TEST_TOKENS
from src.seed import seed_database

@pytest.fixture(autouse=True)
def setup_db():
    seed_database()

client = TestClient(app)

def test_team_join_by_invite():
    resp = client.post("/api/teams/join/inv_tm_01", json={"email": "newbie@example.org"})
    assert resp.status_code == 200
    data = resp.json()
    assert "newbie@example.org" in data["members"]

def test_event_settings_update():
    headers = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}
    payload = {
        "name": "Updated Hack 2026",
        "weights": {"functionality": 0.5, "quality": 0.5}
    }
    resp = client.post("/api/event/settings", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"

def test_svg_certificate_generation():
    resp = client.get("/certificates/prj_01")
    assert resp.status_code == 200
    assert "image/svg+xml" in resp.headers["content-type"]
    assert "HACKATHON RAPTORS" in resp.text
    assert "Certificate of Excellence" in resp.text

def test_embed_gallery():
    resp = client.get("/embed/gallery")
    assert resp.status_code == 200
    assert "VERITAS" in resp.text
    assert "Projects" in resp.text

def test_bulk_import():
    headers = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}
    payload = {
        "projects": [
            {"id": "prj_import_01", "title": "Imported Project Alpha", "summary": "Imported summary"}
        ],
        "scores": [
            {"judge": "jdg_01", "project": "prj_import_01", "criteria": {"functionality": 5}}
        ]
    }
    resp = client.post("/api/export/import", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["imported_projects"] == 1

def test_team_create_and_leave():
    # Register a new unique participant
    reg_res = client.post("/api/auth/signup", json={
        "name": "Jordan Lee",
        "email": "jordan.lee@example.org",
        "password": "securepassword123",
        "event_id": "evt_02"
    })
    assert reg_res.status_code == 200
    token = reg_res.json()["token"]
    headers = {"Authorization": f"Token {token}"}

    # Create team
    create_res = client.post("/api/teams/create", json={
        "name": "Hyperion Labs",
        "event_id": "evt_02"
    }, headers=headers)
    assert create_res.status_code == 200
    data = create_res.json()
    assert data["status"] == "success"
    team = data["team"]
    assert team["name"] == "Hyperion Labs"
    assert "jordan.lee@example.org" in team["members"]
    assert team["invite_code"].startswith("inv_")

    # Leave team
    leave_res = client.post("/api/teams/leave", json={
        "team_id": team["id"]
    }, headers=headers)
    assert leave_res.status_code == 200
    assert leave_res.json()["status"] == "success"

def test_new_participant_dashboard_isolation():
    # Sign up brand new participant
    reg_res = client.post("/api/auth/signup", json={
        "name": "Sarah Connor",
        "email": "sarah.connor@cyberdyne.org",
        "password": "terminatorproof123",
        "event_id": "evt_02"
    })
    assert reg_res.status_code == 200
    token = reg_res.json()["token"]

    # Request dashboard with their session cookie
    dash_res = client.get("/participant/dashboard?event=evt_02", cookies={"session": token})
    assert dash_res.status_code == 200
    html = dash_res.text

    # Verify NO fallback to fixture data
    assert "Nightshift" not in html
    assert "Quiet Hours" not in html
    assert "NO SUBMISSION YET" in html
    assert "Team Formation for" in html
    assert "Create a Team" in html
    assert "Join Existing Team" in html
