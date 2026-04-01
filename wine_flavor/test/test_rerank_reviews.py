import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# Integration-style rerank sanity check using the real SIE client:
# prints the query and reranked output, then checks the strongest white review ranks first.

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from engine.sie_rerank import rerank_wines_with_sie_reviews


def main():
    wines = pd.DataFrame(
        [
            {
                "wine_name": "bright-white",
                "winery_name": "test-cellar",
                "vintage_year": "2023",
                "country_name": "France",
                "region_name": "Loire",
                "taste_acidity": 4.0,
                "taste_fizziness": 0.0,
                "taste_intensity": 3.0,
                "taste_sweetness": 1.0,
                "taste_tannin": 0.0,
                "wine_flavors": [
                    {
                        "group": "citrus_fruit",
                        "primary_keywords": [{"name": "orange zest", "count": 3}],
                        "secondary_keywords": [{"name": "floral", "count": 2}],
                    }
                ],
                "wine_reviews": [
                    {"note": "Bright citrus and mineral finish."},
                    {"note": "Crisp floral white with orange zest."},
                ],
            },
            {
                "wine_name": "soft-red",
                "winery_name": "test-cellar",
                "vintage_year": "2022",
                "country_name": "USA",
                "region_name": "California",
                "taste_acidity": 2.0,
                "taste_fizziness": 0.0,
                "taste_intensity": 3.0,
                "taste_sweetness": 3.0,
                "taste_tannin": 2.0,
                "wine_flavors": [
                    {
                        "group": "oak",
                        "primary_keywords": [{"name": "vanilla", "count": 3}],
                        "secondary_keywords": [{"name": "sweet", "count": 2}],
                    }
                ],
                "wine_reviews": [
                    {"note": "Soft red fruit and vanilla."},
                    {"note": "Jammy and sweet."},
                ],
            },
            {
                "wine_name": "no-reviews",
                "winery_name": "test-cellar",
                "vintage_year": "2021",
                "country_name": "Italy",
                "region_name": "Veneto",
                "taste_acidity": 3.0,
                "taste_fizziness": 0.0,
                "taste_intensity": 2.0,
                "taste_sweetness": 2.0,
                "taste_tannin": 1.0,
                "wine_flavors": [],
                "wine_reviews": [],
            },
        ]
    )

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
    all_flavors = ["orange zest", "minerals", "floral", "vanilla", "sweet"]

    print("User query:")
    print(
        "- structure:",
        ", ".join(f"{name}={value}" for name, value in user_preferences["structure"].items()),
    )
    print(
        "- flavors:",
        ", ".join(f"{name}={value}" for name, value in user_preferences["flavors"].items()),
    )

    reranked = rerank_wines_with_sie_reviews(
        wines,
        candidate_row_indices=[0, 1, 2],
        user_preferences=user_preferences,
        all_flavors=all_flavors,
        model_name="BAAI/bge-reranker-v2-m3",
    )

    print("Reranked output:")
    for item in reranked:
        wine_row = wines.iloc[item["row_index"]]
        print(
            f"- row_index={item['row_index']} | "
            f"wine_name={wine_row['wine_name']} | "
            f"rerank_score={item['rerank_score']:.4f} | "
            f"review_count={item['review_count']} | "
            f"rerank_rank={item['rerank_rank']}"
        )

    passed = (
        reranked[0]["row_index"] == 0
        and reranked[0]["rerank_score"] > reranked[1]["rerank_score"]
        and reranked[-1]["row_index"] == 2
        and reranked[-1]["review_count"] == 0
        and reranked[-1]["rerank_score"] == 0.0
        and reranked[0]["query_vector_length"] == 5 + len(all_flavors)
    )

    if passed:
        print("PASS: rerank output favors the white-like reviews and leaves missing reviews at zero.")
        return

    print("FAIL: rerank output did not match the expected ordering.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
