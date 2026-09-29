import json
import os
from pathlib import Path
from src.database import get_db, init_db, log_audit
from src.config import BASE_DIR, TEST_TOKENS

FIXTURES_PATH = BASE_DIR / "spec" / "fixtures.json"

def seed_database():
    init_db()
    conn = get_db()
    cursor = conn.cursor()

    # Clear existing data in child-first order
    cursor.executescript("""
    PRAGMA foreign_keys = OFF;
    DELETE FROM event_registrations;
    DELETE FROM pairwise_votes;
    DELETE FROM ballots;
    DELETE FROM comments;
    DELETE FROM scores;
    DELETE FROM projects;
    DELETE FROM teams;
    DELETE FROM users;
    DELETE FROM tracks;
    DELETE FROM events;
    DELETE FROM audit_logs;
    DELETE FROM published_results;
    DELETE FROM invitations;
    PRAGMA foreign_keys = ON;
    """)

    if not FIXTURES_PATH.exists():
        print(f"Error: Fixtures file not found at {FIXTURES_PATH}")
        return

    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Event 01: Official Sample Hack 2026 (Fixtures)
    event_data = data.get("event", {})
    weights_json = json.dumps({
        "functionality": 0.4,
        "quality": 0.3,
        "innovation": 0.2,
        "design": 0.1
    })
    cursor.execute(
        """INSERT INTO events (id, name, slug, description, submissions_close, status, weights, organizer_id, join_code, prize_pool)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_data.get("id", "evt_01"),
            event_data.get("name", "Sample Hack 2026"),
            "sample-hack-2026",
            "Official Hackathon Raptors Dogfood Competition Event",
            event_data.get("submissions_close", "2026-03-01T18:00:00Z"),
            "active",
            weights_json,
            "org_root",
            "SAMPLE-2026",
            "$25,000 USD"
        )
    )

    # 2. Event 02: Raptors Global AI & Systems Hackathon 2026
    raptors_weights = json.dumps({
        "architecture": 0.35,
        "performance": 0.25,
        "verifiability": 0.25,
        "user_experience": 0.15
    })
    cursor.execute(
        """INSERT INTO events (id, name, slug, description, submissions_close, status, weights, organizer_id, join_code, prize_pool)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "evt_02",
            "Raptors AI & Systems Challenge 2026",
            "raptors-ai-2026",
            "Premier high-concurrency systems, agentic AI frameworks, and cryptographic auditability championship.",
            "2026-12-31T23:59:59Z",
            "active",
            raptors_weights,
            "org_root",
            "RAPTOR-2026",
            "$100,000 USD"
        )
    )

    # 3. Tracks for evt_01
    for trk in data.get("tracks", []):
        cursor.execute(
            "INSERT INTO tracks (id, event_id, name, description) VALUES (?, ?, ?, ?)",
            (trk["id"], "evt_01", trk["name"], f"Track focus on {trk['name']}")
        )

    # Tracks for evt_02
    cursor.execute("INSERT INTO tracks (id, event_id, name, description) VALUES (?, ?, ?, ?)",
                   ("trk_r1", "evt_02", "Autonomous Agents & LLMs", "Self-directed agentic systems and tool use"))
    cursor.execute("INSERT INTO tracks (id, event_id, name, description) VALUES (?, ?, ?, ?)",
                   ("trk_r2", "evt_02", "High-Performance Systems", "Sub-millisecond latency, zero-copy pipelines"))
    cursor.execute("INSERT INTO tracks (id, event_id, name, description) VALUES (?, ?, ?, ?)",
                   ("trk_r3", "evt_02", "Applied Cryptography & Privacy", "Zero-knowledge proofs, verifiable state, air-gap security"))

    # 4. Teams for evt_01
    for tm in data.get("teams", []):
        cursor.execute(
            "INSERT INTO teams (id, event_id, name, members, invite_code) VALUES (?, ?, ?, ?, ?)",
            (tm["id"], "evt_01", tm["name"], json.dumps(tm.get("members", [])), f"inv_{tm['id']}")
        )

    # Team for evt_02
    cursor.execute(
        "INSERT INTO teams (id, event_id, name, members, invite_code) VALUES (?, ?, ?, ?, ?)",
        ("tm_raptor_01", "evt_02", "Apex Systems", json.dumps(["lead@teamalpha.local", "alex@apex.io"]), "inv_apex_01")
    )

    # 5. Users / Judges / Organizers / Participants
    # Root Organizer
    cursor.execute(
        "INSERT INTO users (id, name, email, role, token, password, tracks) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("org_root", "Event Organizer", "organizer@dogfood.local", "organizer", TEST_TOKENS["organizer"], "password123", "[]")
    )
    # Default Participant
    cursor.execute(
        "INSERT INTO users (id, name, email, role, token, password, tracks) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("prt_01", "Participant One", "participant@example.org", "participant", TEST_TOKENS["participant"], "password123", "[]")
    )
    # Secondary Participant
    cursor.execute(
        "INSERT INTO users (id, name, email, role, token, password, tracks) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("prt_02", "Alex Mercer", "lead@teamalpha.local", "participant", "token_prt_alex_mercer", "password123", "[]")
    )

    # Fixture Judges
    for i, jdg in enumerate(data.get("judges", [])):
        j_id = jdg["id"]
        if j_id == "jdg_01":
            token = TEST_TOKENS["judge_a"]
        elif j_id == "jdg_02":
            token = TEST_TOKENS["judge_b"]
        else:
            token = f"token_{j_id}_secret_key_2026"

        cursor.execute(
            "INSERT INTO users (id, name, email, role, token, password, tracks) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (j_id, jdg["name"], jdg["email"], "judge", token, "password123", json.dumps(jdg.get("tracks", [])))
        )

    # 6. Event Registrations
    cursor.execute("INSERT INTO event_registrations (event_id, user_id, role, joined_at) VALUES ('evt_01', 'org_root', 'organizer', '2026-02-01T00:00:00Z')")
    cursor.execute("INSERT INTO event_registrations (event_id, user_id, role, joined_at) VALUES ('evt_02', 'org_root', 'organizer', '2026-02-01T00:00:00Z')")
    cursor.execute("INSERT INTO event_registrations (event_id, user_id, role, joined_at) VALUES ('evt_01', 'prt_01', 'participant', '2026-02-15T00:00:00Z')")
    cursor.execute("INSERT INTO event_registrations (event_id, user_id, role, joined_at) VALUES ('evt_02', 'prt_02', 'participant', '2026-02-15T00:00:00Z')")
    cursor.execute("INSERT INTO event_registrations (event_id, user_id, role, joined_at) VALUES ('evt_01', 'jdg_01', 'judge', '2026-02-10T00:00:00Z')")
    cursor.execute("INSERT INTO event_registrations (event_id, user_id, role, joined_at) VALUES ('evt_01', 'jdg_02', 'judge', '2026-02-10T00:00:00Z')")
    cursor.execute("INSERT INTO event_registrations (event_id, user_id, role, joined_at) VALUES ('evt_02', 'jdg_01', 'judge', '2026-02-10T00:00:00Z')")

    # 7. Projects for evt_01
    for prj in data.get("projects", []):
        cursor.execute(
            """INSERT INTO projects (id, event_id, team_id, track_id, title, summary, description, repo_url, demo_url, submitted_at, is_draft)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                prj["id"],
                "evt_01",
                prj.get("team"),
                prj.get("track"),
                prj.get("title"),
                prj.get("summary", ""),
                prj.get("description", prj.get("summary", "Complete Hackathon Submission.")),
                prj.get("repo_url", "https://github.com/example/repo"),
                prj.get("demo_url", "https://demo.example.org"),
                prj.get("submitted_at", "2026-02-28T22:00:00Z")
            )
        )

    # Project for evt_02
    cursor.execute(
        """INSERT INTO projects (id, event_id, team_id, track_id, title, summary, description, repo_url, demo_url, submitted_at, is_draft)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (
            "prj_raptor_01",
            "evt_02",
            "tm_raptor_01",
            "trk_r1",
            "Chronos Agent Engine",
            "Deterministic autonomous orchestrator with cryptographically auditable state checkpoints.",
            "Full-featured agent runtime providing zero-cloud execution and reproducible verification.",
            "https://github.com/raptors-dev/chronos",
            "https://chronos.raptors.internal",
            "2026-03-01T12:00:00Z"
        )
    )

    # 8. Scores for evt_01
    for sc in data.get("scores", []):
        cursor.execute(
            """INSERT INTO scores (event_id, judge_id, project_id, criteria, comment, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "evt_01",
                sc["judge"],
                sc["project"],
                json.dumps(sc.get("criteria", {})),
                sc.get("comment", ""),
                "2026-03-02T12:00:00Z"
            )
        )

    # 9. Seed sample Pairwise Votes
    cursor.execute("""
        INSERT INTO pairwise_votes (event_id, judge_id, winner_id, loser_id, created_at) VALUES 
        ('evt_01', 'jdg_01', 'prj_01', 'prj_02', '2026-03-02T14:00:00Z'),
        ('evt_01', 'jdg_01', 'prj_01', 'prj_03', '2026-03-02T14:05:00Z'),
        ('evt_01', 'jdg_02', 'prj_02', 'prj_03', '2026-03-02T14:10:00Z'),
        ('evt_01', 'jdg_02', 'prj_04', 'prj_02', '2026-03-02T14:15:00Z'),
        ('evt_01', 'jdg_03', 'prj_01', 'prj_04', '2026-03-02T14:20:00Z')
    """)

    # 10. Sample Community Comments
    cursor.execute("""
        INSERT INTO comments (project_id, author_name, author_role, content, created_at) VALUES
        ('prj_01', 'Elena Rostova', 'Fellow', 'Remarkable execution on the zero-trust data pipeline.', '2026-03-03T10:00:00Z'),
        ('prj_01', 'Marcus Vance', 'Participant', 'Does this support sub-second query latency offline?', '2026-03-03T11:15:00Z'),
        ('prj_02', 'Tariq Al-Mansoor', 'Judge', 'Clean schema design and elegant isolation boundaries.', '2026-03-03T12:30:00Z')
    """)

    # 11. Sample Invitations with QR-ready tokens
    cursor.execute("""
        INSERT INTO invitations (token, event_id, role, email, tracks, created_by, created_at) VALUES
        ('inv_judge_security_2026', 'evt_02', 'judge', 'judge.security@raptors.internal', '["trk_r3"]', 'org_root', '2026-03-01T10:00:00Z'),
        ('inv_participant_open_2026', 'evt_02', 'participant', NULL, '[]', 'org_root', '2026-03-01T10:00:00Z')
    """)

    conn.commit()
    conn.close()

    log_audit("DATABASE_SEEDED", "system", "all", "Loaded fixtures.json and seeded multi-competition environment")

    print("""
================================================================================
                    VERITAS PLATFORM — SEEDED CREDENTIALS
================================================================================
 ROLE        EMAIL                     PASSWORD      DEFAULT CONTEXT
--------------------------------------------------------------------------------
 Organizer   organizer@dogfood.local   password123   Command Center / War Room
 Participant participant@example.org   password123   Team Nightshift (Sample Hack)
 Participant lead@teamalpha.local      password123   Team Apex (Raptors AI Challenge)
 Judge       ada@example.org           password123   Track: Developer Tools
 Judge       judge_b@example.org       password123   Track: Infrastructure
--------------------------------------------------------------------------------
 Active Competition Join Codes:
   • evt_01: SAMPLE-2026 (Sample Hack 2026 - Official Fixture Event)
   • evt_02: RAPTOR-2026 (Raptors AI & Systems Challenge 2026 - Open Live)
================================================================================
""")

if __name__ == "__main__":
    seed_database()
