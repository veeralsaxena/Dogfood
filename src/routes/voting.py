import random
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Optional
from src.database import get_db, log_audit
from src.models import CommentCreate, CommunityVoteCreate, PairwiseVoteCreate
from src.core.auth import get_current_user, require_auth, UserPrincipal
from src.core.anti_abuse import voting_limiter
from src.core.pairwise import solve_bradley_terry

router = APIRouter(prefix="/api", tags=["voting_and_community"])

@router.get("/ballot")
def get_randomized_ballot():
    """Returns randomized project order to prevent position bias."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, summary, track_id FROM projects WHERE is_draft = 0")
    projects = [dict(r) for r in cursor.fetchall()]
    conn.close()

    random.shuffle(projects)
    return projects

@router.post("/vote")
def cast_community_vote(vote: CommunityVoteCreate, request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=401, 
            detail="Authentication required: Please sign in or register to cast your verified community vote."
        )

    client_ip = request.client.host if request.client else "127.0.0.1"
    voter_token = user.id

    # Rate limiting (anti-abuse)
    if not voting_limiter.is_allowed(voter_token):
        raise HTTPException(status_code=429, detail="Too many votes cast. Please slow down.")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, event_id FROM projects WHERE id = ?", (vote.project_id,))
    proj = cursor.fetchone()
    if not proj:
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")

    event_id = proj["event_id"] or "evt_01"
    now_iso = datetime.now(timezone.utc).isoformat()

    # Check for existing ballot by this user in this competition
    cursor.execute(
        "SELECT id, project_id FROM ballots WHERE event_id = ? AND voter_token = ?",
        (event_id, voter_token)
    )
    existing = cursor.fetchone()

    if existing:
        if existing["project_id"] == vote.project_id:
            conn.close()
            return {
                "status": "success",
                "message": f"Your ballot is already confirmed for {proj['title']}.",
                "project_id": vote.project_id,
                "already_selected": True
            }
        else:
            # Transfer ballot from previously selected project to new project
            cursor.execute(
                "UPDATE ballots SET project_id = ?, voter_ip = ?, created_at = ? WHERE id = ?",
                (vote.project_id, client_ip, now_iso, existing["id"])
            )
            conn.commit()
            conn.close()
            log_audit("COMMUNITY_VOTE_TRANSFERRED", user.name, vote.project_id, f"Transferred vote to {proj['title']}")
            return {
                "status": "success",
                "message": f"Ballot updated! Your vote has been transferred to {proj['title']}.",
                "project_id": vote.project_id,
                "transferred": True
            }
    else:
        cursor.execute(
            """INSERT INTO ballots (event_id, project_id, voter_token, voter_ip, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (event_id, vote.project_id, voter_token, client_ip, now_iso)
        )
        conn.commit()
        conn.close()
        log_audit("COMMUNITY_VOTE_CAST", user.name, vote.project_id, f"Voted for {proj['title']}")
        return {
            "status": "success",
            "message": f"Ballot cast! 1 vote recorded for {proj['title']}.",
            "project_id": vote.project_id,
            "transferred": False
        }

@router.get("/ballot/my-vote")
def get_my_vote(request: Request, event: str = None):
    """Returns the authenticated user's current ballot for the active competition."""
    user = get_current_user(request)
    if not user:
        return {"voted": False, "project_id": None}

    conn = get_db()
    cursor = conn.cursor()
    event_id = event or "evt_01"
    cursor.execute(
        "SELECT project_id, created_at FROM ballots WHERE event_id = ? AND voter_token = ?",
        (event_id, user.id)
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return {"voted": True, "project_id": row["project_id"], "created_at": row["created_at"]}
    return {"voted": False, "project_id": None}

@router.get("/comments/{project_id}")
def get_comments(project_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM comments WHERE project_id = ? ORDER BY created_at ASC", (project_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@router.post("/comments/{project_id}")
def post_comment(project_id: str, comment: CommentCreate, request: Request):
    user = get_current_user(request)
    author_name = user.name if user else (comment.author_name or "Anonymous")
    author_role = user.role.capitalize() if user else "Visitor"

    conn = get_db()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute(
        """INSERT INTO comments (project_id, author_name, author_role, content, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (project_id, author_name, author_role, comment.content, now_iso)
    )
    conn.commit()
    conn.close()

    log_audit("COMMENT_POSTED", author_name, project_id, comment.content[:50])
    return {"status": "success", "author_name": author_name, "content": comment.content}

# --- Bradley-Terry Pairwise Arena Endpoints ---

@router.get("/arena/pair")
def get_arena_pair():
    """Returns two random projects for head-to-head comparison."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, summary, repo_url, track_id FROM projects WHERE is_draft = 0")
    projects = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if len(projects) < 2:
        raise HTTPException(status_code=400, detail="Not enough projects for comparison")

    pair = random.sample(projects, 2)
    return {"project_a": pair[0], "project_b": pair[1]}

@router.post("/arena/vote")
def cast_pairwise_vote(vote: PairwiseVoteCreate, user: UserPrincipal = Depends(require_auth)):
    if user.role not in ("judge", "organizer", "admin"):
        raise HTTPException(status_code=403, detail="Only judges and organizers can cast pairwise evaluations")

    conn = get_db()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute(
        """INSERT INTO pairwise_votes (judge_id, winner_id, loser_id, created_at)
           VALUES (?, ?, ?, ?)""",
        (user.id, vote.winner_id, vote.loser_id, now_iso)
    )
    conn.commit()
    conn.close()

    log_audit("PAIRWISE_VOTE_CAST", user.email, f"{vote.winner_id} > {vote.loser_id}")
    return {"status": "success", "winner": vote.winner_id, "loser": vote.loser_id}

@router.get("/arena/rankings")
def get_arena_rankings():
    """Computes latent skill score using Bradley-Terry Maximum Likelihood Estimation."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT winner_id, loser_id FROM pairwise_votes")
    votes = [(r["winner_id"], r["loser_id"]) for r in cursor.fetchall()]
    
    cursor.execute("SELECT id, title, track_id FROM projects WHERE is_draft = 0")
    projects = {r["id"]: dict(r) for r in cursor.fetchall()}
    conn.close()

    bt_scores = solve_bradley_terry(votes)

    sorted_ranks = sorted(
        bt_scores.items(),
        key=lambda item: item[1],
        reverse=True
    )

    rankings = []
    for rank, (pid, score) in enumerate(sorted_ranks, 1):
        p = projects.get(pid, {})
        rankings.append({
            "rank": rank,
            "project_id": pid,
            "title": p.get("title", pid),
            "track_id": p.get("track_id", ""),
            "skill_score": score
        })

    return {"model": "Bradley-Terry MM-MLE", "comparisons_evaluated": len(votes), "rankings": rankings}
