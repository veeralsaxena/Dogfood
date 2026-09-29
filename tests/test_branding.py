import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.database import init_db
from src.seed import seed_database
from src.config import TEST_TOKENS

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    seed_database()

def test_branding_endpoint_organizer_success():
    """Organizer can customize white-label branding theme."""
    payload = {
        "brand_name": "OXFORD AI SUMMIT",
        "org_name": "University of Oxford",
        "sub_org": "DEPARTMENT OF COMPUTER SCIENCE · AUTONOMOUS SYSTEMS",
        "tagline": "autonomous systems 2026",
        "accent_color": "#002147",
        "accent_hover": "#001530",
        "crest_icon": "oxford",
        "theme_preset": "navy"
    }

    res = client.post(
        "/api/competitions/evt_01/branding",
        headers={"Authorization": f"Token {TEST_TOKENS['organizer']}"},
        json=payload
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["branding"]["brand_name"] == "OXFORD AI SUMMIT"
    assert data["branding"]["accent_color"] == "#002147"

def test_branding_endpoint_unauthorized():
    """Participant or unauthenticated user cannot modify branding."""
    payload = {
        "brand_name": "HACKED BRAND",
        "org_name": "Hacker Org",
        "accent_color": "#ff0000"
    }

    # No token
    res = client.post("/api/competitions/evt_01/branding", json=payload)
    assert res.status_code in (401, 403)

    # Participant token
    res_part = client.post(
        "/api/competitions/evt_01/branding",
        headers={"Authorization": f"Token {TEST_TOKENS['participant']}"},
        json=payload
    )
    assert res_part.status_code == 403

def test_org_portal_gateway():
    """GET /org/{slug} sets active_event cookie and redirects to competition projects."""
    res = client.get("/org/mit-techfair-2026", follow_redirects=False)
    assert res.status_code == 303
    assert "/projects?event=evt_03" in res.headers["location"]
    assert "active_event=evt_03" in res.headers.get("set-cookie", "")

def test_dynamic_certificate_branding():
    """Certificates dynamically render institution name and accent color."""
    # prj_mit_01 belongs to evt_03 (MIT TechFair)
    res = client.get("/certificates/prj_mit_01")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/svg+xml"
    svg_text = res.text
    # Should include MIT organization name and MIT crimson accent #a31f34
    assert "Massachusetts Institute of Technology" in svg_text
    assert "#a31f34" in svg_text or "#A31F34" in svg_text.upper()

def test_platform_branding_stability():
    """Platform navbar retains stable 'VERITAS' identity even when visiting branded events."""
    res = client.get("/projects?event=evt_03")
    assert res.status_code == 200
    html = res.text
    assert "VERITAS" in html

def test_submit_page_branding_stability():
    """Visiting /submit retains stable 'VERITAS' navbar and clean layout."""
    res = client.get("/submit")
    assert res.status_code == 200
    html = res.text
    assert "VERITAS" in html
