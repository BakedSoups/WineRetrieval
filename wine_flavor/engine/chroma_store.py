from pathlib import Path

import pandas as pd


DEFAULT_CHROMA_DIR = Path("data/chroma")
DEFAULT_COLLECTION_NAME = "wine_taste_vectors"


def get_chroma_collection(persist_directory=DEFAULT_CHROMA_DIR, collection_name=DEFAULT_COLLECTION_NAME):
    try:
        import chromadb
    except ImportError as exc:
        raise ImportError("chromadb is required to use the Chroma store.") from exc

    persist_path = Path(persist_directory)
    persist_path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(persist_path))
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def upsert_wine_vectors(collection, wines, wine_matrix):
    if len(wines) != len(wine_matrix):
        raise ValueError("wines and wine_matrix must have the same length.")

    ids = []
    embeddings = []
    metadatas = []
    documents = []

    for row_index, (_, wine_row) in enumerate(wines.iterrows()):
        wine_id = wine_row.get("wine_id")
        if pd.isna(wine_id):
            continue

        wine_id_value = int(wine_id)
        record_id = f"{wine_id_value}:{row_index}"
        ids.append(record_id)
        embeddings.append(wine_matrix[row_index].tolist())
        metadatas.append(
            {
                "row_index": int(row_index),
                "wine_id": wine_id_value,
                "wine_name": str(wine_row.get("wine_name") or ""),
                "winery_name": str(wine_row.get("winery_name") or ""),
                "country_name": str(wine_row.get("country_name") or ""),
                "region_name": str(wine_row.get("region_name") or ""),
                "vintage_year": str(wine_row.get("vintage_year") or ""),
                "price_amount": float(wine_row.get("price_amount") or 0.0),
                "price_currency": str(wine_row.get("price_currency") or ""),
            }
        )
        documents.append(
            " | ".join(
                part
                for part in [
                    str(wine_row.get("winery_name") or "").strip(),
                    str(wine_row.get("wine_name") or "").strip(),
                    str(wine_row.get("vintage_year") or "").strip(),
                ]
                if part
            )
        )

    if not ids:
        return 0

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        metadatas=metadatas,
        documents=documents,
    )
    return len(ids)


def query_wine_vectors(collection, query_vector, top_k=50):
    result = collection.query(
        query_embeddings=[query_vector.tolist()],
        n_results=top_k,
        include=["metadatas", "distances", "documents"],
    )

    matches = []
    ids = result.get("ids", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    for item_id, metadata, distance in zip(ids, metadatas, distances):
        similarity_score = 1.0 - float(distance)
        matches.append(
            {
                "id": item_id,
                "row_index": int(metadata["row_index"]),
                "wine_id": int(metadata["wine_id"]),
                "similarity_score": similarity_score,
            }
        )

    return matches
