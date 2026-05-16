"""Pydantic schemas for the Wine Flavor Demo API.

Request models validate incoming JSON payloads.
Response models validate and document outgoing JSON payloads.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

_COSINE_TOP_K = int(os.getenv("COSINE_TOP_K", "20"))


# ── Shared building blocks ────────────────────────────────────────────────────

class TasteStructure(BaseModel):
    """Taste dimensions scaled to 0–100 for the UI (raw Vivino 0–5 × 20)."""

    acidity:   int = Field(ge=0, le=100)
    fizziness: int = Field(ge=0, le=100)
    intensity: int = Field(ge=0, le=100)
    sweetness: int = Field(ge=0, le=100)
    tannin:    int = Field(ge=0, le=100)


class WineRecord(BaseModel):
    """A single wine entry as returned by /catalog and /detect-wine-image."""

    id:        str
    row_index: int
    name:      str | None = None
    winery:    str | None = None
    vintage:   int | None = None
    country:   str | None = None
    region:    str | None = None
    style:     str
    price:     float | None = None
    structure: TasteStructure
    flavors:   list[str]


# ── Request models ────────────────────────────────────────────────────────────

class StructurePreferences(BaseModel):
    """User taste-profile input, each dimension in [0, 1]."""

    acidity:   float = Field(ge=0.0, le=1.0)
    fizziness: float = Field(ge=0.0, le=1.0)
    intensity: float = Field(ge=0.0, le=1.0)
    sweetness: float = Field(ge=0.0, le=1.0)
    tannin:    float = Field(ge=0.0, le=1.0)


class RecommendationRequest(BaseModel):
    structure:             StructurePreferences
    flavors:               dict[str, float] = Field(default_factory=dict)
    reference_row_indices: list[int]        = Field(default_factory=list)
    top_k:                 int              = Field(default=_COSINE_TOP_K, ge=1, le=50)


# ── Response models ───────────────────────────────────────────────────────────

class RootResponse(BaseModel):
    name:            str
    status:          str
    health:          str
    recommendations: str


class HealthResponse(BaseModel):
    status:          str
    rerank_method:   str
    catalog_loaded:  bool
    demo_num_pages:  int


class FlavorTag(BaseModel):
    category: str
    flavors:  list[str]


class CatalogResponse(BaseModel):
    wines:      list[WineRecord]
    flavorTags: list[FlavorTag]


class RecommendationRecord(BaseModel):
    id:              str
    name:            str | None = None
    winery:          str | None = None
    vintage:         int | None = None
    country:         str | None = None
    region:          str | None = None
    style:           str | None = None
    price:           float | None = None
    matchPercentage: int = Field(ge=0, le=100)
    flavorSummary:   str
    structure:       TasteStructure | None = None
    flavors:         list[str]
    reviewCount:     int | None = None
    rerankScore:     float


class RecommendationsResponse(BaseModel):
    rerank_method:   str
    candidate_count: int
    results:         list[RecommendationRecord]


class DetectedWineResponse(BaseModel):
    detected_wine: WineRecord | None = None
    match_score:   float | None = None
    ocr_text:      str | None = None


class ReloadResponse(BaseModel):
    status:             str
    wine_count:         int
    flavor_count:       int
    chroma_wine_vectors: int
