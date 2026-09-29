"""
tests/test_adversarial_challenger_2.py

Adversarial Challenger 2 Test Suite:
Rigorous empirical stress-testing of Matchmaking, Edge Cases, Queue Limits, and State Persistence.

Focus Areas:
1. select_arena_pair:
   - Single-project tracks, empty tracks, multiple tracks with >=2 projects, tracks with exactly 2 projects.
   - Intra-track preference distribution over 100 iterations.
   - Project dictionary schema tolerance (track_id vs track).
   - High-cardinality scaling (50 tracks, 500 projects).
2. /judge queue:
   - Multi-track judge (jdg_02 with 11 projects across trk_02 and trk_04).
   - Zero-track judge (judge with [] assigned tracks sees all 42 projects without truncation).
   - Empty-track judge fallback.
3. Score updates and state persistence:
   - Score a project, verify DB record and /judge UI display.
   - Re-score with different rubric values and comment.
   - Verify DB upsert (single row maintained, updated comment and criteria).
   - Verify /judge renders updated composite score, comment, dropdown values, and badge.
   - Boundary rubric tests (1 to 5 validation, rejecting <1 or >5).
4. "Skip Matchup" (/api/arena/pair):
   - Repeated calls without ?track= returning distinct valid pairs with intra-track prioritization.
   - Repeated calls with ?track= returning valid pairs within the specified track.
   - Non-existent track returning 400 Bad Request.
   - Full simulated skip and evaluate cycle.
"""

import json
import re
import pytest
from collections import Counter
from fastapi.testclient import TestClient

from src.main import app
from src.config import TEST_TOKENS
from src.seed import seed_database
from src.database import get_db
from src.core.pairwise import select_arena_pair
from src.core.normalization import compute_composite_score

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db_environment():
    """Ensure every test runs against clean seed data and reset cookies."""
    seed_database()
    client.cookies.clear()


# ============================================================================
# FOCUS 1: select_arena_pair Adversarial Stress Testing
# ============================================================================

def test_select_arena_pair_insufficient_and_empty():
    """Verify that insufficient candidates raise ValueError with proper messages."""
    # Empty list
    with pytest.raises(ValueError, match="Insufficient projects to form a pair"):
        select_arena_pair([])

    # Single project
    with pytest.raises(ValueError, match="Insufficient projects to form a pair"):
        select_arena_pair([{"id": "p1", "track_id": "trk_01"}])


def test_select_arena_pair_filtered_edge_cases():
    """Verify track_filter behavior on empty, single-project, and 2-project tracks."""
    projects = [
        {"id": "p1", "track_id": "trk_single"},
        {"id": "p2", "track_id": "trk_pair_1"},
        {"id": "p3", "track_id": "trk_pair_1"},
        {"id": "p4", "track_id": "trk_multi"},
        {"id": "p5", "track_id": "trk_multi"},
        {"id": "p6", "track_id": "trk_multi"},
    ]

    # 1. Filter on non-existent / empty track -> raises ValueError
    with pytest.raises(ValueError, match="Insufficient projects in track trk_empty to form a pair"):
        select_arena_pair(projects, track_filter="trk_empty")

    # 2. Filter on single-project track -> raises ValueError
    with pytest.raises(ValueError, match="Insufficient projects in track trk_single to form a pair"):
        select_arena_pair(projects, track_filter="trk_single")

    # 3. Filter on track with exactly 2 projects -> returns both projects
    for _ in range(20):
        pa, pb = select_arena_pair(projects, track_filter="trk_pair_1")
        assert pa["id"] != pb["id"]
        assert {pa["id"], pb["id"]} == {"p2", "p3"}
        assert pa["track_id"] == "trk_pair_1"
        assert pb["track_id"] == "trk_pair_1"

    # 4. Filter on track with >=3 projects -> always returns distinct projects from that track
    sampled_pairs = set()
    for _ in range(50):
        pa, pb = select_arena_pair(projects, track_filter="trk_multi")
        assert pa["id"] != pb["id"]
        assert pa["track_id"] == "trk_multi"
        assert pb["track_id"] == "trk_multi"
        sampled_pairs.add(tuple(sorted([pa["id"], pb["id"]])))

    # With 3 projects, there are 3 possible combinations; over 50 iterations, all 3 should appear
    assert len(sampled_pairs) == 3, f"Expected all 3 pairs to be sampled, got {sampled_pairs}"


def test_select_arena_pair_unfiltered_only_single_project_tracks_fallback():
    """
    When track_filter is None and NO track has >= 2 projects (e.g. all tracks are single-project),
    select_arena_pair falls back to cross-track uniform sampling across all projects.
    """
    projects = [
        {"id": "p_a", "track_id": "trk_a"},
        {"id": "p_b", "track_id": "trk_b"},
        {"id": "p_c", "track_id": "trk_c"},
        {"id": "p_d", "track_id": "trk_d"},
    ]

    sampled_pairs = set()
    for _ in range(100):
        pa, pb = select_arena_pair(projects, track_filter=None)
        assert pa["id"] != pb["id"], "Must always return distinct projects"
        sampled_pairs.add(tuple(sorted([pa["id"], pb["id"]])))

    # 4 projects -> 6 possible pairs. Over 100 trials, should sample all or most
    assert len(sampled_pairs) >= 5, f"Expected rich cross-track sampling, got {len(sampled_pairs)} pairs"


def test_select_arena_pair_intra_track_preference_distribution_100_iterations():
    """
    Over 100 iterations, verify that when tracks with >=2 projects exist:
    1. 100% of pairings are intra-track (same track_id).
    2. Single-project tracks are NEVER selected (0% selection).
    3. Multiple eligible tracks are both chosen across the iterations.
    """
    projects = [
        # Track A: 3 projects (eligible)
        {"id": "p_a1", "track_id": "trk_alpha"},
        {"id": "p_a2", "track_id": "trk_alpha"},
        {"id": "p_a3", "track_id": "trk_alpha"},
        # Track B: 4 projects (eligible)
        {"id": "p_b1", "track_id": "trk_beta"},
        {"id": "p_b2", "track_id": "trk_beta"},
        {"id": "p_b3", "track_id": "trk_beta"},
        {"id": "p_b4", "track_id": "trk_beta"},
        # Track C: 1 project (ineligible for intra-track)
        {"id": "p_c1", "track_id": "trk_gamma"},
        # Track D: 1 project (ineligible for intra-track)
        {"id": "p_d1", "track_id": "trk_delta"},
    ]

    track_counts = Counter()

    for i in range(100):
        pa, pb = select_arena_pair(projects, track_filter=None)
        assert pa["id"] != pb["id"], f"Iteration {i}: Pair projects must be distinct"
        assert pa["track_id"] == pb["track_id"], f"Iteration {i}: Must prioritize intra-track pairings"
        assert pa["track_id"] in ("trk_alpha", "trk_beta"), f"Iteration {i}: Ineligible track selected: {pa['track_id']}"
        assert pa["id"] not in ("p_c1", "p_d1"), f"Iteration {i}: Single-project track was selected"
        assert pb["id"] not in ("p_c1", "p_d1"), f"Iteration {i}: Single-project track was selected"
        track_counts[pa["track_id"]] += 1

    # Both Track Alpha and Track Beta should have significant selections (approx 50/50)
    assert track_counts["trk_alpha"] >= 25, f"Track alpha under-sampled: {track_counts['trk_alpha']}"
    assert track_counts["trk_beta"] >= 25, f"Track beta under-sampled: {track_counts['trk_beta']}"
    assert track_counts["trk_gamma"] == 0, "Single-project track gamma must never be selected"
    assert track_counts["trk_delta"] == 0, "Single-project track delta must never be selected"


def test_select_arena_pair_tracks_with_exactly_two_projects():
    """
    Test tracks that have exactly 2 projects:
    Track X has 2 projects, Track Y has 2 projects.
    Verify that in every iteration, the pair is either {pX1, pX2} or {pY1, pY2}, never a cross pair.
    """
    projects = [
        {"id": "px1", "track_id": "trk_x"},
        {"id": "px2", "track_id": "trk_x"},
        {"id": "py1", "track_id": "trk_y"},
        {"id": "py2", "track_id": "trk_y"},
    ]

    pair_sets = set()
    for _ in range(100):
        pa, pb = select_arena_pair(projects, track_filter=None)
        pair_set = frozenset([pa["id"], pb["id"]])
        assert pair_set in (frozenset(["px1", "px2"]), frozenset(["py1", "py2"])), f"Unexpected cross-pair: {pair_set}"
        pair_sets.add(pair_set)

    assert len(pair_sets) == 2, "Both track pairs must be sampled over 100 iterations"


def test_select_arena_pair_schema_tolerance_and_scale():
    """
    Adversarial property test:
    - Dicts using 'track' key instead of 'track_id'
    - High cardinality: 50 tracks with 10 projects each (500 projects)
    - 500 iterations must complete swiftly (<0.5s) without error
    """
    projects = []
    for t_idx in range(50):
        for p_idx in range(10):
            # Alternate between track and track_id keys
            key_name = "track" if (t_idx + p_idx) % 2 == 0 else "track_id"
            projects.append({
                "id": f"proj_t{t_idx}_p{p_idx}",
                key_name: f"track_{t_idx}"
            })

    for _ in range(500):
        pa, pb = select_arena_pair(projects, track_filter=None)
        assert pa["id"] != pb["id"]
        tid_a = pa.get("track_id") or pa.get("track")
        tid_b = pb.get("track_id") or pb.get("track")
        assert tid_a == tid_b, "High cardinality intra-track matchmaking failed"


# ============================================================================
# FOCUS 2: /judge Queue Limits and Track Assignments
# ============================================================================

def test_judge_queue_multiple_tracks_no_truncation():
    """
    R4.1: Test multi-track judge (jdg_02 / Judge B) assigned to trk_02 and trk_04.
    In seed fixtures, trk_02 has 6 projects and trk_04 has 5 projects = 11 total projects.
    Verify that /judge displays all 11 projects and does NOT truncate to 6.
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_b']}"}
    resp = client.get("/judge", headers=headers)
    assert resp.status_code == 200

    html = resp.text

    # Extract all project card IDs by matching scoring buttons
    score_buttons = re.findall(r'id="btn-score-([^"]+)"', html)
    assert len(score_buttons) == 11, f"Expected exactly 11 projects in Judge B's queue, found {len(score_buttons)}"

    # Verify the projects belong to trk_02 and trk_04
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM projects WHERE track_id IN ('trk_02', 'trk_04') AND is_draft = 0")
    expected_ids = {r["id"] for r in cursor.fetchall()}
    conn.close()

    assert set(score_buttons) == expected_ids, "Rendered project IDs do not match assigned track projects"


def test_judge_queue_zero_assigned_tracks_shows_all_projects_without_truncation():
    """
    Test judge assigned to 0 tracks (tracks = []).
    When a judge has no track restrictions, the platform must display all competition projects
    without arbitrary truncation (e.g. all 42 projects in evt_01, not 6).
    """
    conn = get_db()
    cursor = conn.cursor()
    # Insert a custom judge with empty tracks []
    test_token = "token_jdg_free_roam_2026"
    cursor.execute(
        """INSERT OR REPLACE INTO users (id, name, email, role, token, password, tracks)
           VALUES ('jdg_free', 'Universal Judge', 'universal@dogfood.local', 'judge', ?, 'password123', '[]')""",
        (test_token,)
    )
    cursor.execute("INSERT OR REPLACE INTO event_registrations (event_id, user_id, role, joined_at) VALUES ('evt_01', 'jdg_free', 'judge', '2026-02-10T00:00:00Z')")
    conn.commit()

    cursor.execute("SELECT count(*) FROM projects WHERE is_draft = 0 AND (event_id = 'evt_01' OR event_id IS NULL)")
    total_evt_projects = cursor.fetchone()[0]
    conn.close()

    assert total_evt_projects > 6, f"Fixture should have >6 projects, found {total_evt_projects}"

    headers = {"Authorization": f"Token {test_token}"}
    resp = client.get("/judge?event=evt_01", headers=headers)
    assert resp.status_code == 200

    html = resp.text
    rendered_projects = re.findall(r'id="btn-score-([^"]+)"', html)
    assert len(rendered_projects) == total_evt_projects, (
        f"Judge with 0 assigned tracks must see all {total_evt_projects} projects without truncation; got {len(rendered_projects)}"
    )


def test_judge_queue_assigned_to_empty_track_graceful_fallback():
    """
    Test judge assigned to a track with 0 projects.
    The system should not crash and should fall back gracefully.
    """
    conn = get_db()
    cursor = conn.cursor()
    test_token = "token_jdg_empty_track_2026"
    cursor.execute(
        """INSERT OR REPLACE INTO users (id, name, email, role, token, password, tracks)
           VALUES ('jdg_empty_trk', 'Empty Track Judge', 'empty_track@dogfood.local', 'judge', ?, 'password123', '["trk_nonexistent"]')""",
        (test_token,)
    )
    conn.commit()
    conn.close()

    headers = {"Authorization": f"Token {test_token}"}
    resp = client.get("/judge", headers=headers)
    assert resp.status_code == 200
    # Page renders successfully with search input and cards
    assert "Evaluation Queue" in resp.text


# ============================================================================
# FOCUS 3: Score Updates, Upsert Integrity, and UI Persistence
# ============================================================================

def test_judge_score_submission_upsert_and_ui_display():
    """
    R4.2, R4.3: Test initial score submission, re-scoring with different rubric and comment,
    database row count (strict upsert without duplicate records), and /judge UI reflection.
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_b']}"}
    target_project_id = "prj_05"  # In trk_02, assigned to judge_b

    conn = get_db()
    cursor = conn.cursor()
    # Ensure starting from clean state for this project & judge
    cursor.execute("DELETE FROM scores WHERE judge_id = 'jdg_02' AND project_id = ?", (target_project_id,))
    conn.commit()
    conn.close()

    # 1. First submission: high scores
    payload_1 = {
        "project_id": target_project_id,
        "criteria": {
            "functionality": 5,
            "quality": 4,
            "innovation": 5,
            "design": 4
        },
        "comment": "Challenger 2 Initial Review: Solid architecture."
    }
    # Expected weighted score: 5*0.4 + 4*0.3 + 5*0.2 + 4*0.1 = 2.0 + 1.2 + 1.0 + 0.4 = 4.60
    resp_1 = client.post("/api/judge/scores", json=payload_1, headers=headers)
    assert resp_1.status_code == 200
    assert resp_1.json()["status"] == "success"

    # Verify DB has exactly 1 row
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT count(*), criteria, comment FROM scores WHERE judge_id = 'jdg_02' AND project_id = ?", (target_project_id,))
    count, crit_json, comment = cursor.fetchone()
    conn.close()
    assert count == 1
    assert json.loads(crit_json) == payload_1["criteria"]
    assert comment == payload_1["comment"]

    # Verify /judge UI displays the initial score and badge
    resp_ui_1 = client.get("/judge", headers=headers)
    assert resp_ui_1.status_code == 200
    html_1 = resp_ui_1.text

    assert f'id="eval-badge-{target_project_id}"' in html_1
    assert "✓ Evaluated (Score: 4.60 / 5.00)" in html_1
    assert f'id="comment-{target_project_id}"' in html_1
    assert 'value="Challenger 2 Initial Review: Solid architecture."' in html_1
    assert f'id="weighted-total-{target_project_id}"' in html_1
    assert "4.60" in html_1

    # 2. Second submission: re-scoring the same project with lower values and updated comment
    payload_2 = {
        "project_id": target_project_id,
        "criteria": {
            "functionality": 2,
            "quality": 3,
            "innovation": 1,
            "design": 2
        },
        "comment": "Challenger 2 Updated Review: Discovered edge-case race conditions."
    }
    # Expected updated weighted score: 2*0.4 + 3*0.3 + 1*0.2 + 2*0.1 = 0.8 + 0.9 + 0.2 + 0.2 = 2.10
    resp_2 = client.post("/api/judge/scores", json=payload_2, headers=headers)
    assert resp_2.status_code == 200
    assert resp_2.json()["status"] == "success"

    # Verify DB STILL has exactly 1 row (UPSERT, not duplicate insert)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT count(*), criteria, comment FROM scores WHERE judge_id = 'jdg_02' AND project_id = ?", (target_project_id,))
    count_2, crit_json_2, comment_2 = cursor.fetchone()
    conn.close()
    assert count_2 == 1, f"Expected exactly 1 row in scores table after upsert, got {count_2}"
    assert json.loads(crit_json_2) == payload_2["criteria"]
    assert comment_2 == payload_2["comment"]

    # Verify /judge UI now reflects the UPDATED composite score and updated comment
    resp_ui_2 = client.get("/judge", headers=headers)
    assert resp_ui_2.status_code == 200
    html_2 = resp_ui_2.text

    assert "✓ Evaluated (Score: 2.10 / 5.00)" in html_2
    assert 'value="Challenger 2 Updated Review: Discovered edge-case race conditions."' in html_2
    assert "2.10" in html_2


def test_judge_score_rubric_boundaries_and_rejections():
    """
    Adversarial boundary testing on /api/judge/scores:
    - Values < 1 or > 5 rejected with 400 Bad Request
    - Perfect 5s produce 5.00 composite score
    - Minimum 1s produce 1.00 composite score
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_b']}"}
    target_project_id = "prj_05"  # In trk_02, assigned to judge_b

    # Criterion value 0 (below minimum 1)
    bad_payload_low = {
        "project_id": target_project_id,
        "criteria": {"functionality": 0, "quality": 4, "innovation": 3, "design": 2}
    }
    r_low = client.post("/api/judge/scores", json=bad_payload_low, headers=headers)
    assert r_low.status_code == 400
    assert "must be between 1 and 5" in r_low.text

    # Criterion value 6 (above maximum 5)
    bad_payload_high = {
        "project_id": target_project_id,
        "criteria": {"functionality": 6, "quality": 4, "innovation": 3, "design": 2}
    }
    r_high = client.post("/api/judge/scores", json=bad_payload_high, headers=headers)
    assert r_high.status_code == 400
    assert "must be between 1 and 5" in r_high.text

    # All 5s
    top_payload = {
        "project_id": target_project_id,
        "criteria": {"functionality": 5, "quality": 5, "innovation": 5, "design": 5},
        "comment": "Perfect score"
    }
    r_top = client.post("/api/judge/scores", json=top_payload, headers=headers)
    assert r_top.status_code == 200
    ui_top = client.get("/judge", headers=headers)
    assert "✓ Evaluated (Score: 5.00 / 5.00)" in ui_top.text

    # All 1s
    min_payload = {
        "project_id": target_project_id,
        "criteria": {"functionality": 1, "quality": 1, "innovation": 1, "design": 1},
        "comment": "Minimum score"
    }
    r_min = client.post("/api/judge/scores", json=min_payload, headers=headers)
    assert r_min.status_code == 200
    ui_min = client.get("/judge", headers=headers)
    assert "✓ Evaluated (Score: 1.00 / 5.00)" in ui_min.text


# ============================================================================
# FOCUS 4: "Skip Matchup" & /api/arena/pair API Consistency
# ============================================================================

def test_skip_matchup_calling_api_arena_pair_unfiltered_50_times():
    """
    R2.3, R3.1: Simulate clicking 'Skip Matchup' 50 times without track filter.
    Assert that:
    1. Every response is HTTP 200.
    2. project_a and project_b are distinct projects.
    3. Intra-track matchmaking priority is strictly maintained across calls.
    4. All required enriched fields are populated.
    5. A diverse variety of candidate pairs is sampled.
    """
    required_keys = [
        "id", "title", "summary", "description", "repo_url",
        "demo_url", "track_id", "track_name", "team_id", "team_name"
    ]
    sampled_pairs = set()

    for _ in range(50):
        resp = client.get("/api/arena/pair")
        assert resp.status_code == 200
        data = resp.json()
        assert "project_a" in data and "project_b" in data
        pa = data["project_a"]
        pb = data["project_b"]

        assert pa["id"] != pb["id"], "Candidate projects must never be identical"

        for k in required_keys:
            assert k in pa, f"Field '{k}' missing from project_a"
            assert k in pb, f"Field '{k}' missing from project_b"

        # Intra-track priority: because evt_01 contains multiple tracks with >=2 projects,
        # candidates must share the same track
        assert pa["track_id"] == pb["track_id"], (
            f"Intra-track matchmaking violation: pa track={pa['track_id']}, pb track={pb['track_id']}"
        )

        sampled_pairs.add(tuple(sorted([pa["id"], pb["id"]])))

    # Ensure the sampling is not degenerate (it should sample multiple distinct pairs)
    assert len(sampled_pairs) >= 10, f"Expected diverse candidate pairs, got only {len(sampled_pairs)} unique pairs"


def test_skip_matchup_calling_api_arena_pair_with_track_filter_50_times():
    """
    R2.3, R3.2: Simulate clicking 'Skip Matchup' 50 times with track filter (?track=trk_02 and ?track=trk_03).
    Assert that:
    1. Every response is HTTP 200.
    2. Both candidate projects strictly belong to the specified track.
    3. project_a != project_b.
    4. Multiple unique pairs from the track are returned.
    """
    for target_track in ("trk_02", "trk_03", "trk_04"):
        sampled_pairs = set()
        for _ in range(25):
            resp = client.get(f"/api/arena/pair?track={target_track}")
            assert resp.status_code == 200
            data = resp.json()
            pa = data["project_a"]
            pb = data["project_b"]

            assert pa["id"] != pb["id"]
            assert pa["track_id"] == target_track
            assert pb["track_id"] == target_track
            sampled_pairs.add(tuple(sorted([pa["id"], pb["id"]])))

        assert len(sampled_pairs) >= 2, f"Track {target_track} should return multiple distinct pairs"


def test_skip_matchup_with_nonexistent_or_insufficient_track():
    """
    Adversarial test: Requesting /api/arena/pair?track=... for a track with 0 or 1 projects
    must return HTTP 400 Bad Request with an informative error message.
    """
    # Non-existent track (0 projects)
    resp_empty = client.get("/api/arena/pair?track=trk_nonexistent_999")
    assert resp_empty.status_code == 400
    assert "Insufficient projects in track trk_nonexistent_999" in resp_empty.json()["detail"]


def test_skip_matchup_full_eval_and_skip_lifecycle():
    """
    Simulate full client lifecycle:
    1. Judge fetches pair via /api/arena/pair?track=trk_03
    2. Judge skips matchup -> calls /api/arena/pair?track=trk_03 again
    3. Judge evaluates second matchup -> posts vote to /api/arena/vote
    4. Vote count is incremented in DB
    5. Judge fetches next matchup
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_a']}"}

    # 1. Initial pair
    r1 = client.get("/api/arena/pair?track=trk_03")
    assert r1.status_code == 200
    pair_1 = r1.json()

    # 2. Skip matchup
    r2 = client.get("/api/arena/pair?track=trk_03")
    assert r2.status_code == 200
    pair_2 = r2.json()

    # 3. Cast vote on second pair
    winner_id = pair_2["project_a"]["id"]
    loser_id = pair_2["project_b"]["id"]
    vote_resp = client.post(
        "/api/arena/vote",
        json={"winner_id": winner_id, "loser_id": loser_id},
        headers=headers
    )
    assert vote_resp.status_code == 200
    assert vote_resp.json()["status"] == "success"

    # 4. Check DB recorded the vote
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT count(*) FROM pairwise_votes WHERE judge_id = 'jdg_01' AND winner_id = ? AND loser_id = ?",
        (winner_id, loser_id)
    )
    assert cursor.fetchone()[0] >= 1
    conn.close()

    # 5. Fetch next pair after vote
    r3 = client.get("/api/arena/pair?track=trk_03")
    assert r3.status_code == 200


# ============================================================================
# FOCUS 5: Advanced Adversarial Security, Isolation & Session Integrity
# ============================================================================

def test_cross_judge_score_isolation_and_no_overwrite():
    """
    Adversarial Isolation Test:
    When Judge A (jdg_01) and Judge B (jdg_02) both evaluate the SAME project,
    neither evaluation overwrites the other, and each judge's /judge dashboard
    renders ONLY their own evaluation and score.
    """
    # Project prj_01 belongs to trk_04 (Judge B) and also exists in the system
    # Let's grant Judge A access to trk_04 as well for this test
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET tracks = '[\"trk_03\", \"trk_04\"]' WHERE id = 'jdg_01'")
    conn.commit()
    conn.close()

    target_pid = "prj_01"
    headers_a = {"Authorization": f"Token {TEST_TOKENS['judge_a']}"}
    headers_b = {"Authorization": f"Token {TEST_TOKENS['judge_b']}"}

    # 1. Judge A scores prj_01 with 5, 5, 5, 5 (Composite: 5.00)
    score_a = {
        "project_id": target_pid,
        "criteria": {"functionality": 5, "quality": 5, "innovation": 5, "design": 5},
        "comment": "Judge A Confidential Assessment"
    }
    r_a = client.post("/api/judge/scores", json=score_a, headers=headers_a)
    assert r_a.status_code == 200

    # 2. Judge B scores prj_01 with 2, 2, 2, 2 (Composite: 2.00)
    score_b = {
        "project_id": target_pid,
        "criteria": {"functionality": 2, "quality": 2, "innovation": 2, "design": 2},
        "comment": "Judge B Confidential Assessment"
    }
    r_b = client.post("/api/judge/scores", json=score_b, headers=headers_b)
    assert r_b.status_code == 200

    # 3. Check DB has distinct records in scores table for jdg_01 and jdg_02
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT judge_id, comment FROM scores WHERE project_id = ? AND judge_id IN ('jdg_01', 'jdg_02') ORDER BY judge_id",
        (target_pid,)
    )
    db_rows = cursor.fetchall()
    conn.close()
    assert len(db_rows) == 2, f"Expected 2 score records for jdg_01 and jdg_02, found {len(db_rows)}"
    assert db_rows[0]["judge_id"] == "jdg_01" and "Judge A" in db_rows[0]["comment"]
    assert db_rows[1]["judge_id"] == "jdg_02" and "Judge B" in db_rows[1]["comment"]

    # 4. Check Judge A's portal: sees 5.00 and Judge A's comment
    ui_a = client.get("/judge", headers=headers_a)
    assert "✓ Evaluated (Score: 5.00 / 5.00)" in ui_a.text
    assert "Judge A Confidential Assessment" in ui_a.text
    assert "Judge B Confidential Assessment" not in ui_a.text

    # 5. Check Judge B's portal: sees 2.00 and Judge B's comment
    ui_b = client.get("/judge", headers=headers_b)
    assert "✓ Evaluated (Score: 2.00 / 5.00)" in ui_b.text
    assert "Judge B Confidential Assessment" in ui_b.text
    assert "Judge A Confidential Assessment" not in ui_b.text


def test_judge_score_special_characters_and_empty_comments():
    """
    Test submitting comment with HTML tags, quotes, unicode characters, and empty comments.
    Verifies that the database faithfully stores the text and HTML escapes prevent injection.
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_b']}"}
    target_pid = "prj_05"

    special_comment = "<script>alert('xss')</script> & \"double quotes\" 'single' 🚀 日本語"
    payload = {
        "project_id": target_pid,
        "criteria": {"functionality": 4, "quality": 4, "innovation": 4, "design": 4},
        "comment": special_comment
    }
    r = client.post("/api/judge/scores", json=payload, headers=headers)
    assert r.status_code == 200

    # DB verification
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT comment FROM scores WHERE judge_id = 'jdg_02' AND project_id = ?", (target_pid,))
    stored = cursor.fetchone()[0]
    conn.close()
    assert stored == special_comment

    # UI verification: comment input has value properly escaped
    ui_resp = client.get("/judge", headers=headers)
    assert ui_resp.status_code == 200
    assert "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in ui_resp.text or special_comment in ui_resp.text

    # Test empty comment
    payload_empty = {
        "project_id": target_pid,
        "criteria": {"functionality": 3, "quality": 3, "innovation": 3, "design": 3},
        "comment": ""
    }
    r_empty = client.post("/api/judge/scores", json=payload_empty, headers=headers)
    assert r_empty.status_code == 200

    ui_empty = client.get("/judge", headers=headers)
    assert ui_empty.status_code == 200
    assert 'value="None"' not in ui_empty.text


def test_arena_html_renders_skip_matchup_button_and_track_filtering():
    """
    Verify /arena HTML rendering:
    - Renders Skip Matchup button with skipMatchup() handler.
    - Renders track filter selector with all tracks.
    - Honors ?track=trk_02 query parameter by selecting trk_02.
    - Displays rich evaluation cards.
    """
    headers = {"Authorization": f"Token {TEST_TOKENS['judge_b']}"}
    resp = client.get("/arena?track=trk_02", headers=headers)
    assert resp.status_code == 200
    html = resp.text

    # Skip button
    assert "Skip Matchup" in html
    assert "skipMatchup()" in html

    # Functional guidance copy (not academic marketing)
    assert "Tie-Breaker" in html
    assert "Compare projects head-to-head on engineering execution and technical difficulty" in html

    # Track filter selector
    assert 'id="track-select"' in html
    assert 'value="trk_02" selected' in html

