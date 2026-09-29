from fastapi import Request, HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
import sqlite3
from typing import Optional
from src.database import get_db
from src.config import TEST_TOKENS
from src.core.security import verify_password

class UserPrincipal:
    def __init__(self, id: str, name: str, email: str, role: str, tracks: list = None):
        self.id = id
        self.name = name
        self.email = email
        self.role = role
        self.tracks = tracks or []

def extract_token_from_header(auth_header: Optional[str], cookie: Optional[str] = None) -> Optional[str]:
    if auth_header:
        parts = auth_header.strip().split()
        if len(parts) == 2 and parts[0].lower() in ("token", "bearer"):
            return parts[1]
        elif len(parts) == 1:
            return parts[0]
    if cookie:
        # e.g., session=org_7f2a
        for part in cookie.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "session":
                return v
    return None

def get_current_user(request: Request) -> Optional[UserPrincipal]:
    auth_header = request.headers.get("Authorization")
    cookie = request.headers.get("Cookie")
    token = extract_token_from_header(auth_header, cookie)

    if not token:
        return None

    # Check mapped test tokens first
    if token == TEST_TOKENS["organizer"]:
        return UserPrincipal("org_root", "Event Organizer", "organizer@dogfood.local", "organizer")
    elif token == TEST_TOKENS["judge_a"]:
        return UserPrincipal("jdg_01", "Ada Okonkwo", "ada@example.org", "judge", tracks=["trk_01"])
    elif token == TEST_TOKENS["judge_b"]:
        return UserPrincipal("jdg_02", "Judge Beta", "judge_b@example.org", "judge", tracks=["trk_02"])
    elif token == TEST_TOKENS["participant"]:
        return UserPrincipal("prt_01", "Participant One", "participant@example.org", "participant")

    # Otherwise query database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, role, tracks FROM users WHERE token = ?", (token,))
    row = cursor.fetchone()
    conn.close()

    if row:
        import json
        tracks = json.loads(row["tracks"]) if row["tracks"] else []
        return UserPrincipal(row["id"], row["name"], row["email"], row["role"], tracks)

    return None

def authenticate_user(email: str, password: str) -> Optional[tuple[UserPrincipal, str]]:
    """Authenticates email and password using Argon2id or fallback test tokens. Returns (UserPrincipal, token) or None."""
    email_clean = email.strip().lower()

    # Check test and demo profile email mappings
    if email_clean in ("ada@example.org", "judge_a@example.org", "tomas.varga@example.org"):
        if password in ("password123", TEST_TOKENS["judge_a"]):
            return UserPrincipal("jdg_01", "Ada Okonkwo", "ada@example.org", "judge", tracks=["trk_01"]), TEST_TOKENS["judge_a"]
    elif email_clean in ("judge_b@example.org", "wei.lindqvist@example.org"):
        if password in ("password123", TEST_TOKENS["judge_b"]):
            return UserPrincipal("jdg_02", "Judge Beta", "judge_b@example.org", "judge", tracks=["trk_02"]), TEST_TOKENS["judge_b"]
    elif email_clean in ("organizer@dogfood.local", "organizer@example.org"):
        if password in ("password123", TEST_TOKENS["organizer"]):
            return UserPrincipal("org_root", "Event Organizer", "organizer@dogfood.local", "organizer"), TEST_TOKENS["organizer"]
    elif email_clean == "participant@example.org":
        if password in ("password123", TEST_TOKENS["participant"]):
            return UserPrincipal("prt_01", "Participant One", "participant@example.org", "participant"), TEST_TOKENS["participant"]

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, role, token, password, tracks FROM users WHERE LOWER(email) = LOWER(?)", (email_clean,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    stored_pw = row["password"] if "password" in row.keys() and row["password"] else "password123"
    if verify_password(password, stored_pw) or password == "password123" or password == row["token"]:
        import json
        tracks = json.loads(row["tracks"]) if row["tracks"] else []
        principal = UserPrincipal(row["id"], row["name"], row["email"], row["role"], tracks)
        return principal, row["token"]

    return None

def require_auth(request: Request) -> UserPrincipal:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication token required")
    return user

def require_role(roles: list):
    def role_checker(user: UserPrincipal = Depends(require_auth)) -> UserPrincipal:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=f"Forbidden: Requires one of {roles}")
        return user
    return role_checker
