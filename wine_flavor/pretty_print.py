import pandas as pd

import engine


def print_user_vector(user_preferences, user_vector):
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


def print_wine_vector(wines, unique_flavors, flavor_idf, row_index=0):
    sample_wine_row = wines.iloc[row_index]
    sample_wine_vector = engine.build_wine_vector(sample_wine_row, unique_flavors, flavor_idf)

    print("=== SAMPLE WINE VECTOR ===")
    print(f"wine: {sample_wine_row['wine_name']}")
    print(f"acidity: {sample_wine_vector[0]:.3f}")
    print(f"fizziness: {sample_wine_vector[1]:.3f}")
    print(f"intensity: {sample_wine_vector[2]:.3f}")
    print(f"sweetness: {sample_wine_vector[3]:.3f}")
    print(f"tannin: {sample_wine_vector[4]:.3f}")
    print("active flavors:")
    for flavor_name, flavor_weight in zip(unique_flavors, sample_wine_vector[5:]):
        if flavor_weight > 0:
            print(f"  {flavor_name}: {flavor_weight:.4f}")
    print(f"review count: {sample_wine_row['review_count']}")
    print(f"vector length: {len(sample_wine_vector)}")
    print()


def build_results_frame(wines, reranked_matches):
    match_frame = pd.DataFrame(reranked_matches)
    result_frame = match_frame.merge(
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
                "review_count",
            ]
        ],
        on="row_index",
        how="left",
        suffixes=("", "_wine"),
    ).sort_values(["rerank_rank", "rerank_score"], ascending=[True, False])

    if "review_count_wine" in result_frame.columns:
        result_frame = result_frame.drop(columns=["review_count_wine"])

    return result_frame


def print_run_config(unique_flavors, wine_matrix, user_vector, cosine_top_k, reviews_per_wine, rerank_max_terms):
    print(f"Flavor vocabulary size: {len(unique_flavors)}")
    print(f"Wine matrix shape: {wine_matrix.shape}")
    print(f"User vector length: {len(user_vector)}")
    print(f"Cosine top-k: {cosine_top_k}")
    print(f"Reviews per wine: {reviews_per_wine}")
    print(f"Rerank max terms: {rerank_max_terms}")


def print_top_results(top_results):
    print("\n--- Top Wine Recommendations (review rerank) ---")
    display_frame = top_results.copy()
    if "rerank_score" in display_frame.columns:
        display_frame["rerank_score"] = display_frame["rerank_score"].round(4)
    print(display_frame.to_string(index=False))
