import json
from pathlib import Path

import pandas as pd

import datasource
import engine
import transforms
from db import SessionLocal, build_full_local_store
from db.init_db import main as init_db

TARGET_WINE_COUNT = 10_000
FETCH_BATCH_PAGES = 10
MAX_STALLED_BATCHES = 5
REVIEWS_PER_WINE = 5
CHROMA_COLLECTION_NAME = "wine_taste_vectors"
CRAWL_STATE_PATH = Path("data/vivino_wine_crawl_state.json")
CRAWL_CACHE_PATH = Path("data/vivino_wine_crawl.pkl")


def _empty_wine_frame():
    return pd.DataFrame()


def load_crawl_state():
    if not CRAWL_STATE_PATH.exists():
        return {
            "next_page": 1,
            "target_wine_count": TARGET_WINE_COUNT,
            "status": "not_started",
            "stalled_batches": 0,
        }

    return json.loads(CRAWL_STATE_PATH.read_text())


def save_crawl_state(state):
    CRAWL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CRAWL_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def load_cached_wines():
    if not CRAWL_CACHE_PATH.exists():
        return _empty_wine_frame()
    return pd.read_pickle(CRAWL_CACHE_PATH)


def save_cached_wines(wines):
    CRAWL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    wines.to_pickle(CRAWL_CACHE_PATH)


def merge_unique_wines(existing_wines, new_wines):
    if existing_wines.empty:
        return new_wines.drop_duplicates(subset=["wine_id"]).reset_index(drop=True)
    if new_wines.empty:
        return existing_wines.drop_duplicates(subset=["wine_id"]).reset_index(drop=True)

    combined_wines = pd.concat([existing_wines, new_wines], ignore_index=True)
    return combined_wines.drop_duplicates(subset=["wine_id"]).reset_index(drop=True)


def crawl_unique_wines():
    state = load_crawl_state()
    wines = load_cached_wines()

    if state.get("status") == "completed" and len(wines) >= TARGET_WINE_COUNT:
        print(f"Using completed cached wine crawl with {len(wines)} wines.", flush=True)
        return wines, True

    current_page = int(state.get("next_page", 1))
    stalled_batches = int(state.get("stalled_batches", 0))
    previous_unique_count = len(wines)

    print(
        f"Resuming wine crawl at page {current_page}. "
        f"Cached unique wines: {previous_unique_count}.",
        flush=True,
    )

    while len(wines) < TARGET_WINE_COUNT:
        page_end = current_page + FETCH_BATCH_PAGES - 1
        print(f"Fetching wine pages {current_page}-{page_end}...", flush=True)

        try:
            batch = datasource.fetch_vivino_wines(
                page=current_page,
                num_pages=FETCH_BATCH_PAGES,
            )
        except RuntimeError as exc:
            state.update(
                {
                    "next_page": current_page,
                    "status": "paused",
                    "last_error": str(exc),
                    "cached_unique_wines": len(wines),
                    "stalled_batches": stalled_batches,
                }
            )
            save_crawl_state(state)
            save_cached_wines(wines)
            print(f"Paused wine crawl after request failure: {exc}", flush=True)
            return wines, False

        if batch.empty:
            state.update(
                {
                    "next_page": current_page,
                    "status": "completed",
                    "last_error": None,
                    "cached_unique_wines": len(wines),
                    "stalled_batches": stalled_batches,
                }
            )
            save_crawl_state(state)
            save_cached_wines(wines)
            print("Wine crawl completed because no more results were returned.", flush=True)
            return wines, True

        wines = merge_unique_wines(wines, batch)
        unique_count = len(wines)
        print(f"Collected {unique_count} unique wines so far (target: {TARGET_WINE_COUNT}).", flush=True)

        if unique_count == previous_unique_count:
            stalled_batches += 1
            print(
                f"No new unique wines found in this batch "
                f"({stalled_batches}/{MAX_STALLED_BATCHES} stalled batches).",
                flush=True,
            )
        else:
            stalled_batches = 0

        current_page += FETCH_BATCH_PAGES
        previous_unique_count = unique_count

        state.update(
            {
                "next_page": current_page,
                "status": "in_progress",
                "last_error": None,
                "cached_unique_wines": unique_count,
                "stalled_batches": stalled_batches,
            }
        )
        save_crawl_state(state)
        save_cached_wines(wines)

        if stalled_batches >= MAX_STALLED_BATCHES:
            state.update(
                {
                    "status": "completed",
                    "last_error": None,
                }
            )
            save_crawl_state(state)
            print("Stopping wine crawl because the unique count has stalled.", flush=True)
            return wines, True

    state.update(
        {
            "next_page": current_page,
            "status": "completed",
            "last_error": None,
            "cached_unique_wines": len(wines),
            "stalled_batches": 0,
        }
    )
    save_crawl_state(state)
    save_cached_wines(wines)
    print(f"Wine crawl reached the target of {TARGET_WINE_COUNT} wines.", flush=True)
    return wines.head(TARGET_WINE_COUNT).reset_index(drop=True), True


def main():
    print("Creating SQL tables...", flush=True)
    init_db()

    print("Crawling wines...", flush=True)
    wines, crawl_completed = crawl_unique_wines()
    if wines.empty:
        print("No wines available to ingest.", flush=True)
        return

    if not crawl_completed:
        print("Wine crawl checkpoint saved. Re-run db_creation.py later to continue.", flush=True)
        return

    if len(wines) > TARGET_WINE_COUNT:
        wines = wines.head(TARGET_WINE_COUNT).reset_index(drop=True)

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

    print(f"Built SQL + Chroma for {upserted_count} wine rows.", flush=True)


if __name__ == "__main__":
    main()
