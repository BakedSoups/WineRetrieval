import os

import numpy as np
from dotenv import load_dotenv

load_dotenv()


def _resolve_sie_connection(base_url=None):
    resolved_base_url = base_url or os.getenv("CLUSTER_URL")
    if not resolved_base_url:
        raise ValueError("Missing SIE base URL. Set CLUSTER_URL in the environment or pass base_url explicitly.")

    api_key = os.getenv("API_KEY")
    if not api_key:
        raise ValueError("Missing SIE API key. Set API_KEY in the environment.")

    return resolved_base_url, api_key


def build_wine_rerank_text(wine_row):
    from .vectors import pull_flavor_counts

    text_parts = []

    wine_name = wine_row.get("wine_name")
    winery_name = wine_row.get("winery_name")
    vintage_year = wine_row.get("vintage_year")
    style_name = wine_row.get("style_name")
    country_name = wine_row.get("country_name")
    region_name = wine_row.get("region_name")

    headline_parts = [part for part in [winery_name, wine_name, vintage_year] if part and part != "None"]
    if headline_parts:
        text_parts.append(" ".join(str(part) for part in headline_parts))
    if style_name:
        text_parts.append(f"Style: {style_name}")
    if country_name or region_name:
        location = ", ".join(str(part) for part in [region_name, country_name] if part and part != "None")
        text_parts.append(f"Origin: {location}")

    flavor_counts = pull_flavor_counts(wine_row)
    if flavor_counts:
        weighted_flavors = sorted(flavor_counts.items(), key=lambda item: item[1], reverse=True)
        flavor_summary = ", ".join(f"{flavor_name} ({flavor_weight:g})" for flavor_name, flavor_weight in weighted_flavors)
        text_parts.append(f"Tasting notes: {flavor_summary}")

    structure_parts = []
    for label, value in [
        ("acidity", wine_row.get("taste_acidity")),
        ("fizziness", wine_row.get("taste_fizziness")),
        ("intensity", wine_row.get("taste_intensity")),
        ("sweetness", wine_row.get("taste_sweetness")),
        ("tannin", wine_row.get("taste_tannin")),
    ]:
        if value is not None:
            structure_parts.append(f"{label}={value}")

    if structure_parts:
        text_parts.append(f"Structure: {', '.join(structure_parts)}")

    return "\n".join(part for part in text_parts if part and part != "None")


def pull_wine_reviews(wine_row):
    reviews = wine_row.get("wine_reviews") or wine_row.get("reviews") or []
    normalized_reviews = []

    for review in reviews:
        if isinstance(review, str) and review.strip():
            normalized_reviews.append(review.strip())
        elif isinstance(review, dict):
            review_text = review.get("text") or review.get("review") or review.get("note")
            if review_text:
                normalized_reviews.append(str(review_text).strip())

    return normalized_reviews


def build_user_query_text(user_preferences):
    structure_preferences = user_preferences.get("structure", {})
    flavor_preferences = user_preferences.get("flavors", {})

    text_parts = ["Find wines matching this taste profile."]

    structure_summary = (
        "Structure preferences: "
        f"acidity={structure_preferences.get('acidity', 0.5)}, "
        f"fizziness={structure_preferences.get('fizziness', 0.5)}, "
        f"intensity={structure_preferences.get('intensity', 0.5)}, "
        f"sweetness={structure_preferences.get('sweetness', 0.5)}, "
        f"tannin={structure_preferences.get('tannin', 0.5)}"
    )
    text_parts.append(structure_summary)

    if flavor_preferences:
        ordered_flavors = sorted(flavor_preferences.items(), key=lambda item: item[1], reverse=True)
        flavor_summary = ", ".join(f"{flavor_name} ({flavor_weight})" for flavor_name, flavor_weight in ordered_flavors)
        text_parts.append(f"Preferred flavors: {flavor_summary}")

    return "\n".join(text_parts)


def _structure_label(value):
    if value >= 0.8:
        return "high"
    if value >= 0.6:
        return "medium-high"
    if value >= 0.4:
        return "medium"
    if value >= 0.2:
        return "low"
    return "very low"


def build_standard_rerank_query_weights(
    user_preferences,
    wines,
    reference_row_indices,
    all_flavors,
    flavor_idf=None,
    alpha=0.7,
    max_terms=None,
):
    from .vectors import build_user_vector, build_wine_vector

    user_vector = build_user_vector(user_preferences, all_flavors, flavor_idf)
    flavor_only_vectors = []

    for row_index in reference_row_indices or []:
        wine_vector = build_wine_vector(wines.iloc[row_index], all_flavors, flavor_idf)
        flavor_only_vector = np.concatenate([np.zeros(5), wine_vector[5:]])
        flavor_only_vectors.append(flavor_only_vector)

    if flavor_only_vectors:
        average_reference_vector = np.mean(np.vstack(flavor_only_vectors), axis=0)
    else:
        average_reference_vector = np.zeros_like(user_vector)

    final_query_vector = alpha * user_vector + (1 - alpha) * average_reference_vector

    term_weights = {}
    structure_names = ["acidity", "fizziness", "intensity", "sweetness", "tannin"]

    for i, structure_name in enumerate(structure_names):
        structure_weight = float(final_query_vector[i])
        if structure_weight > 0:
            term_weights[f"{_structure_label(structure_weight)} {structure_name}"] = structure_weight

    for i, flavor_name in enumerate(all_flavors, start=5):
        flavor_weight = float(final_query_vector[i])
        if flavor_weight > 0:
            term_weights[flavor_name] = flavor_weight

    if max_terms is not None:
        sorted_terms = sorted(term_weights.items(), key=lambda item: item[1], reverse=True)
        term_weights = dict(sorted_terms[:max_terms])

    return term_weights, final_query_vector


def rerank_wines_with_sie_reviews(
    wines,
    candidate_row_indices,
    user_preferences,
    all_flavors,
    flavor_idf=None,
    *,
    reference_row_indices=None,
    alpha=0.7,
    max_terms=12,
    base_url=None,
    model_name="BAAI/bge-reranker-v2-m3",
    gpu=None,
):
    try:
        from sie_sdk import SIEClient
    except ImportError as exc:
        raise ImportError("sie_sdk is required for SIE reranking.") from exc

    base_url, api_key = _resolve_sie_connection(base_url)
    client = SIEClient(base_url, api_key=api_key)
    term_weights, final_query_vector = build_standard_rerank_query_weights(
        user_preferences,
        wines,
        reference_row_indices,
        all_flavors,
        flavor_idf,
        alpha=alpha,
        max_terms=max_terms,
    )

    wine_scores = []
    for row_index in candidate_row_indices:
        wine_row = wines.iloc[row_index]
        reviews = pull_wine_reviews(wine_row)

        if not reviews:
            wine_scores.append({
                "row_index": int(row_index),
                "rerank_score": 0.0,
                "review_count": 0,
            })
            continue

        review_items = [{"id": f"review-{review_index}", "text": review_text} for review_index, review_text in enumerate(reviews)]
        review_score_totals = np.zeros(len(reviews), dtype=float)

        for term_text, term_weight in term_weights.items():
            score_result = client.score(
                model_name,
                {"id": f"term-{term_text}", "text": term_text},
                review_items,
                gpu=gpu,
                wait_for_capacity=True,
                provision_timeout_s=900,
            )

            for score_entry in score_result.get("scores", []):
                review_item_id = score_entry["item_id"]
                review_index = int(review_item_id.split("-")[-1])
                review_score_totals[review_index] += term_weight * float(score_entry["score"])

        final_wine_score = float(np.sum(review_score_totals) / len(reviews))
        wine_scores.append({
            "row_index": int(row_index),
            "rerank_score": final_wine_score,
            "review_count": len(reviews),
        })

    ranked_wines = sorted(wine_scores, key=lambda item: item["rerank_score"], reverse=True)
    for rank, wine_score in enumerate(ranked_wines):
        wine_score["rerank_rank"] = rank
        wine_score["query_vector_length"] = len(final_query_vector)

    return ranked_wines
