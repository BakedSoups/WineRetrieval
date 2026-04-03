# Wine Flavor

Prototype wine recommender using:
- Vivino wine metadata
- in-memory vector retrieval
- SIE-based reranking

## Setup

Install Docker and Docker Compose.

Create a `.env` file with the required backend settings, then run the stack with Docker Compose.

Start:

```bash
docker compose up --build
```

## Env

Create a `.env` file with:

```env
CLUSTER_URL=https://your-sie-cluster-url
API_KEY=your-sie-api-key
RERANK_METHOD=standard
SIE_RERANK_MODEL=BAAI/bge-reranker-v2-m3
SIE_EMBEDDING_MODEL=BAAI/bge-m3
RERANK_ALPHA=0.7
CUSTOM_RERANK_A=0.75
CUSTOM_RERANK_NO_REVIEW_PENALTY=0.5
DEMO_NUM_PAGES=5
DEMO_MAX_WINES=100
```

`RERANK_METHOD` options:
- `standard`: uses SIE `score(...)` on review texts
- `custom`: uses generated tasting notes + review embeddings + cosine similarity

`RERANK_ALPHA` mixes the user query vector with the averaged reference-wine vector.
`CUSTOM_RERANK_A` mixes review embeddings with generated tasting-note embeddings for each wine.

User preferences are expected to come from the UI already normalized. The engine assumes:
- `structure` contains `acidity`, `fizziness`, `intensity`, `sweetness`, and `tannin`
- all structure and flavor values are numeric floats on the normalized 0-1 scale
- `flavors` is a mapping of flavor name to normalized weight

## Run

Run the demo stack:

```bash
docker compose up --build
```

Stop it with:

```bash
docker compose down
```

This starts:
- FastAPI on `http://localhost:8000`
- the React frontend on `http://localhost:3000`

Docker Compose runs:
- a FastAPI backend container on `http://localhost:8000`
- a Next.js frontend container on `http://localhost:3000`

`app.py` is still the backend entrypoint inside the backend container. It preloads a small in-memory demo catalog from Vivino, and the React frontend calls the FastAPI endpoints directly.

`DEMO_NUM_PAGES` controls how many Vivino pages are fetched at startup.
`DEMO_MAX_WINES` caps the in-memory catalog after fetch so the demo stays small.

`main.py` is kept as a script reference for the original prototype flow.

## Tests

Compare the two rerank methods on the same candidate set:

```bash
python test/compare_rerank_methods.py
```

## Flow
1. Fetch wines from Vivino
2. Fetch reviews for retrieved wines
3. Build wine vectors from structure + flavors
4. Retrieve top candidates with cosine similarity
5. Rerank with either:
   - standard SIE reranker
   - custom embedding reranker
