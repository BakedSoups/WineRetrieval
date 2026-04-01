import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import engine

DB_PATH = PROJECT_ROOT / "wine_flavor.db"
CHROMA_PERSIST_DIR = PROJECT_ROOT / "data" / "chroma"
COLLECTION_NAME = "wine_taste_v1"
FLAVOR_VOCAB_PATH = PROJECT_ROOT / "db" / "chroma" / "flavor_vocab.json"
TOP_K = 5

USER_PREFERENCES = {
    "structure": {
        "acidity": 0.8,
        "fizziness": 0.1,
        "intensity": 0.5,
        "sweetness": 0.2,
        "tannin": 0.1,
    },
    "flavors": {
        "orange zest": 1.0,
        "minerals": 0.8,
        "floral": 0.6,
    },
}


def load_flavor_vocab():
    payload = json.loads(FLAVOR_VOCAB_PATH.read_text())
    return payload["unique_flavors"], payload["flavor_idf"]


def get_collection():
    try:
        import chromadb
    except ImportError as exc:
        raise ImportError("chromadb is required to query the Chroma collection.") from exc

    client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
    return client.get_collection(COLLECTION_NAME)


def load_vintages_by_ids(vintage_ids):
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in vintage_ids)
        rows = connection.execute(
            f"""
            SELECT vintage_id, wine_id, wine_name, vintage_name, winery_name, vintage_year,
                   country_name, region_name, style_name, price_amount, price_currency
            FROM vintages
            WHERE vintage_id IN ({placeholders})
            """,
            [int(vintage_id) for vintage_id in vintage_ids],
        ).fetchall()
    finally:
        connection.close()

    rows_by_id = {int(row["vintage_id"]): dict(row) for row in rows}
    return [rows_by_id[int(vintage_id)] for vintage_id in vintage_ids if int(vintage_id) in rows_by_id]


def main():
    unique_flavors, flavor_idf = load_flavor_vocab()
    user_vector = engine.build_user_vector(USER_PREFERENCES, unique_flavors, flavor_idf)
    collection = get_collection()

    results = collection.query(
        query_embeddings=[user_vector.tolist()],
        n_results=TOP_K,
    )

    vintage_ids = results["ids"][0]
    distances = results.get("distances", [[]])[0]
    vintages = load_vintages_by_ids(vintage_ids)

    print("User query:")
    print(
        "- structure:",
        ", ".join(f"{name}={value}" for name, value in USER_PREFERENCES["structure"].items()),
    )
    print(
        "- flavors:",
        ", ".join(f"{name}={value}" for name, value in USER_PREFERENCES["flavors"].items()),
    )
    print()
    print("--- Chroma Top 5 Results ---")

    for rank, vintage in enumerate(vintages):
        distance = distances[rank] if rank < len(distances) else None
        distance_text = f"{distance:.4f}" if distance is not None else "n/a"
        print(
            f"{rank + 1}. vintage_id={vintage['vintage_id']} | "
            f"wine_id={vintage['wine_id']} | "
            f"wine_name={vintage['wine_name']} | "
            f"style_name={vintage['style_name']} | "
            f"country={vintage['country_name']} | "
            f"region={vintage['region_name']} | "
            f"price={vintage['price_amount']} {vintage['price_currency']} | "
            f"distance={distance_text}"
        )


if __name__ == "__main__":
    main()
