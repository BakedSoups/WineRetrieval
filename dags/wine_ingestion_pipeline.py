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
from airflow.providers.postgres.hooks.postgres import PostgresHook

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

def get_hook() -> PostgresHook:
    return PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)


def upsert_many(sql: str, rows: list[tuple]) -> None:
    if rows:
        get_hook().run(sql, parameters=rows)


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
        """Call fetch_vivino_wines for each configured slice and deduplicate on wine_id.

        Returns a JSON-serialisable list of flat wine dicts for XCom transport.
        Requires the wine_flavor package on PYTHONPATH.
        """
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
                    row["wine_flavors"]            = row.get("wine_flavors")            or []
                    row["style_food_pairings"]     = row.get("style_food_pairings")     or []
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
            """Pre-load the standard Vivino wine type set (static, no API data needed)."""
            upsert_many("""
                INSERT INTO wine_type (id, name, seo_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                  SET name = EXCLUDED.name, seo_name = EXCLUDED.seo_name
            """, [
                (1,  "Red",       "red"),
                (2,  "White",     "white"),
                (3,  "Sparkling", "sparkling"),
                (4,  "Rosé",      "rose"),
                (7,  "Dessert",   "dessert"),
                (24, "Fortified", "fortified"),
            ])

        @task
        def load_countries(records: list[dict]) -> None:
            """Upsert countries using country_name / country_seo_name / country_code from the API."""
            seen: dict[str, dict] = {}
            for r in records:
                code = r.get("country_code")
                name = r.get("country_name")
                seo  = r.get("country_seo_name") or (to_seo_name(name) if name else None)
                if code and name and seo:
                    seen[code] = {"name": name, "seo_name": seo, "code": code}

            upsert_many("""
                INSERT INTO country (name, seo_name, country_code)
                VALUES (%s, %s, %s)
                ON CONFLICT (country_code) DO UPDATE
                  SET name     = EXCLUDED.name,
                      seo_name = EXCLUDED.seo_name
            """, [(c["name"], c["seo_name"], c["code"]) for c in seen.values()])

        @task
        def load_regions(records: list[dict]) -> None:
            """Upsert regions using region_name / region_seo_name from the API."""
            seen: dict[str, dict] = {}
            for r in records:
                name = r.get("region_name")
                seo  = r.get("region_seo_name") or (to_seo_name(name) if name else None)
                code = r.get("country_code")
                if name and seo and code:
                    seen[seo] = {"name": name, "seo_name": seo, "country_code": code}

            upsert_many("""
                INSERT INTO region (name, seo_name, country_id)
                VALUES (%s, %s, (SELECT id FROM country WHERE country_code = %s))
                ON CONFLICT (seo_name) DO UPDATE
                  SET name       = EXCLUDED.name,
                      country_id = EXCLUDED.country_id
            """, [(r["name"], r["seo_name"], r["country_code"]) for r in seen.values()])

        @task
        def load_styles(records: list[dict]) -> None:
            """Upsert wine styles using style_name / style_seo_name from the API."""
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

            upsert_many("""
                INSERT INTO style
                    (name, seo_name, description,
                     body_description, acidity_description, wine_type_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (seo_name) DO UPDATE
                  SET name                = EXCLUDED.name,
                      description         = EXCLUDED.description,
                      body_description    = EXCLUDED.body_description,
                      acidity_description = EXCLUDED.acidity_description,
                      wine_type_id        = EXCLUDED.wine_type_id
            """, [
                (s["name"], s["seo_name"], s["description"],
                 s["body_description"], s["acidity_description"], s["wine_type_id"])
                for s in seen.values()
            ])

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
            """Upsert grapes from style_grapes_composition (display names; seo_name generated)."""
            seen: dict[str, str] = {}
            for r in records:
                for gname in r.get("style_grapes_composition") or []:
                    if gname:
                        seen[to_seo_name(gname)] = gname

            upsert_many("""
                INSERT INTO grape (name, seo_name)
                VALUES (%s, %s)
                ON CONFLICT (seo_name) DO UPDATE SET name = EXCLUDED.name
            """, [(name, seo) for seo, name in seen.items()])

        @task
        def load_style_grapes(records: list[dict]) -> None:
            """Upsert style → grape associations (ordered)."""
            rows: list[tuple] = []
            for r in records:
                sseo = r.get("style_seo_name")
                if not sseo:
                    continue
                for sort_order, gname in enumerate(r.get("style_grapes_composition") or []):
                    if gname:
                        rows.append((sseo, to_seo_name(gname), sort_order))

            upsert_many("""
                INSERT INTO style_grape (style_id, grape_id, sort_order)
                VALUES (
                    (SELECT id FROM style WHERE seo_name = %s),
                    (SELECT id FROM grape WHERE seo_name = %s),
                    %s
                )
                ON CONFLICT (style_id, grape_id) DO UPDATE
                  SET sort_order = EXCLUDED.sort_order
            """, rows)

        gr = load_grapes(records)
        gr >> load_style_grapes(records)

    # ── 3. Winery ─────────────────────────────────────────────────────────────

    @task
    def load_wineries(records: list[dict]) -> None:
        """Upsert wineries using winery_name (display) / winery_seo_name from the API."""
        seen: dict[str, dict] = {}
        for r in records:
            name = r.get("winery_name")
            seo  = r.get("winery_seo_name")
            if not name or not seo:
                continue
            seen[seo] = {
                "name":         name,
                "seo_name":     seo,
                "region_seo":   r.get("region_seo_name"),
                "country_code": r.get("country_code"),
            }

        upsert_many("""
            INSERT INTO winery (name, seo_name, region_id, country_id)
            VALUES (
                %s, %s,
                (SELECT id FROM region  WHERE seo_name    = %s),
                (SELECT id FROM country WHERE country_code = %s)
            )
            ON CONFLICT (seo_name) DO UPDATE
              SET name       = EXCLUDED.name,
                  region_id  = EXCLUDED.region_id,
                  country_id = EXCLUDED.country_id
        """, [
            (w["name"], w["seo_name"], w["region_seo"], w["country_code"])
            for w in seen.values()
        ])

    # ── 4. Wine ───────────────────────────────────────────────────────────────

    @task
    def load_wines(records: list[dict]) -> None:
        """Upsert wines using wine_name (display) / wine_seo_name from the API."""
        seen: dict[str, dict] = {}
        for r in records:
            name = r.get("wine_name")
            seo  = r.get("wine_seo_name")
            if not name or not seo:
                continue
            seen[seo] = {
                "name":         name,
                "seo_name":     seo,
                "type_id":      r.get("wine_type_id"),
                "is_natural":   bool(r.get("is_natural")),
                "winery_seo":   r.get("winery_seo_name"),
                "region_seo":   r.get("region_seo_name"),
                "country_code": r.get("country_code"),
                "style_seo":    r.get("style_seo_name"),
            }

        upsert_many("""
            INSERT INTO wine
                (name, seo_name, wine_type_id, is_natural,
                 winery_id, region_id, country_id, style_id)
            VALUES (
                %s, %s, %s, %s,
                (SELECT id FROM winery  WHERE seo_name    = %s),
                (SELECT id FROM region  WHERE seo_name    = %s),
                (SELECT id FROM country WHERE country_code = %s),
                (SELECT id FROM style   WHERE seo_name    = %s)
            )
            ON CONFLICT (seo_name) DO UPDATE
              SET name         = EXCLUDED.name,
                  wine_type_id = EXCLUDED.wine_type_id,
                  is_natural   = EXCLUDED.is_natural,
                  winery_id    = EXCLUDED.winery_id,
                  region_id    = EXCLUDED.region_id,
                  country_id   = EXCLUDED.country_id,
                  style_id     = EXCLUDED.style_id
        """, [
            (w["name"], w["seo_name"], w["type_id"], w["is_natural"],
             w["winery_seo"], w["region_seo"], w["country_code"], w["style_seo"])
            for w in seen.values()
        ])

    # ── 5. Vintages ───────────────────────────────────────────────────────────

    @task
    def load_vintages(records: list[dict]) -> None:
        """Upsert vintages using vintage_name / vintage_seo_name from the API."""
        seen: dict[str, dict] = {}
        for r in records:
            name     = r.get("vintage_name")
            seo      = r.get("vintage_seo_name")
            wine_seo = r.get("wine_seo_name")
            year     = r.get("vintage_year")
            if not name or not seo or not wine_seo or not year:
                continue
            seen[seo] = {
                "name":           name,
                "seo_name":       seo,
                "wine_seo":       wine_seo,
                "year":           int(year),
                "price_amount":   r.get("price_amount"),
                "price_currency": r.get("price_currency"),
                "avg_rating":     r.get("rating_average"),
                "num_reviews":    int(r.get("ratings_count") or 0),
            }

        upsert_many("""
            INSERT INTO vintage
                (name, seo_name, wine_id, year,
                 price_amount, price_currency, average_rating, num_reviews)
            VALUES (
                %s, %s,
                (SELECT id FROM wine WHERE seo_name = %s),
                %s, %s, %s, %s, %s
            )
            ON CONFLICT (seo_name) DO UPDATE
              SET name           = EXCLUDED.name,
                  year           = EXCLUDED.year,
                  price_amount   = EXCLUDED.price_amount,
                  price_currency = EXCLUDED.price_currency,
                  average_rating = EXCLUDED.average_rating,
                  num_reviews    = EXCLUDED.num_reviews
        """, [
            (v["name"], v["seo_name"], v["wine_seo"], v["year"],
             v["price_amount"], v["price_currency"], v["avg_rating"], v["num_reviews"])
            for v in seen.values()
        ])

    # ── 6. Taste profile ──────────────────────────────────────────────────────

    @task_group(group_id="taste_profile")
    def taste_profile(records: list[dict]):

        @task
        def load_taste_structures(records: list[dict]) -> None:
            """Upsert per-wine taste structure; taste_* fields map 1-to-1."""
            seen: dict[str, dict] = {}
            for r in records:
                seo = r.get("wine_seo_name")
                if not seo:
                    continue
                seen[seo] = {
                    "seo_name":  seo,
                    "acidity":   r.get("taste_acidity"),
                    "fizziness": r.get("taste_fizziness"),
                    "intensity": r.get("taste_intensity"),
                    "sweetness": r.get("taste_sweetness"),
                    "tannin":    r.get("taste_tannin"),
                }

            upsert_many("""
                INSERT INTO wine_taste_structure
                    (wine_id, acidity, fizziness, intensity, sweetness, tannin)
                VALUES (
                    (SELECT id FROM wine WHERE seo_name = %s),
                    %s, %s, %s, %s, %s
                )
                ON CONFLICT (wine_id) DO UPDATE
                  SET acidity   = EXCLUDED.acidity,
                      fizziness = EXCLUDED.fizziness,
                      intensity = EXCLUDED.intensity,
                      sweetness = EXCLUDED.sweetness,
                      tannin    = EXCLUDED.tannin
            """, [
                (w["seo_name"], w["acidity"], w["fizziness"],
                 w["intensity"], w["sweetness"], w["tannin"])
                for w in seen.values()
            ])

        @task
        def load_flavor_taxonomy(records: list[dict]) -> None:
            """Upsert flavor_group, flavor_keyword, and flavor_group_keyword.

            Flavor group seo_name generated from group string (e.g. 'red_fruit' → 'red-fruit').
            Flavor keyword seo_name generated from keyword name.
            """
            hook = get_hook()
            groups: dict[str, str]   = {}
            keywords: dict[str, str] = {}
            gk_rows: list[tuple]     = []

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

            hook.run("""
                INSERT INTO flavor_group (name, seo_name) VALUES (%s, %s)
                ON CONFLICT (seo_name) DO UPDATE SET name = EXCLUDED.name
            """, parameters=[(name, seo) for seo, name in groups.items()])

            hook.run("""
                INSERT INTO flavor_keyword (name, seo_name) VALUES (%s, %s)
                ON CONFLICT (seo_name) DO UPDATE SET name = EXCLUDED.name
            """, parameters=[(name, seo) for seo, name in keywords.items()])

            if gk_rows:
                hook.run("""
                    INSERT INTO flavor_group_keyword
                        (flavor_group_id, flavor_keyword_id, keyword_role)
                    VALUES (
                        (SELECT id FROM flavor_group   WHERE seo_name = %s),
                        (SELECT id FROM flavor_keyword WHERE seo_name = %s),
                        %s::keyword_role
                    )
                    ON CONFLICT (flavor_group_id, flavor_keyword_id) DO UPDATE
                      SET keyword_role = EXCLUDED.keyword_role
                """, parameters=gk_rows)

        @task
        def load_wine_flavors(records: list[dict]) -> None:
            """Aggregate and upsert wine_flavor rows (wine × flavor_keyword count)."""
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

            upsert_many("""
                INSERT INTO wine_flavor (wine_id, flavor_keyword_id, count)
                VALUES (
                    (SELECT id FROM wine          WHERE seo_name = %s),
                    (SELECT id FROM flavor_keyword WHERE seo_name = %s),
                    %s
                )
                ON CONFLICT (wine_id, flavor_keyword_id) DO UPDATE
                  SET count = EXCLUDED.count
            """, [
                (wseo, kseo, cnt)
                for wseo, kws in totals.items()
                for kseo, cnt in kws.items()
            ])

        ft = load_flavor_taxonomy(records)
        ts = load_taste_structures(records)
        wf = load_wine_flavors(records)
        ft >> wf  # wine_flavor depends on flavor_keyword rows existing

    # ── 7. Wine-level rating aggregates from vintage stats ────────────────────

    @task
    def update_wine_rating_aggregates() -> None:
        """Roll up vintage-level rating stats to the wine row."""
        get_hook().run("""
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
        """)
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
        """Return IDs of wines whose reviews are stale (NULL or older than 7 days)."""
        rows = get_hook().get_records("""
            SELECT id FROM wine
            WHERE last_reviewed_at IS NULL
               OR last_reviewed_at < NOW() - INTERVAL '7 days'
            ORDER BY last_reviewed_at ASC NULLS FIRST
        """)
        ids = [row[0] for row in rows]
        log.info("Found %d wines to refresh reviews for", len(ids))
        return ids

    @task
    def fetch_and_store_reviews(wine_ids: list[int]) -> dict:
        """Page through the Vivino reviews API and upsert users and reviews.

        API → DB mapping:
          review.user.id       → "user".id       (integer PK)
          review.user.seo_name → "user".username
          review.user.alias    → "user".display_name
          review.rating        → wine_review.rating
          review.note          → wine_review.review
        """
        hook    = get_hook()
        summary = {}

        user_upsert_sql = """
            INSERT INTO "user" (id, username, display_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE
              SET username     = COALESCE(EXCLUDED.username,     "user".username),
                  display_name = COALESCE(EXCLUDED.display_name, "user".display_name)
        """
        review_insert_sql = """
            INSERT INTO wine_review (wine_id, user_id, rating, review)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """

        for wine_id in wine_ids:
            wine_reviews = []
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
                    user_id = user.get("id")        # integer – required for FK
                    rating  = item.get("rating")
                    note    = item.get("note")

                    if user_id:
                        hook.run(user_upsert_sql, parameters=(
                            user_id,
                            user.get("seo_name") or str(user_id),
                            user.get("alias") or user.get("seo_name"),
                        ))

                    if note:
                        hook.run(review_insert_sql,
                                 parameters=(wine_id, user_id, rating, note))

                    wine_reviews.append({"user_id": user_id, "rating": rating})

                page += 1
                time.sleep(API_SLEEP_SECONDS)

            summary[wine_id] = wine_reviews
            log.info("Wine %s: stored %d reviews", wine_id, len(wine_reviews))

        return summary

    @task
    def update_rating_aggregates(summary: dict) -> None:
        """Recompute wine rating stats from wine_review and propagate last_reviewed_at
        to vintages."""
        hook     = get_hook()
        wine_ids = list(summary.keys())
        if not wine_ids:
            return

        ph = ", ".join(["%s"] * len(wine_ids))

        hook.run(f"""
            UPDATE wine w
            SET wine_rating_count   = sub.total_reviews,
                wine_rating_average = sub.avg_rating,
                last_reviewed_at    = sub.latest
            FROM (
                SELECT
                    wr.wine_id,
                    COUNT(*)                                                    AS total_reviews,
                    AVG(wr.rating) FILTER (WHERE wr.rating IS NOT NULL)         AS avg_rating,
                    MAX(wr.created_at)                                          AS latest
                FROM wine_review wr
                WHERE wr.wine_id IN ({ph})
                GROUP BY wr.wine_id
            ) sub
            WHERE w.id = sub.wine_id
        """, parameters=wine_ids)

        hook.run(f"""
            UPDATE vintage v
            SET last_reviewed_at = w.last_reviewed_at
            FROM wine w
            WHERE v.wine_id = w.id AND w.id IN ({ph})
        """, parameters=wine_ids)

        log.info("Updated rating aggregates for %d wines", len(wine_ids))

    @task
    def update_user_review_counts() -> None:
        """Recompute review_count for all users from wine_review."""
        get_hook().run("""
            UPDATE "user" u
            SET review_count = sub.cnt
            FROM (
                SELECT user_id, COUNT(*) AS cnt
                FROM wine_review
                WHERE user_id IS NOT NULL
                GROUP BY user_id
            ) sub
            WHERE u.id = sub.user_id
        """)

    ids     = get_wine_ids()
    summary = fetch_and_store_reviews(ids)
    agg     = update_rating_aggregates(summary)
    ucounts = update_user_review_counts()

    summary >> [agg, ucounts]


wine_reviews_dag = wine_reviews_ingestion()
