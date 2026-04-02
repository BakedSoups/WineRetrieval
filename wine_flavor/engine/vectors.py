import numpy as np
import pandas as pd


STRUCTURE_NAMES = ["acidity", "fizziness", "intensity", "sweetness", "tannin"]


def normalize_preference_value(value, default=0.5):
    if value is None or pd.isna(value):
        return float(default)

    return float(value)


def normalize_user_preferences(user_preferences):
    structure_preferences = user_preferences.get("structure", {})
    flavor_preferences = user_preferences.get("flavors", {})

    normalized_structure = {
        structure_name: normalize_preference_value(
            structure_preferences.get(structure_name, 0.5),
            default=0.5,
        )
        for structure_name in STRUCTURE_NAMES
    }
    normalized_flavors = {
        flavor_name: normalize_preference_value(flavor_value, default=0.0)
        for flavor_name, flavor_value in flavor_preferences.items()
    }

    return {
        "structure": normalized_structure,
        "flavors": normalized_flavors,
    }


def pull_structure(wine_row):
    def normalize_taste(value, default=2.5):
        if pd.isna(value):
            value = default
        return float(value) / 5.0

    return np.array([
        normalize_taste(wine_row.get("taste_acidity")),
        normalize_taste(wine_row.get("taste_fizziness")),
        normalize_taste(wine_row.get("taste_intensity")),
        normalize_taste(wine_row.get("taste_sweetness")),
        normalize_taste(wine_row.get("taste_tannin")),
    ])


def pull_flavor_counts(wine_row):
    flavor_counts = {}

    for flavor_group in wine_row.get("wine_flavors", []):
        for keyword in flavor_group.get("primary_keywords") or []:
            flavor_name = keyword.get("name")
            flavor_count = keyword.get("count", 1)
            if pd.isna(flavor_count):
                flavor_count = 1
            if flavor_name:
                flavor_counts[flavor_name] = flavor_counts.get(flavor_name, 0) + flavor_count

        for keyword in flavor_group.get("secondary_keywords") or []:
            flavor_name = keyword.get("name")
            flavor_count = keyword.get("count", 1)
            if pd.isna(flavor_count):
                flavor_count = 1
            if flavor_name and flavor_name not in flavor_counts:
                flavor_counts[flavor_name] = flavor_counts.get(flavor_name, 0) + flavor_count

    return flavor_counts


def build_flavor_document_frequency(wines):
    document_frequency = {}

    for _, wine_row in wines.iterrows():
        wine_flavors = pull_flavor_counts(wine_row)
        for flavor_name in wine_flavors:
            document_frequency[flavor_name] = document_frequency.get(flavor_name, 0) + 1

    return document_frequency


def build_flavor_idf(wines):
    total_wines = len(wines)
    if total_wines == 0:
        return {}

    document_frequency = build_flavor_document_frequency(wines)
    return {
        flavor_name: np.log(total_wines / doc_count)
        for flavor_name, doc_count in document_frequency.items()
        if doc_count > 0
    }


def build_wine_vector(wine_row, all_flavors, flavor_idf=None):
    structure_vector = pull_structure(wine_row)
    flavor_vector = np.zeros(len(all_flavors))
    flavor_counts = pull_flavor_counts(wine_row)
    total_flavor_count = sum(flavor_counts.values())

    for i, flavor_name in enumerate(all_flavors):
        if flavor_name in flavor_counts and total_flavor_count > 0:
            flavor_weight = flavor_counts[flavor_name] / total_flavor_count
            if flavor_idf is not None:
                flavor_weight *= flavor_idf.get(flavor_name, 1.0)
            flavor_vector[i] = flavor_weight

    return np.concatenate([structure_vector, flavor_vector])


def build_user_vector(user_preferences, all_flavors, flavor_idf=None):
    normalized_preferences = normalize_user_preferences(user_preferences)
    structure_preferences = normalized_preferences["structure"]
    flavor_preferences = normalized_preferences["flavors"]

    structure_vector = np.array([
        structure_preferences.get("acidity", 0.5),
        structure_preferences.get("fizziness", 0.5),
        structure_preferences.get("intensity", 0.5),
        structure_preferences.get("sweetness", 0.5),
        structure_preferences.get("tannin", 0.5),
    ])

    flavor_vector = np.zeros(len(all_flavors))

    for i, flavor_name in enumerate(all_flavors):
        if flavor_name in flavor_preferences:
            flavor_weight = flavor_preferences[flavor_name]
            if flavor_idf is not None:
                flavor_weight *= flavor_idf.get(flavor_name, 1.0)
            flavor_vector[i] = flavor_weight

    return np.concatenate([structure_vector, flavor_vector])
