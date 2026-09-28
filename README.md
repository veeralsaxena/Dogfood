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
- **Public Showcase:** [http://localhost:8080/projects](http://localhost:8080/projects)
- **Live War Room:** [http://localhost:8080/war-room](http://localhost:8080/war-room)
- **Pairwise Arena:** [http://localhost:8080/arena](http://localhost:8080/arena)
- **Judge Portal:** [http://localhost:8080/judge](http://localhost:8080/judge)
- **Cryptographic Audit:** [http://localhost:8080/audit](http://localhost:8080/audit)
- **OpenAPI 3.1 Specs:** [http://localhost:8080/docs](http://localhost:8080/docs)

---

## 🏆 Acceptance Suite Verification

Veritas passes **100%** of the official acceptance suite checks:

```bash
python3 spec/run.py .dogfood.toml
```

Output:
```
DOGFOOD 2026 acceptance report
portal: http://localhost:8080
claimed: T1 T2
fixtures: spec/fixtures.json

T1  gallery is public ................. PASS
T1  project from fixtures shown ....... PASS
T1  closed event refuses submissions .. PASS
T2  judge sees own scores ............. PASS
T2  judge cannot see peer scores ...... PASS
T2  participant blocked ............... PASS
T2  csv export works .................. PASS

claimed T1 T2, verified T1 T2
```

The receipt is committed at [`acceptance-report.txt`](acceptance-report.txt).

---

## 📐 Architecture & Key Features

### 1. Raptors.dev Editorial Aesthetic
* Styled after the official [raptors.dev](https://raptors.dev) brand: **Playfair Display** serif headlines with italic accents, **Inter** geometric body, and **JetBrains Mono** metrics.
* Monochrome high-contrast palette with subtle hairline borders, numbered section markers (`[ 01 ] | SUBMISSIONS SHOWCASE`), and zero external CSS/font CDNs.

### 2. Strict Backend Role Isolation (T2)
* Judge privacy is enforced at the controller and query level, not hidden in CSS/HTML templates.
* A judge requesting peer scores (`/api/judge/scores?judge=judge_a` from `judge_b`) receives a strict **HTTP 403 Forbidden**.
* Participants attempting to access judge endpoints are refused with **HTTP 403 Forbidden**.

### 3. Empirical Bayes Normalization (Bonus Challenge: Hard)
* Models judge leniency via a Two-Way Fixed Effects specification:
  $$Y_{ij} = \mu + \alpha_i + \beta_j + \epsilon_{ij}, \quad \sum_j \beta_j = 0$$
* Accounts for uneven coverage using **Efron-Morris Empirical Bayes shrinkage**:
  $$B_i = \frac{n_i}{n_i + k}, \quad \hat{\alpha}_i^{\text{shrunk}} = B_i \cdot \hat{\alpha}_i$$
* A project with 2 reviews retains ~71% of its signal; a project with 5 reviews retains ~86%.

### 4. Bradley-Terry Pairwise Arena (Bonus Challenge: Hard)
* Allows judges to compare two anonymous projects head-to-head.
* Computes latent skill parameters $\pi_i$ via Minorization-Maximization:
  $$P(i \succ j) = \frac{\pi_i}{\pi_i + \pi_j}$$
* Completely eliminates rating scale compression and subjective grading inflation.

### 5. Ed25519 Cryptographic Verification (Trustless Hackathons)
* When results are published, Veritas generates a canonical JSON bundle and signs it with an **Ed25519** private key.
* Anyone can independently verify the results using the included zero-dependency script:
  ```bash
  curl -s http://localhost:8080/api/export/verification-bundle | python3 verify.py
  ```

---

## 📂 Documentation

- [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) — System architecture, security model, and offline guarantees.
- [`DATA-MODEL.md`](docs/DATA-MODEL.md) — Relational SQLite schema, foreign keys, and migration paths.
- [`JUDGING.md`](docs/JUDGING.md) — Complete mathematical proof for score normalization & Bradley-Terry.
- [`THREAT-MODEL.md`](docs/THREAT-MODEL.md) — Defenses against Sybil attacks, collusion, and timing analysis.
- [`LICENSE`](LICENSE) — OSI-approved MIT License.

---

## 🔍 Honest Limitations

1. **In-Memory Rate Limiting:** The anti-abuse token bucket uses an in-memory dictionary. If scaled horizontally across multiple instances, Redis or shared memcached would be required.
2. **Offline Font Fallback:** In fully air-gapped environments without local system fonts, the browser gracefully falls back to system serif (Georgia / Times New Roman) and system sans.

---

## 📜 License

MIT License. Copyright (c) 2026 Veeral Saxena and Contributors.
