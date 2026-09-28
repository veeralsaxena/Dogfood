import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.config import TEST_TOKENS
from src.seed import seed_database

@pytest.fixture(autouse=True)
def setup_db():
    seed_database()

client = TestClient(app)

def test_judge_a_sees_own_scores():
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_a']}"}
    resp = client.get("/api/judge/scores", headers=headers)
    assert resp.status_code == 200
    scores = resp.json()
    assert isinstance(scores, list)
    for s in scores:
        assert s["judge_id"] == "jdg_01"

def test_judge_b_cannot_see_peer_scores():
    # Peer scores probe as specified in .dogfood.toml
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_b']}"}
    resp = client.get("/api/judge/scores?judge=judge_a", headers=headers)
    assert resp.status_code in (401, 403)
    assert "cannot inspect peer scores" in resp.json()["detail"].lower()

def test_participant_blocked_from_scores():
    headers = {"Authorization": f"Token {TEST_TOKENS['participant']}"}
    resp = client.get("/api/judge/scores", headers=headers)
    assert resp.status_code in (401, 403)

def test_unauthenticated_stranger_blocked():
    resp = client.get("/api/judge/scores")
    assert resp.status_code == 401
