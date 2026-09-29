# E2E Test Infra: Veritas Hackathon Evaluation Platform

## Test Philosophy
- Opaque-box, requirement-driven.
- Full verification of R1-R5 across security, judge isolation, workflow, usability, and offline constraints.
- Methodology: Category-Partition + BVA + Pairwise + Acceptance Verification.

## Feature Inventory
| # | Feature | Source | Tier 1 | Tier 2 | Tier 3 |
|---|---------|--------|:------:|:------:|:------:|
| 1 | R5: Auth & Session Token Handling | ORIGINAL_REQUEST §R5 | 5 | 5 | ✓ |
| 2 | R4: Queue Truncation & State Persistence | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ |
| 3 | R1: Arena De-Anchoring & Isolation | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 4 | R2: Pairwise Card Rich Context & Skip | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 5 | R3: Track-Aware Matchmaking & Filtering | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |

## Test Architecture
- Test Runner: `.venv/bin/pytest tests/ -v` and `python3 spec/run.py .dogfood.toml`.
- Regression Test Suite: `tests/test_arena_and_judging_workflow.py`.
- Cryptographic Signature Verifier: `python3 verify.py`.
- Static Code Analysis: Check zero CDN links and zero hardcoded tokens in templates/static JS.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Judge login, full queue evaluation (all assigned projects, >6), inspect pre-populated scores & badges, update evaluation | R4, R5 | High |
| 2 | Active judge visits /arena, verifies no leaderboard visible, checks progress counter & notice, filters by track, skips matchup, casts pairwise vote | R1, R2, R3, R5 | High |
| 3 | Organizer visits /arena and /war-room, verifies complete Bradley-Terry leaderboard and ALS normalized scores | R1, R5 | Medium |
| 4 | Security isolation: Judge attempts to query /api/arena/rankings and receives 403 Forbidden; unauthenticated POST receives 401 Unauthorized | R1, R5 | High |
| 5 | Full offline & cryptographic verification: seed database, run full judging workflow, export verification bundle, verify Ed25519 signature | All | High |
