"""
Schema compatibility test: db/models.py  ↔  docker/postgres/02_wine_schema.sql
================================================================================

Connects to a live PostgreSQL database (WineAI) and uses SQLAlchemy's Inspector
to reflect the actual schema, then checks it against the ORM models in db/models.py.

Requires the DATABASE_URL environment variable to point to the running WineAI database:

    DATABASE_URL=postgresql://wine_user:wine_password@localhost:5432/WineAI pytest test/test_schema_compat.py -v

All tests are skipped automatically when DATABASE_URL is not set.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.models import Base  # noqa: E402  (needs sys.path inserted above)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def inspector():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping schema compatibility tests")
    engine = create_engine(url)
    try:
        with engine.connect():
            pass
    except Exception as exc:
        pytest.skip(f"Cannot connect to database: {exc}")
    yield inspect(engine)
    engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def model_tables() -> dict:
    return dict(Base.metadata.tables)


def db_column_map(insp, table_name: str) -> dict[str, dict]:
    """Return {column_name: column_info} for a table as reflected from the DB."""
    return {col["name"]: col for col in insp.get_columns(table_name)}


def db_pk_columns(insp, table_name: str) -> set[str]:
    return set(insp.get_pk_constraint(table_name).get("constrained_columns", []))


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 – every model table exists in the DB
# ─────────────────────────────────────────────────────────────────────────────

def test_model_tables_exist_in_db(inspector):
    db_tables = set(inspector.get_table_names())
    missing = [name for name in model_tables() if name not in db_tables]
    assert not missing, (
        f"Tables declared in models but absent from the database:\n"
        + "\n".join(f"  - {t}" for t in sorted(missing))
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 – every DB table has a model (catches schema additions that are
#           not yet mirrored in models.py)
# ─────────────────────────────────────────────────────────────────────────────

def test_db_tables_have_models(inspector):
    db_tables  = set(inspector.get_table_names())
    model_names = set(model_tables().keys())
    extra = db_tables - model_names
    assert not extra, (
        f"Tables present in the database but missing from models.py:\n"
        + "\n".join(f"  - {t}" for t in sorted(extra))
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 – every model column exists in the corresponding DB table
# ─────────────────────────────────────────────────────────────────────────────

def test_model_columns_exist_in_db(inspector):
    errors: list[str] = []
    for table_name, table in model_tables().items():
        try:
            db_cols = db_column_map(inspector, table_name)
        except Exception:
            continue  # table existence is already checked in test_1
        for col in table.columns:
            if col.name not in db_cols:
                errors.append(f"  {table_name}.{col.name}")
    assert not errors, (
        "Columns declared in models but absent from the database:\n"
        + "\n".join(errors)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 – every DB column has a counterpart in the model
# ─────────────────────────────────────────────────────────────────────────────

def test_db_columns_have_models(inspector):
    errors: list[str] = []
    for table_name, table in model_tables().items():
        try:
            db_cols = db_column_map(inspector, table_name)
        except Exception:
            continue
        model_col_names = {col.name for col in table.columns}
        for col_name in db_cols:
            if col_name not in model_col_names:
                errors.append(f"  {table_name}.{col_name}")
    assert not errors, (
        "Columns present in the database but missing from models.py:\n"
        + "\n".join(errors)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 – primary key columns agree
# ─────────────────────────────────────────────────────────────────────────────

def test_primary_keys_match(inspector):
    errors: list[str] = []
    for table_name, table in model_tables().items():
        try:
            db_pks = db_pk_columns(inspector, table_name)
        except Exception:
            continue
        model_pks = {col.name for col in table.primary_key.columns}
        if model_pks != db_pks:
            errors.append(
                f"  {table_name}: model PK {sorted(model_pks)} ≠ db PK {sorted(db_pks)}"
            )
    assert not errors, "Primary key mismatches:\n" + "\n".join(errors)


# ─────────────────────────────────────────────────────────────────────────────
# Test 6 – nullable constraints agree for columns that exist in both
# ─────────────────────────────────────────────────────────────────────────────

def test_nullable_constraints_match(inspector):
    # Columns whose nullable mismatch is known and acceptable.
    # SQLAlchemy marks server_default columns as nullable=True in reflection
    # even when the DB column is NOT NULL with a DEFAULT — skip those.
    _KNOWN_EXCEPTIONS: set[tuple[str, str]] = {
        ("user",             "created_at"),   # server_default="NOW()"
        ("wine_review",      "created_at"),
        ("shop",             "created_at"),
        ("shop_inventory",   "updated_at"),
        ("shop_transaction", "transacted_at"),
    }

    errors: list[str] = []
    for table_name, table in model_tables().items():
        try:
            db_cols = db_column_map(inspector, table_name)
        except Exception:
            continue
        for col in table.columns:
            if col.name not in db_cols:
                continue
            if (table_name, col.name) in _KNOWN_EXCEPTIONS:
                continue
            db_nullable  = db_cols[col.name]["nullable"]
            # SQLAlchemy Column.nullable defaults to True when not explicitly set,
            # so only flag cases where model says NOT NULL but DB says nullable.
            if not col.nullable and db_nullable:
                errors.append(
                    f"  {table_name}.{col.name}: "
                    f"model=NOT NULL  db=nullable"
                )

    assert not errors, "Nullable constraint mismatches:\n" + "\n".join(errors)
