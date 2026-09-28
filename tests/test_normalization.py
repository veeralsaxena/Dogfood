import json
from src.core.normalization import run_normalization
from src.config import BASE_DIR

def test_normalization_fixture_accuracy():
    with open(BASE_DIR / "spec" / "fixtures.json", "r") as f:
        fixtures = json.load(f)

    projects = fixtures["projects"]
    scores = fixtures["scores"]

    res = run_normalization(scores, projects)
    
    assert "mu" in res
    assert 3.0 <= res["mu"] <= 4.5
    assert "k_shrinkage" in res
    assert len(res["rankings"]) > 0

    # Ensure strictly sorted by score
    scores_list = [r["final_score"] for r in res["rankings"]]
    assert scores_list == sorted(scores_list, reverse=True)
