import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import datasource
import engine
import transforms

FETCH_NUM_PAGES = 5
CHROMA_COLLECTION_NAME = "wine_taste_vectors"


def main():
    print("Fetching wines...", flush=True)
    wines = datasource.fetch_vivino_wines(num_pages=FETCH_NUM_PAGES)

    print("Building vectors...", flush=True)
    unique_flavors = transforms.unique_flavors(wines)
    flavor_idf = engine.build_flavor_idf(wines)
    wine_matrix = engine.build_wine_matrix(wines, unique_flavors, flavor_idf)

    print("Opening Chroma collection...", flush=True)
    collection = engine.get_chroma_collection(collection_name=CHROMA_COLLECTION_NAME)

    print("Upserting wine vectors...", flush=True)
    upserted_count = engine.upsert_wine_vectors(collection, wines, wine_matrix)

    print(f"Indexed {upserted_count} wines into Chroma collection '{CHROMA_COLLECTION_NAME}'.")


if __name__ == "__main__":
    main()
