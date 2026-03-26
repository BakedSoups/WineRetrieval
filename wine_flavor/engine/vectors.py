import numpy as np


def pull_structure(wine_row):
    return np.array([
        (wine_row.get("taste_acidity") or 2.5) / 5.0,
        (wine_row.get("taste_fizziness") or 2.5) / 5.0,
        (wine_row.get("taste_intensity") or 2.5) / 5.0,
        (wine_row.get("taste_sweetness") or 2.5) / 5.0,
        (wine_row.get("taste_tannin") or 2.5) / 5.0,
    ])


def pull_flavor_counts(wine_row):
    flavor_counts = {}

    for flavor_group in wine_row.get("wine_flavors", []):
        for keyword in flavor_group.get("primary_keywords") or []:
            flavor_name = keyword.get("name")
            flavor_count = keyword.get("count", 1)
            if flavor_name:
                flavor_counts[flavor_name] = flavor_counts.get(flavor_name, 0) + flavor_count

        for keyword in flavor_group.get("secondary_keywords") or []:
            flavor_name = keyword.get("name")
            flavor_count = keyword.get("count", 1)
            if flavor_name and flavor_name not in flavor_counts:
                flavor_counts[flavor_name] = flavor_counts.get(flavor_name, 0) + flavor_count

    return flavor_counts


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
    structure_preferences = user_preferences.get("structure", {})
    flavor_preferences = user_preferences.get("flavors", {})

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
