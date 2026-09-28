import io
import csv
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from src.database import get_db, log_audit
from src.core.auth import require_auth, UserPrincipal
from src.core.normalization import run_normalization
from src.core.crypto import sign_bundle

router = APIRouter(prefix="/api/export", tags=["export"])

def get_normalized_data():
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

    cursor.execute("SELECT weights FROM events LIMIT 1")
    event_row = cursor.fetchone()
    weights = json.loads(event_row["weights"]) if event_row and event_row["weights"] else None

    conn.close()
    return run_normalization(raw_scores, projects, weights), projects, raw_scores

@router.get("/results.csv")
def export_csv(user: UserPrincipal = Depends(require_auth)):
    if user.role not in ("organizer", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden: Only organizers can export results")

    norm_res, _, _ = get_normalized_data()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "rank", "project_id", "title", "team_id", "track_id",
        "final_score", "raw_mean", "review_count", "uncertainty_se",
        "ci_lower", "ci_upper"
    ])

    for item in norm_res["rankings"]:
        ci = item.get("ci", [0.0, 0.0])
        writer.writerow([
            item["rank"],
            item["project_id"],
            item["title"],
            item.get("team_id", ""),
            item.get("track_id", ""),
            item["final_score"],
            item["raw_mean"],
            item["review_count"],
            item["uncertainty"],
            ci[0] if len(ci) > 0 else "",
            ci[1] if len(ci) > 1 else ""
        ])

    log_audit("RESULTS_EXPORTED_CSV", user.email, "results.csv", f"Exported {len(norm_res['rankings'])} records")
    return Response(content=output.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=results.csv"
    })

@router.get("/results.json")
def export_json(user: UserPrincipal = Depends(require_auth)):
    if user.role not in ("organizer", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden: Only organizers can export results")

    norm_res, projects, raw_scores = get_normalized_data()
    return {
        "event_id": "evt_01",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "model": "Empirical Bayes Two-Way Fixed Effects with Shrinkage",
        "normalization": norm_res,
        "raw_scores": raw_scores
    }

@router.post("/publish")
def publish_results(user: UserPrincipal = Depends(require_auth)):
    if user.role not in ("organizer", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden: Only organizers can publish results")

    norm_res, projects, raw_scores = get_normalized_data()
    
    payload = {
        "event_id": "evt_01",
        "code_commit": "main-dogfood-release",
        "rubric_weights": {"functionality": 0.4, "quality": 0.3, "innovation": 0.2, "design": 0.1},
        "model_parameters": {
            "mu": norm_res["mu"],
            "k_shrinkage": norm_res["k_shrinkage"],
            "residual_variance": norm_res["residual_variance"]
        },
        "judge_biases": norm_res["judge_biases"],
        "rankings": norm_res["rankings"],
        "raw_scores": raw_scores,
        "published_at": datetime.now(timezone.utc).isoformat()
    }

    canonical_json, sig_hex, pub_hex = sign_bundle(payload)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO published_results (event_id, payload_json, signature_hex, public_key_hex, published_at)
           VALUES (?, ?, ?, ?, ?)""",
        ("evt_01", canonical_json, sig_hex, pub_hex, payload["published_at"])
    )
    conn.commit()
    conn.close()

    log_audit("RESULTS_PUBLISHED_AND_SIGNED", user.email, "evt_01", f"Signature: {sig_hex[:16]}...")
    return {
        "status": "published",
        "signature": sig_hex,
        "public_key": pub_hex,
        "timestamp": payload["published_at"]
    }

@router.get("/verification-bundle")
def get_verification_bundle():
    """Public endpoint returning latest cryptographically signed bundle."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT payload_json, signature_hex, public_key_hex, published_at 
           FROM published_results ORDER BY id DESC LIMIT 1"""
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        # If not published yet, publish default snapshot from fixture
        norm_res, projects, raw_scores = get_normalized_data()
        payload = {
            "event_id": "evt_01",
            "code_commit": "seed-fixture-commit",
            "rubric_weights": {"functionality": 0.4, "quality": 0.3, "innovation": 0.2, "design": 0.1},
            "model_parameters": {
                "mu": norm_res["mu"],
                "k_shrinkage": norm_res["k_shrinkage"],
                "residual_variance": norm_res["residual_variance"]
            },
            "judge_biases": norm_res["judge_biases"],
            "rankings": norm_res["rankings"],
            "raw_scores": raw_scores,
            "published_at": datetime.now(timezone.utc).isoformat()
        }
        canonical_json, sig_hex, pub_hex = sign_bundle(payload)
        return {
            "payload": json.loads(canonical_json),
            "signature": sig_hex,
            "public_key": pub_hex,
            "published_at": payload["published_at"]
        }

    return {
        "payload": json.loads(row["payload_json"]),
        "signature": row["signature_hex"],
        "public_key": row["public_key_hex"],
        "published_at": row["published_at"]
    }
