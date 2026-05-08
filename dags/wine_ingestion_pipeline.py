"""
Wine Recommender – Airflow Ingestion Pipeline
=============================================

Two DAGs:
  1. wine_catalog_ingestion  – API-driven via fetch_vivino_wines(), loads all
                               normalized catalog tables into PostgreSQL.
  2. wine_reviews_ingestion  – API-driven (Vivino reviews endpoint), upserts
                               users, inserts reviews, and refreshes rating
                               aggregates on wine and vintage.

fetch_vivino_wines() field → PostgreSQL schema column mapping:

  winery_name / winery_seo_name → winery.name / winery.seo_name
  wine_name   / wine_seo_name   → wine.name   / wine.seo_name
  vintage_name / vintage_seo_name / vintage_year → vintage.*
  country_name / country_seo_name / country_code → country.*
  region_name  / region_seo_name               → region.*
  style_name   / style_seo_name / style_*      → style.*
  taste_*                                      → wine_taste_structure.*
  wine_flavors[].group / .{primary,secondary}_keywords → flavor_group / flavor_keyword / wine_flavor
  style_grapes_composition                     → grape / style_grape

Airflow connection required:
  conn_id  : wine_db
  type     : postgres
  host     : postgres   (Docker service name)
  schema   : WineAI
  login    : wine_user
  password : wine_password
  port     : 5432

wine_flavor package must be on PYTHONPATH (mounted via Docker volume at /opt/airflow).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta

import requests
from airflow.decorators import dag, task, task_group
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models import (
    Country,
    FlavorGroup,
    FlavorGroupKeyword,
    FlavorKeyword,
    Grape,
    Region,
    Style,
    StyleGrape,
    User,
    Vintage,
    Wine,
    WineFlavor,
    WineReview,
    WineTasteStructure,
    WineType,
    Winery,
)
from db.session import get_airflow_engine

log = logging.getLogger(__name__)

POSTGRES_CONN_ID = "wine_db"

# Catalog slices: (country_code | None, wine_type_ids, num_pages)
CATALOG_FETCH_SLICES: list[tuple] = [
    ("FR", [1],    3),   # France – Red
    ("FR", [2],    2),   # France – White
    ("IT", [1],    3),   # Italy – Red
    ("IT", [2],    2),   # Italy – White
    ("ES", [1],    2),   # Spain – Red
    ("US", [1],    2),   # US – Red
    ("US", [2],    2),   # US – White
    ("AR", [1],    2),   # Argentina – Red
    ("AU", [1, 2], 2),   # Australia – mixed
    (None, [3],    2),   # Sparkling – global
    (None, [4],    1),   # Rosé – global
]

REVIEWS_API_URL   = "https://www.vivino.com/api/wines/{wine_id}/reviews"
REVIEWS_PAGE_SIZE = 25
API_SLEEP_SECONDS = 0.5

default_args = {
    "owner": "data_team",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_engine():
    return get_airflow_engine(POSTGRES_CONN_ID)


def to_seo_name(name: str) -> str:
    """Fallback seo_name generator — only used when API returns None for seo_name."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ─────────────────────────────────────────────────────────────────────────────
# DAG 1 – Catalog ingestion (Vivino API → PostgreSQL)
# ─────────────────────────────────────────────────────────────────────────────

@dag(
    dag_id="wine_catalog_ingestion",
    description="Fetch wine catalog from Vivino API and load into WineAI PostgreSQL",
    schedule_interval="@weekly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["wine", "catalog"],
)
def wine_catalog_ingestion():

    # ── 0. Fetch ──────────────────────────────────────────────────────────────

    @task
    def fetch_catalog() -> list[dict]:
        """Call fetch_vivino_wines for each configured slice and deduplicate on wine_id."""
        from wine_flavor.datasource.vivino.vivino_fetch_flavors import fetch_vivino_wines

        seen: dict[int, dict] = {}
        for country_code, wine_type_ids, num_pages in CATALOG_FETCH_SLICES:
            log.info("Fetching: country=%s types=%s pages=%d",
                     country_code, wine_type_ids, num_pages)
            df = fetch_vivino_wines(
                country_code=country_code,
                wine_type_ids=wine_type_ids,
                num_pages=num_pages,
            )
            for row in df.to_dict(orient="records"):
                wine_id = row.get("wine_id")
                if wine_id and wine_id not in seen:
                    row["wine_flavors"]             = row.get("wine_flavors")             or []
                    row["style_food_pairings"]      = row.get("style_food_pairings")      or []
                    row["style_grapes_composition"] = row.get("style_grapes_composition") or []
                    seen[int(wine_id)] = row

        records = list(seen.values())
        log.info("Fetched %d unique wines", len(records))
        return records

    # ── 1. Lookup tables ──────────────────────────────────────────────────────

    @task_group(group_id="lookup_tables")
    def lookup_tables(records: list[dict]):

        @task
        def load_wine_types(_records: list[dict]) -> None:
            rows = [
                {"id": 1,  "name": "Red",       "seo_name": "red"},
                {"id": 2,  "name": "White",     "seo_name": "white"},
                {"id": 3,  "name": "Sparkling", "seo_name": "sparkling"},
                {"id": 4,  "name": "Rosé",      "seo_name": "rose"},
                {"id": 7,  "name": "Dessert",   "seo_name": "dessert"},
                {"id": 24, "name": "Fortified", "seo_name": "fortified"},
            ]
            stmt = pg_insert(WineType).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_=dict(name=stmt.excluded.name, seo_name=stmt.excluded.seo_name),
            )
            with get_engine().begin() as conn:
                conn.execute(stmt)

        @task
        def load_countries(records: list[dict]) -> None:
            seen: dict[str, dict] = {}
            for r in records:
                code = r.get("country_code")
                name = r.get("country_name")
                seo  = r.get("country_seo_name") or (to_seo_name(name) if name else None)
                if code and name and seo:
                    seen[code] = {"name": name, "seo_name": seo, "country_code": code}

            if not seen:
                return
            stmt = pg_insert(Country).values(list(seen.values()))
            stmt = stmt.on_conflict_do_update(
                index_elements=["country_code"],
                set_=dict(name=stmt.excluded.name, seo_name=stmt.excluded.seo_name),
            )
            with get_engine().begin() as conn:
                conn.execute(stmt)

        @task
        def load_regions(records: list[dict]) -> None:
            seen: dict[str, dict] = {}
            for r in records:
                name = r.get("region_name")
                seo  = r.get("region_seo_name") or (to_seo_name(name) if name else None)
                code = r.get("country_code")
                if name and seo and code:
                    seen[seo] = {"name": name, "seo_name": seo, "country_code": code}

            if not seen:
                return

            with get_engine().begin() as conn:
                country_map = {
                    row[0]: row[1]
                    for row in conn.execute(select(Country.country_code, Country.id))
                }
                rows = [
                    {"name": v["name"], "seo_name": v["seo_name"],
                     "country_id": country_map[v["country_code"]]}
                    for v in seen.values()
                    if v["country_code"] in country_map
                ]
                if not rows:
                    return
                stmt = pg_insert(Region).values(rows)
                conn.execute(stmt.on_conflict_do_update(
                    index_elements=["seo_name"],
                    set_=dict(name=stmt.excluded.name, country_id=stmt.excluded.country_id),
                ))

        @task
        def load_styles(records: list[dict]) -> None:
            seen: dict[str, dict] = {}
            for r in records:
                name = r.get("style_name")
                seo  = r.get("style_seo_name") or (to_seo_name(name) if name else None)
                if name and seo and seo not in seen:
                    seen[seo] = {
                        "name":                name,
                        "seo_name":            seo,
                        "description":         r.get("style_description"),
                        "body_description":    r.get("style_body_description"),
                        "acidity_description": r.get("style_acidity_description"),
                        "wine_type_id":        r.get("wine_type_id"),
                    }

            if not seen:
                return
            stmt = pg_insert(Style).values(list(seen.values()))
            stmt = stmt.on_conflict_do_update(
                index_elements=["seo_name"],
                set_=dict(
                    name=stmt.excluded.name,
                    description=stmt.excluded.description,
                    body_description=stmt.excluded.body_description,
                    acidity_description=stmt.excluded.acidity_description,
                    wine_type_id=stmt.excluded.wine_type_id,
                ),
            )
            with get_engine().begin() as conn:
                conn.execute(stmt)

        wt = load_wine_types(records)
        co = load_countries(records)
        re = load_regions(records)
        st = load_styles(records)

        co >> re   # region FK → country
        wt >> st   # style FK → wine_type

    # ── 2. Grapes ─────────────────────────────────────────────────────────────

    @task_group(group_id="grape_tables")
    def grape_tables(records: list[dict]):

        @task
        def load_grapes(records: list[dict]) -> None:
            seen: dict[str, str] = {}
            for r in records:
                for gname in r.get("style_grapes_composition") or []:
                    if gname:
                        seen[to_seo_name(gname)] = gname

            if not seen:
                return
            stmt = pg_insert(Grape).values(
                [{"name": name, "seo_name": seo} for seo, name in seen.items()]
            )
            with get_engine().begin() as conn:
                conn.execute(stmt.on_conflict_do_update(
                    index_elements=["seo_name"],
                    set_=dict(name=stmt.excluded.name),
                ))

        @task
        def load_style_grapes(records: list[dict]) -> None:
            rows_raw: list[tuple] = []
            for r in records:
                sseo = r.get("style_seo_name")
                if not sseo:
                    continue
                for sort_order, gname in enumerate(r.get("style_grapes_composition") or []):
                    if gname:
                        rows_raw.append((sseo, to_seo_name(gname), sort_order))

            if not rows_raw:
                return

            with get_engine().begin() as conn:
                style_map = {row[0]: row[1] for row in conn.execute(select(Style.seo_name, Style.id))}
                grape_map = {row[0]: row[1] for row in conn.execute(select(Grape.seo_name, Grape.id))}
                rows = [
                    {"style_id": style_map[sseo], "grape_id": grape_map[gseo],
                     "sort_order": sort_order}
                    for sseo, gseo, sort_order in rows_raw
                    if sseo in style_map and gseo in grape_map
                ]
                if not rows:
                    return
                stmt = pg_insert(StyleGrape).values(rows)
                conn.execute(stmt.on_conflict_do_update(
                    index_elements=["style_id", "grape_id"],
                    set_=dict(sort_order=stmt.excluded.sort_order),
                ))

        gr = load_grapes(records)
        gr >> load_style_grapes(records)

    # ── 3. Winery ─────────────────────────────────────────────────────────────

    @task
    def load_wineries(records: list[dict]) -> None:
        seen: dict[str, dict] = {}
        for r in records:
            name = r.get("winery_name")
            seo  = r.get("winery_seo_name")
            if name and seo:
                seen[seo] = {
                    "name":         name,
                    "seo_name":     seo,
                    "region_seo":   r.get("region_seo_name"),
                    "country_code": r.get("country_code"),
                }

        if not seen:
            return

        with get_engine().begin() as conn:
            region_map  = {row[0]: row[1] for row in conn.execute(select(Region.seo_name,      Region.id))}
            country_map = {row[0]: row[1] for row in conn.execute(select(Country.country_code, Country.id))}

            rows = [
                {
                    "name":       w["name"],
                    "seo_name":   w["seo_name"],
                    "region_id":  region_map.get(w["region_seo"]),
                    "country_id": country_map.get(w["country_code"]),
                }
                for w in seen.values()
            ]
            stmt = pg_insert(Winery).values(rows)
            conn.execute(stmt.on_conflict_do_update(
                index_elements=["seo_name"],
                set_=dict(
                    name=stmt.excluded.name,
                    region_id=stmt.excluded.region_id,
                    country_id=stmt.excluded.country_id,
                ),
            ))

    # ── 4. Wine ───────────────────────────────────────────────────────────────

    @task
    def load_wines(records: list[dict]) -> None:
        seen: dict[str, dict] = {}
        for r in records:
            name = r.get("wine_name")
            seo  = r.get("wine_seo_name")
            if name and seo:
                seen[seo] = {
                    "name":         name,
                    "seo_name":     seo,
                    "wine_type_id": r.get("wine_type_id"),
                    "is_natural":   bool(r.get("is_natural")),
                    "winery_seo":   r.get("winery_seo_name"),
                    "region_seo":   r.get("region_seo_name"),
                    "country_code": r.get("country_code"),
                    "style_seo":    r.get("style_seo_name"),
                }

        if not seen:
            return

        with get_engine().begin() as conn:
            winery_map  = {row[0]: row[1] for row in conn.execute(select(Winery.seo_name,      Winery.id))}
            region_map  = {row[0]: row[1] for row in conn.execute(select(Region.seo_name,      Region.id))}
            country_map = {row[0]: row[1] for row in conn.execute(select(Country.country_code, Country.id))}
            style_map   = {row[0]: row[1] for row in conn.execute(select(Style.seo_name,       Style.id))}

            rows = [
                {
                    "name":         w["name"],
                    "seo_name":     w["seo_name"],
                    "wine_type_id": w["wine_type_id"],
                    "is_natural":   w["is_natural"],
                    "winery_id":    winery_map.get(w["winery_seo"]),
                    "region_id":    region_map.get(w["region_seo"]),
                    "country_id":   country_map.get(w["country_code"]),
                    "style_id":     style_map.get(w["style_seo"]),
                }
                for w in seen.values()
                if winery_map.get(w["winery_seo"])  # winery_id is NOT NULL
            ]
            if not rows:
                return
            stmt = pg_insert(Wine).values(rows)
            conn.execute(stmt.on_conflict_do_update(
                index_elements=["seo_name"],
                set_=dict(
                    name=stmt.excluded.name,
                    wine_type_id=stmt.excluded.wine_type_id,
                    is_natural=stmt.excluded.is_natural,
                    winery_id=stmt.excluded.winery_id,
                    region_id=stmt.excluded.region_id,
                    country_id=stmt.excluded.country_id,
                    style_id=stmt.excluded.style_id,
                ),
            ))

    # ── 5. Vintages ───────────────────────────────────────────────────────────

    @task
    def load_vintages(records: list[dict]) -> None:
        seen: dict[str, dict] = {}
        for r in records:
            name     = r.get("vintage_name")
            seo      = r.get("vintage_seo_name")
            wine_seo = r.get("wine_seo_name")
            year     = r.get("vintage_year")
            if name and seo and wine_seo and year:
                seen[seo] = {
                    "name":           name,
                    "seo_name":       seo,
                    "wine_seo":       wine_seo,
                    "year":           int(year),
                    "price_amount":   r.get("price_amount"),
                    "price_currency": r.get("price_currency"),
                    "average_rating": r.get("rating_average"),
                    "num_reviews":    int(r.get("ratings_count") or 0),
                }

        if not seen:
            return

        with get_engine().begin() as conn:
            wine_map = {row[0]: row[1] for row in conn.execute(select(Wine.seo_name, Wine.id))}

            rows = [
                {
                    "name":           v["name"],
                    "seo_name":       v["seo_name"],
                    "wine_id":        wine_map[v["wine_seo"]],
                    "year":           v["year"],
                    "price_amount":   v["price_amount"],
                    "price_currency": v["price_currency"],
                    "average_rating": v["average_rating"],
                    "num_reviews":    v["num_reviews"],
                }
                for v in seen.values()
                if v["wine_seo"] in wine_map
            ]
            if not rows:
                return
            stmt = pg_insert(Vintage).values(rows)
            conn.execute(stmt.on_conflict_do_update(
                index_elements=["seo_name"],
                set_=dict(
                    name=stmt.excluded.name,
                    year=stmt.excluded.year,
                    price_amount=stmt.excluded.price_amount,
                    price_currency=stmt.excluded.price_currency,
                    average_rating=stmt.excluded.average_rating,
                    num_reviews=stmt.excluded.num_reviews,
                ),
            ))

    # ── 6. Taste profile ──────────────────────────────────────────────────────

    @task_group(group_id="taste_profile")
    def taste_profile(records: list[dict]):

        @task
        def load_taste_structures(records: list[dict]) -> None:
            seen: dict[str, dict] = {}
            for r in records:
                seo = r.get("wine_seo_name")
                if seo:
                    seen[seo] = {
                        "wine_seo":  seo,
                        "acidity":   r.get("taste_acidity"),
                        "fizziness": r.get("taste_fizziness"),
                        "intensity": r.get("taste_intensity"),
                        "sweetness": r.get("taste_sweetness"),
                        "tannin":    r.get("taste_tannin"),
                    }

            if not seen:
                return

            with get_engine().begin() as conn:
                wine_map = {row[0]: row[1] for row in conn.execute(select(Wine.seo_name, Wine.id))}
                rows = [
                    {
                        "wine_id":   wine_map[w["wine_seo"]],
                        "acidity":   w["acidity"],
                        "fizziness": w["fizziness"],
                        "intensity": w["intensity"],
                        "sweetness": w["sweetness"],
                        "tannin":    w["tannin"],
                    }
                    for w in seen.values()
                    if w["wine_seo"] in wine_map
                ]
                if not rows:
                    return
                stmt = pg_insert(WineTasteStructure).values(rows)
                conn.execute(stmt.on_conflict_do_update(
                    index_elements=["wine_id"],
                    set_=dict(
                        acidity=stmt.excluded.acidity,
                        fizziness=stmt.excluded.fizziness,
                        intensity=stmt.excluded.intensity,
                        sweetness=stmt.excluded.sweetness,
                        tannin=stmt.excluded.tannin,
                    ),
                ))

        @task
        def load_flavor_taxonomy(records: list[dict]) -> None:
            groups:   dict[str, str] = {}
            keywords: dict[str, str] = {}
            gk_rows:  list[tuple]    = []

            for r in records:
                for fg in r.get("wine_flavors") or []:
                    group = fg.get("group")
                    if not group:
                        continue
                    gseo = to_seo_name(group)
                    groups[gseo] = group.replace("_", " ").title()
                    for role, kw_list in [
                        ("primary",   fg.get("primary_keywords")   or []),
                        ("secondary", fg.get("secondary_keywords") or []),
                    ]:
                        for kw in kw_list:
                            kname = kw.get("name")
                            if not kname:
                                continue
                            kseo = to_seo_name(kname)
                            keywords[kseo] = kname
                            gk_rows.append((gseo, kseo, role))

            with get_engine().begin() as conn:
                if groups:
                    stmt = pg_insert(FlavorGroup).values(
                        [{"name": name, "seo_name": seo} for seo, name in groups.items()]
                    )
                    conn.execute(stmt.on_conflict_do_update(
                        index_elements=["seo_name"],
                        set_=dict(name=stmt.excluded.name),
                    ))

                if keywords:
                    stmt = pg_insert(FlavorKeyword).values(
                        [{"name": name, "seo_name": seo} for seo, name in keywords.items()]
                    )
                    conn.execute(stmt.on_conflict_do_update(
                        index_elements=["seo_name"],
                        set_=dict(name=stmt.excluded.name),
                    ))

                if gk_rows:
                    group_map   = {r[0]: r[1] for r in conn.execute(select(FlavorGroup.seo_name,   FlavorGroup.id))}
                    keyword_map = {r[0]: r[1] for r in conn.execute(select(FlavorKeyword.seo_name, FlavorKeyword.id))}
                    fgk_rows = [
                        {"flavor_group_id":   group_map[gseo],
                         "flavor_keyword_id": keyword_map[kseo],
                         "keyword_role":      role}
                        for gseo, kseo, role in gk_rows
                        if gseo in group_map and kseo in keyword_map
                    ]
                    if fgk_rows:
                        stmt = pg_insert(FlavorGroupKeyword).values(fgk_rows)
                        conn.execute(stmt.on_conflict_do_update(
                            index_elements=["flavor_group_id", "flavor_keyword_id"],
                            set_=dict(keyword_role=stmt.excluded.keyword_role),
                        ))

        @task
        def load_wine_flavors(records: list[dict]) -> None:
            totals: dict[str, dict[str, int]] = {}
            for r in records:
                wseo = r.get("wine_seo_name")
                if not wseo:
                    continue
                totals.setdefault(wseo, {})
                for fg in r.get("wine_flavors") or []:
                    for kw_list in [
                        fg.get("primary_keywords")   or [],
                        fg.get("secondary_keywords") or [],
                    ]:
                        for kw in kw_list:
                            kname = kw.get("name")
                            if not kname:
                                continue
                            kseo = to_seo_name(kname)
                            cnt  = int(kw.get("count") or 1)
                            totals[wseo][kseo] = totals[wseo].get(kseo, 0) + cnt

            if not totals:
                return

            with get_engine().begin() as conn:
                wine_map    = {r[0]: r[1] for r in conn.execute(select(Wine.seo_name,          Wine.id))}
                keyword_map = {r[0]: r[1] for r in conn.execute(select(FlavorKeyword.seo_name, FlavorKeyword.id))}

                rows = [
                    {"wine_id": wine_map[wseo], "flavor_keyword_id": keyword_map[kseo], "count": cnt}
                    for wseo, kws in totals.items()
                    if wseo in wine_map
                    for kseo, cnt in kws.items()
                    if kseo in keyword_map
                ]
                if not rows:
                    return
                stmt = pg_insert(WineFlavor).values(rows)
                conn.execute(stmt.on_conflict_do_update(
                    index_elements=["wine_id", "flavor_keyword_id"],
                    set_=dict(count=stmt.excluded.count),
                ))

        ft = load_flavor_taxonomy(records)
        ts = load_taste_structures(records)
        wf = load_wine_flavors(records)
        ft >> wf  # wine_flavor depends on flavor_keyword rows existing

    # ── 7. Wine-level rating aggregates from vintage stats ────────────────────

    @task
    def update_wine_rating_aggregates() -> None:
        with get_engine().begin() as conn:
            conn.execute(text("""
                UPDATE wine w
                SET wine_rating_average = sub.avg_rating,
                    wine_rating_count   = sub.total_reviews,
                    last_reviewed_at    = NOW()
                FROM (
                    SELECT
                        wine_id,
                        AVG(average_rating) FILTER (WHERE average_rating IS NOT NULL) AS avg_rating,
                        SUM(num_reviews)                                               AS total_reviews
                    FROM vintage
                    GROUP BY wine_id
                ) sub
                WHERE w.id = sub.wine_id
            """))
        log.info("Updated wine-level rating aggregates from vintages")

    # ── Wire up ───────────────────────────────────────────────────────────────

    raw          = fetch_catalog()
    lookups      = lookup_tables(raw)
    grapes       = grape_tables(raw)
    winery_task  = load_wineries(raw)
    wine_task    = load_wines(raw)
    vintage_task = load_vintages(raw)
    taste_tasks  = taste_profile(raw)
    agg_task     = update_wine_rating_aggregates()

    lookups     >> winery_task
    grapes      >> winery_task   # style exists before winery for style_grape integrity
    winery_task >> wine_task
    wine_task   >> [vintage_task, taste_tasks]
    vintage_task >> agg_task


wine_catalog_dag = wine_catalog_ingestion()


# ─────────────────────────────────────────────────────────────────────────────
# DAG 2 – Reviews ingestion (Vivino API → PostgreSQL)
# ─────────────────────────────────────────────────────────────────────────────
# Calls the Vivino reviews API directly so that review.user.id (integer) is
# captured for the wine_review.user_id FK. fetch_vivino_reviews() does not
# expose user.id, so it is not used here.
# ─────────────────────────────────────────────────────────────────────────────

@dag(
    dag_id="wine_reviews_ingestion",
    description="Fetch wine reviews from Vivino API and load into WineAI PostgreSQL",
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["wine", "reviews"],
)
def wine_reviews_ingestion():

    @task
    def get_wine_ids() -> list[int]:
        with get_engine().connect() as conn:
            result = conn.execute(
                select(Wine.id)
                .where(
                    (Wine.last_reviewed_at == None) |  # noqa: E711
                    (Wine.last_reviewed_at < text("NOW() - INTERVAL '7 days'"))
                )
                .order_by(Wine.last_reviewed_at.asc().nullsfirst())
            )
            ids = [row[0] for row in result]
        log.info("Found %d wines to refresh reviews for", len(ids))
        return ids

    @task
    def fetch_and_store_reviews(wine_ids: list[int]) -> dict:
        """Page through the Vivino reviews API and upsert users and reviews.

        API → DB mapping:
          review.user.id       → "user".id       (integer PK from API)
          review.user.seo_name → "user".username
          review.user.alias    → "user".display_name
          review.rating        → wine_review.rating
          review.note          → wine_review.review
        """
        summary: dict[int, list] = {}
        engine = get_engine()

        for wine_id in wine_ids:
            wine_reviews: list[dict] = []
            user_rows:    list[dict] = []
            review_rows:  list[dict] = []
            page = 1

            while True:
                try:
                    resp = requests.get(
                        REVIEWS_API_URL.format(wine_id=wine_id),
                        params={"per_page": REVIEWS_PAGE_SIZE, "page": page},
                        timeout=10,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    log.warning("Failed to fetch reviews for wine %s (page %d): %s",
                                wine_id, page, exc)
                    break

                reviews = data.get("reviews", [])
                if not reviews:
                    break

                for item in reviews:
                    user    = item.get("user") or {}
                    user_id = user.get("id")
                    rating  = item.get("rating")
                    note    = item.get("note")

                    if user_id:
                        user_rows.append({
                            "id":           user_id,
                            "username":     user.get("seo_name") or str(user_id),
                            "display_name": user.get("alias") or user.get("seo_name"),
                        })

                    if note:
                        review_rows.append({
                            "wine_id": wine_id,
                            "user_id": user_id,
                            "rating":  rating,
                            "review":  note,
                        })

                    wine_reviews.append({"user_id": user_id, "rating": rating})

                page += 1
                time.sleep(API_SLEEP_SECONDS)

            with engine.begin() as conn:
                if user_rows:
                    stmt = pg_insert(User).values(user_rows)
                    conn.execute(stmt.on_conflict_do_update(
                        index_elements=["id"],
                        set_=dict(
                            username=stmt.excluded.username,
                            display_name=stmt.excluded.display_name,
                        ),
                    ))
                if review_rows:
                    conn.execute(pg_insert(WineReview).values(review_rows))

            summary[wine_id] = wine_reviews
            log.info("Wine %s: stored %d reviews", wine_id, len(wine_reviews))

        return summary

    @task
    def update_rating_aggregates(summary: dict) -> None:
        wine_ids = list(summary.keys())
        if not wine_ids:
            return

        with get_engine().begin() as conn:
            conn.execute(text("""
                UPDATE wine w
                SET wine_rating_count   = sub.total_reviews,
                    wine_rating_average = sub.avg_rating,
                    last_reviewed_at    = sub.latest
                FROM (
                    SELECT
                        wr.wine_id,
                        COUNT(*)                                              AS total_reviews,
                        AVG(wr.rating) FILTER (WHERE wr.rating IS NOT NULL)  AS avg_rating,
                        MAX(wr.created_at)                                   AS latest
                    FROM wine_review wr
                    WHERE wr.wine_id = ANY(:ids)
                    GROUP BY wr.wine_id
                ) sub
                WHERE w.id = sub.wine_id
            """), {"ids": wine_ids})

            conn.execute(text("""
                UPDATE vintage v
                SET last_reviewed_at = w.last_reviewed_at
                FROM wine w
                WHERE v.wine_id = w.id AND w.id = ANY(:ids)
            """), {"ids": wine_ids})

        log.info("Updated rating aggregates for %d wines", len(wine_ids))

    @task
    def update_user_review_counts() -> None:
        with get_engine().begin() as conn:
            conn.execute(text("""
                UPDATE "user" u
                SET review_count = sub.cnt
                FROM (
                    SELECT user_id, COUNT(*) AS cnt
                    FROM wine_review
                    WHERE user_id IS NOT NULL
                    GROUP BY user_id
                ) sub
                WHERE u.id = sub.user_id
            """))

    ids     = get_wine_ids()
    summary = fetch_and_store_reviews(ids)
    agg     = update_rating_aggregates(summary)
    ucounts = update_user_review_counts()

    summary >> [agg, ucounts]


wine_reviews_dag = wine_reviews_ingestion()
