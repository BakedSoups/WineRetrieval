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

It does five things:

1. Fetches wines from Vivino with `datasource.fetch_vivino_wines(...)`.
2. Builds the shared flavor vocabulary with `transforms.unique_flavors(...)`.
3. Defines the editable `user_preferences` dictionary.
4. Builds the wine matrix and user vector through `engine`.
5. Runs retrieval and optional SIE reranking, then prints the top matches.

The main things you will edit in [`main.py`](/home/alex/code/pp/WineRetrieval/wine_flavor/main.py) are:

- `USE_SIE_RERANK`
- `SIE_BASE_URL`
- `SIE_RERANK_MODEL`
- `user_preferences`
