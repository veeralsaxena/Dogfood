import json
import random
from datetime import datetime, timezone
from typing import Optional
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

def get_active_event_context(request: Request, event_id_or_slug: str = None):
    conn = get_db()
    cursor = conn.cursor()
    if event_id_or_slug:
        cursor.execute("SELECT * FROM events WHERE id = ? OR slug = ?", (event_id_or_slug, event_id_or_slug))
    else:
        req_event = request.query_params.get("event") or request.query_params.get("org") or request.cookies.get("active_event") or "evt_01"
        cursor.execute("SELECT * FROM events WHERE id = ? OR slug = ?", (req_event, req_event))
    row = cursor.fetchone()
    if not row:
        cursor.execute("SELECT * FROM events ORDER BY id ASC LIMIT 1")
        row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    if d.get("branding"):
        try:
            d["brand"] = json.loads(d["branding"])
        except Exception:
            d["brand"] = {}
    else:
        # Default brand presets based on event
        if d.get("id") == "evt_02" or "raptor" in (d.get("slug") or ""):
            d["brand"] = {
                "brand_name": "HACKATHON RAPTORS",
                "org_name": "Hackathon Raptors Fellowship",
                "tagline": "fellowship championship",
                "accent_color": "#10b981",
                "accent_hover": "#059669",
                "theme_preset": "emerald",
                "crest_icon": "raptors",
                "hero_title": "Frontier AI & Systems Engineering Championship."
            }
        else:
            d["brand"] = {
                "brand_name": "VERITAS",
                "org_name": d.get("name", "Veritas"),
                "tagline": "evaluation platform",
                "accent_color": "#10b981",
                "accent_hover": "#059669",
                "theme_preset": "emerald",
                "crest_icon": "veritas",
                "hero_title": "Software built for rigorous evaluation."
            }
    return d

def get_all_events():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*,
            (SELECT COUNT(*) FROM projects p WHERE p.event_id = e.id AND p.is_draft = 0) as project_count,
            (SELECT COUNT(*) FROM tracks t WHERE t.event_id = e.id) as track_count
        FROM events e
        ORDER BY e.submissions_close DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = get_current_user(request)
    if user:
        if user.role == "participant":
            return RedirectResponse(url="/participant/dashboard")
        elif user.role == "judge":
            return RedirectResponse(url="/judge")
        elif user.role in ("organizer", "admin"):
            return RedirectResponse(url="/war-room")
    return RedirectResponse(url="/competitions")

@router.get("/competitions", response_class=HTMLResponse)
def competitions_list_view(request: Request):
    competitions = get_all_events()
    user = get_current_user(request)
    active_event = get_active_event_context(request)

    return templates.TemplateResponse(
        request=request,
        name="competitions_list.html",
        context={
            "active_page": "competitions",
            "competitions": competitions,
            "user": user,
            "active_event": active_event
        }
    )

@router.get("/c/{slug}", response_class=HTMLResponse)
def competition_detail_view(request: Request, slug: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE slug = ? OR id = ?", (slug, slug))
    event_row = cursor.fetchone()
    if not event_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Competition not found")

    event = dict(event_row)
    weights = json.loads(event["weights"]) if event.get("weights") else {}

    cursor.execute("SELECT id, name, description FROM tracks WHERE event_id = ?", (event["id"],))
    tracks = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT p.*, t.name as track_name
        FROM projects p
        LEFT JOIN tracks t ON p.track_id = t.id
        WHERE (p.event_id = ? OR p.event_id IS NULL) AND p.is_draft = 0
        ORDER BY p.submitted_at ASC
    """, (event["id"],))
    projects = [dict(r) for r in cursor.fetchall()]
    conn.close()

    user = get_current_user(request)
    return templates.TemplateResponse(
        request=request,
        name="competition_detail.html",
        context={
            "active_page": "competitions",
            "event": event,
            "tracks": tracks,
            "weights": weights,
            "projects": projects,
            "user": user,
            "active_event": event
        }
    )

@router.get("/org/{slug}")
def org_portal_view(slug: str):
    """Institutional / White-label direct gateway. Sets active event cookie and routes to the institution's portal."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, slug, name FROM events WHERE slug = ? OR id = ?", (slug, slug))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Institution or competition '{slug}' not found.")
    
    response = RedirectResponse(url=f"/projects?event={row['id']}", status_code=303)
    response.set_cookie(key="active_event", value=row["id"], max_age=86400 * 30, path="/")
    return response

@router.get("/join/{join_code}", response_class=HTMLResponse)
def join_view(request: Request, join_code: str):
    code = join_code.strip().upper()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE UPPER(join_code) = ?", (code,))
    event_row = cursor.fetchone()
    conn.close()

    if not event_row:
        raise HTTPException(status_code=404, detail="Competition not found for this join code")

    event = dict(event_row)
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url=f"/login?join_code={code}", status_code=303)

    # Register user in event
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        """INSERT INTO event_registrations (event_id, user_id, role, joined_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(event_id, user_id) DO NOTHING""",
        (event["id"], user.id, user.role, now)
    )
    conn.commit()
    conn.close()

    redirect_target = f"/judge?event={event['id']}" if user.role == "judge" else f"/participant/dashboard?event={event['id']}"
    response = RedirectResponse(url=redirect_target, status_code=303)
    response.set_cookie(key="active_event", value=event["id"], max_age=86400 * 30, path="/")
    return response

@router.get("/organizer/competitions", response_class=HTMLResponse)
def organizer_competitions_view(request: Request):
    user = get_current_user(request)
    if not user or user.role not in ("organizer", "admin"):
        return RedirectResponse(url="/login", status_code=303)

    competitions = get_all_events()
    active_event = get_active_event_context(request)

    return templates.TemplateResponse(
        request=request,
        name="organizer_competitions.html",
        context={
            "active_page": "org_competitions",
            "competitions": competitions,
            "user": user,
            "active_event": active_event
        }
    )

@router.get("/projects", response_class=HTMLResponse)
def gallery_view(request: Request, track: str = Query(None), search: str = Query(None), event: str = Query(None)):
    conn = get_db()
    cursor = conn.cursor()

    # Tracks
    track_query = "SELECT id, name FROM tracks"
    track_params = []
    if event:
        track_query += " WHERE event_id = ?"
        track_params.append(event)
    track_query += " ORDER BY id ASC"
    cursor.execute(track_query, track_params)
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
    if event:
        query += " AND (p.event_id = ? OR p.event_id IS NULL)"
        params.append(event)
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
    active_event = get_active_event_context(request, event)
    all_events = get_all_events()

    return templates.TemplateResponse(
        request=request,
        name="gallery.html",
        context={
            "active_page": "gallery",
            "projects": projects,
            "tracks": tracks,
            "selected_track": track,
            "selected_event": event,
            "search_query": search,
            "user": user,
            "active_event": active_event,
            "all_events": all_events
        }
    )

@router.get("/war-room", response_class=HTMLResponse)
def war_room_view(request: Request, event: str = Query(None)):
    user = get_current_user(request)
    active_event = get_active_event_context(request, event)
    all_events = get_all_events()

    conn = get_db()
    cursor = conn.cursor()

    proj_query = "SELECT id, team_id as team, track_id as track, title, repo_url FROM projects WHERE is_draft = 0"
    proj_params = []
    if event:
        proj_query += " AND (event_id = ? OR event_id IS NULL)"
        proj_params.append(event)
    cursor.execute(proj_query, proj_params)
    projects = [dict(r) for r in cursor.fetchall()]

    score_query = "SELECT judge_id, project_id, criteria, comment FROM scores"
    score_params = []
    if event:
        score_query += " WHERE (event_id = ? OR event_id IS NULL)"
        score_params.append(event)
    cursor.execute(score_query, score_params)
    raw_scores = []
    for r in cursor.fetchall():
        d = dict(r)
        d["criteria"] = json.loads(d["criteria"]) if isinstance(d["criteria"], str) else d["criteria"]
        raw_scores.append(d)

    cursor.execute("SELECT id, name, tracks FROM users WHERE role = 'judge'")
    judges = [dict(r) for r in cursor.fetchall()]

    weights = json.loads(active_event["weights"]) if active_event and active_event.get("weights") else None

    track_query = "SELECT id, name FROM tracks"
    track_params = []
    if active_event:
        track_query += " WHERE event_id = ?"
        track_params.append(active_event["id"])
    track_query += " ORDER BY id ASC"
    cursor.execute(track_query, track_params)
    tracks = [dict(r) for r in cursor.fetchall()]
    if not tracks:
        cursor.execute("SELECT id, name FROM tracks ORDER BY id ASC LIMIT 10")
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
            "user": user,
            "active_event": active_event,
            "all_events": all_events
        }
    )

@router.get("/arena", response_class=HTMLResponse)
def arena_view(request: Request, event: str = Query(None)):
    conn = get_db()
    cursor = conn.cursor()

    proj_query = "SELECT id, title, summary, repo_url, track_id FROM projects WHERE is_draft = 0"
    proj_params = []
    if event:
        proj_query += " AND (event_id = ? OR event_id IS NULL)"
        proj_params.append(event)
    cursor.execute(proj_query, proj_params)
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
    active_event = get_active_event_context(request, event)

    return templates.TemplateResponse(
        request=request,
        name="arena.html",
        context={
            "active_page": "arena",
            "pair": pair,
            "rankings": rankings,
            "user": user,
            "active_event": active_event
        }
    )

@router.get("/judge", response_class=HTMLResponse)
@router.get("/judge/dashboard", response_class=HTMLResponse)
def judge_portal_view(request: Request, event: str = Query(None)):
    user = get_current_user(request)
    active_event = get_active_event_context(request, event)

    conn = get_db()
    cursor = conn.cursor()
    proj_query = "SELECT id, title, summary, repo_url, track_id FROM projects WHERE is_draft = 0"
    proj_params = []
    if event:
        proj_query += " AND (event_id = ? OR event_id IS NULL)"
        proj_params.append(event)
    cursor.execute(proj_query, proj_params)
    projects = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if user and user.tracks:
        projects.sort(key=lambda p: 0 if p.get("track_id") in user.tracks else 1)

    return templates.TemplateResponse(
        request=request,
        name="judge_portal.html",
        context={
            "active_page": "judge",
            "projects": projects,
            "user": user,
            "active_event": active_event
        }
    )

@router.get("/audit", response_class=HTMLResponse)
def audit_view(request: Request):
    user = get_current_user(request)
    active_event = get_active_event_context(request)
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
            "user": user,
            "active_event": active_event
        }
    )

@router.get("/submit", response_class=HTMLResponse)
def submit_view(request: Request, event: str = Query(None)):
    all_events = get_all_events()
    now_iso = datetime.now(timezone.utc).isoformat()

    # If no event is explicitly requested in query, default to an open competition (where deadline > now)
    if not event:
        open_events = [e for e in all_events if e.get("submissions_close", "") > now_iso]
        if open_events:
            active_event = open_events[0]
        else:
            active_event = get_active_event_context(request, event)
    else:
        active_event = get_active_event_context(request, event)

    conn = get_db()
    cursor = conn.cursor()
    
    # Fetch tracks for the active event
    track_query = "SELECT id, event_id, name FROM tracks"
    track_params = []
    if active_event:
        track_query += " WHERE event_id = ?"
        track_params.append(active_event["id"])
    track_query += " ORDER BY id ASC"
    cursor.execute(track_query, track_params)
    tracks = [dict(r) for r in cursor.fetchall()]
    if not tracks:
        cursor.execute("SELECT id, event_id, name FROM tracks ORDER BY id ASC LIMIT 8")
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
            "event": active_event,
            "tracks": tracks,
            "teams": teams,
            "user": user,
            "active_event": active_event,
            "all_events": all_events,
            "now_iso": now_iso
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
        raise HTTPException(status_code=404, detail="Team invitation not found or expired")

    team = dict(row)
    members = json.loads(team.get("members", "[]"))
    user = get_current_user(request)
    active_event = get_active_event_context(request)

    return templates.TemplateResponse(
        request=request,
        name="team_invite.html",
        context={
            "active_page": "team",
            "team": team,
            "members": members,
            "user": user,
            "active_event": active_event
        }
    )

@router.get("/settings", response_class=HTMLResponse)
@router.get("/event-settings", response_class=HTMLResponse)
def event_settings_view(request: Request, event: str = Query(None)):
    active_event = get_active_event_context(request, event)
    weights = json.loads(active_event.get("weights", "{}")) if active_event and active_event.get("weights") else {}
    user = get_current_user(request)
    all_events = get_all_events()

    return templates.TemplateResponse(
        request=request,
        name="event_settings.html",
        context={
            "active_page": "settings",
            "event": active_event,
            "weights": weights,
            "user": user,
            "active_event": active_event,
            "all_events": all_events
        }
    )

@router.get("/certificates/{project_id}")
def certificate_view(project_id: str):
    from fastapi.responses import Response
    from src.core.certificates import generate_svg_certificate
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT p.id, p.title, p.event_id, tm.name as team_name, e.name as event_name, e.branding 
           FROM projects p 
           LEFT JOIN teams tm ON p.team_id = tm.id 
           LEFT JOIN events e ON p.event_id = e.id
           WHERE p.id = ?""",
        (project_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    brand = {}
    if row["branding"]:
        try:
            brand = json.loads(row["branding"])
        except Exception:
            brand = {}

    org_name = brand.get("org_name") or row["event_name"] or "HACKATHON RAPTORS"
    sub_org = brand.get("sub_org") or f"{brand.get('brand_name', 'VERITAS')} OFFICIAL COMPETITION"
    accent = brand.get("accent_color") or "#10b981"

    svg_content = generate_svg_certificate(
        project_id=row["id"],
        title=row["title"],
        team_name=row["team_name"] or "Engineering Team",
        rank=1,
        org_name=org_name,
        sub_org=sub_org,
        accent_color=accent
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
def community_voting_view(request: Request, event: str = Query(None)):
    active_event = get_active_event_context(request, event)
    conn = get_db()
    cursor = conn.cursor()
    proj_query = "SELECT id, title, summary, track_id, repo_url FROM projects WHERE is_draft = 0"
    proj_params = []
    if event:
        proj_query += " AND (event_id = ? OR event_id IS NULL)"
        proj_params.append(event)
    cursor.execute(proj_query, proj_params)
    projects = [dict(r) for r in cursor.fetchall()]
    conn.close()

    random.shuffle(projects)
    user = get_current_user(request)
    user_voted_project_id = None
    if user:
        event_id = active_event["id"] if active_event else "evt_01"
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT project_id FROM ballots WHERE event_id = ? AND voter_token = ?", (event_id, user.id))
        ballot_row = cursor.fetchone()
        conn.close()
        if ballot_row:
            user_voted_project_id = ballot_row["project_id"]

    return templates.TemplateResponse(
        request=request,
        name="voting.html",
        context={
            "active_page": "vote",
            "projects": projects,
            "user": user,
            "active_event": active_event,
            "user_voted_project_id": user_voted_project_id
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
    join_code: Optional[str] = None

@router.get("/login", response_class=HTMLResponse)
def login_view(request: Request, join_code: str = Query(None)):
    user = get_current_user(request)
    if user:
        if join_code:
            return RedirectResponse(url=f"/join/{join_code}", status_code=303)
        if user.role == "participant":
            return RedirectResponse(url="/participant/dashboard", status_code=303)
        elif user.role == "judge":
            return RedirectResponse(url="/judge", status_code=303)
        elif user.role in ("organizer", "admin"):
            return RedirectResponse(url="/war-room", status_code=303)
        else:
            return RedirectResponse(url="/projects", status_code=303)

    active_event = get_active_event_context(request)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "active_page": "login",
            "user": None,
            "join_code": join_code,
            "active_event": active_event
        }
    )

@router.get("/signup", response_class=HTMLResponse)
def signup_view(request: Request, join_code: str = Query(None)):
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

    active_event = get_active_event_context(request)
    all_events = get_all_events()
    return templates.TemplateResponse(
        request=request,
        name="signup.html",
        context={
            "active_page": "signup",
            "user": None,
            "join_code": join_code or "RAPTOR-2026",
            "active_event": active_event,
            "all_events": all_events
        }
    )

@router.post("/api/auth/login")
def auth_login(payload: LoginRequest, response: Response):
    auth_result = authenticate_user(payload.email, payload.password)
    if not auth_result:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    principal, token = auth_result
    response.set_cookie(key="session", value=token, path="/", httponly=False)

    if payload.join_code:
        redirect_url = f"/join/{payload.join_code}"
    elif principal.role == "participant":
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
def participant_dashboard_view(request: Request, event: str = Query(None)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    active_event = get_active_event_context(request, event)

    conn = get_db()
    cursor = conn.cursor()

    # User teams
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

    track_query = "SELECT id, name FROM tracks"
    track_params = []
    if active_event:
        track_query += " WHERE event_id = ?"
        track_params.append(active_event["id"])
    track_query += " ORDER BY id ASC"
    cursor.execute(track_query, track_params)
    tracks = [dict(r) for r in cursor.fetchall()]
    if not tracks:
        cursor.execute("SELECT id, name FROM tracks ORDER BY id ASC LIMIT 8")
        tracks = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="participant_dashboard.html",
        context={
            "active_page": "participant_dash",
            "user": user,
            "event": active_event,
            "active_event": active_event,
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
    
    if not inv_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Invitation link not found or expired")

    inv = dict(inv_row)
    if inv.get("used_at"):
        conn.close()
        raise HTTPException(status_code=400, detail="This invitation link has already been used.")

    event_id = inv.get("event_id") or "evt_01"
    cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    event_row = cursor.fetchone()
    conn.close()

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
            "active_event": event,
            "user": get_current_user(request)
        }
    )

@router.get("/profile", response_class=HTMLResponse)
def profile_view(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    active_event = get_active_event_context(request)
    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "active_page": "profile",
            "user": user,
            "active_event": active_event
        }
    )
