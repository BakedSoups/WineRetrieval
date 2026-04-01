import sys
import runpy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import datasource
import engine
import transforms

FETCH_NUM_PAGES = 5
TOP_K = 5


def run_crisp_white_sanity_test():
    print("Running crisp white vector sanity test...", flush=True)

    wines = datasource.fetch_vivino_wines(num_pages=FETCH_NUM_PAGES)
    unique_flavors = transforms.unique_flavors(wines)
    flavor_idf = engine.build_flavor_idf(wines)
    wine_matrix = engine.build_wine_matrix(wines, unique_flavors, flavor_idf)

    user_preferences = {
        "structure": {
            "acidity": 0.8,
            "fizziness": 0.1,
            "intensity": 0.5,
            "sweetness": 0.2,
            "tannin": 0.1,
        },
        "flavors": {
            "orange zest": 1.0,
            "minerals": 0.8,
            "floral": 0.6,
        },
    }

    user_vector = engine.build_user_vector(user_preferences, unique_flavors, flavor_idf)
    top_matches = engine.cosine_similarity_search(user_vector, wine_matrix, top_k=TOP_K)
    top_rows = wines.iloc[[match["row_index"] for match in top_matches]]

    white_like_hits = 0
    inspected = []
    for _, wine_row in top_rows.iterrows():
        label = " ".join(
            str(part).lower()
            for part in [
                wine_row.get("wine_name") or "",
                wine_row.get("style_name") or "",
            ]
        )
        inspected.append(
            {
                "wine_id": int(wine_row["wine_id"]),
                "wine_name": wine_row.get("wine_name"),
                "style_name": wine_row.get("style_name"),
            }
        )
        if any(keyword in label for keyword in ["chardonnay", "sauvignon", "chenin", "white", "riesling", "pinot grigio"]):
            white_like_hits += 1

    print("Top cosine matches:")
    for item in inspected:
        print(f"- {item['wine_id']} | {item['wine_name']} | {item['style_name']}")

    if white_like_hits >= 3:
        print("PASS: crisp white query returns mostly white-like wines.")
        return True

    print("FAIL: crisp white query does not return enough white-like wines.")
    return False


def run_review_rerank_test():
    print("Running review rerank sanity test...", flush=True)
    runpy.run_path(str(PROJECT_ROOT / "test" / "test_rerank_reviews.py"), run_name="__main__")
    return True


if __name__ == "__main__":
    success = run_crisp_white_sanity_test()
    if success:
        success = run_review_rerank_test()
    raise SystemExit(0 if success else 1)
