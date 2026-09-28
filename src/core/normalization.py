import json
import math
from typing import Dict, List, Any, Tuple

DEFAULT_WEIGHTS = {
    "functionality": 0.4,
    "quality": 0.3,
    "innovation": 0.2,
    "design": 0.1
}

def compute_composite_score(criteria_scores: Dict[str, int], weights: Dict[str, float] = None) -> float:
    """Computes weighted average composite score (1 to 5 scale)."""
    w = weights or DEFAULT_WEIGHTS
    total_w = 0.0
    weighted_sum = 0.0
    for crit, score in criteria_scores.items():
        weight = w.get(crit, 1.0)
        weighted_sum += weight * float(score)
        total_w += weight
    return weighted_sum / total_w if total_w > 0 else 0.0

def run_normalization(raw_scores: List[Dict[str, Any]], projects: List[Dict[str, Any]], weights: Dict[str, float] = None) -> Dict[str, Any]:
    """
    Fits Two-Way Fixed Effects (Additive Model) with Efron-Morris Empirical Bayes Shrinkage:
      Y_{ij} = mu + alpha_i + beta_j + epsilon_{ij}
      sum_j(beta_j) = 0
    Returns ranking, project stats, judge biases, and model parameters.
    """
    if not raw_scores:
        return {
            "rankings": [],
            "mu": 0.0,
            "k_shrinkage": 1.0,
            "judge_biases": {},
            "projects": {}
        }

    # 1. Deduplicate / canonicalize projects
    # Map project ids
    proj_map = {p["id"]: p for p in projects}
    
    # Check for duplicate submissions (same team and repo or same title and team)
    seen_keys = {}
    canonical_proj_id = {}
    for p in projects:
        key = (p.get("team"), p.get("repo_url")) if p.get("team") and p.get("repo_url") else p["id"]
        if key in seen_keys:
            canonical_proj_id[p["id"]] = seen_keys[key]
        else:
            seen_keys[key] = p["id"]
            canonical_proj_id[p["id"]] = p["id"]

    # 2. Extract composite scores
    reviews = []
    judges_set = set()
    projects_set = set()

    for s in raw_scores:
        orig_p_id = s.get("project") or s.get("project_id")
        p_id = canonical_proj_id.get(orig_p_id, orig_p_id)
        j_id = s.get("judge") or s.get("judge_id")
        crit = s.get("criteria", {})
        comp = compute_composite_score(crit, weights)
        
        reviews.append({
            "project_id": p_id,
            "orig_project_id": orig_p_id,
            "judge_id": j_id,
            "composite": comp,
            "comment": s.get("comment", "")
        })
        judges_set.add(j_id)
        projects_set.add(p_id)

    # Global mean mu
    all_scores = [r["composite"] for r in reviews]
    mu = sum(all_scores) / len(all_scores)

    # Initialize effects
    alpha = {p: 0.0 for p in projects_set}
    beta = {j: 0.0 for j in judges_set}

    # Group reviews by project and by judge
    proj_reviews = {p: [] for p in projects_set}
    judge_reviews = {j: [] for j in judges_set}
    for r in reviews:
        proj_reviews[r["project_id"]].append(r)
        judge_reviews[r["judge_id"]].append(r)

    # 3. Iterative estimation of alpha_i and beta_j (Alternating Least Squares)
    max_iters = 25
    tol = 1e-6
    for _ in range(max_iters):
        max_delta = 0.0
        # Update alpha_i (project quality)
        for p, r_list in proj_reviews.items():
            if r_list:
                new_a = sum(r["composite"] - mu - beta[r["judge_id"]] for r in r_list) / len(r_list)
                max_delta = max(max_delta, abs(new_a - alpha[p]))
                alpha[p] = new_a

        # Update beta_j (judge leniency)
        for j, r_list in judge_reviews.items():
            if r_list:
                new_b = sum(r["composite"] - mu - alpha[r["project_id"]] for r in r_list) / len(r_list)
                max_delta = max(max_delta, abs(new_b - beta[j]))
                beta[j] = new_b

        # Center beta so sum(beta_j) = 0
        mean_beta = sum(beta.values()) / len(beta) if beta else 0.0
        for j in beta:
            beta[j] -= mean_beta

        if max_delta < tol:
            break

    # 4. Compute residual variance and project variance for Empirical Bayes Shrinkage
    residuals = []
    for r in reviews:
        p = r["project_id"]
        j = r["judge_id"]
        fitted = mu + alpha[p] + beta[j]
        residuals.append(r["composite"] - fitted)

    var_noise = sum(res ** 2 for res in residuals) / max(1, len(residuals) - len(projects_set) - len(judges_set))
    var_alpha = max(1e-4, sum(a ** 2 for a in alpha.values()) / max(1, len(alpha)))

    # Shrinkage parameter k
    k = var_noise / var_alpha if var_alpha > 0 else 0.81
    # Cap k to reasonable empirical range [0.1, 3.0]
    k = max(0.1, min(3.0, k))

    # 5. Calculate final shrunk scores and confidence bounds
    project_results = {}
    for p in projects_set:
        n_i = len(proj_reviews[p])
        raw_avg = sum(r["composite"] for r in proj_reviews[p]) / n_i if n_i > 0 else mu
        # Shrinkage factor
        b_i = n_i / (n_i + k)
        shrunk_quality = b_i * alpha[p]
        final_score = round(mu + shrunk_quality, 4)
        se = math.sqrt(var_noise / (n_i + k)) if n_i > 0 else 1.0

        project_results[p] = {
            "project_id": p,
            "raw_mean": round(raw_avg, 4),
            "unbiased_alpha": round(alpha[p], 4),
            "shrunk_score": final_score,
            "review_count": n_i,
            "shrinkage_factor": round(b_i, 4),
            "uncertainty_se": round(se, 4),
            "ci_lower": round(final_score - 1.96 * se, 4),
            "ci_upper": round(final_score + 1.96 * se, 4)
        }

    # 6. Build final ranking
    # Sort projects by shrunk_score descending, then by review_count descending
    ranked_ids = sorted(project_results.keys(), key=lambda pid: (project_results[pid]["shrunk_score"], project_results[pid]["review_count"]), reverse=True)

    rankings = []
    for rank, pid in enumerate(ranked_ids, 1):
        res = project_results[pid]
        p_obj = proj_map.get(pid, {})
        rankings.append({
            "rank": rank,
            "project_id": pid,
            "title": p_obj.get("title", pid),
            "team_id": p_obj.get("team"),
            "track_id": p_obj.get("track"),
            "final_score": res["shrunk_score"],
            "raw_mean": res["raw_mean"],
            "review_count": res["review_count"],
            "uncertainty": res["uncertainty_se"],
            "ci": [res["ci_lower"], res["ci_upper"]]
        })

    return {
        "mu": round(mu, 4),
        "k_shrinkage": round(k, 4),
        "residual_variance": round(var_noise, 4),
        "judge_biases": {j: round(b, 4) for j, b in beta.items()},
        "project_details": project_results,
        "rankings": rankings
    }
