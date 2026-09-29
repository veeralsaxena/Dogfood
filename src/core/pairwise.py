import math
import random
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

def solve_bradley_terry(comparisons: List[Tuple[str, str]], max_iter: int = 50, tol: float = 1e-6) -> Dict[str, float]:
    """
    Solves Bradley-Terry model via Minorization-Maximization:
    comparisons: list of (winner_id, loser_id)
    Returns: mapping of project_id -> latent skill score pi_i (normalized to sum=100)
    """
    if not comparisons:
        return {}

    items = list(set([w for w, l in comparisons] + [l for w, l in comparisons]))
    item_idx = {item: i for i, item in enumerate(items)}
    n = len(items)

    # Wins matrix W[i, j] = number of times i beat j
    W = [[0 for _ in range(n)] for _ in range(n)]
    wins = [0 for _ in range(n)]

    for w, l in comparisons:
        i, j = item_idx[w], item_idx[l]
        W[i][j] += 1
        wins[i] += 1

    # Total pairwise matchups N[i, j]
    N = [[W[i][j] + W[j][i] for j in range(n)] for i in range(n)]

    # Initial skill values pi_i = 1.0
    pi = [1.0] * n

    for _ in range(max_iter):
        new_pi = [0.0] * n
        max_delta = 0.0

        for i in range(n):
            denom = 0.0
            for j in range(n):
                if i != j and N[i][j] > 0:
                    denom += N[i][j] / (pi[i] + pi[j])
            
            # Smoothing with Laplace prior to avoid division by zero or zero skill
            w_smoothed = wins[i] + 0.5
            denom_smoothed = denom + 0.5 / pi[i]
            new_val = w_smoothed / denom_smoothed if denom_smoothed > 0 else 1.0
            max_delta = max(max_delta, abs(new_val - pi[i]))
            new_pi[i] = new_val

        # Normalize so mean = 1.0
        mean_val = sum(new_pi) / n
        pi = [v / mean_val for v in new_pi]

        if max_delta < tol:
            break

    # Scale to 0-100 score
    max_pi = max(pi) if pi else 1.0
    min_pi = min(pi) if pi else 0.0
    
    result = {}
    for item, i in item_idx.items():
        if max_pi == min_pi:
            scaled = 50.0
        else:
            scaled = 50.0 + 50.0 * ((pi[i] - min_pi) / (max_pi - min_pi))
        result[item] = round(scaled, 2)

    return result


def select_arena_pair(projects: List[dict], track_filter: Optional[str] = None) -> Tuple[dict, dict]:
    """
    Selects two candidate projects for head-to-head evaluation.
    - If track_filter is provided and that track has >= 2 projects, sample 2 distinct projects from that track.
    - If track_filter is provided and track has < 2 projects, raises ValueError.
    - If track_filter is None: group projects by track_id. Identify tracks with >= 2 projects.
      If any exist, randomly pick one such track and sample 2 projects from it (prioritizing intra-track pairings).
      If no track has >= 2 projects, sample 2 projects uniformly from all projects.
    """
    if not projects or len(projects) < 2:
        raise ValueError("Insufficient projects to form a pair")

    if track_filter:
        candidates = [p for p in projects if p.get("track_id") == track_filter or p.get("track") == track_filter]
        if len(candidates) >= 2:
            return tuple(random.sample(candidates, 2))
        raise ValueError(f"Insufficient projects in track {track_filter} to form a pair (found {len(candidates)})")

    # Group by track_id
    tracks = defaultdict(list)
    for p in projects:
        tid = p.get("track_id") or p.get("track")
        tracks[tid].append(p)

    valid_tracks = [t for t, p_list in tracks.items() if len(p_list) >= 2]
    if valid_tracks:
        chosen_track = random.choice(valid_tracks)
        return tuple(random.sample(tracks[chosen_track], 2))

    return tuple(random.sample(projects, 2))

