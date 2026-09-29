import json
import secrets
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from pydantic import BaseModel
from src.database import get_db, log_audit
from src.core.auth import get_current_user, require_role, require_auth, UserPrincipal
from src.core.security import hash_password, verify_password, generate_secure_token
from src.core.qrcode import generate_offline_svg_qr

router = APIRouter(tags=["auth_admin"])

class InviteCreateRequest(BaseModel):
    role: str  # 'judge' or 'participant'
    email: Optional[str] = None
    event_id: Optional[str] = None
    tracks: Optional[List[str]] = []
    team_id: Optional[str] = None

class OnboardRequest(BaseModel):
    token: str
    name: str
    email: str
    password: str

class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str

class PasswordResetRequest(BaseModel):
    new_password: Optional[str] = "password123"

class SignupRequest(BaseModel):
    name: str
    email: str
    password: str
    event_id: Optional[str] = None
    join_code: Optional[str] = None
    team_invite_code: Optional[str] = None

@router.post("/api/auth/signup")
def signup_user(payload: SignupRequest, response: Response):
    email = payload.email.strip().lower()
    name = payload.name.strip()
    if not email or not payload.password:
        raise HTTPException(status_code=400, detail="Name, email and password are required")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="An account with this email already exists. Please sign in.")

    # Determine event to register for
    event_id = "evt_02"
    if payload.event_id:
        cursor.execute("SELECT id FROM events WHERE id = ?", (payload.event_id.strip(),))
        ev = cursor.fetchone()
        if ev:
            event_id = ev["id"]
    elif payload.join_code and payload.join_code.strip():
        code = payload.join_code.strip().upper()
        cursor.execute("SELECT id FROM events WHERE UPPER(join_code) = ? OR id = ?", (code, payload.join_code.strip()))
        ev = cursor.fetchone()
        if ev:
            event_id = ev["id"]

    # Check and join team if invite code provided
    if payload.team_invite_code and payload.team_invite_code.strip():
        cursor.execute("SELECT * FROM teams WHERE invite_code = ?", (payload.team_invite_code.strip(),))
        tm = cursor.fetchone()
        if tm:
            tm_members = json.loads(tm["members"]) if tm["members"] else []
            if len(tm_members) >= 4:
                conn.close()
                raise HTTPException(status_code=400, detail="Team is already full (maximum 4 members)")
            if email not in [m.lower() for m in tm_members]:
                tm_members.append(email)
                cursor.execute("UPDATE teams SET members = ? WHERE id = ?", (json.dumps(tm_members), tm["id"]))
            if tm["event_id"]:
                event_id = tm["event_id"]

    user_id = f"prt_{secrets.token_hex(4)}"
    user_token = f"token_{secrets.token_hex(16)}"
    hashed_pw = hash_password(payload.password.strip())
    now = datetime.now(timezone.utc).isoformat()

    cursor.execute(
        """INSERT INTO users (id, name, email, role, token, password, tracks)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, name, email, "participant", user_token, hashed_pw, "[]")
    )

    cursor.execute(
        """INSERT INTO event_registrations (event_id, user_id, role, joined_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(event_id, user_id) DO NOTHING""",
        (event_id, user_id, "participant", now)
    )

    conn.commit()
    conn.close()

    log_audit("user_signup", user_id, "participant", f"New user {email} signed up for {event_id}")

    response.set_cookie(key="session", value=user_token, path="/", httponly=False)

    return {
        "status": "success",
        "user": {
            "id": user_id,
            "name": name,
            "email": email,
            "role": "participant"
        },
        "token": user_token,
        "redirect_url": f"/participant/dashboard?event={event_id}"
    }

@router.post("/api/organizer/invites")
def create_invite(payload: InviteCreateRequest, user: UserPrincipal = Depends(require_role(["organizer", "admin"]))):
    if payload.role not in ("judge", "participant"):
        raise HTTPException(status_code=400, detail="Role must be 'judge' or 'participant'")

    token = generate_secure_token("inv")
    now = datetime.now(timezone.utc).isoformat()
    event_id = payload.event_id or "evt_01"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO invitations (token, event_id, role, email, tracks, team_id, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            token,
            event_id,
            payload.role,
            payload.email,
            json.dumps(payload.tracks or []),
            payload.team_id,
            user.id,
            now
        )
    )
    conn.commit()
    conn.close()

    log_audit("create_invite", user.id, token, f"Role: {payload.role} for Event: {event_id}")

    return {
        "status": "success",
        "invite_token": token,
        "invite_url": f"/onboard/{token}",
        "qr_url": f"/api/invitations/{token}/qr",
        "role": payload.role,
        "event_id": event_id,
        "tracks": payload.tracks,
        "created_at": now
    }

@router.get("/api/organizer/invites")
def list_invites(user: UserPrincipal = Depends(require_role(["organizer", "admin"]))):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invitations ORDER BY created_at DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for r in rows:
        r["tracks"] = json.loads(r["tracks"]) if r.get("tracks") else []
        r["invite_url"] = f"/onboard/{r['token']}"
        r["qr_url"] = f"/api/invitations/{r['token']}/qr"
    return {"invitations": rows}

@router.get("/api/organizer/users")
def list_users(user: UserPrincipal = Depends(require_role(["organizer", "admin"]))):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, role, tracks FROM users ORDER BY role, name")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for r in rows:
        r["tracks"] = json.loads(r["tracks"]) if r.get("tracks") else []
    return {"users": rows}

@router.post("/api/organizer/users/{user_id}/reset-password")
def reset_user_password(user_id: str, payload: PasswordResetRequest, user: UserPrincipal = Depends(require_role(["organizer", "admin"]))):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email FROM users WHERE id = ?", (user_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    new_pw = payload.new_password or "password123"
    hashed_pw = hash_password(new_pw)
    cursor.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_pw, user_id))
    conn.commit()
    conn.close()

    log_audit("reset_password", user.id, user_id, f"Reset password for {target['email']}")
    return {"status": "success", "message": f"Password for {target['email']} has been reset."}

@router.post("/api/auth/onboard")
def onboard_user(payload: OnboardRequest, response: Response):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invitations WHERE token = ?", (payload.token,))
    inv = cursor.fetchone()
    if not inv:
        conn.close()
        raise HTTPException(status_code=404, detail="Invalid invitation token")

    if inv["used_at"]:
        conn.close()
        raise HTTPException(status_code=400, detail="This invitation link has already been used.")

    cursor.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (payload.email.strip(),))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    prefix = "jdg" if inv["role"] == "judge" else "prt"
    user_id = f"{prefix}_{secrets.token_hex(4)}"
    user_token = f"token_{secrets.token_hex(16)}"
    now = datetime.now(timezone.utc).isoformat()
    hashed_pw = hash_password(payload.password.strip())

    cursor.execute(
        """INSERT INTO users (id, name, email, role, token, password, tracks)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            payload.name.strip(),
            payload.email.strip(),
            inv["role"],
            user_token,
            hashed_pw,
            inv["tracks"]
        )
    )

    # Event registration
    event_id = inv["event_id"] or "evt_01"
    cursor.execute(
        """INSERT INTO event_registrations (event_id, user_id, role, joined_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(event_id, user_id) DO NOTHING""",
        (event_id, user_id, inv["role"], now)
    )

    cursor.execute("UPDATE invitations SET used_at = ? WHERE token = ?", (now, payload.token))

    if inv["role"] == "participant" and inv["team_id"]:
        cursor.execute("SELECT members FROM teams WHERE id = ?", (inv["team_id"],))
        team_row = cursor.fetchone()
        if team_row:
            members = json.loads(team_row["members"]) if team_row["members"] else []
            if payload.email.strip() not in members:
                members.append(payload.email.strip())
                cursor.execute("UPDATE teams SET members = ? WHERE id = ?", (json.dumps(members), inv["team_id"]))

    conn.commit()
    conn.close()

    log_audit("onboard_user", user_id, inv["role"], f"User {payload.email} onboarded to {event_id}")

    response.set_cookie(key="session", value=user_token, path="/", httponly=False)

    redirect_url = "/judge" if inv["role"] == "judge" else "/participant/dashboard"
    return {
        "status": "success",
        "user": {
            "id": user_id,
            "name": payload.name,
            "email": payload.email,
            "role": inv["role"]
        },
        "token": user_token,
        "redirect_url": redirect_url
    }

@router.post("/api/auth/change-password")
def change_password(payload: PasswordChangeRequest, user: UserPrincipal = Depends(require_auth)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE id = ?", (user.id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="User record not found")

    stored_pw = row["password"] or "password123"
    if not verify_password(payload.old_password, stored_pw):
        conn.close()
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    hashed_pw = hash_password(payload.new_password)
    cursor.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_pw, user.id))
    conn.commit()
    conn.close()

    log_audit("change_password", user.id, user.id, "User updated their own password")
    return {"status": "success", "message": "Password updated successfully."}
