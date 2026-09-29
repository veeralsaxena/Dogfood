import json
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.config import TEST_TOKENS
from src.database import get_db

client = TestClient(app)

def test_dynamic_rubric_custom_criteria_lifecycle():
    org_header = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}
    judge_header = {"Authorization": f"Token {TEST_TOKENS['judge_a']}"}

    # 1. Organizer updates rubric with 5 custom criteria including 'security'
    custom_weights = {
        "functionality": 0.25,
        "quality": 0.25,
        "security": 0.20,
        "innovation": 0.15,
        "presentation": 0.15
    }

    settings_payload = {
        "event_id": "evt_01",
        "name": "Sample Hack 2026 - Custom Rubric",
        "submissions_close": "2026-03-01T18:00:00Z",
        "weights": custom_weights
    }

    res = client.post("/api/event/settings", json=settings_payload, headers=org_header)
    assert res.status_code == 200, f"Expected 200 from settings update, got {res.status_code}: {res.text}"
    assert res.json()["status"] == "updated"

    # 2. Verify Judge Portal HTML renders all 5 criteria dynamically
    judge_page = client.get("/judge", headers=judge_header)
    assert judge_page.status_code == 200
    html = judge_page.text
    assert "SECURITY (20%)" in html
    assert "PRESENTATION (15%)" in html
    assert "FUNCTIONALITY (25%)" in html

    # 3. Judge evaluates a project from their track (prj_02 in trk_03) with the 5 criteria
    score_payload = {
        "project_id": "prj_02",
        "criteria": {
            "functionality": 5,
            "quality": 4,
            "security": 5,
            "innovation": 4,
            "presentation": 5
        },
        "comment": "Exemplary security posture and flawless presentation."
    }

    score_res = client.post("/api/judge/scores", json=score_payload, headers=judge_header)
    assert score_res.status_code == 200, f"Expected 200 from score submit, got {score_res.status_code}: {score_res.text}"

    # 4. Verify composite score calculation
    # Expected weighted score: 5*0.25 + 4*0.25 + 5*0.20 + 4*0.15 + 5*0.15 = 1.25 + 1.0 + 1.0 + 0.6 + 0.75 = 4.60
    judge_page_after = client.get("/judge", headers=judge_header)
    assert "4.60" in judge_page_after.text

    # 5. Restore default weights so subsequent tests stay in expected baseline
    restore_weights = {
        "functionality": 0.4,
        "quality": 0.3,
        "innovation": 0.2,
        "design": 0.1
    }
    client.post("/api/event/settings", json={
        "event_id": "evt_01",
        "name": "Sample Hack 2026",
        "submissions_close": "2026-03-01T18:00:00Z",
        "weights": restore_weights
    }, headers=org_header)
