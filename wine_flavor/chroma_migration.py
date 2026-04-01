from pathlib import Path

from db.chroma import (
    build_flavor_idf_from_vintages,
    collect_all_possible_flavors,
    load_all_vintages_from_sqlite,
    open_or_create_chroma_collection,
    save_all_possible_flavors,
    save_vintage_vectors_to_chroma,
)

DB_PATH = Path("wine_flavor.db")
CHROMA_PERSIST_DIR = Path("data/chroma")
COLLECTION_NAME = "wine_taste_v1"
FLAVOR_VOCAB_PATH = Path("db/chroma/flavor_vocab.json")


def main():
    print(f"Reading vintages from {DB_PATH.resolve()}...", flush=True)
    vintages = load_all_vintages_from_sqlite(DB_PATH)
    if vintages.empty:
        raise SystemExit("No vintages found in SQLite database.")

    print(f"Loaded {len(vintages)} vintages from SQLite.", flush=True)

    print("Building frozen flavor vocabulary...", flush=True)
    unique_flavors = collect_all_possible_flavors(vintages)

    flavor_idf = build_flavor_idf_from_vintages(vintages)

    save_all_possible_flavors(FLAVOR_VOCAB_PATH, unique_flavors, flavor_idf)

    
    print(
        f"Saved flavor vocabulary with {len(unique_flavors)} unique flavors to {FLAVOR_VOCAB_PATH.resolve()}.",
        flush=True,
    )

    print(f"Opening Chroma collection '{COLLECTION_NAME}'...", flush=True)
    collection = open_or_create_chroma_collection(CHROMA_PERSIST_DIR, COLLECTION_NAME)

    print("Upserting vintage vectors into Chroma...", flush=True)
    upserted = save_vintage_vectors_to_chroma(collection, vintages, unique_flavors, flavor_idf)
    print(
        f"Completed Chroma migration. Upserted {upserted} vintages into {CHROMA_PERSIST_DIR.resolve()}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
