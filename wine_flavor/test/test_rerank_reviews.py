import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pandas as pd

# Validates review-based reranking with a mocked SIE client:
# better review matches should rank higher, and missing reviews should score zero.

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.sie_rerank import rerank_wines_with_sie_reviews


class FakeSIEClient:
    def __init__(self, base_url, api_key=None):
        self.base_url = base_url
        self.api_key = api_key

    def score(self, model_name, query, items, gpu=None, wait_for_capacity=True, provision_timeout_s=900):
        scores = []
        for rank, item in enumerate(items):
            text = item["text"].lower()
            if any(keyword in text for keyword in ["citrus", "mineral", "floral", "orange zest", "crisp"]):
                score = 0.9
            elif any(keyword in text for keyword in ["vanilla", "jammy", "sweet"]):
                score = 0.2
            else:
                score = 0.1

            scores.append(
                {
                    "item_id": item["id"],
                    "score": score,
                    "rank": rank,
                }
            )

        return {"scores": scores}


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

    fake_module = types.ModuleType("sie_sdk")
    fake_module.SIEClient = FakeSIEClient

    with patch.dict(sys.modules, {"sie_sdk": fake_module}):
        with patch.dict(os.environ, {"API_KEY": "test-api-key"}, clear=False):
            reranked = rerank_wines_with_sie_reviews(
                wines,
                candidate_row_indices=[0, 1, 2],
                user_preferences=user_preferences,
                all_flavors=all_flavors,
                base_url="http://test-sie",
                model_name="BAAI/bge-reranker-v2-m3",
            )

    print("User query:")
    print(
        "- structure:",
        ", ".join(f"{name}={value}" for name, value in user_preferences["structure"].items()),
    )
    print(
        "- flavors:",
        ", ".join(f"{name}={value}" for name, value in user_preferences["flavors"].items()),
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

    assert reranked[0]["row_index"] == 0
    assert reranked[0]["rerank_score"] > reranked[1]["rerank_score"]
    assert reranked[-1]["row_index"] == 2
    assert reranked[-1]["review_count"] == 0
    assert reranked[-1]["rerank_score"] == 0.0
    assert reranked[0]["query_vector_length"] == 5 + len(all_flavors)
    print("PASS: review rerank prefers stronger review matches and handles missing reviews.")


if __name__ == "__main__":
    main()
