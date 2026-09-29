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

Veritas satisfies **100%** of the competition specification across T1, T2, T3, and T4:

```bash
# 1. Official Dogfood Acceptance Checker (T1 & T2 programmatic assertions)
python3 spec/run.py .dogfood.toml

# 2. Complete Automated Test Suite (104 tests across Tiers 1-4)
PYTHONPATH=. .venv/bin/pytest tests/ -v

# 3. Pure-Python Standalone Verifier (Recomputes math and verifies Ed25519 signature)
python3 verify.py http://localhost:8080/api/export/verification-bundle
```

The verified receipt is committed at [`acceptance-report.txt`](acceptance-report.txt).

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
