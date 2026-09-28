import json
import random
from fastapi import APIRouter, Request, Query, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from src.database import get_db
from src.config import BASE_DIR, TEST_TOKENS
from src.core.auth import get_current_user, authenticate_user
from src.core.normalization import run_normalization
from src.core.pairwise import solve_bradley_terry
from src.core.crypto import get_or_create_keys

router = APIRouter(tags=["web_pages"])
templates = Jinja2Templates(directory=str(BASE_DIR / "src" / "templates"))

@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return RedirectResponse(url="/projects")

@router.get("/projects", response_class=HTMLResponse)
def gallery_view(request: Request, track: str = Query(None), search: str = Query(None)):
    conn = get_db()
    cursor = conn.cursor()

    # Tracks
    cursor.execute("SELECT id, name FROM tracks ORDER BY id ASC")
    tracks = [dict(r) for r in cursor.fetchall()]

    # Projects
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

    query += " ORDER BY p.submitted_at ASC"
    cursor.execute(query, params)
    projects = [dict(r) for r in cursor.fetchall()]
    conn.close()

    user = get_current_user(request)
    return templates.TemplateResponse(
        request=request,
        name="gallery.html",
        context={
            "active_page": "gallery",
            "projects": projects,
            "tracks": tracks,
            "selected_track": track,
            "search_query": search,
            "user": user
        }
    )

@router.get("/war-room", response_class=HTMLResponse)
def war_room_view(request: Request):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, team_id as team, track_id as track, title, repo_url FROM projects WHERE is_draft = 0")
    projects = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT judge_id, project_id, criteria, comment FROM scores")
    raw_scores = []
    for r in cursor.fetchall():
        d = dict(r)
        d["criteria"] = json.loads(d["criteria"]) if isinstance(d["criteria"], str) else d["criteria"]
        raw_scores.append(d)

    cursor.execute("SELECT id, name, tracks FROM users WHERE role = 'judge'")
    judges = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT weights FROM events LIMIT 1")
    event_row = cursor.fetchone()
    weights = json.loads(event_row["weights"]) if event_row and event_row["weights"] else None

    cursor.execute("SELECT id, name FROM tracks ORDER BY id ASC")
    tracks = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM invitations ORDER BY created_at DESC LIMIT 10")
    invitations = [dict(r) for r in cursor.fetchall()]
    for inv in invitations:
        inv["tracks"] = json.loads(inv["tracks"]) if inv.get("tracks") else []

    cursor.execute("SELECT id, name, email, role, tracks FROM users ORDER BY role, name LIMIT 25")
    all_users = [dict(r) for r in cursor.fetchall()]
    for u in all_users:
        u["tracks"] = json.loads(u["tracks"]) if u.get("tracks") else []

    conn.close()

    normalization = run_normalization(raw_scores, projects, weights)

    stats = {
        "total_projects": len(projects),
        "total_judges": len(judges),
        "total_scores": len(raw_scores)
    }

    user = get_current_user(request)
    return templates.TemplateResponse(
        request=request,
        name="war_room.html",
        context={
            "active_page": "war_room",
            "projects": projects,
            "judges": judges,
            "stats": stats,
            "normalization": normalization,
            "tracks": tracks,
            "invitations": invitations,
            "all_users": all_users,
            "user": user
        }
    )

@router.get("/arena", response_class=HTMLResponse)
def arena_view(request: Request):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, summary, repo_url, track_id FROM projects WHERE is_draft = 0")
    projects = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT winner_id, loser_id FROM pairwise_votes")
    votes = [(r["winner_id"], r["loser_id"]) for r in cursor.fetchall()]
    conn.close()

    pair = None
    if len(projects) >= 2:
        sampled = random.sample(projects, 2)
        pair = {"project_a": sampled[0], "project_b": sampled[1]}

    bt_scores = solve_bradley_terry(votes)
    proj_dict = {p["id"]: p for p in projects}
    sorted_ranks = sorted(bt_scores.items(), key=lambda item: item[1], reverse=True)

    rankings = []
    for rank, (pid, score) in enumerate(sorted_ranks, 1):
        p = proj_dict.get(pid, {})
        rankings.append({
            "rank": rank,
            "project_id": pid,
            "title": p.get("title", pid),
            "skill_score": score
        })

    user = get_current_user(request)
    return templates.TemplateResponse(
        request=request,
        name="arena.html",
        context={
            "active_page": "arena",
            "pair": pair,
            "rankings": rankings,
            "user": user
        }
    )

@router.get("/judge", response_class=HTMLResponse)
@router.get("/judge/dashboard", response_class=HTMLResponse)
def judge_portal_view(request: Request):
    user = get_current_user(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, summary, repo_url, track_id FROM projects WHERE is_draft = 0")
    projects = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Prioritize projects matching judge's tracks if available
    if user and user.tracks:
        projects.sort(key=lambda p: 0 if p.get("track_id") in user.tracks else 1)

    return templates.TemplateResponse(
        request=request,
        name="judge_portal.html",
        context={
            "active_page": "judge",
            "projects": projects,
            "user": user
        }
    )

@router.get("/audit", response_class=HTMLResponse)
def audit_view(request: Request):
    user = get_current_user(request)
    _, pub_key = get_or_create_keys()
    pub_bytes = pub_key.public_bytes(
        encoding=__import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding']).Encoding.Raw,
        format=__import__('cryptography.hazmat.primitives.serialization', fromlist=['PublicFormat']).PublicFormat.Raw
    )

    return templates.TemplateResponse(
        request=request,
        name="audit.html",
        context={
            "active_page": "audit",
            "public_key": pub_bytes.hex(),
            "user": user
        }
    )

@router.get("/submit", response_class=HTMLResponse)
def submit_view(request: Request):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events LIMIT 1")
    event = dict(cursor.fetchone() or {})
    cursor.execute("SELECT id, name FROM tracks ORDER BY id ASC")
    tracks = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT id, name FROM teams ORDER BY id ASC")
    teams = [dict(r) for r in cursor.fetchall()]
    conn.close()

    user = get_current_user(request)
    return templates.TemplateResponse(
        request=request,
        name="submit.html",
        context={
            "active_page": "submit",
            "event": event,
            "tracks": tracks,
            "teams": teams,
            "user": user
        }
    )

@router.get("/team/join/{invite_code}", response_class=HTMLResponse)
def team_join_view(request: Request, invite_code: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM teams WHERE invite_code = ?", (invite_code,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Team invitation not found or expired")

    team = dict(row)
    members = json.loads(team.get("members", "[]"))
    user = get_current_user(request)

    return templates.TemplateResponse(
        request=request,
        name="team_invite.html",
        context={
            "active_page": "team",
            "team": team,
            "members": members,
            "user": user
        }
    )

@router.get("/settings", response_class=HTMLResponse)
@router.get("/event-settings", response_class=HTMLResponse)
def event_settings_view(request: Request):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events LIMIT 1")
    event = dict(cursor.fetchone() or {})
    weights = json.loads(event.get("weights", "{}")) if event.get("weights") else {}
    conn.close()

    user = get_current_user(request)
    return templates.TemplateResponse(
        request=request,
        name="event_settings.html",
        context={
            "active_page": "settings",
            "event": event,
            "weights": weights,
            "user": user
        }
    )

@router.get("/certificates/{project_id}")
def certificate_view(project_id: str):
    from fastapi.responses import Response
    from src.core.certificates import generate_svg_certificate
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT p.id, p.title, tm.name as team_name 
           FROM projects p 
           LEFT JOIN teams tm ON p.team_id = tm.id 
           WHERE p.id = ?""",
        (project_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Project not found")

    svg_content = generate_svg_certificate(
        project_id=row["id"],
        title=row["title"],
        team_name=row["team_name"] or "Engineering Team",
        rank=1
    )
    return Response(content=svg_content, media_type="image/svg+xml")

@router.get("/embed/gallery", response_class=HTMLResponse)
def embed_gallery_view(request: Request):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, summary, track_id FROM projects WHERE is_draft = 0")
    projects = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="embed_gallery.html",
        context={"projects": projects}
    )

@router.get("/vote", response_class=HTMLResponse)
def community_voting_view(request: Request):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, summary, track_id, repo_url FROM projects WHERE is_draft = 0")
    projects = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Tier 3 requirement: Fisher-Yates shuffle to counteract primacy/positional bias
    random.shuffle(projects)

    user = get_current_user(request)
    return templates.TemplateResponse(
        request=request,
        name="voting.html",
        context={
            "active_page": "vote",
            "projects": projects,
            "user": user
        }
    )

@router.get("/api/auth/me")
def auth_me(request: Request):
    user = get_current_user(request)
    if not user:
        return {"authenticated": False, "role": "visitor", "name": "Anonymous Visitor"}
    return {
        "authenticated": True,
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "tracks": user.tracks
    }

@router.post("/api/auth/switch-role")
def auth_switch_role(payload: dict, response: Response):
    role = payload.get("role", "visitor")
    token_map = {
        "organizer": TEST_TOKENS["organizer"],
        "judge_a": TEST_TOKENS["judge_a"],
        "judge_b": TEST_TOKENS["judge_b"],
        "participant": TEST_TOKENS["participant"],
    }
    if role in token_map:
        tok = token_map[role]
        response.set_cookie(key="session", value=tok, path="/", httponly=False)
        return {"status": "success", "role": role, "token": tok}
    else:
        response.delete_cookie(key="session", path="/")
        return {"status": "success", "role": "visitor", "token": None}

class LoginRequest(BaseModel):
    email: str
    password: str

@router.get("/login", response_class=HTMLResponse)
def login_view(request: Request):
    user = get_current_user(request)
    if user:
        if user.role == "participant":
            return RedirectResponse(url="/participant/dashboard", status_code=303)
        elif user.role == "judge":
            return RedirectResponse(url="/judge", status_code=303)
        elif user.role in ("organizer", "admin"):
            return RedirectResponse(url="/war-room", status_code=303)
        else:
            return RedirectResponse(url="/projects", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "active_page": "login",
            "user": None
        }
    )

@router.post("/api/auth/login")
def auth_login(payload: LoginRequest, response: Response):
    auth_result = authenticate_user(payload.email, payload.password)
    if not auth_result:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    principal, token = auth_result
    response.set_cookie(key="session", value=token, path="/", httponly=False)

    if principal.role == "participant":
        redirect_url = "/participant/dashboard"
    elif principal.role == "judge":
        redirect_url = "/judge"
    elif principal.role in ("organizer", "admin"):
        redirect_url = "/war-room"
    else:
        redirect_url = "/projects"

    return {
        "status": "success",
        "token": token,
        "user": {
            "id": principal.id,
            "name": principal.name,
            "email": principal.email,
            "role": principal.role
        },
        "redirect_url": redirect_url
    }

@router.get("/logout")
def logout_view():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="session", path="/")
    return response

@router.get("/participant/dashboard", response_class=HTMLResponse)
def participant_dashboard_view(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events LIMIT 1")
    event_row = cursor.fetchone()
    event = dict(event_row or {})

    # Check teams
    cursor.execute("SELECT * FROM teams")
    teams = [dict(r) for r in cursor.fetchall()]
    user_team = None
    team_members = []
    for t in teams:
        members = json.loads(t.get("members", "[]")) if t.get("members") else []
        if any(user.email.lower() == str(m).lower() or user.name.lower() == str(m).lower() for m in members):
            user_team = t
            team_members = members
            break

    if not user_team and teams:
        user_team = teams[0]
        team_members = json.loads(user_team.get("members", "[]")) if user_team.get("members") else []

    project = None
    if user_team:
        cursor.execute("SELECT * FROM projects WHERE team_id = ? ORDER BY id DESC LIMIT 1", (user_team["id"],))
        p_row = cursor.fetchone()
        if p_row:
            project = dict(p_row)

    if not project:
        cursor.execute("SELECT * FROM projects ORDER BY id DESC LIMIT 1")
        p_row = cursor.fetchone()
        if p_row:
            project = dict(p_row)

    track = None
    if project and project.get("track_id"):
        cursor.execute("SELECT * FROM tracks WHERE id = ?", (project["track_id"],))
        tr_row = cursor.fetchone()
        if tr_row:
            track = dict(tr_row)

    cursor.execute("SELECT id, name FROM tracks ORDER BY id ASC")
    tracks = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="participant_dashboard.html",
        context={
            "active_page": "participant_dash",
            "user": user,
            "event": event,
            "team": user_team,
            "team_members": team_members,
            "project": project,
            "track": track,
            "tracks": tracks
        }
    )

@router.get("/onboard/{token}", response_class=HTMLResponse)
def onboard_view(request: Request, token: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invitations WHERE token = ?", (token,))
    inv_row = cursor.fetchone()
    cursor.execute("SELECT * FROM events LIMIT 1")
    event_row = cursor.fetchone()
    conn.close()

    if not inv_row:
        raise HTTPException(status_code=404, detail="Invitation link not found or expired")

    inv = dict(inv_row)
    if inv.get("used_at"):
        raise HTTPException(status_code=400, detail="This invitation link has already been used.")

    event = dict(event_row or {})
    tracks = json.loads(inv["tracks"]) if inv.get("tracks") else []

    return templates.TemplateResponse(
        request=request,
        name="onboard.html",
        context={
            "token": token,
            "invitation": inv,
            "tracks": tracks,
            "event": event,
            "user": get_current_user(request)
        }
    )

@router.get("/profile", response_class=HTMLResponse)
def profile_view(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "active_page": "profile",
            "user": user
        }
    )


