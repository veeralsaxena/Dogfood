"""
tests/test_adversarial_judge_isolation.py

Adversarial Stress Test Suite: Judge Isolation, Security Boundaries, and Auth Handling
Author: Challenger 1 (teamwork_preview_challenger)

Probes:
  1. Active judge attempts to view /arena, scrape peer rankings, access /api/arena/rankings directly.
  2. Unauthenticated requests to /api/judge/scores and /api/arena/vote (ensure 401 Unauthorized, no fallback to judge_a).
  3. Session cookie authentication without Authorization header for different judges (ensure no cross-judge contamination).
  4. Organizer access to /war-room and /arena (ensure Bradley-Terry leaderboard and ALS scores remain fully accessible).
  5. Static grep for any residual fallback tokens.
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
def reset_test_env():
    """Ensure every adversarial test starts with a clean database and cleared client cookies."""
    seed_database()
    client.cookies.clear()


# ============================================================================
# Section 1: Active Judge Isolation & Anti-Anchoring Attack Vectors
# ============================================================================

def test_adv_judge_cannot_view_leaderboard_under_any_query_params():
    """
    Adversarial Probe 1.1: Active judges must not see the Arena Leaderboard,
    Bradley-Terry skill scores, or rankings on /arena under any combination
    of query parameters designed to bypass role gating.
    """
    bypass_attempts = [
        {},
        {"role": "organizer"},
        {"role": "admin"},
        {"admin": "1"},
        {"admin": "true"},
        {"debug": "1"},
        {"show_leaderboard": "1"},
        {"show_leaderboard": "true"},
        {"track": "trk_01"},
        {"track": "trk_02"},
        {"event": "evt_01"},
        {"event": "evt_fixture_01"},
    ]

    for judge_key in ["judge_a", "judge_b"]:
        headers = {"Authorization": f"Token {TEST_TOKENS[judge_key]}"}
        for params in bypass_attempts:
            resp = client.get("/arena", headers=headers, params=params)
            assert resp.status_code == 200, f"Judge /arena returned {resp.status_code} for params {params}"
            html = resp.text

            # Anti-anchoring assertions
            assert "Arena Leaderboard (Latent Skill" not in html, (
                f"Judge {judge_key} was exposed to Arena Leaderboard header with params {params}"
            )
            assert "Bradley-Terry Skill Rating" not in html, (
                f"Judge {judge_key} saw Bradley-Terry Skill Rating column with params {params}"
            )
            assert "Arena Rank" not in html, (
                f"Judge {judge_key} saw Arena Rank column with params {params}"
            )

            # Must display evaluation progress counter and sealed notice
            assert "matchup" in html and "evaluated by you" in html, (
                f"Judge {judge_key} missing progress counter with params {params}"
            )
            assert "Integrity Notice:" in html, (
                f"Judge {judge_key} missing integrity notice with params {params}"
            )
            assert "Global rankings and latent skill scores remain sealed" in html, (
                f"Judge {judge_key} missing sealed notice text with params {params}"
            )


def test_adv_judge_html_contains_zero_embedded_leaderboard_data():
    """
    Adversarial Probe 1.2: Ensure that peer rankings, latent skill scores,
    or solve_bradley_terry outputs are NOT leaked secretly into HTML script
    tags, inline JSON data, or hidden attributes.
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_a']}"}
    resp = client.get("/arena", headers=headers)
    assert resp.status_code == 200
    html = resp.text

    # Ensure no ranking table headers or rows are rendered
    assert "<th>Arena Rank</th>" not in html
    assert "<th>Bradley-Terry Skill Rating</th>" not in html
    assert "/ 100" not in html, "Raw Bradley-Terry skill scores (/ 100) must not appear in judge HTML"

    # Check script tags do not leak ranking data
    script_blocks = re.findall(r"<script[\s\S]*?</script>", html, re.IGNORECASE)
    for block in script_blocks:
        assert "skill_score" not in block.lower(), "Skill scores leaked in script block!"
        assert "solve_bradley_terry" not in block.lower(), "Bradley-Terry data leaked in script block!"


def test_adv_judge_blocked_from_arena_rankings_api_with_spoofed_headers():
    """
    Adversarial Probe 1.3: Judges attempting to hit /api/arena/rankings
    directly must receive HTTP 403 Forbidden even if sending spoofed
    privilege-escalation headers.
    """
    spoof_headers_list = [
        {"Authorization": f"Token {TEST_TOKENS['judge_a']}"},
        {"Authorization": f"Token {TEST_TOKENS['judge_b']}"},
        {"Authorization": f"Token {TEST_TOKENS['judge_a']}", "X-Role": "organizer"},
        {"Authorization": f"Token {TEST_TOKENS['judge_a']}", "X-Admin": "true"},
        {"Authorization": f"Token {TEST_TOKENS['judge_a']}", "X-Forwarded-For": "127.0.0.1"},
        {"Authorization": f"Token {TEST_TOKENS['judge_a']}", "X-Original-URL": "/war-room"},
        {"Authorization": f"Token {TEST_TOKENS['judge_b']}", "X-Role": "admin"},
    ]

    for h in spoof_headers_list:
        resp = client.get("/api/arena/rankings", headers=h)
        assert resp.status_code == 403, (
            f"Expected 403 for /api/arena/rankings with headers {h}, got {resp.status_code}"
        )
        assert "sealed until judging closes" in resp.json().get("detail", "").lower() or (
            "forbidden" in resp.json().get("detail", "").lower()
        )


def test_adv_judge_cannot_scrape_peer_scores_via_alias_or_sqli():
    """
    Adversarial Probe 1.4: Strict peer score isolation.
    Judge A (jdg_01) cannot inspect Judge B (jdg_02) scores via any query parameter variation,
    alias, whitespace injection, SQL injection probe, or case tampering.
    """
    forbidden_probes = [
        "?judge=judge_b",
        "?judge=jdg_02",
        "?judge_id=judge_b",
        "?judge_id=jdg_02",
        "?judge=JUDGE_B",
        "?judge=Judge_B",
        "?judge=jdg_02&judge_id=jdg_02",
        "?judge=jdg_01'%20OR%20'1'='1",
        "?judge=jdg_02;--",
        "?judge=jdg_9999",
        "?judge=%20jdg_02%20",
    ]

    headers_a = {"Authorization": f"Token {TEST_TOKENS['judge_a']}"}

    for probe in forbidden_probes:
        url = f"/api/judge/scores{probe}"
        resp = client.get(url, headers=headers_a)
        assert resp.status_code == 403, (
            f"Expected 403 when Judge A probed {url}, got {resp.status_code}: {resp.text}"
        )
        data = resp.json()
        assert "cannot inspect peer scores" in data.get("detail", "").lower() or (
            "role isolation violation" in data.get("detail", "").lower()
        )

    # Verify audit log recorded the violation attempts
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT action, actor FROM audit_logs WHERE action = 'PEER_SCORE_ACCESS_DENIED'"
    )
    logs = cursor.fetchall()
    conn.close()
    assert len(logs) >= len(forbidden_probes), "Peer score access attempts must be logged in audit_logs"


def test_adv_judge_unfiltered_scores_strictly_scoped_to_self():
    """
    Adversarial Probe 1.5: When a judge calls /api/judge/scores with NO filter,
    the endpoint must strictly scope output to the caller's scores only (no cross-judge leaks).
    """
    # 1. Judge A
    resp_a = client.get("/api/judge/scores", headers={"Authorization": f"Token {TEST_TOKENS['judge_a']}"})
    assert resp_a.status_code == 200
    scores_a = resp_a.json()
    assert len(scores_a) > 0, "Judge A should have seed scores"
    for s in scores_a:
        assert s["judge_id"] == "jdg_01", f"Expected jdg_01 score, found {s['judge_id']}"

    # 2. Judge B
    resp_b = client.get("/api/judge/scores", headers={"Authorization": f"Token {TEST_TOKENS['judge_b']}"})
    assert resp_b.status_code == 200
    scores_b = resp_b.json()
    for s in scores_b:
        assert s["judge_id"] == "jdg_02", f"Expected jdg_02 score, found {s['judge_id']}"


def test_adv_dynamically_created_judge_isolation():
    """
    Adversarial Probe 1.6: A newly invited and onboarded judge (not part of static seed)
    must be strictly subject to the same isolation rules (no arena leaderboard, 403 on rankings,
    403 on peer scores, scoped to assigned queue).
    """
    org_headers = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}

    # 1. Organizer creates invite for new judge
    inv_resp = client.post(
        "/api/organizer/invites",
        headers=org_headers,
        json={"role": "judge", "email": "gamma@test.org", "tracks": ["trk_03"]}
    )
    assert inv_resp.status_code == 200
    inv_token = inv_resp.json()["invite_token"]

    # 2. Onboard new judge
    onboard_resp = client.post(
        "/api/auth/onboard",
        json={
            "token": inv_token,
            "name": "Judge Gamma",
            "email": "gamma@test.org",
            "password": "Password123!"
        }
    )
    assert onboard_resp.status_code == 200
    gamma_token = onboard_resp.json()["token"]
    gamma_headers = {"Authorization": f"Token {gamma_token}"}

    # 3. New judge visits /arena: anti-anchoring verified
    arena_resp = client.get("/arena", headers=gamma_headers)
    assert arena_resp.status_code == 200
    assert "Arena Leaderboard" not in arena_resp.text
    assert "0 matchups evaluated by you" in arena_resp.text

    # 4. New judge hits /api/arena/rankings -> 403
    rank_resp = client.get("/api/arena/rankings", headers=gamma_headers)
    assert rank_resp.status_code == 403

    # 5. New judge attempts to inspect Judge A scores -> 403
    peer_resp = client.get("/api/judge/scores?judge=judge_a", headers=gamma_headers)
    assert peer_resp.status_code == 403

    # 6. New judge queries own scores -> empty list, 200
    own_resp = client.get("/api/judge/scores", headers=gamma_headers)
    assert own_resp.status_code == 200
    assert own_resp.json() == []


# ============================================================================
# Section 2: Unauthenticated Requests & Fallback Prevention
# ============================================================================

def test_adv_unauthenticated_score_submission_matrix():
    """
    Adversarial Probe 2.1: Unauthenticated requests to POST /api/judge/scores
    must return 401 Unauthorized across all malformed header variations
    and NEVER fall back to judge_a or record unauthorized scores in the DB.
    """
    malformed_headers = [
        {},
        {"Authorization": ""},
        {"Authorization": "   "},
        {"Authorization": "Token "},
        {"Authorization": "Bearer "},
        {"Authorization": "Token invalid_token_xyz"},
        {"Authorization": "Bearer invalid_token_xyz"},
        {"Authorization": "Token judgea0000000000000000000000000000000000_fake"},
        {"Authorization": "Token null"},
        {"Authorization": "Token undefined"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
    ]

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM scores")
    initial_score_count = cursor.fetchone()[0]
    conn.close()

    payload = {
        "project_id": "prj_01",
        "criteria": {"functionality": 5, "quality": 5, "innovation": 5, "design": 5},
        "comment": "Adversarial unauthorized injection"
    }

    for h in malformed_headers:
        client.cookies.clear()
        resp = client.post("/api/judge/scores", headers=h, json=payload)
        assert resp.status_code == 401, (
            f"Expected 401 for /api/judge/scores with headers {h}, got {resp.status_code}: {resp.text}"
        )

    # Verify no new row was inserted into SQLite
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM scores")
    final_score_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM scores WHERE comment = 'Adversarial unauthorized injection'")
    injected_count = cursor.fetchone()[0]
    conn.close()

    assert final_score_count == initial_score_count, "Database scores count must not increase on rejected attempts"
    assert injected_count == 0, "No unauthorized score row must be recorded"


def test_adv_unauthenticated_pairwise_vote_matrix():
    """
    Adversarial Probe 2.2: Unauthenticated requests to POST /api/arena/vote
    must return 401 Unauthorized across all malformed header variations
    and NEVER fall back to judge_a or record unauthorized votes in the DB.
    """
    malformed_headers = [
        {},
        {"Authorization": ""},
        {"Authorization": "Token "},
        {"Authorization": "Bearer "},
        {"Authorization": "Token bogus_vote_token"},
        {"Authorization": "Bearer undefined"},
    ]

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pairwise_votes")
    initial_vote_count = cursor.fetchone()[0]
    conn.close()

    payload = {"winner_id": "prj_01", "loser_id": "prj_02"}

    for h in malformed_headers:
        client.cookies.clear()
        resp = client.post("/api/arena/vote", headers=h, json=payload)
        assert resp.status_code == 401, (
            f"Expected 401 for /api/arena/vote with headers {h}, got {resp.status_code}"
        )

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pairwise_votes")
    final_vote_count = cursor.fetchone()[0]
    conn.close()

    assert final_vote_count == initial_vote_count, "No unauthorized vote must be recorded in pairwise_votes"


def test_adv_unauthenticated_rankings_and_scores_read_rejected():
    """
    Adversarial Probe 2.3: Unauthenticated GET /api/arena/rankings and
    GET /api/judge/scores must strictly return 401 Unauthorized.
    """
    client.cookies.clear()

    # /api/arena/rankings
    resp_rankings = client.get("/api/arena/rankings")
    assert resp_rankings.status_code == 401, f"Expected 401, got {resp_rankings.status_code}"

    # /api/judge/scores
    resp_scores = client.get("/api/judge/scores")
    assert resp_scores.status_code == 401, f"Expected 401, got {resp_scores.status_code}"


def test_adv_participant_forbidden_from_judging_and_rankings():
    """
    Adversarial Probe 2.4: Authenticated participant (prt_01) must receive
    HTTP 403 Forbidden across all judge- and organizer-exclusive endpoints.
    """
    part_headers = {"Authorization": f"Token {TEST_TOKENS['participant']}"}

    # Cannot view judge scores
    assert client.get("/api/judge/scores", headers=part_headers).status_code == 403

    # Cannot submit judge scores
    assert client.post(
        "/api/judge/scores",
        headers=part_headers,
        json={"project_id": "prj_01", "criteria": {"functionality": 3}}
    ).status_code == 403

    # Cannot vote in arena
    assert client.post(
        "/api/arena/vote",
        headers=part_headers,
        json={"winner_id": "prj_01", "loser_id": "prj_02"}
    ).status_code == 403

    # Cannot view arena rankings API
    assert client.get("/api/arena/rankings", headers=part_headers).status_code == 403

    # Cannot export results
    assert client.get("/api/export/results.csv", headers=part_headers).status_code == 403


# ============================================================================
# Section 3: Session Cookie Auth & Isolation (Cross-Judge Contamination)
# ============================================================================

def test_adv_session_cookie_strict_attribution_and_isolation():
    """
    Adversarial Probe 3.1: Session cookie authentication ('Cookie: session=<token>')
    without Authorization header must accurately attribute all actions
    strictly to the cookie owner without cross-judge contamination.
    """
    client.cookies.clear()
    token_a = TEST_TOKENS["judge_a"]
    token_b = TEST_TOKENS["judge_b"]

    # 1. Judge A votes via cookie
    resp_vote_a = client.post(
        "/api/arena/vote",
        headers={"Cookie": f"session={token_a}"},
        json={"winner_id": "prj_01", "loser_id": "prj_02"}
    )
    assert resp_vote_a.status_code == 200

    # 2. Judge B votes via cookie
    resp_vote_b = client.post(
        "/api/arena/vote",
        headers={"Cookie": f"session={token_b}"},
        json={"winner_id": "prj_03", "loser_id": "prj_04"}
    )
    assert resp_vote_b.status_code == 200

    # Verify attribution in DB
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT judge_id FROM pairwise_votes WHERE winner_id = 'prj_01' AND loser_id = 'prj_02' ORDER BY id DESC LIMIT 1"
    )
    row_a = cursor.fetchone()
    assert row_a["judge_id"] == "jdg_01", f"Vote should be jdg_01, got {row_a['judge_id']}"

    cursor.execute(
        "SELECT judge_id FROM pairwise_votes WHERE winner_id = 'prj_03' AND loser_id = 'prj_04' ORDER BY id DESC LIMIT 1"
    )
    row_b = cursor.fetchone()
    assert row_b["judge_id"] == "jdg_02", f"Vote should be jdg_02, got {row_b['judge_id']}"

    # 3. Judge A scores via cookie
    resp_score_a = client.post(
        "/api/judge/scores",
        headers={"Cookie": f"session={token_a}"},
        json={"project_id": "prj_01", "criteria": {"functionality": 4}, "comment": "Judge A Cookie Score"}
    )
    assert resp_score_a.status_code == 200

    # 4. Judge B scores via cookie
    resp_score_b = client.post(
        "/api/judge/scores",
        headers={"Cookie": f"session={token_b}"},
        json={"project_id": "prj_03", "criteria": {"functionality": 5}, "comment": "Judge B Cookie Score"}
    )
    assert resp_score_b.status_code == 200

    cursor.execute("SELECT judge_id, comment FROM scores WHERE comment = 'Judge A Cookie Score'")
    s_a = cursor.fetchone()
    assert s_a["judge_id"] == "jdg_01"

    cursor.execute("SELECT judge_id, comment FROM scores WHERE comment = 'Judge B Cookie Score'")
    s_b = cursor.fetchone()
    assert s_b["judge_id"] == "jdg_02"
    conn.close()


def test_adv_cookie_rapid_interleaved_session_switching():
    """
    Adversarial Probe 3.2: Rapid alternating interleaved requests between
    Judge A and Judge B session cookies to stress-test against thread-local,
    global mutable state, or connection pool session leakage.
    """
    client.cookies.clear()
    token_a = TEST_TOKENS["judge_a"]
    token_b = TEST_TOKENS["judge_b"]

    for i in range(10):
        # Even: Judge A
        resp_a = client.get("/api/judge/scores", headers={"Cookie": f"session={token_a}"})
        assert resp_a.status_code == 200
        for item in resp_a.json():
            assert item["judge_id"] == "jdg_01", f"Iteration {i}: Judge A leaked peer score {item['judge_id']}"

        # Odd: Judge B
        resp_b = client.get("/api/judge/scores", headers={"Cookie": f"session={token_b}"})
        assert resp_b.status_code == 200
        for item in resp_b.json():
            assert item["judge_id"] == "jdg_02", f"Iteration {i}: Judge B leaked peer score {item['judge_id']}"


def test_adv_cookie_parsing_precedence_and_malformed_values():
    """
    Adversarial Probe 3.3:
    - Authorization header takes precedence over Cookie.
    - Multiple cookies in string are correctly parsed.
    - Malformed or invalid cookie returns 401 (never falls back to judge_a).
    """
    token_a = TEST_TOKENS["judge_a"]
    token_b = TEST_TOKENS["judge_b"]

    # 1. Header precedence: Header is Judge A, Cookie is Judge B
    resp_prec = client.get(
        "/api/judge/scores",
        headers={
            "Authorization": f"Token {token_a}",
            "Cookie": f"session={token_b}"
        }
    )
    assert resp_prec.status_code == 200
    for s in resp_prec.json():
        assert s["judge_id"] == "jdg_01", "Authorization header must take precedence over Cookie header"

    # 2. Multi-cookie header
    multi_cookie = f"analytics=off; session={token_b}; darkmode=true; tracker=none"
    resp_multi = client.get("/api/judge/scores", headers={"Cookie": multi_cookie})
    assert resp_multi.status_code == 200
    for s in resp_multi.json():
        assert s["judge_id"] == "jdg_02", "Session cookie must be extracted correctly from compound Cookie header"

    # 3. Invalid cookies
    invalid_cookie_headers = [
        "session=",
        "session=invalid_fake_token",
        "other_session=abc",
        "foo=bar; baz=qux",
    ]
    for c_hdr in invalid_cookie_headers:
        client.cookies.clear()
        resp = client.get("/api/judge/scores", headers={"Cookie": c_hdr})
        assert resp.status_code == 401, f"Expected 401 for Cookie '{c_hdr}', got {resp.status_code}"


# ============================================================================
# Section 4: Organizer Access to /war-room and /arena
# ============================================================================

def test_adv_organizer_full_visibility_in_war_room():
    """
    Adversarial Probe 4.1: Organizers accessing /war-room must retain
    unrestricted visibility of:
    - Arena Leaderboard (Bradley-Terry Latent Skill pi_i)
    - Bradley-Terry Skill Rating column
    - ALS normalized scores and shrinkage parameters
    - Judge Leniency Offset Matrix (beta_j)
    """
    org_headers = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}
    resp = client.get("/war-room", headers=org_headers)
    assert resp.status_code == 200
    html = resp.text

    assert "Arena Leaderboard (Bradley-Terry Latent Skill" in html, (
        "Organizer visiting /war-room must see Arena Leaderboard header"
    )
    assert "Bradley-Terry Skill Rating" in html, (
        "Organizer visiting /war-room must see Bradley-Terry Skill Rating table column"
    )
    assert "Judge Leniency Offset Matrix" in html, (
        "Organizer visiting /war-room must see Judge Leniency Offset Matrix"
    )
    assert (
        "Defensible Leaderboard" in html or
        "Shrunk Score" in html or
        "Normalized Quality" in html
    ), "Organizer visiting /war-room must see normalized composite scores"


def test_adv_organizer_full_visibility_in_arena():
    """
    Adversarial Probe 4.2: Organizers accessing /arena must retain
    unrestricted visibility of the real-time Arena Leaderboard, and must
    NOT be presented with the sealed integrity notice shown to judges.
    """
    org_headers = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}
    resp = client.get("/arena", headers=org_headers)
    assert resp.status_code == 200
    html = resp.text

    assert "Arena Leaderboard (Latent Skill" in html, (
        "Organizer visiting /arena must see Arena Leaderboard header"
    )
    assert "Bradley-Terry Skill Rating" in html, (
        "Organizer visiting /arena must see Bradley-Terry Skill Rating column"
    )
    assert "Arena Rank" in html, (
        "Organizer visiting /arena must see Arena Rank column"
    )
    assert "Global rankings and latent skill scores remain sealed" not in html, (
        "Organizer visiting /arena must NOT see sealed rankings notice"
    )


def test_adv_organizer_api_endpoints_full_access():
    """
    Adversarial Probe 4.3: Organizers querying APIs must have full administrative
    access:
    - /api/arena/rankings -> 200 OK with full Bradley-Terry rankings
    - /api/judge/scores (all) -> 200 OK with all judges' evaluations
    - /api/judge/scores?judge=judge_a -> 200 OK filtered to Judge A
    - /api/judge/scores?judge=judge_b -> 200 OK filtered to Judge B
    - /api/export/results.csv -> 200 OK with CSV data
    """
    org_headers = {"Authorization": f"Token {TEST_TOKENS['organizer']}"}

    # 1. /api/arena/rankings
    resp_ranks = client.get("/api/arena/rankings", headers=org_headers)
    assert resp_ranks.status_code == 200
    data = resp_ranks.json()
    assert data.get("model") == "Bradley-Terry MM-MLE"
    assert "rankings" in data
    assert len(data["rankings"]) > 0

    # 2. /api/judge/scores unfiltered (all judges)
    resp_all_scores = client.get("/api/judge/scores", headers=org_headers)
    assert resp_all_scores.status_code == 200
    scores = resp_all_scores.json()
    judge_ids = {s["judge_id"] for s in scores}
    assert "jdg_01" in judge_ids and "jdg_02" in judge_ids, (
        "Organizer must be able to view scores from all judges"
    )

    # 3. Filtered by judge_a
    resp_a = client.get("/api/judge/scores?judge=judge_a", headers=org_headers)
    assert resp_a.status_code == 200
    for s in resp_a.json():
        assert s["judge_id"] == "jdg_01"

    # 4. Filtered by judge_b
    resp_b = client.get("/api/judge/scores?judge=judge_b", headers=org_headers)
    assert resp_b.status_code == 200
    for s in resp_b.json():
        assert s["judge_id"] == "jdg_02"

    # 5. Export results.csv
    resp_csv = client.get("/api/export/results.csv", headers=org_headers)
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers["content-type"]
    assert "rank,project_id,title" in resp_csv.text


# ============================================================================
# Section 5: Static Grep Audit for Residual Fallback Tokens
# ============================================================================

def test_adv_static_grep_sweep_zero_fallback_tokens():
    """
    Adversarial Probe 5.1: Exhaustive static sweep across all HTML templates
    and static JavaScript files to verify that zero hardcoded fallback tokens
    or fallback token assignments exist.
    """
    templates_dir = BASE_DIR / "src" / "templates"
    static_dir = BASE_DIR / "src" / "static"

    target_files = list(templates_dir.glob("*.html")) + list(static_dir.glob("**/*.*"))

    banned_tokens = [
        "judgea0000000000000000000000000000000000",
        "judgeb0000000000000000000000000000000000",
        "organizer0000000000000000000000000000000",
        "participant00000000000000000000000000000",
        "judgea000",
        "judgeb000",
        "organizer000",
        "participant000",
    ]

    for fpath in target_files:
        if not fpath.is_file() or fpath.suffix not in (".html", ".js", ".css"):
            continue
        content = fpath.read_text(encoding="utf-8", errors="ignore")
        rel_path = fpath.relative_to(BASE_DIR)

        for banned in banned_tokens:
            assert banned not in content, (
                f"Residual banned token pattern '{banned}' discovered in client file {rel_path}"
            )

        # Check for fallback pattern: getItem(...) || 'Token ...'
        fallback_pattern = re.search(r"getItem\([^)]+\)\s*\|\|\s*['\"]Token\s", content)
        assert fallback_pattern is None, (
            f"Residual fallback assignment pattern 'getItem(...) || Token' found in {rel_path}"
        )
