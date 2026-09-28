import sqlite3
import json
from datetime import datetime, timezone
from src.config import DB_PATH

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        submissions_close TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        weights TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS tracks (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT
    );

    CREATE TABLE IF NOT EXISTS teams (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        members TEXT NOT NULL, -- JSON array of emails
        invite_code TEXT UNIQUE
    );

    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL, -- 'visitor', 'participant', 'judge', 'organizer', 'admin'
        token TEXT UNIQUE NOT NULL,
        password TEXT DEFAULT 'password123',
        tracks TEXT -- JSON array of track ids
    );

    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        team_id TEXT REFERENCES teams(id),
        track_id TEXT REFERENCES tracks(id),
        title TEXT NOT NULL,
        summary TEXT,
        description TEXT,
        repo_url TEXT,
        demo_url TEXT,
        submitted_at TEXT NOT NULL,
        is_draft INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        judge_id TEXT NOT NULL REFERENCES users(id),
        project_id TEXT NOT NULL REFERENCES projects(id),
        criteria TEXT NOT NULL, -- JSON dict {criteria_name: score_int}
        comment TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(judge_id, project_id)
    );

    CREATE TABLE IF NOT EXISTS pairwise_votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        judge_id TEXT NOT NULL REFERENCES users(id),
        winner_id TEXT NOT NULL REFERENCES projects(id),
        loser_id TEXT NOT NULL REFERENCES projects(id),
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS ballots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL REFERENCES projects(id),
        voter_token TEXT NOT NULL,
        voter_ip TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(project_id, voter_token)
    );

    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL REFERENCES projects(id),
        author_name TEXT NOT NULL,
        author_role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT NOT NULL,
        actor TEXT NOT NULL,
        target TEXT,
        details TEXT,
        timestamp TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS published_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        signature_hex TEXT NOT NULL,
        public_key_hex TEXT NOT NULL,
        published_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS invitations (
        token TEXT PRIMARY KEY,
        role TEXT NOT NULL,
        email TEXT,
        tracks TEXT,
        team_id TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        used_at TEXT,
        expires_at TEXT
    );
    """)
    conn.commit()
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN password TEXT DEFAULT 'password123'")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()

def log_audit(action: str, actor: str, target: str = None, details: str = None):
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO audit_logs (action, actor, target, details, timestamp) VALUES (?, ?, ?, ?, ?)",
        (action, actor, target, details, now)
    )
    conn.commit()
    conn.close()
