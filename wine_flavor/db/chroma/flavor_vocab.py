import json
from pathlib import Path

import engine
from engine.vectors import pull_flavor_counts


def collect_all_possible_flavors(vintages):
    unique_flavors = set()
    for _, vintage_row in vintages.iterrows():
        unique_flavors.update(pull_flavor_counts(vintage_row).keys())
    return sorted(unique_flavors)


def build_flavor_idf_from_vintages(vintages):
    return engine.build_flavor_idf(vintages)


def save_all_possible_flavors(output_path, unique_flavors, flavor_idf):
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


def load_all_possible_flavors(input_path):
    input_path = Path(input_path)
    payload = json.loads(input_path.read_text())
    return payload["unique_flavors"], payload["flavor_idf"]
