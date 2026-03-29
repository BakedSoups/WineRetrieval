from datetime import datetime, timezone

import pandas as pd

from .models import Wine, WineFlavorTerm, WineReview, WineStructure, WineVector

VECTOR_VERSION = "taste_v1"
FLAVOR_VOCAB_VERSION = "vivino_flavors_v1"


def _is_missing(value):
    return pd.isna(value) if value is not None else True


def _to_optional_int(value):
    if _is_missing(value):
        return None
    return int(value)


def _to_optional_float(value):
    if _is_missing(value):
        return None
    return float(value)


def _to_optional_str(value):
    if _is_missing(value):
        return None
    return str(value)


def _build_vivino_url(wine_id, wine_name):
    if wine_id is None or _is_missing(wine_name):
        return None
    return f"https://www.vivino.com/US/en/{wine_name}/w/{int(wine_id)}"


def _unique_wine_rows(wines):
    unique_rows = []
    seen_wine_ids = set()

    for _, wine_row in wines.iterrows():
        wine_id = _to_optional_int(wine_row.get("wine_id"))
        if wine_id is None or wine_id in seen_wine_ids:
            continue
        seen_wine_ids.add(wine_id)
        unique_rows.append(wine_row)

    return unique_rows


def upsert_wines(session, wines):
    for wine_row in _unique_wine_rows(wines):
        wine_id = _to_optional_int(wine_row.get("wine_id"))
        if wine_id is None:
            continue

        wine = Wine(
            wine_id=wine_id,
            wine_name=_to_optional_str(wine_row.get("wine_name")),
            winery_name=_to_optional_str(wine_row.get("winery_name")),
            vintage_year=_to_optional_str(wine_row.get("vintage_year")),
            wine_type_id=_to_optional_int(wine_row.get("wine_type_id")),
            country_name=_to_optional_str(wine_row.get("country_name")),
            region_name=_to_optional_str(wine_row.get("region_name")),
            style_id=_to_optional_int(wine_row.get("style_id")),
            style_name=_to_optional_str(wine_row.get("style_name")),
            is_natural=wine_row.get("is_natural") if not _is_missing(wine_row.get("is_natural")) else None,
            rating_average=_to_optional_float(wine_row.get("rating_average")),
            ratings_count=_to_optional_int(wine_row.get("ratings_count")),
            price_amount=_to_optional_float(wine_row.get("price_amount")),
            price_currency=_to_optional_str(wine_row.get("price_currency")),
            vivino_url=_build_vivino_url(wine_id, wine_row.get("wine_name")),
        )
        session.merge(wine)

    session.flush()


def replace_wine_structures(session, wines):
    for wine_row in _unique_wine_rows(wines):
        wine_id = _to_optional_int(wine_row.get("wine_id"))
        if wine_id is None:
            continue

        structure = WineStructure(
            wine_id=wine_id,
            acidity=_to_optional_float(wine_row.get("taste_acidity")),
            fizziness=_to_optional_float(wine_row.get("taste_fizziness")),
            intensity=_to_optional_float(wine_row.get("taste_intensity")),
            sweetness=_to_optional_float(wine_row.get("taste_sweetness")),
            tannin=_to_optional_float(wine_row.get("taste_tannin")),
        )
        session.merge(structure)

    session.flush()


def replace_wine_flavor_terms(session, wines):
    wine_ids = [
        _to_optional_int(wine_row.get("wine_id"))
        for wine_row in _unique_wine_rows(wines)
        if _to_optional_int(wine_row.get("wine_id")) is not None
    ]
    if wine_ids:
        session.query(WineFlavorTerm).filter(WineFlavorTerm.wine_id.in_(set(wine_ids))).delete(synchronize_session=False)

    for wine_row in _unique_wine_rows(wines):
        wine_id = _to_optional_int(wine_row.get("wine_id"))
        if wine_id is None:
            continue

        for flavor_group in wine_row.get("wine_flavors") or []:
            flavor_group_name = _to_optional_str(flavor_group.get("group"))

            for keyword in flavor_group.get("primary_keywords") or []:
                flavor_name = _to_optional_str(keyword.get("name"))
                if not flavor_name:
                    continue
                session.add(
                    WineFlavorTerm(
                        wine_id=wine_id,
                        flavor_group=flavor_group_name,
                        flavor_name=flavor_name,
                        flavor_role="primary",
                        count=_to_optional_float(keyword.get("count")),
                    )
                )

            for keyword in flavor_group.get("secondary_keywords") or []:
                flavor_name = _to_optional_str(keyword.get("name"))
                if not flavor_name:
                    continue
                session.add(
                    WineFlavorTerm(
                        wine_id=wine_id,
                        flavor_group=flavor_group_name,
                        flavor_name=flavor_name,
                        flavor_role="secondary",
                        count=_to_optional_float(keyword.get("count")),
                    )
                )

    session.flush()


def upsert_wine_reviews(session, wines):
    for wine_row in _unique_wine_rows(wines):
        wine_id = _to_optional_int(wine_row.get("wine_id"))
        if wine_id is None:
            continue

        for review in wine_row.get("wine_reviews") or []:
            review_id = _to_optional_int(review.get("review_id"))
            if review_id is None:
                continue

            session.merge(
                WineReview(
                    review_id=review_id,
                    wine_id=wine_id,
                    language=_to_optional_str(review.get("language")),
                    rating=_to_optional_float(review.get("rating")),
                    note=_to_optional_str(review.get("note")),
                    author=_to_optional_str(review.get("author")),
                    created_at=_to_optional_str(review.get("created_at")),
                )
            )

    session.flush()


def upsert_wine_vectors(session, wines, wine_matrix):
    indexed_at = datetime.now(timezone.utc).isoformat()

    for row_index, wine_row in enumerate(_unique_wine_rows(wines)):
        wine_id = _to_optional_int(wine_row.get("wine_id"))
        if wine_id is None:
            continue

        chroma_document_id = f"{wine_id}:{row_index}"
        session.merge(
            WineVector(
                wine_id=wine_id,
                vector_version=VECTOR_VERSION,
                flavor_vocab_version=FLAVOR_VOCAB_VERSION,
                chroma_document_id=chroma_document_id,
                indexed_at=indexed_at,
            )
        )

    session.flush()


def build_full_local_store(session, wines, wine_matrix):
    upsert_wines(session, wines)
    replace_wine_structures(session, wines)
    replace_wine_flavor_terms(session, wines)
    upsert_wine_reviews(session, wines)
    upsert_wine_vectors(session, wines, wine_matrix)
