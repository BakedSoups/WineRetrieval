import os
from contextlib import asynccontextmanager
from threading import Lock

import datasource
import engine
import pandas as pd
import pretty_print
import transforms
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()


def _require_env(name):
    value = os.getenv(name)
    if value is None or value == "":
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _require_float_env(name, fallback_name=None):
    value = os.getenv(name)
    if (value is None or value == "") and fallback_name:
        value = os.getenv(fallback_name)
    if value is None or value == "":
        if fallback_name:
            raise ValueError(f"Missing required environment variable: {name} (or legacy {fallback_name})")
        raise ValueError(f"Missing required environment variable: {name}")
    return float(value)


def _require_int_env(name, default):
    value = os.getenv(name)
    if value is None or value == "":
        return int(default)
    return int(value)


try:
    SIE_BASE_URL = _require_env("CLUSTER_URL")
    SIE_API_KEY = _require_env("API_KEY")
    RERANK_METHOD = _require_env("RERANK_METHOD")
    SIE_RERANK_MODEL = _require_env("SIE_RERANK_MODEL")
    SIE_EMBEDDING_MODEL = _require_env("SIE_EMBEDDING_MODEL")
    RERANK_ALPHA = _require_float_env("RERANK_ALPHA")
    CUSTOM_RERANK_A = _require_float_env("CUSTOM_RERANK_A")
    CUSTOM_RERANK_NO_REVIEW_PENALTY = float(_require_env("CUSTOM_RERANK_NO_REVIEW_PENALTY"))
except ValueError as exc:
    raise ValueError(f"{exc}. Add it to your .env file.") from exc

ALLOWED_SIE_RERANK_MODELS = {
    "BAAI/bge-reranker-v2-m3",
    "jinaai/jina-reranker-v2-base-multilingual",
}
ALLOWED_RERANK_METHODS = {"standard", "custom"}
DEMO_NUM_PAGES = _require_int_env("DEMO_NUM_PAGES", 5)
DEMO_MAX_WINES = _require_int_env("DEMO_MAX_WINES", 100)
REVIEWS_PER_WINE = _require_int_env("REVIEWS_PER_WINE", 5)
REVIEW_PAGES = _require_int_env("REVIEW_PAGES", 1)
COSINE_TOP_K = _require_int_env("COSINE_TOP_K", 5)
RERANK_MAX_TERMS = _require_int_env("RERANK_MAX_TERMS", 12)
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

if RERANK_METHOD not in ALLOWED_RERANK_METHODS:
    raise ValueError(
        f"Unsupported rerank method '{RERANK_METHOD}'. "
        f"Choose one of: {sorted(ALLOWED_RERANK_METHODS)}"
    )

if SIE_RERANK_MODEL not in ALLOWED_SIE_RERANK_MODELS:
    raise ValueError(
        f"Unsupported SIE reranker model '{SIE_RERANK_MODEL}'. "
        f"Choose one of: {sorted(ALLOWED_SIE_RERANK_MODELS)}"
    )


class StructurePreferences(BaseModel):
    acidity: float = Field(ge=0.0, le=1.0)
    fizziness: float = Field(ge=0.0, le=1.0)
    intensity: float = Field(ge=0.0, le=1.0)
    sweetness: float = Field(ge=0.0, le=1.0)
    tannin: float = Field(ge=0.0, le=1.0)


class RecommendationRequest(BaseModel):
    structure: StructurePreferences
    flavors: dict[str, float] = Field(default_factory=dict)
    reference_row_indices: list[int] = Field(default_factory=list)
    top_k: int = Field(default=COSINE_TOP_K, ge=1, le=50)


class DemoCatalog:
    def __init__(self):
        self._lock = Lock()
        self._loaded = False
        self.wines = None
        self.unique_flavors = None
        self.flavor_idf = None
        self.wine_matrix = None

    def load(self, force=False):
        with self._lock:
            if self._loaded and not force:
                return

            wines = datasource.fetch_vivino_wines(num_pages=DEMO_NUM_PAGES)
            if DEMO_MAX_WINES > 0:
                wines = wines.head(DEMO_MAX_WINES).copy()

            wines = datasource.attach_vivino_reviews(
                wines,
                review_pages=REVIEW_PAGES,
                reviews_per_page=REVIEWS_PER_WINE,
                language="en",
            )
            unique_flavors = transforms.unique_flavors(wines)
            flavor_idf = engine.build_flavor_idf(wines)
            wine_matrix = engine.build_wine_matrix(wines, unique_flavors, flavor_idf)

            self.wines = wines
            self.unique_flavors = unique_flavors
            self.flavor_idf = flavor_idf
            self.wine_matrix = wine_matrix
            self._loaded = True


catalog = DemoCatalog()


def _request_to_preferences(payload):
    return {
        "structure": payload.structure.model_dump(),
        "flavors": {name: float(value) for name, value in payload.flavors.items()},
    }


def _normalize_record(record):
    if isinstance(record, dict):
        return {key: _normalize_record(value) for key, value in record.items()}

    if isinstance(record, list):
        return [_normalize_record(value) for value in record]

    if isinstance(record, tuple):
        return [_normalize_record(value) for value in record]

    try:
        if pd.isna(record):
            return None
    except (TypeError, ValueError):
        pass

    return record


def _to_ui_structure_from_row(wine_row):
    def _scale(value):
        if value is None or pd.isna(value):
            return 0
        return int(round(float(value) * 20))

    return {
        "acidity": _scale(wine_row.get("taste_acidity")),
        "fizziness": _scale(wine_row.get("taste_fizziness")),
        "intensity": _scale(wine_row.get("taste_intensity")),
        "sweetness": _scale(wine_row.get("taste_sweetness")),
        "tannin": _scale(wine_row.get("taste_tannin")),
    }


def _extract_wine_flavors(wine_row, max_flavors=6):
    flavor_counts = {}
    for flavor_group in wine_row.get("wine_flavors", []) or []:
        for keyword in flavor_group.get("primary_keywords") or []:
            name = keyword.get("name")
            count = keyword.get("count", 1) or 1
            if name:
                flavor_counts[name] = flavor_counts.get(name, 0) + count
        for keyword in flavor_group.get("secondary_keywords") or []:
            name = keyword.get("name")
            count = keyword.get("count", 1) or 1
            if name:
                flavor_counts[name] = flavor_counts.get(name, 0) + count

    ordered_flavors = sorted(flavor_counts.items(), key=lambda item: item[1], reverse=True)
    return [name for name, _ in ordered_flavors[:max_flavors]]


def _wine_style(wine_row):
    return wine_row.get("style_name") or wine_row.get("style_varietal_name") or "Wine"


def _catalog_wine_record(wine_row):
    wine_id = wine_row.get("wine_id")
    return _normalize_record({
        "id": str(int(wine_id)) if wine_id is not None and not pd.isna(wine_id) else "",
        "row_index": int(wine_row.name),
        "name": wine_row.get("wine_name"),
        "winery": wine_row.get("winery_name"),
        "vintage": wine_row.get("vintage_year"),
        "country": wine_row.get("country_name"),
        "region": wine_row.get("region_name"),
        "style": _wine_style(wine_row),
        "price": wine_row.get("price_amount"),
        "structure": _to_ui_structure_from_row(wine_row),
        "flavors": _extract_wine_flavors(wine_row),
    })


def _build_flavor_tags(wines):
    grouped_flavors = {}

    for _, wine_row in wines.iterrows():
        for flavor_group in wine_row.get("wine_flavors", []) or []:
            category = (flavor_group.get("group") or "other").replace("_", " ").title()
            grouped_flavors.setdefault(category, set())
            for keyword in flavor_group.get("primary_keywords") or []:
                if keyword.get("name"):
                    grouped_flavors[category].add(keyword["name"])
            for keyword in flavor_group.get("secondary_keywords") or []:
                if keyword.get("name"):
                    grouped_flavors[category].add(keyword["name"])

    return [
        {
            "category": category,
            "flavors": sorted(list(flavors))[:12],
        }
        for category, flavors in sorted(grouped_flavors.items())
        if flavors
    ]


def _to_recommendation_record(record):
    score = float(record.get("rerank_score") or 0.0)
    return {
        "id": str(record.get("wine_id")),
        "name": record.get("wine_name"),
        "winery": record.get("winery_name"),
        "vintage": record.get("vintage_year"),
        "country": record.get("country_name"),
        "region": record.get("region_name"),
        "style": record.get("style"),
        "price": record.get("price_amount"),
        "matchPercentage": max(0, min(100, int(round(score * 100)))),
        "flavorSummary": ", ".join(record.get("flavors", [])),
        "structure": record.get("structure"),
        "flavors": record.get("flavors", []),
        "reviewCount": record.get("review_count"),
        "rerankScore": score,
    }


@asynccontextmanager
async def lifespan(_app):
    catalog.load()
    yield


app = FastAPI(title="Wine Flavor Demo API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "name": "Wine Flavor Demo API",
        "status": "ok",
        "health": "/health",
        "recommendations": "/recommendations",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "rerank_method": RERANK_METHOD,
        "catalog_loaded": catalog._loaded,
        "demo_num_pages": DEMO_NUM_PAGES,
        "demo_max_wines": DEMO_MAX_WINES,
    }


@app.get("/catalog")
def catalog_view():
    catalog.load()
    return jsonable_encoder({
        "wines": [_catalog_wine_record(wine_row) for _, wine_row in catalog.wines.iterrows()],
        "flavorTags": _build_flavor_tags(catalog.wines),
    })


@app.post("/recommendations")
def recommendations(payload: RecommendationRequest):
    catalog.load()
    user_preferences = _request_to_preferences(payload)

    user_vector = engine.build_user_vector(
        user_preferences,
        catalog.unique_flavors,
        catalog.flavor_idf,
    )
    top_matches = engine.cosine_similarity_search(
        user_vector,
        catalog.wine_matrix,
        top_k=payload.top_k,
    )
    candidate_row_indices = [match["row_index"] for match in top_matches]

    if RERANK_METHOD == "custom":
        reranked_matches = engine.rerank_wines_with_custom_embeddings(
            catalog.wines,
            candidate_row_indices,
            user_preferences,
            reference_row_indices=payload.reference_row_indices,
            base_url=SIE_BASE_URL,
            model_name=SIE_EMBEDDING_MODEL,
            a=CUSTOM_RERANK_A,
            alpha=RERANK_ALPHA,
            no_review_penalty=CUSTOM_RERANK_NO_REVIEW_PENALTY,
        )
    else:
        reranked_matches = engine.rerank_wines_with_sie_reviews(
            catalog.wines,
            candidate_row_indices,
            user_preferences,
            catalog.unique_flavors,
            catalog.flavor_idf,
            reference_row_indices=payload.reference_row_indices,
            alpha=RERANK_ALPHA,
            max_terms=RERANK_MAX_TERMS,
            base_url=SIE_BASE_URL,
            model_name=SIE_RERANK_MODEL,
        )

    result_frame = pretty_print.build_results_frame(catalog.wines, reranked_matches)
    result_records = []
    for record in result_frame.to_dict(orient="records"):
        wine_row = catalog.wines.iloc[record["row_index"]]
        enriched_record = {
            **record,
            "style": _wine_style(wine_row),
            "structure": _to_ui_structure_from_row(wine_row),
            "flavors": _extract_wine_flavors(wine_row),
        }
        result_records.append(_normalize_record(enriched_record))

    return jsonable_encoder({
        "rerank_method": RERANK_METHOD,
        "candidate_count": len(candidate_row_indices),
        "results": [_to_recommendation_record(record) for record in result_records],
    })


@app.post("/reload")
def reload_catalog():
    catalog.load(force=True)
    return {
        "status": "reloaded",
        "wine_count": len(catalog.wines),
        "flavor_count": len(catalog.unique_flavors),
    }


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
