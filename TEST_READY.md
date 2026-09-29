# TEST_READY: Veritas Hackathon Evaluation Platform Test Suite

## Executive Summary
A comprehensive, requirement-driven, opaque-box regression test suite has been authored in `tests/test_arena_and_judging_workflow.py`. The suite rigorously covers Requirements **R1 through R5**, Tier 4 real-world evaluation workflows, and platform offline constraints without modifying any existing baseline tests.

- **Baseline Test Suite Status**: **44 / 44 PASSED** (100% pass rate in `tests/test_*.py`)
- **Official Specification Status**: **Claimed T1 & T2, Verified T1 & T2** (100% pass on `spec/run.py .dogfood.toml`)
- **New Regression Test Suite**: `tests/test_arena_and_judging_workflow.py` (22 total tests)
  - **Syntax & Collection**: 100% valid syntax, zero collection errors.
  - **TDD Red Phase Status**: 5 passed, 17 failing as expected on current un-remediated codebase. Every failure precisely corresponds to one of the identified flaws in R1–R5.

---

## Test Execution Commands

### 1. Run the New Regression Test Suite
```bash
PYTHONPATH=. .venv/bin/pytest tests/test_arena_and_judging_workflow.py -v
```

### 2. Run All Tests (Baseline 44 + New 22 = 66 Total)
```bash
PYTHONPATH=. .venv/bin/pytest tests/ -v
```

### 3. Run the Official Acceptance Specification Checker
```bash
python3 spec/run.py .dogfood.toml
```

---

## Requirement Coverage Matrix

| Req | Test Function Name | Focus & Acceptance Assertion |
| :--- | :--- | :--- |
| **R1** | `test_r1_judge_visiting_arena_cannot_see_leaderboard` | Active judges visiting `/arena` are blocked from viewing Arena Leaderboard, Bradley-Terry skill scores, or ranks. |
| **R1** | `test_r1_judge_sees_progress_counter_and_sealed_integrity_notice` | Active judges see "X matchups evaluated by you" counter and an integrity notice that global rankings remain sealed. |
| **R1** | `test_r1_organizer_retains_full_leaderboard_in_arena` | Organizers visiting `/arena` retain complete visibility of the Bradley-Terry Arena Leaderboard. |
| **R1** | `test_r1_organizer_sees_arena_leaderboard_in_war_room` | Organizers visiting `/war-room` retain complete visibility of Bradley-Terry Arena standings alongside ALS scores. |
| **R1** | `test_r1_api_arena_rankings_role_gating` | `/api/arena/rankings` returns HTTP 403 for judges and participants; HTTP 401/403 for unauthenticated visitors; HTTP 200 for organizers. |
| **R2** | `test_r2_api_arena_pair_returns_enriched_metadata` | `/api/arena/pair` returns `id`, `title`, `summary`, `description`, `repo_url`, `demo_url`, `track_id`, `track_name`, `team_id`, and `team_name`. |
| **R2** | `test_r2_arena_html_renders_rich_evaluation_cards` | `/arena` HTML renders track badges, team names, live demo links, repository inspection links, and technical summaries. |
| **R2** | `test_r2_arena_functional_guidance_and_skip_button` | Academic marketing copy replaced with functional calibration guidance; functional "Skip Matchup" button rendered. |
| **R3** | `test_r3_api_arena_pair_track_filtering` | `/api/arena/pair?track=trk_03` strictly filters candidate pairs to projects belonging to `trk_03`. |
| **R3** | `test_r3_intra_track_matchmaking_priority` | Candidate matchmaking prioritizes intra-track pairings over cross-domain pairings when multi-project tracks exist. |
| **R3** | `test_r3_select_arena_pair_contract` | `src.core.pairwise.select_arena_pair` unit contract handles track filtering, intra-track prioritization, and distinct project pairs. |
| **R3** | `test_r3_arena_track_filter_selector_rendered` | `/arena` HTML renders track filter dropdown selector populated with competition tracks; handles `?track=` navigation. |
| **R4** | `test_r4_judge_queue_no_truncation_all_assigned_projects_shown` | `/judge` displays all projects assigned to judge's tracks (e.g. all 11 projects for Judge B) without `[:6]` slice truncation. |
| **R4** | `test_r4_judge_portal_prepopulates_existing_evaluation_and_badge` | Previously scored project (`prj_07` by `jdg_01`) displays pre-populated comment, rubric selects, score, and "✓ Evaluated (Score: X.XX / 5.00)" badge. |
| **R4** | `test_r4_judge_score_submission_upsert_and_persistence` | Updating an evaluation via `POST /api/judge/scores` updates database record and re-renders updated comment, badge, and score in `/judge`. |
| **R4** | `test_r4_unevaluated_projects_do_not_show_evaluated_badge` | Projects not yet evaluated do not display active "✓ Evaluated" status badge. |
| **R5** | `test_r5_no_hardcoded_tokens_in_client_assets` | Scans `app.js` and all HTML templates to confirm zero occurrences of hardcoded fallback token `'judgea0000000000000000000000000000000000'`. |
| **R5** | `test_r5_unauthenticated_request_rejected_401` | Unauthenticated `POST /api/judge/scores` and `POST /api/arena/vote` return HTTP 401 Unauthorized rather than falling back to Judge A. |
| **R5** | `test_r5_session_cookie_auth_works_seamlessly_without_header` | `Cookie: session=<token>` without `Authorization` header authenticates correctly and attributes votes and scores to the cookie holder without impersonation. |
| **R5** | `test_r5_cookie_session_in_judge_portal_view` | `/judge` accessed via session cookie resolves active judge and displays assigned queue without defaulting to Judge A. |
| **E2E**| `test_e2e_full_judging_and_organizer_isolation_lifecycle` | End-to-end multi-role lifecycle: Judge B queue evaluation, score save, anti-anchored arena vote with track filter, organizer war-room inspection. |
| **Off**| `test_offline_zero_external_network_calls_or_cdns` | Scans all templates and static assets to verify zero external CDN dependencies (100% offline self-contained compliance). |

---

## TDD Baseline Verification Log

```text
=========================== short test summary info ============================
FAILED tests/test_arena_and_judging_workflow.py::test_r1_judge_visiting_arena_cannot_see_leaderboard
FAILED tests/test_arena_and_judging_workflow.py::test_r1_judge_sees_progress_counter_and_sealed_integrity_notice
FAILED tests/test_arena_and_judging_workflow.py::test_r1_organizer_sees_arena_leaderboard_in_war_room
FAILED tests/test_arena_and_judging_workflow.py::test_r1_api_arena_rankings_role_gating
FAILED tests/test_arena_and_judging_workflow.py::test_r2_api_arena_pair_returns_enriched_metadata
FAILED tests/test_arena_and_judging_workflow.py::test_r2_arena_html_renders_rich_evaluation_cards
FAILED tests/test_arena_and_judging_workflow.py::test_r2_arena_functional_guidance_and_skip_button
FAILED tests/test_arena_and_judging_workflow.py::test_r3_api_arena_pair_track_filtering
FAILED tests/test_arena_and_judging_workflow.py::test_r3_intra_track_matchmaking_priority
FAILED tests/test_arena_and_judging_workflow.py::test_r3_select_arena_pair_contract
FAILED tests/test_arena_and_judging_workflow.py::test_r3_arena_track_filter_selector_rendered
FAILED tests/test_arena_and_judging_workflow.py::test_r4_judge_queue_no_truncation_all_assigned_projects_shown
FAILED tests/test_arena_and_judging_workflow.py::test_r4_judge_portal_prepopulates_existing_evaluation_and_badge
FAILED tests/test_arena_and_judging_workflow.py::test_r4_judge_score_submission_upsert_and_persistence
FAILED tests/test_arena_and_judging_workflow.py::test_r4_unevaluated_projects_do_not_show_evaluated_badge
FAILED tests/test_arena_and_judging_workflow.py::test_r5_no_hardcoded_tokens_in_client_assets
FAILED tests/test_arena_and_judging_workflow.py::test_e2e_full_judging_and_organizer_isolation_lifecycle
PASSED tests/test_arena_and_judging_workflow.py::test_r1_organizer_retains_full_leaderboard_in_arena
PASSED tests/test_arena_and_judging_workflow.py::test_r5_unauthenticated_request_rejected_401
PASSED tests/test_arena_and_judging_workflow.py::test_r5_session_cookie_auth_works_seamlessly_without_header
PASSED tests/test_arena_and_judging_workflow.py::test_r5_cookie_session_in_judge_portal_view
PASSED tests/test_offline_zero_external_network_calls_or_cdns
=================== 17 failed, 5 passed, 1 warning in 0.46s ====================
```

All 17 failures accurately isolate the specific flaws to be remediated by the implementers. Once remediation is applied, running `PYTHONPATH=. .venv/bin/pytest tests/ -v` will produce 66 / 66 passing tests (100%).
