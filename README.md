# Veritas · Hackathon Raptors Dogfood Platform

> An open-source, air-gapped, cryptographically verifiable hackathon submission & judging platform designed to evaluate engineering hackathons without trusting the host.

Built for the **DOGFOOD 2026** Hackathon organized by [Hackathon Raptors](https://raptors.dev).

---

## ⚡ Quickstart (One Command, 100% Offline)

As mandated by the competition brief (*"If it does not come up on a laptop with the network off, we cannot adopt it"*), Veritas has zero cloud dependencies, no external font/CDN downloads, and boots in one command:

```bash
docker compose up
```

Or run locally with Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 src/seed.py
uvicorn src.main:app --host 0.0.0.0 --port 8080
```

Once running:
- **Executive Role Switcher:** Pinned at top of all pages (`Visitor`, `Participant`, `Judge A`, `Judge B`, `Organizer`)
- **Public Showcase:** [http://localhost:8080/projects](http://localhost:8080/projects)
- **Participant Submission Console:** [http://localhost:8080/submit](http://localhost:8080/submit)
- **Community Ballot & People's Choice:** [http://localhost:8080/vote](http://localhost:8080/vote)
- **Live War Room & Coverage Matrix:** [http://localhost:8080/war-room](http://localhost:8080/war-room)
- **Pairwise Arena:** [http://localhost:8080/arena](http://localhost:8080/arena)
- **Judge Portal:** [http://localhost:8080/judge](http://localhost:8080/judge)
- **Event Configuration & Audit Logs:** [http://localhost:8080/settings](http://localhost:8080/settings)
- **Cryptographic Audit Console:** [http://localhost:8080/audit](http://localhost:8080/audit)
- **Verifiable SVG Certificates:** [http://localhost:8080/certificates/prj_01](http://localhost:8080/certificates/prj_01)
- **OpenAPI 3.1 Specs:** [http://localhost:8080/docs](http://localhost:8080/docs)

---

## 🏆 Acceptance Suite & Extended Tier 1–4 Verification

Veritas satisfies **100%** of the competition specification across Tiers 1, 2, 3, and 4:

```bash
# 1. Official Dogfood Acceptance Checker (T1 & T2 programmatic assertions)
python3 spec/run.py .dogfood.toml

# 2. Complete Automated Test Suite (105 tests across Tiers 1-4)
PYTHONPATH=. .venv/bin/pytest tests/ -v

# 3. Pure-Python Standalone Verifier (Recomputes math and verifies Ed25519 signature)
curl -s http://localhost:8080/api/export/verification-bundle | python3 verify.py
```

The verified receipt is committed at [`acceptance-report.txt`](acceptance-report.txt).

---

## 📊 FIG. 01 — Event Pipeline (All 10 Stages Implemented)

Veritas directly implements the complete 10-stage lifecycle defined in the competition brief:

```
[01 REGISTRATION] ──> [02 TEAMS] ──> [03 SUBMISSIONS] ──> [04 ELIGIBILITY] ──> [05 ASSIGNMENT]
        │
        └───> [06 SCORING] ──> [07 NORMALIZATION ★] ──> [08 RESULTS] ──> [09 CERTIFICATES] ──> [10 ARCHIVE]
```

| Stage | Name | Status | Platform Implementation |
| :---: | :--- | :---: | :--- |
| **01** | **Registration** | ✅ Complete | Onboarding via magic links (`/onboard/{token}`) and self-service signup (`/signup`). 5-role scoping (`visitor`, `participant`, `judge`, `organizer`, `admin`). |
| **02** | **Teams** | ✅ Complete | Invite code team formation (`/team/join/{invite_code}`). Dynamic membership roster, leave team, 1-click onboarding for new participants. |
| **03** | **Submissions** | ✅ Complete | Draft-and-edit until freeze (`/submit`). Full schema: title, tagline, long description, repo URL, demo URL, tracks, tech tags. |
| **04** | **Eligibility** | ✅ Complete | Hard server-side UTC deadline enforcement (terminates late POST/PUT with `HTTP 403 Forbidden`). Duplicate submission canonicalization `(team, repo_url)`. |
| **05** | **Assignment** | ✅ Complete | Batched & track-based judge assignments. Strict backend role isolation: no judge can query peer scores or peer ballots via API or UI. |
| **06** | **Scoring** | ✅ Complete | Weighted, organizer-configurable rubric with **arbitrary topics (add/remove/edit)**. Private comments. Pairwise head-to-head Arena mode (`/arena`). |
| **07** | **Normalization** | 🛡️ **DEFENDED** | **Official Failure Surface Solved.** Two-Way Fixed Effects with Empirical Bayes shrinkage ($Y_{ij} = \mu + \alpha_i + \beta_j + \epsilon_{ij}$). Recomputable in `verify.py`. |
| **08** | **Results** | ✅ Complete | War Room (`/war-room`) live progress dashboard. Sealed community results during voting window until organizer publication. |
| **09** | **Certificates** | ✅ Complete | Dynamic SVG certificate generation (`/certificates/{project_id}`) with pure-vector offline QR code verification (`src/core/qrcode.py`). |
| **10** | **Archive** | ✅ Complete | Deterministic Ed25519-signed verification snapshot bundle (`/api/export/verification-bundle`), CSV export at every stage, and full bulk JSON import/export. |

---

## 🎯 Formal Bonus Challenges (All 4 Solved)

The hackathon specification lists four formal bonus challenges for breaking ties and competing for the *Best Judging Engine* prize:

| Bonus Challenge | Difficulty | Points | Implementation in Veritas |
| :--- | :---: | :---: | :--- |
| **1. Normalization Proof** | **Hard** | **+5** | Two-Way Fixed Effects with Empirical Bayes shrinkage ($k \approx 1.93$ on fixtures). Documented mathematical proof in [`JUDGING.md`](JUDGING.md). Tested and proven against official 40-project fixtures with live spread visualizer in War Room. Verified offline by standalone [`verify.py`](verify.py). |
| **2. Pairwise Mode (Bradley-Terry)** | **Hard** | **+5** | Head-to-head comparison arena (`/arena`) implementing Minorization-Maximization (Hunter, 2004) with Laplace prior smoothing in `src/core/pairwise.py`. Intra-track matchmaking priority, skip buttons, and organizer rankings. Completely sidesteps rating scale compression. |
| **3. Threat Model** | **Medium** | **+3** | Comprehensive, defensible threat model published at [`THREAT-MODEL.md`](THREAT-MODEL.md), detailing defenses against Sybil votes, ballot stuffing, scraping, judge collusion, and post-deadline alterations. |
| **4. API First Design** | **Medium** | **+3** | Complete RESTful API with published OpenAPI 3.1 specification at `/openapi.json` and interactive offline Swagger UI documentation at `/docs`. Every UI action is backed by an authenticated endpoint. |

---

## 🪜 Tier Breakdown (T1 – T4 Satisfaction)

### 🟢 Tier 1: Core (Required Floor)
* [x] **Authentication & Sessions:** Token and session-cookie based authentication with executive switcher and `/login`, `/signup`, `/logout`.
* [x] **Real Role Model:** Distinct behavioral permissions for `visitor`, `participant`, `judge`, `organizer`, `admin`.
* [x] **Event Creation:** Configurable dates, submissions deadline, tracks, and prizes (`/competitions`, `/settings`).
* [x] **Team Formation:** Shareable invite links (`/team/join/{code}`) with membership rosters.
* [x] **Project Submission:** Rich submission form with draft-and-edit capability up until the deadline.
* [x] **Deadline Enforcement:** Hard server-side UTC validation refusing late submissions with HTTP 403 Forbidden.
* [x] **Public Gallery:** Public project gallery (`/projects`) with instant multi-track filtering and search.

### 🟢 Tier 2: Judging
* [x] **Judge Invitation & Assignment:** Batch onboarding via magic links and track-based assignment matrix.
* [x] **Weighted, Configurable Rubric:** Organizers can **add, edit, and remove criteria topics** on `/settings`. Supports dynamic weights with auto-normalization to 100%. Judge cards automatically adapt.
* [x] **Backend Role Isolation:** Strict query-level isolation. A judge requesting peer scores receives HTTP 403 Forbidden (verified by `spec/run.py` check T2.02).
* [x] **Live Progress Dashboard:** War Room (`/war-room`) displaying real-time review counts, completion metrics, and uncalibrated vs. normalized spread.
* [x] **Cross-Judge Normalization:** Two-Way Fixed Effects with Empirical Bayes shrinkage, mathematically documented in `JUDGING.md`.
* [x] **CSV Export:** Full CSV results export at `/api/export/results.csv`.

### 🟢 Tier 3: Public
* [x] **Community Voting:** People's Choice ballot (`/vote`) with configurable authentication.
* [x] **Anti-Sybil & Quadratic Mechanics:** Fisher-Yates ballot randomization to eliminate position bias. Unique voter token constraints preventing duplicate votes.
* [x] **Gallery Comments:** Public and authenticated discussion comments on project showcase pages.
* [x] **Sealed Ballots:** Results remain strictly sealed from participants and judges until published by the organizer.
* [x] **Anti-Abuse Engine:** In-memory token bucket rate limiting (`src/core/anti_abuse.py`) and human-readable audit logs (`/audit`).

### 🟢 Tier 4: Stretch
* [x] **REST API & Webhooks:** Comprehensive OpenAPI 3.1 endpoints and real-time webhook dispatcher (`src/core/webhooks.py`) for Discord/Slack integrations.
* [x] **Dynamic SVG Certificates:** Generated on-the-fly (`/certificates/{project_id}`) with pure-vector QR code verification.
* [x] **Verifiable Ed25519 Records:** Published results bundle signed with Curve25519 (RFC 8032) keys.
* [x] **Embeddable Gallery Widget:** Standalone embeddable showcase component (`/embed/gallery`).
* [x] **Bulk Import & Export:** Full JSON backup and migration engine (`/api/export/backup.json`, `/api/export/import`).

---

## 📐 Architecture & Key Features

### 1. Unstop-Style Navigational Architecture & Raptors.dev Editorial Aesthetic
* Collapsible 64px icon-only rail expanding smoothly to 240px on hover with nested submenus, zero Cumulative Layout Shift (CLS), and role-specific views (`Participant`, `Judge`, `Organizer`, `Visitor`).
* Styled after the official [raptors.dev](https://raptors.dev) brand: **Playfair Display** serif headlines with italic accents, **Inter** geometric body, and **JetBrains Mono** metrics.
* Monochrome high-contrast palette with subtle hairline borders, numbered section markers (`[ 01 ] | SUBMISSIONS SHOWCASE`), zero external CSS/font CDNs, and zero emojis.

### 2. Production Multi-Competition & Team Formation Engine
* Complete lifecycle management across multiple competitions simultaneously (e.g. `Sample Hack 2026`, `Raptors AI Challenge`, `MIT TechFair Grand Prix`).
* Dynamic team formation supporting up to 4 members with direct invite links (`/team/join/{invite_code}`) providing 1-click onboarding for logged-in users and simultaneous registration + team joining for new participants.

### 3. Strict Backend Role Isolation (T2)
* Judge privacy is enforced at the controller and query level, not hidden in CSS/HTML templates.
* A judge requesting peer scores (`/api/judge/scores?judge=judge_a` from `judge_b`) receives a strict **HTTP 403 Forbidden**.
* Participants attempting to access judge endpoints are refused with **HTTP 403 Forbidden**.

### 4. Empirical Bayes Normalization (Bonus Challenge: Hard)
* Models judge leniency via a Two-Way Fixed Effects specification:
  $$Y_{ij} = \mu + \alpha_i + \beta_j + \epsilon_{ij}, \quad \sum_j \beta_j = 0$$
* Accounts for uneven coverage using **Efron-Morris Empirical Bayes shrinkage**:
  $$B_i = \frac{n_i}{n_i + k}, \quad \hat{\alpha}_i^{\text{shrunk}} = B_i \cdot \hat{\alpha}_i$$
* A project with 2 reviews retains ~71% of its signal; a project with 5 reviews retains ~86%.

### 5. Bradley-Terry Pairwise Arena (Bonus Challenge: Hard)
* Allows judges to compare two anonymous projects head-to-head.
* Computes latent skill parameters $\pi_i$ via Minorization-Maximization:
  $$P(i \succ j) = \frac{\pi_i}{\pi_i + \pi_j}$$
* Completely eliminates rating scale compression and subjective grading inflation.

### 6. Ed25519 Cryptographic Verification (Trustless Hackathons)
* When results are published, Veritas generates a canonical JSON bundle and signs it with an **Ed25519** private key.
* Anyone can independently verify the results using the included zero-dependency script:
  ```bash
  curl -s http://localhost:8080/api/export/verification-bundle | python3 verify.py
  ```

---

## 📂 Documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — System architecture, security model, and offline guarantees.
- [`DATA-MODEL.md`](DATA-MODEL.md) — Relational SQLite schema, foreign keys, and migration paths.
- [`JUDGING.md`](JUDGING.md) — Complete mathematical proof for score normalization & Bradley-Terry.
- [`THREAT-MODEL.md`](THREAT-MODEL.md) — Defenses against Sybil attacks, collusion, and timing analysis.
- [`LICENSE`](LICENSE) — OSI-approved MIT License.

---

## 🔍 Honest Limitations

1. **In-Memory Rate Limiting:** The anti-abuse token bucket uses an in-memory dictionary. If scaled horizontally across multiple instances, Redis or shared memcached would be required.
2. **Offline Font Fallback:** In fully air-gapped environments without local system fonts, the browser gracefully falls back to system serif (Georgia / Times New Roman) and system sans.

---

## 📜 License

MIT License. Copyright (c) 2026 Veeral Saxena and Contributors.
