"""SQLAlchemy ORM models mirroring the WineAI PostgreSQL schema (02_wine_schema.sql).

ENUM types (keyword_role, shop_type, transaction_type) are declared with
create_type=False because the schema SQL script already creates them.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
from sqlalchemy.orm import DeclarativeBase

# ── PostgreSQL native ENUM references ────────────────────────────────────────
# create_type=False: the types already exist (created by 02_wine_schema.sql).
_keyword_role    = Enum("primary", "secondary",      name="keyword_role",    create_type=False)
_shop_type       = Enum("restaurant", "grocery",     name="shop_type",       create_type=False)
_transaction_type = Enum("sale", "reception",        name="transaction_type", create_type=False)


class Base(DeclarativeBase):
    pass


# ── Lookup tables ─────────────────────────────────────────────────────────────

class Country(Base):
    __tablename__ = "country"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    name           = Column(String(100), nullable=False)
    seo_name       = Column(String(100), unique=True, nullable=False)
    country_code   = Column(String(2),   unique=True, nullable=False)
    regions_count  = Column(Integer, nullable=False, default=0)
    users_count    = Column(Integer, nullable=False, default=0)
    wines_count    = Column(Integer, nullable=False, default=0)
    wineries_count = Column(Integer, nullable=False, default=0)


class Region(Base):
    __tablename__ = "region"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(150), nullable=False)
    seo_name   = Column(String(150), unique=True, nullable=False)
    country_id = Column(Integer, ForeignKey("country.id", ondelete="RESTRICT"), nullable=False)


class WineType(Base):
    __tablename__ = "wine_type"

    id       = Column(Integer, primary_key=True)
    name     = Column(String(50), unique=True, nullable=False)
    seo_name = Column(String(50), unique=True, nullable=False)


class Style(Base):
    __tablename__ = "style"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    name                = Column(String(100), nullable=False)
    seo_name            = Column(String(100), unique=True, nullable=False)
    description         = Column(Text)
    body_description    = Column(String(100))
    acidity_description = Column(String(100))
    wine_type_id        = Column(Integer, ForeignKey("wine_type.id", ondelete="SET NULL"))


# ── Winery ────────────────────────────────────────────────────────────────────

class Winery(Base):
    __tablename__ = "winery"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(200), nullable=False)
    seo_name   = Column(String(200), unique=True, nullable=False)
    region_id  = Column(Integer, ForeignKey("region.id",  ondelete="SET NULL"))
    country_id = Column(Integer, ForeignKey("country.id", ondelete="SET NULL"))


# ── Wine & Vintage ────────────────────────────────────────────────────────────

class Wine(Base):
    __tablename__ = "wine"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    name                = Column(String(200), nullable=False)
    seo_name            = Column(String(200), unique=True, nullable=False)
    wine_type_id        = Column(Integer, ForeignKey("wine_type.id", ondelete="RESTRICT"), nullable=False)
    is_natural          = Column(Boolean, nullable=False, default=False)
    winery_id           = Column(Integer, ForeignKey("winery.id",  ondelete="RESTRICT"), nullable=False)
    region_id           = Column(Integer, ForeignKey("region.id",  ondelete="SET NULL"))
    country_id          = Column(Integer, ForeignKey("country.id", ondelete="SET NULL"))
    style_id            = Column(Integer, ForeignKey("style.id",   ondelete="SET NULL"))
    wine_rating_average = Column(Numeric(3, 2))
    wine_rating_count   = Column(Integer, nullable=False, default=0)
    last_reviewed_at    = Column(TIMESTAMPTZ)


class Vintage(Base):
    __tablename__ = "vintage"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    name             = Column(String(200), nullable=False)
    seo_name         = Column(String(200), unique=True, nullable=False)
    wine_id          = Column(Integer, ForeignKey("wine.id", ondelete="RESTRICT"), nullable=False)
    year             = Column(SmallInteger, nullable=False)
    label_image_url  = Column(Text)
    price_amount     = Column(Numeric(10, 2))
    price_currency   = Column(String(3))
    average_rating   = Column(Numeric(3, 2))
    num_reviews      = Column(Integer, nullable=False, default=0)
    last_reviewed_at = Column(TIMESTAMPTZ)


# ── Users & Reviews ───────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "user"

    # id is supplied by the Vivino API (integer), not auto-generated
    id           = Column(Integer, primary_key=True)
    username     = Column(String(100), unique=True, nullable=False)
    email        = Column(String(200))
    display_name = Column(String(150))
    country_id   = Column(Integer, ForeignKey("country.id", ondelete="SET NULL"))
    review_count = Column(Integer, nullable=False, default=0)
    created_at   = Column(TIMESTAMPTZ, nullable=False, server_default="NOW()")


class WineReview(Base):
    __tablename__ = "wine_review"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    wine_id    = Column(Integer, ForeignKey("wine.id",  ondelete="CASCADE"),  nullable=False)
    user_id    = Column(Integer, ForeignKey("user.id",  ondelete="SET NULL"))
    rating     = Column(Numeric(3, 2))
    review     = Column(Text, nullable=False)
    created_at = Column(TIMESTAMPTZ, nullable=False, server_default="NOW()")


# ── Taste profile ─────────────────────────────────────────────────────────────

class WineTasteStructure(Base):
    __tablename__ = "wine_taste_structure"

    wine_id   = Column(Integer, ForeignKey("wine.id", ondelete="CASCADE"), primary_key=True)
    acidity   = Column(Numeric(3, 1))
    fizziness = Column(Numeric(3, 1))
    intensity = Column(Numeric(3, 1))
    sweetness = Column(Numeric(3, 1))
    tannin    = Column(Numeric(3, 1))


class FlavorGroup(Base):
    __tablename__ = "flavor_group"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    name     = Column(String(100), unique=True, nullable=False)
    seo_name = Column(String(100), unique=True, nullable=False)


class FlavorKeyword(Base):
    __tablename__ = "flavor_keyword"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    name     = Column(String(100), unique=True, nullable=False)
    seo_name = Column(String(100), unique=True, nullable=False)


class FlavorGroupKeyword(Base):
    __tablename__ = "flavor_group_keyword"

    flavor_group_id   = Column(Integer, ForeignKey("flavor_group.id",   ondelete="CASCADE"), primary_key=True)
    flavor_keyword_id = Column(Integer, ForeignKey("flavor_keyword.id", ondelete="CASCADE"), primary_key=True)
    keyword_role      = Column(_keyword_role, nullable=False, default="primary")


class WineFlavor(Base):
    __tablename__ = "wine_flavor"

    wine_id           = Column(Integer, ForeignKey("wine.id",          ondelete="CASCADE"),  primary_key=True)
    flavor_keyword_id = Column(Integer, ForeignKey("flavor_keyword.id", ondelete="RESTRICT"), primary_key=True)
    count             = Column(Integer, nullable=False, default=1)


# ── Grapes ────────────────────────────────────────────────────────────────────

class Grape(Base):
    __tablename__ = "grape"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(150), nullable=False)
    seo_name    = Column(String(150), unique=True, nullable=False)
    wines_count = Column(Integer, nullable=False, default=0)


class CountryGrape(Base):
    __tablename__ = "country_grape"

    country_id = Column(Integer, ForeignKey("country.id", ondelete="CASCADE"), primary_key=True)
    grape_id   = Column(Integer, ForeignKey("grape.id",   ondelete="CASCADE"), primary_key=True)
    sort_order = Column(SmallInteger, nullable=False, default=0)


class StyleGrape(Base):
    __tablename__ = "style_grape"

    style_id   = Column(Integer, ForeignKey("style.id", ondelete="CASCADE"), primary_key=True)
    grape_id   = Column(Integer, ForeignKey("grape.id", ondelete="CASCADE"), primary_key=True)
    sort_order = Column(SmallInteger, nullable=False, default=0)


class VintageGrape(Base):
    __tablename__ = "vintage_grape"

    vintage_id = Column(Integer, ForeignKey("vintage.id", ondelete="CASCADE"), primary_key=True)
    grape_id   = Column(Integer, ForeignKey("grape.id",   ondelete="CASCADE"), primary_key=True)
    sort_order = Column(SmallInteger, nullable=False, default=0)


# ── Inventory ─────────────────────────────────────────────────────────────────

class Shop(Base):
    __tablename__ = "shop"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    name         = Column(String(200), nullable=False)
    seo_name     = Column(String(200), unique=True, nullable=False)
    shop_type    = Column(_shop_type, nullable=False)
    address_line = Column(String(300))
    city         = Column(String(100))
    country_id   = Column(Integer, ForeignKey("country.id", ondelete="SET NULL"))
    phone        = Column(String(30))
    email        = Column(String(200))
    website_url  = Column(Text)
    created_at   = Column(TIMESTAMPTZ, nullable=False, server_default="NOW()")


class ShopInventory(Base):
    __tablename__ = "shop_inventory"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    shop_id        = Column(Integer, ForeignKey("shop.id",    ondelete="CASCADE"),  nullable=False)
    wine_id        = Column(Integer, ForeignKey("wine.id",    ondelete="RESTRICT"), nullable=False)
    vintage_id     = Column(Integer, ForeignKey("vintage.id", ondelete="SET NULL"))
    quantity       = Column(Integer, nullable=False, default=0)
    price_amount   = Column(Numeric(10, 2))
    price_currency = Column(String(3))
    in_stock       = Column(Boolean, nullable=False, default=True)
    updated_at     = Column(TIMESTAMPTZ, nullable=False, server_default="NOW()")


class ShopTransaction(Base):
    __tablename__ = "shop_transaction"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    shop_id          = Column(Integer, ForeignKey("shop.id",    ondelete="RESTRICT"), nullable=False)
    wine_id          = Column(Integer, ForeignKey("wine.id",    ondelete="RESTRICT"), nullable=False)
    vintage_id       = Column(Integer, ForeignKey("vintage.id", ondelete="SET NULL"))
    transaction_type = Column(_transaction_type, nullable=False)
    quantity         = Column(Integer, nullable=False)
    unit_price       = Column(Numeric(10, 2))
    currency         = Column(String(3))
    transacted_at    = Column(TIMESTAMPTZ, nullable=False, server_default="NOW()")
    notes            = Column(Text)
