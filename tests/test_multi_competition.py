import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.config import TEST_TOKENS
from src.core.security import hash_password, verify_password

client = TestClient(app)

def test_list_competitions():
    res = client.get("/api/competitions")
    assert res.status_code == 200
    data = res.json()
    assert "competitions" in data
    assert len(data["competitions"]) >= 2

    # Check evt_01 (Sample Hack 2026) and evt_02 (Raptors AI Challenge)
    slugs = [c["slug"] for c in data["competitions"]]
    assert "sample-hack-2026" in slugs
    assert "raptors-ai-2026" in slugs

    # Check join codes and QR URLs
    for c in data["competitions"]:
        assert c["join_code"] is not None
        assert "qr_url" in c

def test_create_competition_and_lifecycle():
    headers = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}
    
    # 1. Organizer provisions new competition
    res = client.post("/api/competitions", headers=headers, json={
        "name": "Zero-Knowledge Systems Cup 2026",
        "description": "Verifiable compute and cryptography championship.",
        "submissions_close": "2026-11-30T23:59:59Z",
        "prize_pool": "$75,000 USD",
        "tracks": ["SNARKs & STARKs", "Hardware Acceleration", "ZK-Rollups"]
    })
    assert res.status_code == 200
    created = res.json()
    assert created["status"] == "success"
    assert "join_code" in created
    assert created["join_code"].startswith("RAPTOR-")
    event_id = created["event_id"]

    # 2. Lifecycle transitions
    patch_res = client.patch(f"/api/competitions/{event_id}/status", headers=headers, json={
        "status": "frozen"
    })
    assert patch_res.status_code == 200
    assert patch_res.json()["new_status"] == "frozen"

    # 3. Participant cannot transition status (RBAC violation blocked)
    part_headers = {"Authorization": f"Token {TEST_TOKENS['participant']}"}
    unauth_res = client.patch(f"/api/competitions/{event_id}/status", headers=part_headers, json={
        "status": "published"
    })
    assert unauth_res.status_code == 403

def test_join_competition_by_code():
    headers = {"Authorization": f"Token {TEST_TOKENS['participant']}"}

    # 1. Successful join with valid code
    res = client.post("/api/competitions/join", headers=headers, json={
        "join_code": "RAPTOR-2026"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["slug"] == "raptors-ai-2026"
    assert data["redirect_url"] == "/participant/dashboard"

    # 2. Case-insensitive join
    res_lower = client.post("/api/competitions/join", headers=headers, json={
        "join_code": "raptor-2026"
    })
    assert res_lower.status_code == 200

    # 3. Invalid code returns 404
    bad_res = client.post("/api/competitions/join", headers=headers, json={
        "join_code": "NONEXISTENT-CODE"
    })
    assert bad_res.status_code == 404

def test_offline_vector_svg_qr_generation():
    # 1. Competition QR Code (Pure SVG, 0 external calls)
    res = client.get("/api/competitions/evt_02/qr")
    assert res.status_code == 200
    assert "image/svg+xml" in res.headers["content-type"]
    assert "<svg" in res.text
    assert "</svg>" in res.text

    # 2. Invitation QR Code
    headers = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}
    inv_res = client.post("/api/organizer/invites", headers=headers, json={
        "role": "judge",
        "tracks": ["trk_r1"]
    })
    assert inv_res.status_code == 200
    token = inv_res.json()["invite_token"]

    qr_res = client.get(f"/api/invitations/{token}/qr")
    assert qr_res.status_code == 200
    assert "image/svg+xml" in qr_res.headers["content-type"]
    assert "<svg" in qr_res.text

def test_web_routes_and_role_segregation():
    # 1. Public Competitions Directory
    comp_page = client.get("/competitions")
    assert comp_page.status_code == 200
    assert "Active Competitions" in comp_page.text
    assert "Raptors AI" in comp_page.text

    # 2. Competition Landing Page
    detail_page = client.get("/c/raptors-ai-2026")
    assert detail_page.status_code == 200
    assert "Autonomous Agents" in detail_page.text
    assert "RAPTOR-2026" in detail_page.text

    # 3. Direct Join Route (unauthenticated redirects to login)
    client.cookies.clear()
    join_redir = client.get("/join/RAPTOR-2026", follow_redirects=False)
    assert join_redir.status_code == 303
    assert "/login?join_code=RAPTOR-2026" in join_redir.headers["location"]

    # 4. Organizer Competitions Management (participant blocked from organizer portal)
    client.cookies.set("session", TEST_TOKENS["participant"])
    blocked_org = client.get("/organizer/competitions", follow_redirects=False)
    assert blocked_org.status_code == 303  # Redirects away to login / forbidden

    # 5. Organizer Access Granted
    client.cookies.set("session", TEST_TOKENS["organizer"])
    org_page = client.get("/organizer/competitions")
    assert org_page.status_code == 200
    assert "Multi-Competition Hub" in org_page.text

def test_argon2id_cryptographic_verification():
    pw = "SuperSecure@Venue123!"
    hashed = hash_password(pw)
    assert hashed.startswith("$argon2id$")
    assert verify_password(pw, hashed) is True
    assert verify_password("wrongpassword", hashed) is False
