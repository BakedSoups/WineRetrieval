# Wine Flavor

Prototype wine recommender using:
- Vivino wine metadata
- in-memory vector retrieval
- SIE-based reranking

## Setup

Create a virtualenv, activate it, and install dependencies:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
note: we have sie_sdk in this requirements.txt you may need to install separately if you have issues with the installation. 
```bash
pip install sie_sdk
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
```

`RERANK_METHOD` options:
- `standard`: uses SIE `score(...)` on review texts
- `custom`: uses generated tasting notes + review embeddings + cosine similarity

`RERANK_ALPHA` mixes the user query vector with the averaged reference-wine vector.
`CUSTOM_RERANK_A` mixes review embeddings with generated tasting-note embeddings for each wine.

## Run

Run the prototype:

```bash
python main.py
```

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
