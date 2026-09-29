"""
tests/test_arena_and_judging_workflow.py

Comprehensive, requirement-driven, opaque-box regression test suite for
Veritas Hackathon Platform remediation covering Requirements R1 through R5.

Requirements Covered:
  - R1: Eliminating Evaluator Anchoring in Pairwise Arena
        (Arena Leaderboard hidden from judges; progress counter & sealed notice shown;
         organizers see leaderboard in /war-room and /arena; /api/arena/rankings 403 for judges, 200 for organizers)
  - R2: Contextualize Pairwise Evaluation Cards
        (/api/arena/pair returns enriched metadata: track_name, team_name, demo_url, description;
         /arena HTML renders functional calibration guidance and a Skip Matchup button)
  - R3: Track-Aware Matchmaking & Filtering
        (/api/arena/pair?track=... filters by track; intra-track matchmaking priority;
         /arena track filter selector)
  - R4: Fix Evaluation Queue Truncation & State Persistence
        (/judge displays all assigned projects without [:6] truncation limit;
         previously scored projects display existing score, comment, rubric values, and
         '✓ Evaluated (Score: X.XX / 5.00)' badge; updates persist seamlessly)
  - R5: Remove Fragile Hardcoded Auth Fallbacks
        (no hardcoded judgea000 fallback tokens in static JS or HTML templates;
         unauthenticated requests return 401 Unauthorized;
         session cookie authentication works seamlessly without impersonation)
"""

import json
import re
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.config import TEST_TOKENS, BASE_DIR
from src.seed import seed_database
from src.database import get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_test_environment():
    """Ensure every test runs against clean seed data with empty client cookies."""
    seed_database()
    client.cookies.clear()


# ============================================================================
# R1: Eliminate Evaluator Anchoring in Pairwise Arena
# ============================================================================

def test_r1_judge_visiting_arena_cannot_see_leaderboard():
    """
    R1.1: Active judge visiting /arena must NOT see the real-time Arena Leaderboard
    or Bradley-Terry latent skill scores (pi_i) to prevent evaluator anchoring.
    """
    # 1. Test with judge_a (Ada Okonkwo / jdg_01)
    headers_a = {"Authorization": f"Token {TEST_TOKENS['judge_a']}"}
    resp_a = client.get("/arena", headers=headers_a)
    assert resp_a.status_code == 200

    html_a = resp_a.text
    assert "Arena Leaderboard" not in html_a, "Active judge must not see Arena Leaderboard"
    assert "Bradley-Terry Skill Rating" not in html_a, "Active judge must not see Bradley-Terry skill ratings"
    assert "Latent Skill" not in html_a, "Active judge must not see latent skill values"
    assert "Arena Rank" not in html_a, "Active judge must not see arena ranks"

    # 2. Test with judge_b (Wei Lindqvist / jdg_02)
    headers_b = {"Authorization": f"Token {TEST_TOKENS['judge_b']}"}
    resp_b = client.get("/arena", headers=headers_b)
    assert resp_b.status_code == 200
    html_b = resp_b.text
    assert "Arena Leaderboard" not in html_b
    assert "Bradley-Terry Skill Rating" not in html_b


def test_r1_judge_sees_progress_counter_and_sealed_integrity_notice():
    """
    R1.2: Active judge visiting /arena must see an evaluation progress counter
    (e.g., 'X matchups evaluated by you') and an integrity notice that global
    rankings remain sealed until judging closes.
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_a']}"}
    resp = client.get("/arena", headers=headers)
    assert resp.status_code == 200
    html = resp.text.lower()

    # In fixture data, jdg_01 has completed 2 pairwise votes
    has_counter = (
        ("2 matchup" in html and "evaluated" in html) or
        ("matchup" in html and "evaluated by you" in html) or
        ("evaluations completed" in html)
    )
    assert has_counter, (
        "Judge /arena view must display an evaluation progress counter showing matchups evaluated by the judge"
    )

    # Integrity notice that global rankings remain sealed
    has_notice = (
        ("integrity notice" in html or "confidentiality notice" in html) and
        ("sealed" in html or "closing" in html or "anchoring" in html)
    )
    assert has_notice, (
        "Judge /arena view must display an integrity notice stating global rankings remain sealed"
    )


def test_r1_organizer_retains_full_leaderboard_in_arena():
    """
    R1.3: Organizers visiting /arena retain full visibility of Bradley-Terry
    latent skill rankings and leaderboard table.
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}
    resp = client.get("/arena", headers=headers)
    assert resp.status_code == 200
    html = resp.text

    assert "Arena Leaderboard" in html, "Organizer visiting /arena must see Arena Leaderboard"
    assert (
        "Bradley-Terry Skill Rating" in html or
        "Latent Skill" in html or
        "Arena Rank" in html
    ), "Organizer must see Bradley-Terry skill rating columns in /arena"


def test_r1_organizer_sees_arena_leaderboard_in_war_room():
    """
    R1.3: Organizers visiting /war-room must see the full Bradley-Terry
    Arena Leaderboard alongside normalization scores.
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}
    resp = client.get("/war-room", headers=headers)
    assert resp.status_code == 200
    html = resp.text

    assert (
        "Arena Leaderboard" in html or
        "Bradley-Terry" in html
    ), "Organizer visiting /war-room must see Bradley-Terry Arena standings"


def test_r1_api_arena_rankings_role_gating():
    """
    R1.4: /api/arena/rankings must be strictly role-gated:
    - HTTP 403 for judges and participants
    - HTTP 401 or 403 for unauthenticated visitors
    - HTTP 200 for organizers and admins
    """
    # Active judge A blocked
    resp_judge = client.get(
        "/api/arena/rankings",
        headers={"Authorization": f"Token {TEST_TOKENS['judge_a']}"}
    )
    assert resp_judge.status_code == 403, "Judges must be forbidden (403) from querying /api/arena/rankings"

    # Active judge B blocked
    resp_judge_b = client.get(
        "/api/arena/rankings",
        headers={"Authorization": f"Token {TEST_TOKENS['judge_b']}"}
    )
    assert resp_judge_b.status_code == 403, "Judge B must be forbidden (403) from /api/arena/rankings"

    # Participant blocked
    resp_participant = client.get(
        "/api/arena/rankings",
        headers={"Authorization": f"Token {TEST_TOKENS['participant']}"}
    )
    assert resp_participant.status_code in (401, 403), "Participants must not access /api/arena/rankings"

    # Unauthenticated visitor blocked
    resp_anon = client.get("/api/arena/rankings")
    assert resp_anon.status_code in (401, 403), "Unauthenticated requests to /api/arena/rankings must be rejected"

    # Organizer permitted
    resp_org = client.get(
        "/api/arena/rankings",
        headers={"Authorization": f"Token {TEST_TOKENS['organizer']}"}
    )
    assert resp_org.status_code == 200, "Organizers must receive 200 OK from /api/arena/rankings"
    data = resp_org.json()
    assert "rankings" in data, "Rankings payload must contain 'rankings' list"
    assert isinstance(data["rankings"], list), "'rankings' must be a list"
    assert len(data["rankings"]) > 0, "'rankings' should contain ranked projects"
    first = data["rankings"][0]
    assert "project_id" in first
    assert "rank" in first
    assert "skill_score" in first


# ============================================================================
# R2: Contextualize Pairwise Evaluation Cards
# ============================================================================

def test_r2_api_arena_pair_returns_enriched_metadata():
    """
    R2.1: /api/arena/pair must return comprehensive project evaluation metadata:
    track_name, team_name, demo_url, description, repo_url, etc.
    """
    resp = client.get("/api/arena/pair")
    assert resp.status_code == 200
    data = resp.json()

    assert "project_a" in data and "project_b" in data, "Response must include project_a and project_b"
    pa = data["project_a"]
    pb = data["project_b"]

    required_fields = [
        "id", "title", "summary", "description", "repo_url",
        "demo_url", "track_id", "track_name", "team_id", "team_name"
    ]
    for field in required_fields:
        assert field in pa, f"project_a is missing required enriched field: {field}"
        assert field in pb, f"project_b is missing required enriched field: {field}"

    # Verify track_name and team_name are resolved non-empty strings
    assert pa["track_name"] and isinstance(pa["track_name"], str), "project_a track_name must be populated"
    assert pb["track_name"] and isinstance(pb["track_name"], str), "project_b track_name must be populated"
    assert pa["team_name"] and isinstance(pa["team_name"], str), "project_a team_name must be populated"
    assert pb["team_name"] and isinstance(pb["team_name"], str), "project_b team_name must be populated"


def test_r2_arena_html_renders_rich_evaluation_cards():
    """
    R2.1: /arena HTML must render track badges, team names, live demo links,
    and technical summaries for candidate comparison cards.
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_a']}"}
    resp = client.get("/arena", headers=headers)
    assert resp.status_code == 200
    html = resp.text

    # Track badge rendered
    assert "badge" in html, "/arena cards must include visual badge styling"
    # Live demo link or button
    assert (
        "Live Demo" in html or
        "demo_url" in html or
        "demo" in html.lower()
    ), "/arena cards must display live demo links when present"
    # Repository inspection link
    assert (
        "Inspect Repo" in html or
        "Repository" in html or
        "repo" in html.lower()
    ), "/arena cards must display repository links"
    # Team identification
    assert (
        "Team:" in html or
        "team" in html.lower()
    ), "/arena cards must display team names or IDs"


def test_r2_arena_functional_guidance_and_skip_button():
    """
    R2.2 & R2.3:
    - Replace academic marketing copy with functional evaluation guidance.
    - Include a functional 'Skip Matchup' button allowing judges to request
      an alternate pairing.
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_a']}"}
    resp = client.get("/arena", headers=headers)
    assert resp.status_code == 200
    html = resp.text

    # Functional evaluation guidance
    has_guidance = (
        "Tie-Breaker" in html or
        "Calibration" in html or
        "Compare projects head-to-head" in html
    )
    assert has_guidance, (
        "/arena must feature functional evaluation guidance (e.g. Tie-Breaker & Calibration Arena)"
    )

    # Skip Matchup button
    assert "Skip Matchup" in html, (
        "/arena must render a 'Skip Matchup' action button for requesting alternate pairings"
    )


# ============================================================================
# R3: Track-Aware Matchmaking & Filtering
# ============================================================================

def test_r3_api_arena_pair_track_filtering():
    """
    R3.1: /api/arena/pair?track=... must filter comparison candidates
    strictly to the requested track.
    """
    # Request track trk_03 (Accessibility - 6 projects in fixtures)
    resp = client.get("/api/arena/pair?track=trk_03")
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_a"]["track_id"] == "trk_03", "project_a must belong to requested track trk_03"
    assert data["project_b"]["track_id"] == "trk_03", "project_b must belong to requested track trk_03"

    # Request track trk_02 (Data and analytics - 6 projects in fixtures)
    resp2 = client.get("/api/arena/pair?track=trk_02")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["project_a"]["track_id"] == "trk_02", "project_a must belong to requested track trk_02"
    assert data2["project_b"]["track_id"] == "trk_02", "project_b must belong to requested track trk_02"


def test_r3_intra_track_matchmaking_priority():
    """
    R3.1: Candidate matchmaking must prioritize intra-track pairings over
    cross-track comparisons to avoid 'apples-to-airplanes' evaluations.
    """
    # Query /api/arena/pair multiple times without track filter.
    # In an event where tracks have >= 2 projects, sampled candidates must
    # prioritize matching within the same track.
    same_track_count = 0
    total_samples = 10
    for _ in range(total_samples):
        resp = client.get("/api/arena/pair")
        assert resp.status_code == 200
        pair = resp.json()
        if pair["project_a"]["track_id"] == pair["project_b"]["track_id"]:
            same_track_count += 1

    assert same_track_count >= 8, (
        f"Matchmaking must prioritize intra-track pairings; got {same_track_count}/{total_samples} from same track"
    )


def test_r3_select_arena_pair_contract():
    """
    R3.1: src.core.pairwise.select_arena_pair function contract:
    - Input: projects list, optional track_filter
    - Returns: (project_a, project_b) tuple of distinct projects
    - Behavior: filters to track if specified; prioritizes intra-track if multiple tracks
    """
    try:
        from src.core.pairwise import select_arena_pair
    except ImportError:
        pytest.fail("src.core.pairwise.select_arena_pair function must be implemented")

    synthetic_projects = [
        {"id": "p1", "track_id": "trk_01", "title": "P1"},
        {"id": "p2", "track_id": "trk_01", "title": "P2"},
        {"id": "p3", "track_id": "trk_02", "title": "P3"},
        {"id": "p4", "track_id": "trk_02", "title": "P4"},
    ]
    pa, pb = select_arena_pair(synthetic_projects)
    assert pa["id"] != pb["id"], "Selected projects must be distinct"
    assert pa["track_id"] == pb["track_id"], "Intra-track matchmaking must pair from the same track"

    # Explicit track filter in helper
    pa_f, pb_f = select_arena_pair(synthetic_projects, track_filter="trk_02")
    assert pa_f["track_id"] == "trk_02", "Project A must match requested track filter"
    assert pb_f["track_id"] == "trk_02", "Project B must match requested track filter"
    assert pa_f["id"] != pb_f["id"], "Filtered projects must be distinct"


def test_r3_arena_track_filter_selector_rendered():
    """
    R3.2: /arena must render a track filter dropdown selector allowing judges
    to filter comparisons by track.
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_a']}"}
    resp = client.get("/arena", headers=headers)
    assert resp.status_code == 200
    html = resp.text

    # Dropdown selector for track filter
    assert "<select" in html, "/arena must render a select dropdown for track filtering"
    has_track_options = (
        "trk_01" in html or
        "trk_02" in html or
        "trk_03" in html or
        "Developer tools" in html or
        "Accessibility" in html
    )
    assert has_track_options, "/arena track selector must be populated with competition tracks"

    # Visiting with ?track=trk_03 renders candidates within trk_03
    resp_track = client.get("/arena?track=trk_03", headers=headers)
    assert resp_track.status_code == 200
    assert "trk_03" in resp_track.text or "Accessibility" in resp_track.text


# ============================================================================
# R4: Fix Evaluation Queue Truncation & State Persistence
# ============================================================================

def test_r4_judge_queue_no_truncation_all_assigned_projects_shown():
    """
    R4.1: /judge must display all projects assigned to the judge's tracks
    without arbitrary truncation to 6 (removing hardcoded projects[:6]).
    Judge B (jdg_02) is assigned to trk_02 (6 projects) and trk_04 (5 projects) = 11 projects total.
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_b']}"}
    resp = client.get("/judge", headers=headers)
    assert resp.status_code == 200
    html = resp.text

    # The 11 assigned project IDs for Judge B (trk_02 and trk_04):
    # trk_02: prj_05, prj_11, prj_21, prj_25, prj_28, prj_38
    # trk_04: prj_01, prj_08, prj_15, prj_16, prj_22
    assigned_project_ids = [
        "prj_01", "prj_05", "prj_08", "prj_11", "prj_15",
        "prj_16", "prj_21", "prj_22", "prj_25", "prj_28", "prj_38"
    ]

    rendered_count = 0
    for pid in assigned_project_ids:
        if pid in html:
            rendered_count += 1

    assert rendered_count == 11, (
        f"All 11 assigned projects must be visible to Judge B in /judge without [:6] truncation. "
        f"Found {rendered_count}/11 rendered."
    )
    assert rendered_count > 6, "Queue must not be capped at 6 projects"


def test_r4_judge_portal_prepopulates_existing_evaluation_and_badge():
    """
    R4.2 & R4.3: Previously scored projects on /judge must display:
    - Pre-populated comment input
    - Pre-selected rubric criteria values
    - Correct weighted total score
    - '✓ Evaluated (Score: X.XX / 5.00)' status badge
    """
    # In seed data, Judge A (jdg_01) has evaluated prj_07 (trk_03) with:
    # criteria: functionality=2, quality=2, innovation=2
    # comment: "Docs are thin."
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_a']}"}
    resp = client.get("/judge", headers=headers)
    assert resp.status_code == 200
    html = resp.text

    # 1. Evaluated Status Badge
    assert "✓ Evaluated" in html, (
        "Scored project card must display '✓ Evaluated' status badge"
    )
    assert "/ 5.00" in html, "Evaluated badge must show score relative to 5.00 scale"

    # 2. Pre-populated comment
    assert 'value="Docs are thin."' in html or "Docs are thin." in html, (
        "Pre-existing comment must be pre-populated in input"
    )

    # 3. Weighted score for prj_07 (composite score 2.00)
    assert "2.00" in html, "Pre-existing weighted score of 2.00 should be rendered for prj_07"


def test_r4_judge_score_submission_upsert_and_persistence():
    """
    R4.2 & R4.3: Submitting an updated evaluation score updates the existing
    record and reflects the new score and status badge in the portal.
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_a']}"}

    # Judge A submits an updated score for prj_07
    updated_payload = {
        "project_id": "prj_07",
        "criteria": {
            "functionality": 5,
            "quality": 5,
            "innovation": 4,
            "design": 4
        },
        "comment": "Substantial improvements: full documentation and test coverage in v2."
    }
    submit_resp = client.post("/api/judge/scores", headers=headers, json=updated_payload)
    assert submit_resp.status_code == 200, f"Score submission failed: {submit_resp.text}"

    # Verify directly in SQLite database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT criteria, comment FROM scores WHERE judge_id = 'jdg_01' AND project_id = 'prj_07'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None, "Score row must exist in database"
    assert "Substantial improvements" in row["comment"]
    saved_criteria = json.loads(row["criteria"]) if isinstance(row["criteria"], str) else row["criteria"]
    assert saved_criteria.get("functionality") == 5

    # Reload /judge and verify updated comment, badge, and weighted score
    # evt_01 weights: func=0.4, qual=0.3, innov=0.2, des=0.1
    # 5*0.4 + 5*0.3 + 4*0.2 + 4*0.1 = 2.0 + 1.5 + 0.8 + 0.4 = 4.70
    portal_resp = client.get("/judge", headers=headers)
    assert portal_resp.status_code == 200
    portal_html = portal_resp.text

    assert "Substantial improvements" in portal_html, "Updated comment must appear in /judge"
    assert "4.70" in portal_html, "Updated weighted score 4.70 must appear in /judge"
    assert "✓ Evaluated" in portal_html, "Status badge must remain active on re-evaluation"


def test_r4_unevaluated_projects_do_not_show_evaluated_badge():
    """
    R4.3: Projects assigned to a judge that have NOT yet been scored must NOT
    display an active '✓ Evaluated' status badge.
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_a']}"}
    resp = client.get("/judge", headers=headers)
    assert resp.status_code == 200
    html = resp.text

    # In trk_03, only prj_07 was scored by jdg_01.
    # Other projects in trk_03 (e.g. prj_02, prj_03, prj_20, prj_39) are unevaluated.
    # Check that unscored projects do not display an active evaluation badge
    # (either display:none or not rendered)
    badge_matches = re.findall(r'✓ Evaluated \(Score: [0-9.]+\s*/\s*5\.00\)', html)
    assert len(badge_matches) == 1, (
        f"Only prj_07 has been evaluated by Judge A; expected exactly 1 active evaluation badge, found {len(badge_matches)}"
    )


# ============================================================================
# R5: Remove Fragile Hardcoded Auth Fallbacks
# ============================================================================

def test_r5_no_hardcoded_tokens_in_client_assets():
    """
    R5.1: Zero hardcoded fallback tokens ('judgea0000000000000000000000000000000000')
    must remain in static JavaScript files or Jinja2 HTML templates.
    """
    banned_token = "judgea0000000000000000000000000000000000"

    client_paths = [
        BASE_DIR / "src" / "static" / "js" / "app.js",
        BASE_DIR / "src" / "templates" / "judge_portal.html",
        BASE_DIR / "src" / "templates" / "arena.html",
        BASE_DIR / "src" / "templates" / "submit.html",
        BASE_DIR / "src" / "templates" / "event_settings.html",
        BASE_DIR / "src" / "templates" / "organizer_competitions.html",
        BASE_DIR / "src" / "templates" / "war_room.html",
    ]

    for p in client_paths:
        if p.exists():
            content = p.read_text(encoding="utf-8")
            assert banned_token not in content, (
                f"Hardcoded judge_a fallback token found in {p.relative_to(BASE_DIR)}"
            )

    # In app.js specifically, ensure no 'Token judgea' literal exists
    app_js = (BASE_DIR / "src" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "Token judgea" not in app_js, "app.js must not contain hardcoded judge_a token fallback"


def test_r5_unauthenticated_request_rejected_401():
    """
    R5.2: Unauthenticated POST requests must return HTTP 401 Unauthorized
    rather than silently falling back to Judge A credentials.
    """
    client.cookies.clear()

    # Score submission without auth
    resp_score = client.post(
        "/api/judge/scores",
        json={"project_id": "prj_01", "criteria": {"functionality": 3}}
    )
    assert resp_score.status_code == 401, (
        "Unauthenticated score submission must return 401, not fall back to Judge A"
    )

    # Pairwise vote submission without auth
    resp_vote = client.post(
        "/api/arena/vote",
        json={"winner_id": "prj_01", "loser_id": "prj_02"}
    )
    assert resp_vote.status_code == 401, (
        "Unauthenticated pairwise vote must return 401, not fall back to Judge A"
    )


def test_r5_session_cookie_auth_works_seamlessly_without_header():
    """
    R5.2: Session cookie authentication ('Cookie: session=<token>') must work
    seamlessly without an Authorization header, and must attribute actions
    strictly to the cookie holder without cross-judge impersonation.
    """
    client.cookies.clear()
    judge_b_token = TEST_TOKENS["judge_b"]

    # 1. Cast pairwise vote using cookie only
    vote_resp = client.post(
        "/api/arena/vote",
        headers={"Cookie": f"session={judge_b_token}"},
        json={"winner_id": "prj_05", "loser_id": "prj_11"}
    )
    assert vote_resp.status_code == 200, f"Cookie-authenticated pairwise vote failed: {vote_resp.text}"

    # Verify vote in DB is attributed to jdg_02, NOT jdg_01
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT judge_id FROM pairwise_votes WHERE winner_id = 'prj_05' AND loser_id = 'prj_11' ORDER BY id DESC LIMIT 1"
    )
    vote_row = cursor.fetchone()
    assert vote_row is not None
    assert vote_row["judge_id"] == "jdg_02", (
        f"Vote must be recorded as Judge B (jdg_02), got {vote_row['judge_id']}"
    )

    # 2. Submit score using cookie only
    score_resp = client.post(
        "/api/judge/scores",
        headers={"Cookie": f"session={judge_b_token}"},
        json={
            "project_id": "prj_05",
            "criteria": {"functionality": 4, "quality": 4, "innovation": 4, "design": 4},
            "comment": "Cookie-authenticated score by Judge B"
        }
    )
    assert score_resp.status_code == 200, f"Cookie-authenticated score submission failed: {score_resp.text}"

    cursor.execute(
        "SELECT judge_id, comment FROM scores WHERE project_id = 'prj_05' AND judge_id = 'jdg_02'"
    )
    score_row = cursor.fetchone()
    conn.close()
    assert score_row is not None, "Score must be recorded for jdg_02"
    assert "Cookie-authenticated score by Judge B" in score_row["comment"]


def test_r5_cookie_session_in_judge_portal_view():
    """
    R5.2: Visiting /judge via session cookie correctly resolves the active judge
    and displays their assigned queue and evaluations without impersonation.
    """
    client.cookies.clear()
    resp = client.get("/judge", headers={"Cookie": f"session={TEST_TOKENS['judge_b']}"})
    assert resp.status_code == 200

    # Judge B has tracks trk_02 and trk_04. Check that trk_02 and trk_04 projects appear.
    html = resp.text
    assert "trk_02" in html or "trk_04" in html, (
        "Judge B accessing /judge via session cookie must see their assigned tracks"
    )


# ============================================================================
# Tier 4 Real-World E2E Workflow & System Constraint Verification
# ============================================================================

def test_e2e_full_judging_and_organizer_isolation_lifecycle():
    """
    Tier 4 E2E Scenario: Full cross-role evaluation lifecycle:
    1. Judge B evaluates assigned queue on /judge (verifying no [:6] truncation).
    2. Judge B saves evaluation, checks persistence and status badge.
    3. Judge B visits /arena, verifies no leaderboard (anti-anchoring), sees progress counter.
    4. Judge B filters /arena by assigned track, skips a pair, votes on another.
    5. Judge B is denied access to /api/arena/rankings (HTTP 403).
    6. Organizer accesses /arena and /war-room, retains full leaderboard visibility.
    7. Organizer accesses /api/arena/rankings successfully (HTTP 200).
    """
    client.cookies.clear()
    judge_b_token = TEST_TOKENS["judge_b"]
    org_token = TEST_TOKENS["organizer"]

    # 1. Judge B visits /judge
    judge_resp = client.get("/judge", headers={"Authorization": f"Token {judge_b_token}"})
    assert judge_resp.status_code == 200
    # Must see assigned projects (11 total)
    assert "prj_05" in judge_resp.text
    assert "prj_22" in judge_resp.text

    # 2. Judge B scores prj_22 (trk_04)
    score_resp = client.post(
        "/api/judge/scores",
        headers={"Authorization": f"Token {judge_b_token}"},
        json={
            "project_id": "prj_22",
            "criteria": {"functionality": 4, "quality": 5, "innovation": 4, "design": 3},
            "comment": "Robust cryptography implementation."
        }
    )
    assert score_resp.status_code == 200

    # Revisit /judge, assert badge appears
    revisit_resp = client.get("/judge", headers={"Authorization": f"Token {judge_b_token}"})
    assert revisit_resp.status_code == 200
    assert "✓ Evaluated" in revisit_resp.text

    # 3. Judge B visits /arena: anti-anchoring verified
    arena_resp = client.get("/arena", headers={"Authorization": f"Token {judge_b_token}"})
    assert arena_resp.status_code == 200
    assert "Arena Leaderboard" not in arena_resp.text
    assert "Bradley-Terry Skill Rating" not in arena_resp.text

    # 4. Judge B filters by track trk_04 in /api/arena/pair
    pair_resp = client.get("/api/arena/pair?track=trk_04")
    assert pair_resp.status_code == 200
    pair_data = pair_resp.json()
    assert pair_data["project_a"]["track_id"] == "trk_04"
    assert pair_data["project_b"]["track_id"] == "trk_04"

    # Vote on track pair
    vote_resp = client.post(
        "/api/arena/vote",
        headers={"Authorization": f"Token {judge_b_token}"},
        json={"winner_id": pair_data["project_a"]["id"], "loser_id": pair_data["project_b"]["id"]}
    )
    assert vote_resp.status_code == 200

    # 5. Judge B denied /api/arena/rankings
    rank_forbidden = client.get("/api/arena/rankings", headers={"Authorization": f"Token {judge_b_token}"})
    assert rank_forbidden.status_code == 403

    # 6. Organizer retains full visibility
    org_arena = client.get("/arena", headers={"Authorization": f"Token {org_token}"})
    assert org_arena.status_code == 200
    assert "Arena Leaderboard" in org_arena.text

    org_war_room = client.get("/war-room", headers={"Authorization": f"Token {org_token}"})
    assert org_war_room.status_code == 200
    assert "Arena Leaderboard" in org_war_room.text or "Bradley-Terry" in org_war_room.text

    # 7. Organizer queries /api/arena/rankings
    org_rankings = client.get("/api/arena/rankings", headers={"Authorization": f"Token {org_token}"})
    assert org_rankings.status_code == 200
    assert "rankings" in org_rankings.json()


def test_offline_zero_external_network_calls_or_cdns():
    """
    Acceptance Verification: Zero external CDNs or remote network calls.
    Veritas platform is strictly self-contained and operates 100% offline.
    """
    cdn_patterns = [
        "cdn.jsdelivr.net",
        "cdnjs.cloudflare.com",
        "unpkg.com",
        "fonts.googleapis.com",
        "fonts.gstatic.com",
        "stackpath.bootstrapcdn.com",
        "maxcdn.bootstrapcdn.com",
        "cdn.tailwindcss.com"
    ]

    templates_dir = BASE_DIR / "src" / "templates"
    static_dir = BASE_DIR / "src" / "static"

    files_to_check = list(templates_dir.glob("*.html")) + list(static_dir.glob("**/*.*"))

    for fpath in files_to_check:
        if fpath.is_file() and fpath.suffix in (".html", ".js", ".css"):
            text = fpath.read_text(encoding="utf-8", errors="ignore")
            for cdn in cdn_patterns:
                assert cdn not in text, f"External CDN dependency '{cdn}' found in {fpath.relative_to(BASE_DIR)}"
