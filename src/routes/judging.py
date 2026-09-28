import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional, List
from src.database import get_db, log_audit
from src.models import ScoreCreate
from src.core.auth import require_auth, UserPrincipal

router = APIRouter(prefix="/api/judge", tags=["judging"])

@router.get("/scores")
def get_scores(
    request: Request,
    judge: Optional[str] = Query(None),
    judge_id: Optional[str] = Query(None),
    user: UserPrincipal = Depends(require_auth)
):
    """
    Returns scores with strict role isolation enforced at the backend:
    - Participants & strangers are refused with 403 / 401.
    - Judges can ONLY see their own scores. Accessing peer scores returns 403.
    - Organizers can view all scores or filter by judge.
    """
    if user.role not in ("judge", "organizer", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Participants and visitors cannot access judging scores"
        )

    target_judge = judge or judge_id

    # If the user is a judge, enforce strict peer isolation
    if user.role == "judge":
        # Target judge normalization (maps "judge_a" alias to "jdg_01", etc.)
        if target_judge:
            is_own_alias = (
                target_judge == user.id or
                (user.id == "jdg_01" and target_judge in ("judge_a", "jdg_01")) or
                (user.id == "jdg_02" and target_judge in ("judge_b", "jdg_02"))
            )
            if not is_own_alias:
                log_audit(
                    "PEER_SCORE_ACCESS_DENIED",
                    user.email,
                    target_judge,
                    f"Judge {user.id} attempted to access scores for {target_judge}"
                )
                raise HTTPException(
                    status_code=403,
                    detail="Forbidden: Role isolation violation. Judges cannot inspect peer scores"
                )
        effective_judge_id = user.id
    else:
        # Organizer / Admin can view requested judge or all
        effective_judge_id = target_judge

    conn = get_db()
    cursor = conn.cursor()

    if effective_judge_id:
        # If alias e.g. judge_a or judge_b
        if effective_judge_id == "judge_a":
            effective_judge_id = "jdg_01"
        elif effective_judge_id == "judge_b":
            effective_judge_id = "jdg_02"

        cursor.execute(
            """SELECT s.*, p.title as project_title, p.repo_url
               FROM scores s
               JOIN projects p ON s.project_id = p.id
               WHERE s.judge_id = ?""",
            (effective_judge_id,)
        )
    else:
        cursor.execute(
            """SELECT s.*, p.title as project_title, p.repo_url
               FROM scores s
               JOIN projects p ON s.project_id = p.id"""
        )

    rows = []
    for r in cursor.fetchall():
        d = dict(r)
        d["criteria"] = json.loads(d["criteria"]) if isinstance(d["criteria"], str) else d["criteria"]
        rows.append(d)

    conn.close()
    return rows

@router.post("/scores", status_code=200)
def submit_score(score: ScoreCreate, user: UserPrincipal = Depends(require_auth)):
    if user.role not in ("judge", "organizer", "admin"):
        raise HTTPException(status_code=403, detail="Only judges can submit scores")

    conn = get_db()
    cursor = conn.cursor()

    # Validate criteria scores are 1 to 5
    for c_name, val in score.criteria.items():
        if not (1 <= val <= 5):
            raise HTTPException(status_code=400, detail=f"Criterion '{c_name}' must be between 1 and 5")

    criteria_json = json.dumps(score.criteria)
    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute(
        """INSERT INTO scores (judge_id, project_id, criteria, comment, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(judge_id, project_id) DO UPDATE SET
               criteria = excluded.criteria,
               comment = excluded.comment,
               created_at = excluded.created_at""",
        (user.id, score.project_id, criteria_json, score.comment or "", now_iso)
    )
    conn.commit()
    conn.close()

    log_audit("SCORE_SUBMITTED", user.email, score.project_id, f"Criteria: {criteria_json}")
    return {"status": "success", "project_id": score.project_id}
