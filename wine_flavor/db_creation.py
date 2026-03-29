import datasource
import engine
import transforms
from db import SessionLocal, build_full_local_store
from db.init_db import main as init_db

TARGET_WINE_COUNT = 10_000
FETCH_BATCH_PAGES = 10
REVIEWS_PER_WINE = 5
CHROMA_COLLECTION_NAME = "wine_taste_vectors"


def main():
    print("Creating SQL tables...", flush=True)
    init_db()

    print("Fetching wines...", flush=True)
    wines = datasource.fetch_vivino_wines_until_count(
        TARGET_WINE_COUNT,
        batch_pages=FETCH_BATCH_PAGES,
    )

    print("Fetching reviews...", flush=True)
    wines = datasource.attach_vivino_reviews(
        wines,
        review_pages=1,
        reviews_per_page=REVIEWS_PER_WINE,
        language="en",
    )

    print("Building vectors...", flush=True)
    unique_flavors = transforms.unique_flavors(wines)
    flavor_idf = engine.build_flavor_idf(wines)
    wine_matrix = engine.build_wine_matrix(wines, unique_flavors, flavor_idf)

    print("Writing SQL records...", flush=True)
    session = SessionLocal()
    try:
        build_full_local_store(session, wines, wine_matrix)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print("Building Chroma index...", flush=True)
    collection = engine.get_chroma_collection(collection_name=CHROMA_COLLECTION_NAME)
    upserted_count = engine.upsert_wine_vectors(collection, wines, wine_matrix)

    print(f"Built SQL + Chroma for {upserted_count} wine rows.")


if __name__ == "__main__":
    main()
