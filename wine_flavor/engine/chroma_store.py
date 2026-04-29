import logging
from pathlib import Path

import chromadb
import numpy as np

from .vectors import build_wine_vector

log = logging.getLogger(__name__)

_CHROMA_PATH = Path(__file__).parent.parent.parent / "chroma_data"
_WINES_COLLECTION = "wine_vectors"
_QUERIES_COLLECTION = "user_query_vectors"
_UPSERT_BATCH = 500


class ChromaWineStore:
    """Persistent ChromaDB store for wine feature vectors and user query vectors.

    Wine vectors: 5 taste dimensions + IDF-weighted flavor dimensions.
    Query vectors: same shape, stored for auditing / offline analysis.

    Uses cosine distance so similarity_score = 1 - distance.
    """

    def __init__(self, path: Path | None = None):
        chroma_path = path or _CHROMA_PATH
        chroma_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(chroma_path))
        self._wines = self._client.get_or_create_collection(
            name=_WINES_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        self._queries = self._client.get_or_create_collection(
            name=_QUERIES_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Wine vectors
    # ------------------------------------------------------------------

    def ingest_wines(
        self,
        wines,
        all_flavors: list[str],
        flavor_idf: dict | None = None,
    ) -> int:
        """Build and upsert wine vectors from a wines DataFrame.

        Returns the number of wines ingested.
        """
        ids: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict] = []

        for row_index, (_, wine_row) in enumerate(wines.iterrows()):
            vec = build_wine_vector(wine_row, all_flavors, flavor_idf)
            wine_id = wine_row.get("wine_id")
            doc_id = str(int(wine_id)) if wine_id is not None else str(row_index)
            ids.append(doc_id)
            embeddings.append(vec.tolist())
            metadatas.append(
                {
                    "row_index": row_index,
                    "wine_id": int(wine_id) if wine_id is not None else row_index,
                    "wine_name": str(wine_row.get("wine_name") or ""),
                    "winery_name": str(wine_row.get("winery_name") or ""),
                }
            )

        for i in range(0, len(ids), _UPSERT_BATCH):
            end = i + _UPSERT_BATCH
            self._wines.upsert(
                ids=ids[i:end],
                embeddings=embeddings[i:end],
                metadatas=metadatas[i:end],
            )
            log.debug("Upserted wine vectors %d–%d", i, min(end, len(ids)))

        log.info("ChromaDB: ingested %d wine vectors (dim=%d)", len(ids), 5 + len(all_flavors))
        return len(ids)

    def search_wines(
        self, query_vector: np.ndarray, top_k: int = 5
    ) -> list[dict]:
        """Return top-k wines ordered by cosine similarity.

        Each result matches the shape expected by service.get_recommendations:
            {"row_index": int, "similarity_score": float}
        """
        count = self._wines.count()
        if count == 0:
            return []

        results = self._wines.query(
            query_embeddings=[query_vector.tolist()],
            n_results=min(top_k, count),
        )
        if not results["ids"] or not results["ids"][0]:
            return []

        return [
            {
                "row_index": int(meta["row_index"]),
                "similarity_score": float(1.0 - dist),
            }
            for meta, dist in zip(results["metadatas"][0], results["distances"][0])
        ]

    def wine_count(self) -> int:
        return self._wines.count()

    def is_populated(self) -> bool:
        return self._wines.count() > 0

    # ------------------------------------------------------------------
    # User query vectors
    # ------------------------------------------------------------------

    def store_query(
        self,
        query_id: str,
        query_vector: np.ndarray,
        metadata: dict | None = None,
    ) -> None:
        """Persist a user query vector for auditing / offline analysis."""
        self._queries.upsert(
            ids=[query_id],
            embeddings=[query_vector.tolist()],
            metadatas=[metadata or {}],
        )
        log.debug("Stored query vector %s", query_id)

    def query_count(self) -> int:
        return self._queries.count()
