from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Wine(Base):
    __tablename__ = "wines"

    wine_id: Mapped[int] = mapped_column(primary_key=True)
    wine_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    winery_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    vintage_year: Mapped[str | None] = mapped_column(String(32), nullable=True)
    wine_type_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    country_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    style_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_natural: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rating_average: Mapped[float | None] = mapped_column(Float, nullable=True)
    ratings_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    vivino_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    structure: Mapped["WineStructure | None"] = relationship(back_populates="wine", cascade="all, delete-orphan")
    flavor_terms: Mapped[list["WineFlavorTerm"]] = relationship(back_populates="wine", cascade="all, delete-orphan")
    reviews: Mapped[list["WineReview"]] = relationship(back_populates="wine", cascade="all, delete-orphan")
    vector: Mapped["WineVector | None"] = relationship(back_populates="wine", cascade="all, delete-orphan")


class WineStructure(Base):
    __tablename__ = "wine_structures"

    wine_id: Mapped[int] = mapped_column(ForeignKey("wines.wine_id"), primary_key=True)
    acidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    fizziness: Mapped[float | None] = mapped_column(Float, nullable=True)
    intensity: Mapped[float | None] = mapped_column(Float, nullable=True)
    sweetness: Mapped[float | None] = mapped_column(Float, nullable=True)
    tannin: Mapped[float | None] = mapped_column(Float, nullable=True)

    wine: Mapped["Wine"] = relationship(back_populates="structure")


class WineFlavorTerm(Base):
    __tablename__ = "wine_flavor_terms"
    __table_args__ = (
        UniqueConstraint("wine_id", "flavor_group", "flavor_name", "flavor_role", name="uq_wine_flavor_term"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    wine_id: Mapped[int] = mapped_column(ForeignKey("wines.wine_id"), nullable=False, index=True)
    flavor_group: Mapped[str | None] = mapped_column(Text, nullable=True)
    flavor_name: Mapped[str] = mapped_column(Text, nullable=False)
    flavor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    count: Mapped[float | None] = mapped_column(Float, nullable=True)

    wine: Mapped["Wine"] = relationship(back_populates="flavor_terms")


class WineReview(Base):
    __tablename__ = "wine_reviews"

    review_id: Mapped[int] = mapped_column(primary_key=True)
    wine_id: Mapped[int] = mapped_column(ForeignKey("wines.wine_id"), nullable=False, index=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str | None] = mapped_column(String(64), nullable=True)

    wine: Mapped["Wine"] = relationship(back_populates="reviews")


class WineVector(Base):
    __tablename__ = "wine_vectors"

    wine_id: Mapped[int] = mapped_column(ForeignKey("wines.wine_id"), primary_key=True)
    vector_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    flavor_vocab_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chroma_document_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    indexed_at: Mapped[str | None] = mapped_column(String(64), nullable=True)

    wine: Mapped["Wine"] = relationship(back_populates="vector")
