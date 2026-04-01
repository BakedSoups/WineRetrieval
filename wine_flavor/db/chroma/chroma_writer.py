from pathlib import Path

import engine


def get_collection(persist_directory, collection_name):
    try:
        import chromadb
    except ImportError as exc:
        raise ImportError("chromadb is required for Chroma migration.") from exc

    persist_directory = Path(persist_directory)
    persist_directory.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(persist_directory))
    return client.get_or_create_collection(collection_name)


def upsert_vintages(collection, vintages, unique_flavors, flavor_idf, batch_size=200):
    total_upserted = 0

    for batch_start in range(0, len(vintages), batch_size):
        batch = vintages.iloc[batch_start:batch_start + batch_size]
        ids = []
        embeddings = []
        metadatas = []

        for _, vintage_row in batch.iterrows():
            vintage_id = vintage_row.get("vintage_id")
            if vintage_id is None:
                continue

            ids.append(str(int(vintage_id)))
            embeddings.append(engine.build_wine_vector(vintage_row, unique_flavors, flavor_idf).tolist())
            metadatas.append(
                {
                    "wine_id": int(vintage_row["wine_id"]) if vintage_row.get("wine_id") is not None else None,
                    "vintage_id": int(vintage_id),
                    "wine_name": vintage_row.get("wine_name"),
                    "vintage_name": vintage_row.get("vintage_name"),
                    "winery_name": vintage_row.get("winery_name"),
                    "country_name": vintage_row.get("country_name"),
                    "region_name": vintage_row.get("region_name"),
                    "wine_type_id": int(vintage_row["wine_type_id"]) if vintage_row.get("wine_type_id") is not None else None,
                    "price_amount": float(vintage_row["price_amount"]) if vintage_row.get("price_amount") is not None else None,
                    "price_currency": vintage_row.get("price_currency"),
                }
            )

        if not ids:
            continue

        collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas)
        total_upserted += len(ids)

    return total_upserted
