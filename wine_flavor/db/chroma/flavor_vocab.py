import json
from pathlib import Path

import engine
from engine.vectors import pull_flavor_counts


def build_unique_flavors(vintages):
    unique_flavors = set()
    for _, vintage_row in vintages.iterrows():
        unique_flavors.update(pull_flavor_counts(vintage_row).keys())
    return sorted(unique_flavors)


def build_flavor_idf_from_rows(vintages):
    return engine.build_flavor_idf(vintages)


def save_flavor_vocab(output_path, unique_flavors, flavor_idf):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "unique_flavors": unique_flavors,
                "flavor_idf": flavor_idf,
            },
            indent=2,
            sort_keys=True,
        )
    )
