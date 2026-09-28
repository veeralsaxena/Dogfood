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
    assert "HACKATHON RAPTORS" in resp.text
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
