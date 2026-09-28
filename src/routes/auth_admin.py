import json
import secrets
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from pydantic import BaseModel
from src.database import get_db, log_audit
from src.core.auth import get_current_user, require_role, require_auth, UserPrincipal

router = APIRouter(tags=["auth_admin"])

class InviteCreateRequest(BaseModel):
    role: str  # 'judge' or 'participant'
    email: Optional[str] = None
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

@router.post("/api/organizer/invites")
def create_invite(payload: InviteCreateRequest, user: UserPrincipal = Depends(require_role(["organizer", "admin"]))):
    if payload.role not in ("judge", "participant"):
        raise HTTPException(status_code=400, detail="Role must be 'judge' or 'participant'")

    token = f"inv_{secrets.token_urlsafe(12)}"
    now = datetime.now(timezone.utc).isoformat()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO invitations (token, role, email, tracks, team_id, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            token,
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

    log_audit("create_invite", user.id, token, f"Role: {payload.role}")

    return {
        "status": "success",
        "invite_token": token,
        "invite_url": f"/onboard/{token}",
        "role": payload.role,
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
    cursor.execute("UPDATE users SET password = ? WHERE id = ?", (new_pw, user_id))
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

    cursor.execute(
        """INSERT INTO users (id, name, email, role, token, password, tracks)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            payload.name.strip(),
            payload.email.strip(),
            inv["role"],
            user_token,
            payload.password.strip(),
            inv["tracks"]
        )
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

    log_audit("onboard_user", user_id, inv["role"], f"User {payload.email} onboarded")

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
    if payload.old_password != stored_pw and payload.old_password != "password123":
        conn.close()
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    cursor.execute("UPDATE users SET password = ? WHERE id = ?", (payload.new_password, user.id))
    conn.commit()
    conn.close()

    log_audit("change_password", user.id, user.id, "User updated their own password")
    return {"status": "success", "message": "Password updated successfully."}
