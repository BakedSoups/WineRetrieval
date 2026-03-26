# wine_flavor

Wine retrieval experiments built on Vivino data.

## Setup

Assume you want this layout:

```bash
cd ~/code/pp
git clone <your-sie-repo-url> sie
git clone <your-wine-retrieval-repo-url> WineRetrieval
cd WineRetrieval/wine_flavor
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e ../../sie/packages/sie_sdk
pip install -e ../../sie/integrations/sie_chroma
pip install -e ../../sie/packages/sie_server
```

Start SIE in one terminal:

```bash
cd ~/code/pp/WineRetrieval/wine_flavor
source venv/bin/activate
sie-server serve
```

Run this project in another terminal:

```bash
cd ~/code/pp/WineRetrieval/wine_flavor
source venv/bin/activate
python main.py
```

## main.py

[`main.py`](/home/alex/code/pp/WineRetrieval/wine_flavor/main.py) is the main hub of operations.

It does six things:

1. Fetches wines from Vivino with `datasource.fetch_vivino_wines(...)`.
2. Fetches English reviews for those wines with `datasource.attach_vivino_reviews(...)`.
3. Builds the shared flavor vocabulary with `transforms.unique_flavors(...)`.
4. Defines the editable `user_preferences` dictionary.
5. Builds the wine matrix and user vector through `engine`.
6. Runs cosine candidate retrieval, then review-based SIE reranking, then prints the top matches.

The main things you will edit in [`main.py`](/home/alex/code/pp/WineRetrieval/wine_flavor/main.py) are:

- `SIE_BASE_URL`
- `SIE_RERANK_MODEL`
- `user_preferences`
