# Original User Request

## 2026-09-29T13:41:24Z

Remediate critical judging flaws, evaluation bias, shallow presentation, and workflow bugs across the Veritas hackathon evaluation platform. Ensure strict Tier 1 & Tier 2 compliance, prevent evaluator anchoring, enrich evaluation metadata, and fix scoring queue limitations.

Working directory: /Users/veeralsaxena/Hackthon/Dog food hackathon
Integrity mode: development

## Requirements

### R1. Eliminate Evaluator Anchoring in Pairwise Arena
- Remove the real-time Arena Leaderboard (Latent Skill pi_i) from the `/arena` view for active judges.
- For judges, display an evaluation progress counter (e.g., "X matchups evaluated by you") and an integrity notice that global rankings remain sealed until judging closes.
- Preserve full leaderboard visibility for organizers and admins in `/war-room` and `/arena` (when authenticated as organizer).

### R2. Contextualize Pairwise Evaluation Cards
- Replace the superficial 1-liner cards in `/arena` with comprehensive project evaluation summaries: track badge, team name/ID, repository link, live demo link (if present), and technical summary.
- Replace academic marketing copy with functional evaluation guidance (e.g., "Tie-Breaker & Calibration Arena: Compare projects head-to-head on engineering execution and technical difficulty").
- Add a "Skip Matchup" button so judges can request an alternate pairing if they lack expertise in a specific domain.

### R3. Track-Aware Matchmaking & Filtering
- Add a track filter selector to `/arena` allowing judges to compare projects within their assigned track or a selected category (preventing unfair cross-domain "apples-to-airplanes" comparisons).
- Prioritize intra-track pairings when sampling candidate projects for head-to-head evaluation.

### R4. Fix Evaluation Queue Truncation & State Persistence
- In `/judge` and `judge_portal.html`, remove the hardcoded `projects[:6]` slice limitation so judges can inspect and score all projects assigned to their tracks.
- Pre-populate evaluation cards with the judge's existing scores and comments if the project was previously evaluated.
- Display a clear "✓ Evaluated (Score: X.XX / 5.00)" status badge on already-scored cards, enabling judges to review and update their evaluations seamlessly.

### R5. Remove Fragile Hardcoded Auth Fallbacks
- Eliminate all hardcoded fallback tokens ('Token judgea0000000000000000000000000000000000') in `src/static/js/app.js` and `src/templates/judge_portal.html`.
- Utilize standard session credentials or active `localStorage` tokens without cross-judge impersonation.

## Acceptance Criteria

### Security & Judge Isolation
- [ ] Active judges visiting `/arena` do NOT see peer scores, rankings, or global skill scores.
- [ ] Organizers visiting `/war-room` or `/arena` retain full visibility of Bradley-Terry latent skill rankings.
- [ ] No hardcoded `judge_a` fallback tokens remain in any client scripts or templates.

### Judging Workflow & Usability
- [ ] `/judge` displays all projects assigned to the judge's track without arbitrary truncation to 6.
- [ ] Previously scored projects on `/judge` display the existing score, comment, and pre-selected rubric values.
- [ ] `/arena` displays track badges, tech details, and includes a "Skip Matchup" button.
- [ ] `/arena` allows filtering pairs by track.

### Test & Specification Verification
- [ ] `PYTHONPATH=. .venv/bin/pytest tests/ -v` passes 100% (all existing tests + new regression tests).
- [ ] `python3 spec/run.py .dogfood.toml` passes 100% with claimed T1 and T2 verified.
- [ ] Zero external CDNs or network calls introduced; 100% offline self-contained operation preserved.
