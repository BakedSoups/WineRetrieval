from pathlib import Path

from db.chroma import (
    build_flavor_idf_from_rows,
    build_unique_flavors,
    get_collection,
    load_all_vintages,
    save_flavor_vocab,
    upsert_vintages,
)

DB_PATH = Path("wine_flavor.db")
CHROMA_PERSIST_DIR = Path("data/chroma")
COLLECTION_NAME = "wine_taste_v1"
FLAVOR_VOCAB_PATH = Path("db/chroma/flavor_vocab.json")


def main():
    print(f"Reading vintages from {DB_PATH.resolve()}...", flush=True)
    vintages = load_all_vintages(DB_PATH)
    if vintages.empty:
        raise SystemExit("No vintages found in SQLite database.")

    print(f"Loaded {len(vintages)} vintages from SQLite.", flush=True)

    print("Building frozen flavor vocabulary...", flush=True)
    unique_flavors = build_unique_flavors(vintages)
    flavor_idf = build_flavor_idf_from_rows(vintages)
    save_flavor_vocab(FLAVOR_VOCAB_PATH, unique_flavors, flavor_idf)
    print(
        f"Saved flavor vocabulary with {len(unique_flavors)} unique flavors to {FLAVOR_VOCAB_PATH.resolve()}.",
        flush=True,
    )

    print(f"Opening Chroma collection '{COLLECTION_NAME}'...", flush=True)
    collection = get_collection(CHROMA_PERSIST_DIR, COLLECTION_NAME)

    print("Upserting vintage vectors into Chroma...", flush=True)
    upserted = upsert_vintages(collection, vintages, unique_flavors, flavor_idf)
    print(
        f"Completed Chroma migration. Upserted {upserted} vintages into {CHROMA_PERSIST_DIR.resolve()}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
