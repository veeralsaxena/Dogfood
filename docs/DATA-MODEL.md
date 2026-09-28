# DATA-MODEL.md · Relational Schema & Persistence

This document details the database schema, entity relationships, and data portability pathways for **Veritas**.

---

## 1. Entity-Relationship Diagram

```mermaid
erDiagram
    EVENTS ||--o{ TRACKS : contains
    EVENTS ||--o{ PROJECTS : receives
    TRACKS ||--o{ PROJECTS : categorizes
    TEAMS ||--o{ PROJECTS : submits
    USERS ||--o{ SCORES : evaluates
    PROJECTS ||--o{ SCORES : receives
    USERS ||--o{ PAIRWISE_VOTES : evaluates
    PROJECTS ||--o{ PAIRWISE_VOTES : compares
    PROJECTS ||--o{ BALLOTS : receives
    PROJECTS ||--o{ COMMENTS : receives

    EVENTS {
        string id PK
        string name
        string description
        string submissions_close
        string status
        string weights
    }

    TRACKS {
        string id PK
        string name
        string description
    }

    TEAMS {
        string id PK
        string name
        string members
        string invite_code
    }

    USERS {
        string id PK
        string name
        string email
        string role
        string token
        string tracks
    }

    PROJECTS {
        string id PK
        string team_id FK
        string track_id FK
        string title
        string summary
        string description
        string repo_url
        string demo_url
        string submitted_at
        integer is_draft
    }

    SCORES {
        integer id PK
        string judge_id FK
        string project_id FK
        string criteria
        string comment
        string created_at
    }

    PAIRWISE_VOTES {
        integer id PK
        string judge_id FK
        string winner_id FK
        string loser_id FK
        string created_at
    }

    BALLOTS {
        integer id PK
        string project_id FK
        string voter_token
        string voter_ip
        string created_at
    }

    COMMENTS {
        integer id PK
        string project_id FK
        string author_name
        string author_role
        string content
        string created_at
    }

    AUDIT_LOGS {
        integer id PK
        string action
        string actor
        string target
        string details
        string timestamp
    }
```

---

## 2. Table Specifications

### `events`
Stores hackathon configuration, deadlines, and criteria weights.
- `id` (TEXT, PK): Event identifier (e.g. `evt_01`).
- `submissions_close` (TEXT): ISO 8601 UTC timestamp enforced strictly on all submissions.
- `weights` (TEXT): JSON object defining criteria weights (e.g. `{"functionality": 0.4, "quality": 0.3, "innovation": 0.2, "design": 0.1}`).

### `users`
Models participants, judges, and administrators.
- `role` (TEXT): One of `'visitor'`, `'participant'`, `'judge'`, `'organizer'`, `'admin'`.
- `token` (TEXT, UNIQUE): Cryptographic access token.
- `tracks` (TEXT): JSON list of assigned track IDs for judges.

### `projects`
Stores team submissions.
- `is_draft` (INTEGER): `0` for submitted, `1` for draft.

### `scores`
Stores individual rubric evaluations.
- `criteria` (TEXT): JSON dictionary of criterion scores (1 to 5 scale).
- `UNIQUE(judge_id, project_id)` constraint ensures idempotent evaluations.

### `pairwise_votes`
Stores head-to-head match results for Bradley-Terry modeling.

---

## 3. Data Migration & Portability

Veritas supports complete round-trip JSON data exports and imports:
- **Export:** `GET /api/export/results.json` returns complete raw evaluations and normalized statistics.
- **Portability:** Database is a self-contained single-file SQLite database located at `data/dogfood.db`. An organizer can archive, backup, or transfer the file between instances with zero dependencies.
