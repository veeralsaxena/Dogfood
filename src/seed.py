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
    PRAGMA foreign_keys = ON;
    """)

    if not FIXTURES_PATH.exists():
        print(f"Error: Fixtures file not found at {FIXTURES_PATH}")
        return

    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Event
    event_data = data.get("event", {})
    weights_json = json.dumps({
        "functionality": 0.4,
        "quality": 0.3,
        "innovation": 0.2,
        "design": 0.1
    })
    cursor.execute(
        "INSERT INTO events (id, name, description, submissions_close, status, weights) VALUES (?, ?, ?, ?, ?, ?)",
        (
            event_data.get("id", "evt_01"),
            event_data.get("name", "Sample Hack 2026"),
            "Official Hackathon Raptors Dogfood Competition Event",
            event_data.get("submissions_close", "2026-03-01T18:00:00Z"),
            "active",
            weights_json
        )
    )

    # 2. Tracks
    for trk in data.get("tracks", []):
        cursor.execute(
            "INSERT INTO tracks (id, name, description) VALUES (?, ?, ?)",
            (trk["id"], trk["name"], f"Track focus on {trk['name']}")
        )

    # 3. Teams
    for tm in data.get("teams", []):
        cursor.execute(
            "INSERT INTO teams (id, name, members, invite_code) VALUES (?, ?, ?, ?)",
            (tm["id"], tm["name"], json.dumps(tm.get("members", [])), f"inv_{tm['id']}")
        )

    # 4. Users / Judges / Organizers / Participants
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

    # Fixture Judges
    for i, jdg in enumerate(data.get("judges", [])):
        j_id = jdg["id"]
        # Map judge_a to jdg_01 and judge_b to jdg_02 for exact checker mapping
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

    # 5. Projects
    for prj in data.get("projects", []):
        cursor.execute(
            """INSERT INTO projects (id, team_id, track_id, title, summary, description, repo_url, demo_url, submitted_at, is_draft)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                prj["id"],
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

    # 6. Scores
    for sc in data.get("scores", []):
        cursor.execute(
            """INSERT INTO scores (judge_id, project_id, criteria, comment, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                sc["judge"],
                sc["project"],
                json.dumps(sc.get("criteria", {})),
                sc.get("comment", ""),
                "2026-03-02T12:00:00Z"
            )
        )

    # 7. Seed sample Pairwise Votes (Bonus challenge T4 / Pairwise Arena)
    cursor.execute("""
        INSERT INTO pairwise_votes (judge_id, winner_id, loser_id, created_at) VALUES 
        ('jdg_01', 'prj_01', 'prj_02', '2026-03-02T14:00:00Z'),
        ('jdg_01', 'prj_01', 'prj_03', '2026-03-02T14:05:00Z'),
        ('jdg_02', 'prj_02', 'prj_03', '2026-03-02T14:10:00Z'),
        ('jdg_02', 'prj_04', 'prj_02', '2026-03-02T14:15:00Z'),
        ('jdg_03', 'prj_01', 'prj_04', '2026-03-02T14:20:00Z')
    """)

    # 8. Seed sample Community Comments & Ballots (T3)
    cursor.execute("""
        INSERT INTO comments (project_id, author_name, author_role, content, created_at) VALUES
        ('prj_01', 'Elena Rostova', 'Fellow', 'Remarkable execution on the zero-trust data pipeline.', '2026-03-03T10:00:00Z'),
        ('prj_01', 'Marcus Vance', 'Participant', 'Does this support sub-second query latency offline?', '2026-03-03T11:15:00Z'),
        ('prj_02', 'Tariq Al-Mansoor', 'Judge', 'Clean schema design and elegant isolation boundaries.', '2026-03-03T12:30:00Z')
    """)

    conn.commit()
    conn.close()

    log_audit("DATABASE_SEEDED", "system", "all", "Loaded fixtures.json and initialized security principals")

    print("seeded. test logins:")
    print(f"  organizer    Authorization: Token {TEST_TOKENS['organizer']}")
    print(f"  judge_a      Authorization: Token {TEST_TOKENS['judge_a']}")
    print(f"  judge_b      Authorization: Token {TEST_TOKENS['judge_b']}")
    print(f"  participant  Authorization: Token {TEST_TOKENS['participant']}")
    print("\nweb login credentials (http://localhost:8080/login):")
    print("  Organizer:    organizer@dogfood.local  /  password123")
    print("  Judge Ada:    ada@example.org          /  password123")
    print("  Judge Beta:   judge_b@example.org      /  password123")
    print("  Participant:  participant@example.org  /  password123")

if __name__ == "__main__":
    seed_database()
