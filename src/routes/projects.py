import json
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from typing import List, Optional
from pydantic import BaseModel
from src.database import get_db, log_audit
from src.models import ProjectCreate, ProjectResponse
from src.core.auth import get_current_user, require_auth, UserPrincipal

class TeamCreateRequest(BaseModel):
    name: str
    event_id: Optional[str] = "evt_02"

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.get("", response_model=List[dict])
def list_projects(track: Optional[str] = None, search: Optional[str] = None):
    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT p.*, t.name as track_name, tm.name as team_name
        FROM projects p
        LEFT JOIN tracks t ON p.track_id = t.id
        LEFT JOIN teams tm ON p.team_id = tm.id
        WHERE p.is_draft = 0
    """
    params = []
    if track:
        query += " AND p.track_id = ?"
        params.append(track)
    if search:
        query += " AND (p.title LIKE ? OR p.summary LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY p.submitted_at DESC"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@router.post("", status_code=201)
def submit_project(project: ProjectCreate, request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required to submit project")

    conn = get_db()
    cursor = conn.cursor()

    # 1. Enforce deadline from events table
    target_event_id = project.event_id or "evt_01"
    cursor.execute("SELECT id, submissions_close FROM events WHERE id = ? OR slug = ?", (target_event_id, target_event_id))
    event_row = cursor.fetchone()
    if not event_row:
        cursor.execute("SELECT id, submissions_close FROM events LIMIT 1")
        event_row = cursor.fetchone()

    if event_row:
        close_str = event_row["submissions_close"]
        target_event_id = event_row["id"]
        try:
            close_dt = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            if now_dt > close_dt:
                conn.close()
                log_audit("SUBMISSION_REFUSED_DEADLINE", user.email, project.title, f"Deadline {close_str} passed")
                raise HTTPException(status_code=403, detail=f"Submissions closed on {close_str}")
        except ValueError:
            pass

    # 2. Insert project
    import uuid
    new_id = f"prj_{uuid.uuid4().hex[:6]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    valid_team_id = None
    if project.team_id and str(project.team_id).strip():
        cursor.execute("SELECT id FROM teams WHERE id = ?", (str(project.team_id).strip(),))
        if cursor.fetchone():
            valid_team_id = str(project.team_id).strip()
    elif user:
        cursor.execute("SELECT id, members FROM teams WHERE (event_id = ? OR event_id IS NULL)", (target_event_id,))
        for t_row in cursor.fetchall():
            m_list = json.loads(t_row["members"]) if t_row["members"] else []
            if any(user.email.lower() == str(m).lower() or user.name.lower() == str(m).lower() for m in m_list):
                valid_team_id = t_row["id"]
                break

    valid_track_id = None
    if project.track_id:
        cursor.execute("SELECT id FROM tracks WHERE id = ?", (project.track_id,))
        if cursor.fetchone():
            valid_track_id = project.track_id
    if not valid_track_id:
        cursor.execute("SELECT id FROM tracks WHERE event_id = ? LIMIT 1", (target_event_id,))
        tr_row = cursor.fetchone()
        if tr_row:
            valid_track_id = tr_row["id"]
        else:
            cursor.execute("SELECT id FROM tracks LIMIT 1")
            fallback_tr = cursor.fetchone()
            valid_track_id = fallback_tr["id"] if fallback_tr else None

    cursor.execute(
        """INSERT INTO projects (id, event_id, team_id, track_id, title, summary, description, repo_url, demo_url, submitted_at, is_draft)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            new_id,
            target_event_id,
            valid_team_id,
            valid_track_id,
            project.title,
            project.summary or "",
            project.description or "",
            project.repo_url or "",
            project.demo_url or "",
            now_iso,
            1 if project.is_draft else 0
        )
    )
    conn.commit()
    conn.close()

    log_audit("PROJECT_SUBMITTED", user.email, new_id, project.title)
    return {"id": new_id, "title": project.title, "status": "submitted"}

@router.get("/{project_id}")
def get_project(project_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT p.*, t.name as track_name, tm.name as team_name
           FROM projects p
           LEFT JOIN tracks t ON p.track_id = t.id
           LEFT JOIN teams tm ON p.team_id = tm.id
           WHERE p.id = ?""",
        (project_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return dict(row)

team_router = APIRouter(prefix="/api/teams", tags=["teams"])
event_router = APIRouter(prefix="/api/event", tags=["event"])

@team_router.post("/create")
def create_team(payload: TeamCreateRequest, request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required to create a team")
    
    team_name = payload.name.strip()
    if not team_name:
        raise HTTPException(status_code=400, detail="Team name is required")
    
    event_id = payload.event_id or "evt_02"
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if user already in a team for this event
    cursor.execute("SELECT id, name, members FROM teams WHERE (event_id = ? OR event_id IS NULL)", (event_id,))
    for row in cursor.fetchall():
        members = json.loads(row["members"]) if row["members"] else []
        if any(user.email.lower() == str(m).lower() or user.name.lower() == str(m).lower() for m in members):
            conn.close()
            raise HTTPException(status_code=400, detail=f"You are already in team '{row['name']}' for this competition.")
    
    team_id = f"tm_{secrets.token_hex(4)}"
    invite_code = f"inv_{secrets.token_hex(4)}"
    members = [user.email]
    
    cursor.execute(
        "INSERT INTO teams (id, event_id, name, members, invite_code) VALUES (?, ?, ?, ?, ?)",
        (team_id, event_id, team_name, json.dumps(members), invite_code)
    )
    
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        """INSERT INTO event_registrations (event_id, user_id, role, joined_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(event_id, user_id) DO NOTHING""",
        (event_id, user.id, "participant", now)
    )
    
    conn.commit()
    conn.close()
    log_audit("TEAM_CREATED", user.email, team_id, f"Created team {team_name} for {event_id}")
    return {
        "status": "success",
        "team": {
            "id": team_id,
            "event_id": event_id,
            "name": team_name,
            "invite_code": invite_code,
            "members": members
        }
    }

@team_router.post("/join")
@team_router.post("/join/{invite_code}")
def join_team_by_code(request: Request, invite_code: Optional[str] = None, body: Optional[dict] = None):
    body = body or {}
    code = invite_code or body.get("invite_code")
    if not code:
        raise HTTPException(status_code=400, detail="Invite code is required")

    user = get_current_user(request)
    email = body.get("email") or (user.email if user else None)
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM teams WHERE invite_code = ?", (code.strip(),))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Team invite code not found")

    members = json.loads(row["members"]) if row["members"] else []
    if len(members) >= 4 and not any(email.lower() == str(m).lower() for m in members):
        conn.close()
        raise HTTPException(status_code=400, detail="Team is already full (maximum 4 members)")

    if row["event_id"]:
        cursor.execute("SELECT id, name, members FROM teams WHERE event_id = ? AND id != ?", (row["event_id"], row["id"]))
        for other_tm in cursor.fetchall():
            other_m = json.loads(other_tm["members"]) if other_tm["members"] else []
            if any(email.lower() == str(m).lower() for m in other_m):
                conn.close()
                raise HTTPException(status_code=400, detail=f"You are already in team '{other_tm['name']}' for this competition. Leave it first.")

    if not any(email.lower() == str(m).lower() for m in members):
        members.append(email)
        cursor.execute("UPDATE teams SET members = ? WHERE id = ?", (json.dumps(members), row["id"]))

    if user and row["event_id"]:
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """INSERT INTO event_registrations (event_id, user_id, role, joined_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(event_id, user_id) DO NOTHING""",
            (row["event_id"], user.id, "participant", now)
        )

    conn.commit()
    conn.close()
    log_audit("TEAM_JOINED", email, row["id"], f"Joined team {row['name']}")
    return {"status": "success", "team_id": row["id"], "team_name": row["name"], "event_id": row["event_id"], "members": members}

@team_router.post("/leave")
def leave_team_endpoint(request: Request, body: dict):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    team_id = body.get("team_id")
    if not team_id:
        raise HTTPException(status_code=400, detail="team_id is required")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM teams WHERE id = ?", (team_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Team not found")
    
    members = json.loads(row["members"]) if row["members"] else []
    members = [m for m in members if user.email.lower() != str(m).lower() and user.name.lower() != str(m).lower()]
    cursor.execute("UPDATE teams SET members = ? WHERE id = ?", (json.dumps(members), team_id))
    conn.commit()
    conn.close()
    log_audit("TEAM_LEFT", user.email, team_id, f"Left team {row['name']}")
    return {"status": "success", "message": f"Left team {row['name']}"}

@event_router.post("/settings")
def update_event_settings(settings: dict, user: UserPrincipal = Depends(require_auth)):
    if user.role not in ("organizer", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden: Only organizers can adjust event settings")

    conn = get_db()
    cursor = conn.cursor()

    name = settings.get("name")
    close_ts = settings.get("submissions_close")
    weights = settings.get("weights")
    weights_json = json.dumps(weights) if weights else None

    if name:
        cursor.execute("UPDATE events SET name = ?", (name,))
    if close_ts:
        cursor.execute("UPDATE events SET submissions_close = ?", (close_ts,))
    if weights_json:
        cursor.execute("UPDATE events SET weights = ?", (weights_json,))

    conn.commit()
    conn.close()

    log_audit("EVENT_SETTINGS_UPDATED", user.email, "evt_01", f"Updated settings: {settings}")
    return {"status": "updated", "settings": settings}


