
import datasource
import engine
import os
import pretty_print
import transforms
from dotenv import load_dotenv

load_dotenv()

SIE_BASE_URL = os.getenv("CLUSTER_URL")
SIE_API_KEY = os.getenv("API_KEY")
SIE_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
ALLOWED_SIE_RERANK_MODELS = {
    "BAAI/bge-reranker-v2-m3",
    "jinaai/jina-reranker-v2-base-multilingual",
}
COSINE_TOP_K = 3
REVIEWS_PER_WINE = 5
RERANK_MAX_TERMS = 12
REFERENCE_ROW_INDICES = []


def validate_sie_config():
    if not SIE_BASE_URL:
        raise ValueError("Missing CLUSTER_URL in the environment.")
    if not SIE_API_KEY:
        raise ValueError("Missing API_KEY in the environment.")


if SIE_RERANK_MODEL not in ALLOWED_SIE_RERANK_MODELS:
    raise ValueError(
        f"Unsupported SIE reranker model '{SIE_RERANK_MODEL}'. "
        f"Choose one of: {sorted(ALLOWED_SIE_RERANK_MODELS)}"
    )


validate_sie_config()

# If you need a broader batch later, uncomment this to print back some IDs.
# datasource.print_vivino_wine_ids(num_pages=3, limit=10)

print("Fetching wines...", flush=True)
wines = datasource.fetch_vivino_wines(num_pages=1)
print("Fetching reviews...", flush=True)
wines = datasource.attach_vivino_reviews(wines, review_pages=1, reviews_per_page=REVIEWS_PER_WINE, language="en")

# get all unique flavors from wine
print("Building vectors...", flush=True)
unique_flavors = transforms.unique_flavors(wines)
flavor_idf = engine.build_flavor_idf(wines)

user_preferences = {
    "structure": {
        "acidity": 0.7,
        "fizziness": 0.0,
        "intensity": 0.8,
        "sweetness": 0.3,
        "tannin": 0.6,
    },
    "flavors": {
        "black cherry": 1.0,
        "plum": 0.9,
        "vanilla": 0.7,
        "oak": 0.6,
        "earthy": 0.8,
    },
}

wine_matrix = engine.build_wine_matrix(wines, unique_flavors, flavor_idf)
user_vector = engine.build_user_vector(user_preferences, unique_flavors, flavor_idf)
top_matches = engine.cosine_similarity_search(user_vector, wine_matrix, top_k=COSINE_TOP_K)
candidate_row_indices = [match["row_index"] for match in top_matches]

# pretty_print.print_user_vector(user_preferences, user_vector)
# pretty_print.print_wine_vector(wines, unique_flavors, flavor_idf)

print("Reranking candidates with SIE...", flush=True)
reranked_matches = engine.rerank_wines_with_sie_reviews(
    wines,
    candidate_row_indices,
    user_preferences,
    unique_flavors,
    flavor_idf,
    reference_row_indices=REFERENCE_ROW_INDICES,
    max_terms=RERANK_MAX_TERMS,
    base_url=SIE_BASE_URL,
    model_name=SIE_RERANK_MODEL,
)
top_results = pretty_print.build_results_frame(wines, reranked_matches)

# pretty_print.print_run_config(
#     unique_flavors,
#     wine_matrix,
#     user_vector,
#     COSINE_TOP_K,
#     REVIEWS_PER_WINE,
#     RERANK_MAX_TERMS,
# )
pretty_print.print_top_results(top_results)
