from .base import Base
from .session import engine

# Import models so SQLAlchemy registers them on Base.metadata before create_all.
from . import models  # noqa: F401


def main():
    Base.metadata.create_all(bind=engine)
    print("Database tables created.")


if __name__ == "__main__":
    main()
