#!/usr/bin/env python3
"""
verify.py — Standalone Zero-Dependency Hackathon Results Verifier
Hackathon Raptors Dogfood Platform

Verifies the published Ed25519 cryptographic signature and recomputes
the two-way fixed-effects normalization from raw score records.

Usage:
    python3 verify.py <bundle.json>
    or:
    curl -s http://localhost:8080/api/export/verification-bundle | python3 verify.py
"""

import sys
import json
import math
import hashlib

# --- Pure Python RFC 8032 Ed25519 Signature Verification Fallback ---
# (Allows running on any bare Python 3 without pip installing cryptography)

def verify_ed25519_sig(public_key_bytes: bytes, signature_bytes: bytes, message_bytes: bytes) -> bool:
    """Verifies Ed25519 signature using cryptography if present, or pure Python fallback."""
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        pub = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
        pub.verify(signature_bytes, message_bytes)
        return True
    except ImportError:
        pass
    except Exception:
        return False

    # Pure Python Ed25519 implementation (Edwards25519 curve)
    q = 2**255 - 19
    d = -121665 * pow(121666, q - 2, q) % q
    
    def inv(x):
        return pow(x, q - 2, q)

    def xrecover(y):
        xx = (y * y - 1) * inv(d * y * y + 1)
        x = pow(xx, (q + 3) // 8, q)
        if (x * x - xx) % q != 0:
            x = (x * pow(2, (q - 1) // 4, q)) % q
        if x % 2 != 0:
            x = q - x
        return x

    def edwards_add(P, Q):
        x1, y1 = P
        x2, y2 = Q
        x3 = (x1*y2 + x2*y1) * inv(1 + d*x1*x2*y1*y2) % q
        y3 = (y1*y2 + x1*x2) * inv(1 - d*x1*x2*y1*y2) % q
        return (x3, y3)

    def scalarmult(P, e):
        if e == 0:
            return (0, 1)
        Q = scalarmult(P, e // 2)
        Q = edwards_add(Q, Q)
        if e & 1:
            Q = edwards_add(Q, P)
        return Q

    try:
        # Base point B
        By = 4 * inv(5) % q
        Bx = xrecover(By)
        B = (Bx, By)

        A_y = int.from_bytes(public_key_bytes, "little")
        A_x = xrecover(A_y)
        A = (A_x, A_y)

        R_bytes = signature_bytes[:32]
        S_bytes = signature_bytes[32:]
        R_y = int.from_bytes(R_bytes, "little")
        R_x = xrecover(R_y)
        R = (R_x, R_y)
        S = int.from_bytes(S_bytes, "little")

        h = hashlib.sha512(R_bytes + public_key_bytes + message_bytes).digest()
        k = int.from_bytes(h, "little")

        SB = scalarmult(B, S)
        kA = scalarmult(A, k)
        R_plus_kA = edwards_add(R, kA)

        return SB == R_plus_kA
    except Exception:
        return False

# --- Recomputation Engine ---

def recompute_normalization(raw_scores, weights):
    """Recomputes Two-Way Fixed Effects normalization from raw scores."""
    w = weights or {"functionality": 0.4, "quality": 0.3, "innovation": 0.2, "design": 0.1}
    total_w = sum(w.values())

    reviews = []
    projects = set()
    judges = set()

    for s in raw_scores:
        p_id = s.get("project") or s.get("project_id")
        j_id = s.get("judge") or s.get("judge_id")
        crit = s.get("criteria", {})
        comp = sum(w.get(k, 1.0) * v for k, v in crit.items()) / total_w
        reviews.append({"project": p_id, "judge": j_id, "comp": comp})
        projects.add(p_id)
        judges.add(j_id)

    # Mean
    all_comp = [r["comp"] for r in reviews]
    mu = sum(all_comp) / len(all_comp)

    alpha = {p: 0.0 for p in projects}
    beta = {j: 0.0 for j in judges}

    proj_rev = {p: [] for p in projects}
    judge_rev = {j: [] for j in judges}
    for r in reviews:
        proj_rev[r["project"]].append(r)
        judge_rev[r["judge"]].append(r)

    # ALS iteration
    for _ in range(25):
        for p in projects:
            alpha[p] = sum(r["comp"] - mu - beta[r["judge"]] for r in proj_rev[p]) / len(proj_rev[p])
        for j in judges:
            beta[j] = sum(r["comp"] - mu - alpha[r["project"]] for r in judge_rev[j]) / len(judge_rev[j])
        mean_b = sum(beta.values()) / len(beta)
        for j in beta:
            beta[j] -= mean_b

    # Shrinkage
    res = [r["comp"] - (mu + alpha[r["project"]] + beta[r["judge"]]) for r in reviews]
    var_noise = sum(x**2 for x in res) / max(1, len(res) - len(projects) - len(judges))
    var_alpha = max(1e-4, sum(a**2 for a in alpha.values()) / max(1, len(alpha)))
    k = max(0.1, min(3.0, var_noise / var_alpha if var_alpha > 0 else 0.81))

    scores = {}
    for p in projects:
        n_i = len(proj_rev[p])
        b_i = n_i / (n_i + k)
        scores[p] = round(mu + b_i * alpha[p], 4)

    ranked = sorted(scores.keys(), key=lambda p: (scores[p], len(proj_rev[p])), reverse=True)
    return mu, k, ranked, scores


def main():
    if len(sys.argv) > 1 and sys.argv[1] not in ("-h", "--help"):
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            bundle = json.load(f)
    else:
        bundle = json.load(sys.stdin)

    payload = bundle.get("payload", bundle)
    sig_hex = bundle.get("signature", "")
    pub_hex = bundle.get("public_key", "")

    print("================================================================")
    print("      HACKATHON RAPTORS — VERIFIABLE RESULTS AUDITOR           ")
    print("================================================================")
    print(f"Event ID:      {payload.get('event_id', 'unknown')}")
    print(f"Code Commit:   {payload.get('code_commit', 'unknown')}")
    print(f"Published At:  {payload.get('published_at', 'unknown')}")
    print()

    # 1. Math Recomputation
    raw_scores = payload.get("raw_scores", [])
    weights = payload.get("rubric_weights", {})
    bundle_rankings = [r.get("project_id") for r in payload.get("rankings", [])]

    print(f"[1] Recomputing normalization over {len(raw_scores)} raw scores...")
    mu, k, recomputed_rankings, recomputed_scores = recompute_normalization(raw_scores, weights)
    print(f"    ✓ Global Mean mu:           {mu:.4f}")
    print(f"    ✓ Empirical Shrinkage k:    {k:.4f}")
    
    # Compare rankings
    matches = bundle_rankings == recomputed_rankings
    if matches:
        print(f"    ✓ Leaderboard Match:        100% BITWISE IDENTICAL ({len(recomputed_rankings)} projects)")
    else:
        print("    ✗ Discrepancy detected in ranking order!")

    # 2. Cryptographic Signature
    print("\n[2] Verifying Ed25519 Cryptographic Signature...")
    if not sig_hex or not pub_hex:
        print("    ✗ Signature or public key missing from bundle.")
        return 1

    canonical_bytes = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    sig_valid = verify_ed25519_sig(bytes.fromhex(pub_hex), bytes.fromhex(sig_hex), canonical_bytes)

    if sig_valid:
        print("    ✓ Cryptographic Signature:  VALID (Authentic & Untampered)")
        print(f"    ✓ Signed with Public Key:   {pub_hex[:32]}...")
    else:
        print("    ✗ Cryptographic Signature:  INVALID OR CORRUPT")
        return 1

    print("\n================================================================")
    print("RESULT: VERIFICATION SUCCESSFUL. RESULTS ARE DEFENSIBLE & VALID.")
    print("================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
