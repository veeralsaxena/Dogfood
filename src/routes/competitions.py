import json
import re
import secrets
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from pydantic import BaseModel
from src.database import get_db, log_audit
from src.core.auth import get_current_user, require_role, require_auth, UserPrincipal
from src.core.qrcode import generate_offline_svg_qr
from src.core.security import generate_join_code

router = APIRouter(tags=["competitions"])

class CompetitionCreateRequest(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = ""
    submissions_close: str
    weights: Optional[Dict[str, float]] = None
    prize_pool: Optional[str] = None
    tracks: Optional[List[str]] = None

class CompetitionStatusUpdate(BaseModel):
    status: str  # 'draft', 'registration', 'active', 'frozen', 'judging', 'published', 'archived'

class JoinCompetitionRequest(BaseModel):
    join_code: str

def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_-]+', '-', s)
    return s.strip('-')

@router.get("/api/competitions")
def list_competitions():
    """Lists all active and configured competitions with summary metrics."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*,
            (SELECT COUNT(*) FROM projects p WHERE p.event_id = e.id AND p.is_draft = 0) as project_count,
            (SELECT COUNT(*) FROM tracks t WHERE t.event_id = e.id) as track_count,
            (SELECT COUNT(*) FROM event_registrations r WHERE r.event_id = e.id) as participant_count
        FROM events e
        ORDER BY e.submissions_close DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    for r in rows:
        r["weights"] = json.loads(r["weights"]) if r.get("weights") else {}
        r["join_url"] = f"/join/{r['join_code']}" if r.get("join_code") else None
        r["qr_url"] = f"/api/competitions/{r['id']}/qr"
    
    return {"competitions": rows}

@router.post("/api/competitions")
def create_competition(
    payload: CompetitionCreateRequest,
    user: UserPrincipal = Depends(require_role(["organizer", "admin"]))
):
    """Creates a new competition with unique join code, tracks, and criteria weights."""
    event_id = f"evt_{secrets.token_hex(4)}"
    base_slug = payload.slug or slugify(payload.name)
    slug = base_slug

    conn = get_db()
    cursor = conn.cursor()

    # Ensure unique slug
    cursor.execute("SELECT id FROM events WHERE slug = ?", (slug,))
    if cursor.fetchone():
        slug = f"{base_slug}-{secrets.token_hex(2)}"

    join_code = generate_join_code("RAPTOR")
    weights_json = json.dumps(payload.weights or {
        "functionality": 0.4,
        "quality": 0.3,
        "innovation": 0.2,
        "design": 0.1
    })

    cursor.execute(
        """INSERT INTO events (id, name, slug, description, submissions_close, status, weights, organizer_id, join_code, prize_pool)
           VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
        (
            event_id,
            payload.name.strip(),
            slug,
            payload.description.strip(),
            payload.submissions_close,
            weights_json,
            user.id,
            join_code,
            payload.prize_pool or "TBD"
        )
    )

    # Insert tracks if provided
    tracks = payload.tracks or ["General Innovation", "Developer Tools", "Systems & Security"]
    for i, trk_name in enumerate(tracks):
        trk_id = f"trk_{event_id}_{i+1}"
        cursor.execute(
            "INSERT INTO tracks (id, event_id, name, description) VALUES (?, ?, ?, ?)",
            (trk_id, event_id, trk_name, f"Category track: {trk_name}")
        )

    # Register organizer in event
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO event_registrations (event_id, user_id, role, joined_at) VALUES (?, ?, 'organizer', ?)",
        (event_id, user.id, now)
    )

    conn.commit()
    conn.close()

    log_audit("create_competition", user.id, event_id, f"Created {payload.name} (Code: {join_code})")

    return {
        "status": "success",
        "event_id": event_id,
        "slug": slug,
        "join_code": join_code,
        "join_url": f"/join/{join_code}",
        "qr_url": f"/api/competitions/{event_id}/qr",
        "message": f"Competition '{payload.name}' successfully provisioned."
    }

@router.get("/api/competitions/{event_id_or_slug}")
def get_competition_details(event_id_or_slug: str):
    """Retrieves single competition details, tracks, and schedule."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM events WHERE id = ? OR slug = ?",
        (event_id_or_slug, event_id_or_slug)
    )
    event_row = cursor.fetchone()
    if not event_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Competition not found")

    event = dict(event_row)
    event["weights"] = json.loads(event["weights"]) if event.get("weights") else {}

    cursor.execute("SELECT id, name, description FROM tracks WHERE event_id = ?", (event["id"],))
    tracks = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*) as count FROM projects WHERE event_id = ? AND is_draft = 0", (event["id"],))
    proj_count = cursor.fetchone()["count"]

    conn.close()

    event["tracks"] = tracks
    event["project_count"] = proj_count
    event["join_url"] = f"/join/{event.get('join_code', '')}"
    event["qr_url"] = f"/api/competitions/{event['id']}/qr"

    return {"competition": event}

@router.patch("/api/competitions/{event_id_or_slug}/status")
def update_competition_status(
    event_id_or_slug: str,
    payload: CompetitionStatusUpdate,
    user: UserPrincipal = Depends(require_role(["organizer", "admin"]))
):
    """Transitions competition lifecycle state."""
    allowed = {"draft", "registration", "active", "frozen", "judging", "published", "archived"}
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {allowed}")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE events SET status = ? WHERE id = ? OR slug = ?",
        (payload.status, event_id_or_slug, event_id_or_slug)
    )
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Competition not found")

    conn.commit()
    conn.close()

    log_audit("update_status", user.id, event_id_or_slug, f"Transitioned to {payload.status}")
    return {"status": "success", "new_status": payload.status}

@router.post("/api/competitions/join")
def join_competition(
    payload: JoinCompetitionRequest,
    user: UserPrincipal = Depends(require_auth)
):
    """Allows a participant or judge to join a competition using a join code or scanned QR token."""
    code = payload.join_code.strip().upper()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, slug FROM events WHERE UPPER(join_code) = ?", (code,))
    event_row = cursor.fetchone()
    if not event_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Invalid competition join code")

    event_id = event_row["id"]
    event_name = event_row["name"]
    event_slug = event_row["slug"]
    now = datetime.now(timezone.utc).isoformat()

    # Register user (ignore if already registered)
    cursor.execute(
        """INSERT INTO event_registrations (event_id, user_id, role, joined_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(event_id, user_id) DO NOTHING""",
        (event_id, user.id, user.role, now)
    )
    conn.commit()
    conn.close()

    log_audit("join_competition", user.id, event_id, f"Joined as {user.role} via code {code}")

    redirect_url = "/judge" if user.role == "judge" else "/participant/dashboard"
    return {
        "status": "success",
        "event_id": event_id,
        "event_name": event_name,
        "slug": event_slug,
        "role": user.role,
        "redirect_url": redirect_url,
        "message": f"Successfully joined {event_name}!"
    }

@router.get("/api/competitions/{event_id_or_slug}/qr")
def get_competition_qr(request: Request, event_id_or_slug: str):
    """Returns standalone, pure vector SVG QR code for the competition onboarding URL."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, join_code, slug FROM events WHERE id = ? OR slug = ?",
        (event_id_or_slug, event_id_or_slug)
    )
    event_row = cursor.fetchone()
    conn.close()

    if not event_row:
        raise HTTPException(status_code=404, detail="Competition not found")

    base_url = str(request.base_url).rstrip("/")
    join_target = f"{base_url}/join/{event_row['join_code']}"
    svg_data = generate_offline_svg_qr(join_target)

    return Response(content=svg_data, media_type="image/svg+xml")

@router.get("/api/invitations/{token}/qr")
def get_invitation_qr(request: Request, token: str):
    """Returns standalone vector SVG QR code for an onboarding token."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT token FROM invitations WHERE token = ?", (token,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Invitation not found")

    base_url = str(request.base_url).rstrip("/")
    target = f"{base_url}/onboard/{token}"
    svg_data = generate_offline_svg_qr(target)

    return Response(content=svg_data, media_type="image/svg+xml")
