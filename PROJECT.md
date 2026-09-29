# Project: Veritas Hackathon Evaluation Platform Remediation

## Architecture
Veritas is a self-contained, offline-first evaluation platform for hackathons.
- **Backend**: FastAPI / Starlette, SQLite with WAL mode, Ed25519 cryptographic score signing.
- **Core Algorithms**: Bradley-Terry (MM-MLE) for pairwise comparisons, Empirical Bayes / Alternating Least Squares (ALS) for multi-criteria judge score normalization.
- **Frontend**: Server-rendered Jinja2 HTML templates styled with vanilla CSS and progressive vanilla JS (`app.js`).
- **Authentication**: Token-based (`Authorization: Token <token>` or `Authorization: Bearer <token>`) and session cookie (`Cookie: session=<token>`).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | R5.1: Remove Hardcoded Client Tokens | Remove hardcoded `judgea000...` fallback tokens in `app.js` and `judge_portal.html` | M1 | ORIGINAL_REQUEST §R5 |
| 2 | R5.2: Session & Auth Fallback Cleanup | Clean up hardcoded fallback tokens across all templates, use active credentials | M1 | ORIGINAL_REQUEST §R5 |
| 3 | R4.1: Eliminate Queue Truncation | Remove `[:6]` slice limitation in `judge_portal.html` and filter to judge's tracks | M2 | ORIGINAL_REQUEST §R4 |
| 4 | R4.2: Evaluation State Persistence | Pre-populate judge scores, comments, rubric dropdowns, and weighted totals | M2 | ORIGINAL_REQUEST §R4 |
| 5 | R4.3: Evaluated Status Badge | Display "✓ Evaluated (Score: X.XX / 5.00)" on already-scored cards | M2 | ORIGINAL_REQUEST §R4 |
| 6 | R1.1: Arena Leaderboard Role Gating | Hide real-time Bradley-Terry leaderboard from active judges visiting `/arena` | M3 | ORIGINAL_REQUEST §R1 |
| 7 | R1.2: Judge Evaluation Counter & Notice | Display "X matchups evaluated by you" and sealed rankings integrity notice | M3 | ORIGINAL_REQUEST §R1 |
| 8 | R1.3: War Room Arena Visibility | Display full Bradley-Terry leaderboard in `/war-room` for organizers | M3 | ORIGINAL_REQUEST §R1 |
| 9 | R1.4: API Rankings Role Gating | Restrict `/api/arena/rankings` to organizers/admins (HTTP 403 for judges) | M3 | ORIGINAL_REQUEST §R1 |
| 10 | R2.1: Rich Pairwise Evaluation Cards | Include track badge, team name/ID, repo link, live demo link, technical summary | M4 | ORIGINAL_REQUEST §R2 |
| 11 | R2.2: Functional Evaluation Copy | Replace academic marketing copy with functional evaluation guidance | M4 | ORIGINAL_REQUEST §R2 |
| 12 | R2.3: Skip Matchup Action | Add "Skip Matchup" button allowing judges to request an alternate pairing | M4 | ORIGINAL_REQUEST §R2 |
| 13 | R3.1: Intra-Track Prioritization | Matchmaking algorithm prioritizes intra-track pairings over cross-domain pairings | M4 | ORIGINAL_REQUEST §R3 |
| 14 | R3.2: Track Filter Selector | Add track filter dropdown selector in `/arena` and `?track=` parameter support | M4 | ORIGINAL_REQUEST §R3 |
| 15 | Verification: 100% Pytest Pass | Run existing 44 tests + all new regression tests covering R1-R5 | M5 | ORIGINAL_REQUEST §AC |
| 16 | Verification: 100% Spec Pass | Run `python3 spec/run.py .dogfood.toml` verifying claimed T1 & T2 | M5 | ORIGINAL_REQUEST §AC |
| 17 | Verification: Offline & Integrity | Zero external CDNs/remote calls, cryptographic verification, forensic audit | M5 | ORIGINAL_REQUEST §AC |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: Auth & Session Hardening | Eliminate hardcoded auth fallbacks (R5) | none | IN_PROGRESS |
| 2 | M2: Judge Portal Queue & State Persistence | Fix queue truncation, pre-populate scores, show badge (R4) | M1 | PLANNED |
| 3 | M3: Arena De-Anchoring & Leaderboard Isolation | Hide arena leaderboard from judges, add counter/notice, expose in war-room (R1) | M1 | PLANNED |
| 4 | M4: Rich Cards, Skip & Track-Aware Arena | Enrich cards, update copy, add skip button, track filter & matchmaking (R2, R3) | M3 | PLANNED |
| 5 | M5: Final Verification & Test Hardening | 100% pass on pytest, spec runner T1/T2, forensic audit (All AC) | M1, M2, M3, M4 | PLANNED |

## Code Layout
- `src/core/auth.py`: Authentication, token parsing, role dependencies
- `src/core/pairwise.py`: Bradley-Terry solver and matchmaking sampling
- `src/core/normalization.py`: Composite score computation and ALS normalization
- `src/routes/web.py`: HTML view handlers (`/arena`, `/judge`, `/war-room`)
- `src/routes/voting.py`: Pairwise API routes (`/api/arena/pair`, `/api/arena/vote`, `/api/arena/rankings`)
- `src/routes/judging.py`: Criteria score API routes (`/api/judge/scores`)
- `src/templates/arena.html`: Pairwise evaluation template
- `src/templates/judge_portal.html`: Judge scoring portal template
- `src/templates/war_room.html`: Organizer war-room template
- `src/static/js/app.js`: Client-side logic for voting, scoring, skipping
- `tests/`: Pytest test suite (baseline 44 tests + new test files)
- `spec/run.py`: Acceptance specification checker (.dogfood.toml)

## Interface Contracts
### `src.core.pairwise.select_arena_pair(projects, track_filter=None) -> (project_a, project_b)`
- Inputs: `projects` (list of project dicts with `track_id`, `id`, etc.), `track_filter` (optional track ID string).
- Behavior: If `track_filter` is provided, filters projects to that track. If no filter or track has <2 projects, prioritizes selecting pairs from the same track if any track has $\ge 2$ projects; falls back to cross-track if needed.
- Returns: Tuple of two distinct project dictionaries.

### `/api/arena/pair`
- Method: `GET`
- Query Params: `event` (optional), `track` (optional)
- Returns: `{"project_a": {...}, "project_b": {...}}` with enriched fields (`id`, `title`, `summary`, `description`, `repo_url`, `demo_url`, `track_id`, `track_name`, `team_id`, `team_name`).

### `/api/arena/rankings`
- Method: `GET`
- Auth: Required (Organizer or Admin role). Returns 403 Forbidden for judges or unauthenticated users.
- Returns: `{"model": "Bradley-Terry MM-MLE", "comparisons_evaluated": N, "rankings": [...]}`.

### `/judge` and `p["evaluation"]`
- In `judge_portal_view`, projects have an `evaluation` key if scored by `user.id`:
  `{"composite_score": float, "criteria": dict, "comment": str}`.
- If not scored, `p["evaluation"]` is `None`.
