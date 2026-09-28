import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from typing import List, Optional
from src.database import get_db, log_audit
from src.models import ProjectCreate, ProjectResponse
from src.core.auth import get_current_user, require_auth, UserPrincipal

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
    cursor.execute("SELECT submissions_close FROM events LIMIT 1")
    event_row = cursor.fetchone()
    if event_row:
        close_str = event_row["submissions_close"]
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
    cursor.execute(
        """INSERT INTO projects (id, team_id, track_id, title, summary, description, repo_url, demo_url, submitted_at, is_draft)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            new_id,
            project.team_id or "tm_user",
            project.track_id or "trk_01",
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

@team_router.post("/join/{invite_code}")
def join_team_by_code(invite_code: str, body: dict):
    email = body.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM teams WHERE invite_code = ?", (invite_code,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Team invite code not found")

    members = json.loads(row["members"])
    if len(members) >= 4:
        conn.close()
        raise HTTPException(status_code=400, detail="Team is already full (maximum 4 members)")

    if email not in members:
        members.append(email)
        cursor.execute("UPDATE teams SET members = ? WHERE id = ?", (json.dumps(members), row["id"]))
        conn.commit()

    conn.close()
    log_audit("TEAM_JOINED", email, row["id"], f"Joined team {row['name']}")
    return {"status": "success", "team_id": row["id"], "team_name": row["name"], "members": members}

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


