def build_wine_rerank_text(wine_row):
    text_parts = [
        f"Wine: {wine_row.get('wine_name')}",
        f"Winery: {wine_row.get('winery_name')}",
        f"Vintage: {wine_row.get('vintage_year')}",
        f"Country: {wine_row.get('country_name')}",
        f"Region: {wine_row.get('region_name')}",
        f"Style: {wine_row.get('style_name')}",
    ]

    flavor_names = []
    for flavor_group in wine_row.get("wine_flavors", []):
        for keyword in flavor_group.get("primary_keywords") or []:
            flavor_name = keyword.get("name")
            if flavor_name:
                flavor_names.append(flavor_name)
        for keyword in flavor_group.get("secondary_keywords") or []:
            flavor_name = keyword.get("name")
            if flavor_name:
                flavor_names.append(flavor_name)

    if flavor_names:
        text_parts.append(f"Flavors: {', '.join(flavor_names)}")

    return "\n".join(part for part in text_parts if part and part != "None")


def build_user_query_text(user_preferences):
    structure_preferences = user_preferences.get("structure", {})
    flavor_preferences = user_preferences.get("flavors", {})

    text_parts = [
        "Wine preference query",
        "Structure preferences:",
        f"- acidity: {structure_preferences.get('acidity', 0.5)}",
        f"- fizziness: {structure_preferences.get('fizziness', 0.5)}",
        f"- intensity: {structure_preferences.get('intensity', 0.5)}",
        f"- sweetness: {structure_preferences.get('sweetness', 0.5)}",
        f"- tannin: {structure_preferences.get('tannin', 0.5)}",
    ]

    if flavor_preferences:
        ordered_flavors = sorted(flavor_preferences.items(), key=lambda item: item[1], reverse=True)
        text_parts.append("Flavor preferences:")
        text_parts.extend(f"- {flavor_name}: {flavor_weight}" for flavor_name, flavor_weight in ordered_flavors)

    return "\n".join(text_parts)


def rerank_wines_with_sie(
    wines,
    candidate_row_indices,
    user_preferences,
    *,
    base_url="http://localhost:8080",
    model_name="BAAI/bge-reranker-v2-m3",
    instruction=None,
):
    try:
        from sie_sdk import SIEClient
    except ImportError as exc:
        raise ImportError("sie_sdk is required for SIE reranking.") from exc

    client = SIEClient(base_url)
    query_item = {"id": "user-query", "text": build_user_query_text(user_preferences)}

    candidate_rows = wines.iloc[candidate_row_indices]
    items = []
    row_index_by_item_id = {}

    for row_index, wine_row in candidate_rows.iterrows():
        item_id = f"wine-{row_index}"
        items.append({
            "id": item_id,
            "text": build_wine_rerank_text(wine_row),
        })
        row_index_by_item_id[item_id] = int(row_index)

    score_result = client.score(
        model_name,
        query=query_item,
        items=items,
        instruction=instruction,
    )

    reranked_matches = []
    for score_entry in score_result.get("scores", []):
        item_id = score_entry["item_id"]
        reranked_matches.append({
            "row_index": row_index_by_item_id[item_id],
            "rerank_score": float(score_entry["score"]),
            "rerank_rank": int(score_entry["rank"]),
        })

    return reranked_matches
