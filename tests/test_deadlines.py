import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.config import TEST_TOKENS

client = TestClient(app)

def test_closed_event_refuses_submissions():
    headers = {"Authorization": f"Token {TEST_TOKENS['participant']}"}
    payload = {
        "title": "Late Project Probe",
        "summary": "This should be refused by strict backend deadline check."
    }
    resp = client.post("/api/projects", json=payload, headers=headers)
    assert 400 <= resp.status_code < 500
    assert "closed" in resp.json()["detail"].lower()
