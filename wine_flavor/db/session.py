import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DEFAULT_DATABASE_URL = "sqlite:///data/wine_flavor.db"


def get_database_url():
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


database_url = get_database_url()
if database_url.startswith("sqlite:///"):
    sqlite_path = database_url.removeprefix("sqlite:///")
    Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    database_url,
    connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
