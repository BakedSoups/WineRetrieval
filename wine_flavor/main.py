
import datasource
import debugs
import engine
import pandas as pd
import transforms

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

top5 = pd.DataFrame(top_matches).merge(
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
).sort_values("similarity_score", ascending=False)

# debugs.print_wine_flavors(wines)
# print(wines.head())
# print(wines.shape)
# print(wines.columns)

print(f"Flavor vocabulary size: {len(unique_flavors)}")
print(f"Wine matrix shape: {wine_matrix.shape}")
print(f"User vector length: {len(user_vector)}")
print("\n--- Top 5 Wine Recommendations (taste only) ---")
print(top5.to_string(index=False))
