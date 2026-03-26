
import datasource
import debugs
import engine
import pandas as pd
import transforms

USE_SIE_RERANK = True
SIE_BASE_URL = "http://localhost:8080"
SIE_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"

# If you need a broader batch later, uncomment this to print back some IDs.
# datasource.print_vivino_wine_ids(num_pages=3, limit=10)

wines = datasource.fetch_vivino_wines(num_pages=1)

# get all unique flavors from wine
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
top_matches = engine.cosine_similarity_search(user_vector, wine_matrix, top_k=5)

print("=== USER VECTOR ===")
print(f"acidity: {user_vector[0]:.3f}")
print(f"fizziness: {user_vector[1]:.3f}")
print(f"intensity: {user_vector[2]:.3f}")
print(f"sweetness: {user_vector[3]:.3f}")
print(f"tannin: {user_vector[4]:.3f}")
print("flavor weights:")
for flavor_name, flavor_weight in sorted(user_preferences["flavors"].items(), key=lambda item: item[1], reverse=True):
    print(f"  {flavor_name}: {flavor_weight}")
print(f"vector length: {len(user_vector)}")
print()

if USE_SIE_RERANK:
    reranked_matches = engine.rerank_wines_with_sie(
        wines,
        [match["row_index"] for match in top_matches],
        user_preferences,
        base_url=SIE_BASE_URL,
        model_name=SIE_RERANK_MODEL,
    )
    match_frame = pd.DataFrame(reranked_matches)
    sort_columns = ["rerank_rank", "rerank_score"]
    ascending = [True, False]
    rerank_status = "enabled"
else:
    match_frame = pd.DataFrame(top_matches)
    sort_columns = ["similarity_score"]
    ascending = [False]
    rerank_status = "disabled"

top5 = match_frame.merge(
    wines.reset_index().rename(columns={"index": "row_index"})[
        [
            "row_index",
            "wine_id",
            "wine_name",
            "winery_name",
            "vintage_year",
            "rating_average",
            "country_name",
            "region_name",
            "price_amount",
            "price_currency",
        ]
    ],
    on="row_index",
    how="left",
).sort_values(sort_columns, ascending=ascending)

# debugs.print_wine_flavors(wines)
# print(wines.head())
# print(wines.shape)
# print(wines.columns)

print(f"Flavor vocabulary size: {len(unique_flavors)}")
print(f"Wine matrix shape: {wine_matrix.shape}")
print(f"User vector length: {len(user_vector)}")
print(f"SIE rerank status: {rerank_status}")
print("\n--- Top 5 Wine Recommendations (taste only) ---")
print(top5.to_string(index=False))
