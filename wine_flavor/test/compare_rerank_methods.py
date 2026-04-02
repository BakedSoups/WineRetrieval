import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import datasource
import engine
import pretty_print
import transforms
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

SIE_BASE_URL = os.getenv("CLUSTER_URL")
SIE_API_KEY = os.getenv("API_KEY")
SIE_RERANK_MODEL = os.getenv("SIE_RERANK_MODEL")
SIE_EMBEDDING_MODEL = os.getenv("SIE_EMBEDDING_MODEL")
CUSTOM_RERANK_A = float(os.getenv("CUSTOM_RERANK_A", "0.75"))
CUSTOM_RERANK_NO_REVIEW_PENALTY = float(os.getenv("CUSTOM_RERANK_NO_REVIEW_PENALTY", "0.5"))
COSINE_TOP_K = 5
REVIEWS_PER_WINE = 5
RERANK_MAX_TERMS = 12
REFERENCE_ROW_INDICES = []
FETCH_NUM_PAGES = 5

USER_PREFERENCES = {
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


def validate_config():
    required = {
        "CLUSTER_URL": SIE_BASE_URL,
        "API_KEY": SIE_API_KEY,
        "SIE_RERANK_MODEL": SIE_RERANK_MODEL,
        "SIE_EMBEDDING_MODEL": SIE_EMBEDDING_MODEL,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f"Missing required environment variable(s): {', '.join(missing)}")


def run_no_review_penalty_test():
    wines = pd.DataFrame(
        [
            {
                "wine_id": 1,
                "wine_name": "reviewed-white",
                "winery_name": "test-cellar",
                "vintage_year": "2023",
                "rating_average": 4.1,
                "country_name": "France",
                "region_name": "Loire",
                "price_amount": 12.0,
                "price_currency": "USD",
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
                    {"note": "Bright citrus and floral finish."},
                    {"note": "Mineral white with crisp orange zest."},
                ],
                "review_count": 2,
            },
            {
                "wine_id": 2,
                "wine_name": "no-review-white",
                "winery_name": "test-cellar",
                "vintage_year": "2022",
                "rating_average": 4.0,
                "country_name": "France",
                "region_name": "Loire",
                "price_amount": 11.0,
                "price_currency": "USD",
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
                "wine_reviews": [],
                "review_count": 0,
            },
        ]
    )

    print("\n--- Custom No-Review Penalty Test ---")
    print(f"Penalty factor: {CUSTOM_RERANK_NO_REVIEW_PENALTY}")
    custom_matches = engine.rerank_wines_with_custom_embeddings(
        wines,
        candidate_row_indices=[0, 1],
        user_preferences=USER_PREFERENCES,
        base_url=SIE_BASE_URL,
        model_name=SIE_EMBEDDING_MODEL,
        a=CUSTOM_RERANK_A,
        no_review_penalty=CUSTOM_RERANK_NO_REVIEW_PENALTY,
    )
    custom_results = pretty_print.build_results_frame(wines, custom_matches)
    pretty_print.print_top_results(custom_results)

    top_row = custom_matches[0]
    no_review_row = next(match for match in custom_matches if match["review_count"] == 0)
    if top_row["review_count"] > 0 and no_review_row["rerank_score"] <= top_row["rerank_score"]:
        print("PASS: no-review penalty lowers the wine without reviews.")
    else:
        print("FAIL: no-review penalty behavior did not match expectations.")
        raise SystemExit(1)


def main():
    validate_config()

    print("User query:")
    print(
        "- structure:",
        ", ".join(f"{name}={value}" for name, value in USER_PREFERENCES["structure"].items()),
    )
    print(
        "- flavors:",
        ", ".join(f"{name}={value}" for name, value in USER_PREFERENCES["flavors"].items()),
    )

    print("\nFetching wines...", flush=True)
    wines = datasource.fetch_vivino_wines(num_pages=FETCH_NUM_PAGES)
    print("Fetching reviews...", flush=True)
    wines = datasource.attach_vivino_reviews(
        wines,
        review_pages=1,
        reviews_per_page=REVIEWS_PER_WINE,
        language="en",
    )

    print("Building vectors...", flush=True)
    unique_flavors = transforms.unique_flavors(wines)
    flavor_idf = engine.build_flavor_idf(wines)
    wine_matrix = engine.build_wine_matrix(wines, unique_flavors, flavor_idf)
    user_vector = engine.build_user_vector(USER_PREFERENCES, unique_flavors, flavor_idf)
    top_matches = engine.cosine_similarity_search(user_vector, wine_matrix, top_k=COSINE_TOP_K)
    candidate_row_indices = [match["row_index"] for match in top_matches]

    print("\nCandidate rows from cosine retrieval:")
    for match in top_matches:
        wine_row = wines.iloc[match["row_index"]]
        print(
            f"- row_index={match['row_index']} | "
            f"wine_id={wine_row['wine_id']} | "
            f"wine_name={wine_row['wine_name']} | "
            f"similarity_score={match['similarity_score']:.4f}"
        )

    print("\nRunning standard reranker...", flush=True)
    standard_matches = engine.rerank_wines_with_sie_reviews(
        wines,
        candidate_row_indices,
        USER_PREFERENCES,
        unique_flavors,
        flavor_idf,
        reference_row_indices=REFERENCE_ROW_INDICES,
        max_terms=RERANK_MAX_TERMS,
        base_url=SIE_BASE_URL,
        model_name=SIE_RERANK_MODEL,
    )
    standard_results = pretty_print.build_results_frame(wines, standard_matches)
    print("\n--- Standard Reranker ---")
    pretty_print.print_top_results(standard_results)

    print("\nRunning custom reranker...", flush=True)
    custom_matches = engine.rerank_wines_with_custom_embeddings(
        wines,
        candidate_row_indices,
        USER_PREFERENCES,
        base_url=SIE_BASE_URL,
        model_name=SIE_EMBEDDING_MODEL,
        a=CUSTOM_RERANK_A,
        no_review_penalty=CUSTOM_RERANK_NO_REVIEW_PENALTY,
    )
    custom_results = pretty_print.build_results_frame(wines, custom_matches)
    print("\n--- Custom Reranker ---")
    pretty_print.print_top_results(custom_results)
    run_no_review_penalty_test()


if __name__ == "__main__":
    main()
