import json
import random
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from src.database import get_db
from src.config import BASE_DIR
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

    return templates.TemplateResponse("gallery.html", {
        "request": request,
        "active_page": "gallery",
        "projects": projects,
        "tracks": tracks,
        "selected_track": track,
        "search_query": search
    })

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

    conn.close()

    normalization = run_normalization(raw_scores, projects, weights)

    stats = {
        "total_projects": len(projects),
        "total_judges": len(judges),
        "total_scores": len(raw_scores)
    }

    return templates.TemplateResponse("war_room.html", {
        "request": request,
        "active_page": "war_room",
        "projects": projects,
        "judges": judges,
        "stats": stats,
        "normalization": normalization
    })

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

    return templates.TemplateResponse("arena.html", {
        "request": request,
        "active_page": "arena",
        "pair": pair,
        "rankings": rankings
    })

@router.get("/judge", response_class=HTMLResponse)
def judge_portal_view(request: Request):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, summary, repo_url, track_id FROM projects WHERE is_draft = 0")
    projects = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return templates.TemplateResponse("judge_portal.html", {
        "request": request,
        "active_page": "judge",
        "projects": projects
    })

@router.get("/audit", response_class=HTMLResponse)
def audit_view(request: Request):
    _, pub_key = get_or_create_keys()
    pub_bytes = pub_key.public_bytes(
        encoding=__import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding']).Encoding.Raw,
        format=__import__('cryptography.hazmat.primitives.serialization', fromlist=['PublicFormat']).PublicFormat.Raw
    )

    return templates.TemplateResponse("audit.html", {
        "request": request,
        "active_page": "audit",
        "public_key": pub_bytes.hex()
    })
