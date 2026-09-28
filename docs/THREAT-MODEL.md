# THREAT-MODEL.md · Security & Abuse Defense Architecture

This document presents a structured threat analysis for **Veritas**, detailing attack surfaces, adversary models, and mitigations.

---

## 1. Adversary Model & Attack Surfaces

We assume four threat profiles:

1. **Malicious Participant:** Seeks to submit late code, manipulate peer scores, or stuff community vote ballots.
2. **Collusive Judge:** Seeks to artificially inflate ratings for affiliated projects or view peer judge evaluations prior to deliberations.
3. **Sybil Network / Botnet:** Seeks to brigade community voting using automated HTTP clients or rotating IP proxies.
4. **Compromised Host / Dishonest Organizer:** Seeks to alter final rankings after code freeze without detection.

---

## 2. Threat Analysis & Mitigations

### Threat 1: Sybil Voting & Ballot Stuffing (Community Track)
* **Attack:** Adversary scripts thousands of requests to `/api/vote` using unique fake emails or rotating proxy IPs.
* **Mitigations:**
  1. **Token-Bucket Rate Limiting:** Enforces strict burst limits (5 votes max burst, 1 refill per 5 seconds per IP/token) in `src/core/anti_abuse.py`. Exceeding limits returns HTTP 429.
  2. **Unique Balloting Constraint:** The database schema enforces `UNIQUE(project_id, voter_token)`. Duplicate votes for the same project are rejected at the SQLite engine level.
  3. **Randomized Ballot Ordering:** The public voting endpoint `/api/ballot` returns projects in randomized order, eliminating position-bias manipulation.

### Threat 2: Peer-Judge Score Peeking & Collusion
* **Attack:** A corrupt judge attempts to view what other judges have awarded a specific project to tailor their own score.
* **Mitigations:**
  1. **Strict Controller-Level Scoping:** In `src/routes/judging.py`, if a requesting user has the `judge` role and supplies a query parameter targeting another judge (`?judge=judge_a`), the server raises an immediate HTTP 403 Forbidden.
  2. **Audit Logging:** Every attempted peer-access probe triggers an immutable entry in `audit_logs` logging the requesting judge's identity, timestamp, and target.

### Threat 3: Post-Deadline Submission Alterations (Timing Attacks)
* **Attack:** A participant modifies or submits code after the official countdown reaches zero.
* **Mitigations:**
  1. **Server-Enforced UTC Timestamp Check:** The server validates the event's `submissions_close` timestamp stored in the database. Client-side clocks are ignored.
  2. **Hard Database Rejection:** If `now_utc > submissions_close`, the API terminates with HTTP 403 Forbidden before touching the projects table.

### Threat 4: Post-Publication Result Tampering (Organizer Bias)
* **Attack:** An event host privately favors a team and adjusts the rankings or raw numbers before announcing winners.
* **Mitigations:**
  1. **Ed25519 Cryptographic Bundle Signing:** Every published outcome produces a canonical, deterministically sorted JSON object containing all raw scores, judge biases, commit hash, and rankings.
  2. **Public Verification Key:** The deployment public key is published on the portal.
  3. **Zero-Dependency `verify.py`:** Any competitor can download the raw bundle, recompute the least-squares normalization math, and verify the cryptographic signature independently on their local terminal. Any modified score invalidates the cryptographic signature.

---

## 3. Residual Risks & Future Hardening

- **Distributed Denial of Service (DDoS):** For internet-scale public voting, an edge reverse proxy (e.g. Cloudflare / Nginx with fail2ban) should be placed in front of uvicorn.
- **Judge Identity Verification:** Currently relies on bearer tokens. In enterprise deployments, WebAuthn / FIDO2 hardware keys can be bound to judge sessions.
