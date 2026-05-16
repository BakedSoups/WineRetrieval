"""
Seed ChromaDB from the local wine_flavor.db SQLite catalog.

Run once (or after the catalog is refreshed) to populate the vector store:

    python -m wine_flavor.scripts.seed_chroma
    # or from the repo root:
    python wine_flavor/scripts/seed_chroma.py
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path

import pandas as pd

# Allow running as a top-level script from the repo root.
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from wine_flavor.engine.chroma_store import ChromaWineStore
from wine_flavor.engine.vectors import build_flavor_idf
from wine_flavor.transforms import unique_flavors

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

DB_PATH = _ROOT / "wine_flavor.db"


def load_wines(db_path: Path) -> pd.DataFrame:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite catalog not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(
            """
            SELECT
                wine_id, winery_name, wine_name, vintage_year,
                rating_average, ratings_count,
                country_name, region_name, is_natural, wine_type_id,
                taste_acidity, taste_fizziness, taste_intensity,
                taste_sweetness, taste_tannin,
                wine_flavors_json,
                style_id, style_name, style_varietal_name,
                style_body_description, style_acidity_description,
                style_description,
                price_amount, price_currency
            FROM wines
            ORDER BY wine_id
            """,
            conn,
        )
    finally:
        conn.close()

    df["wine_flavors"] = df["wine_flavors_json"].apply(
        lambda v: json.loads(v or "[]")
    )
    df = df.drop(columns=["wine_flavors_json"])
    return df


def main() -> None:
    log.info("Loading wines from %s …", DB_PATH)
    wines = load_wines(DB_PATH)
    log.info("Loaded %d wines", len(wines))

    all_flavors = unique_flavors(wines)
    flavor_idf = build_flavor_idf(wines)
    vector_dim = 5 + len(all_flavors)
    log.info("Flavor vocabulary: %d terms  |  vector dim: %d", len(all_flavors), vector_dim)

    store = ChromaWineStore()
    if store.is_populated():
        log.info(
            "ChromaDB already has %d vectors — re-seeding (upsert)…",
            store.wine_count(),
        )

    count = store.ingest_wines(wines, all_flavors, flavor_idf)
    log.info("Done — %d wine vectors stored in ChromaDB at %s", count, store._client._identifier)


if __name__ == "__main__":
    main()
