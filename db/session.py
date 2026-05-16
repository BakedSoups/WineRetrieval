from __future__ import annotations

from sqlalchemy import Engine, create_engine


def get_engine(url: str) -> Engine:
    """Create a SQLAlchemy engine from an explicit connection URL."""
    return create_engine(url, pool_pre_ping=True)


def get_airflow_engine(conn_id: str = "wine_db") -> Engine:
    """Create a SQLAlchemy engine via an Airflow PostgresHook connection."""
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    return PostgresHook(postgres_conn_id=conn_id).get_sqlalchemy_engine()
