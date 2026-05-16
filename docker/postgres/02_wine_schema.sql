-- =============================================================================
-- Wine Recommender System – Database Schema
-- Applied to the WineAI database on first container start.
-- =============================================================================

-- =============================================================================
-- ENUM DEFINITIONS
-- =============================================================================

CREATE TYPE keyword_role AS ENUM (
  'primary',
  'secondary'
);

CREATE TYPE shop_type AS ENUM (
  'restaurant',
  'grocery'
);

CREATE TYPE transaction_type AS ENUM (
  'sale',       -- wine sold to a customer
  'reception'   -- wine received into stock from a supplier
);

-- =============================================================================
-- LOOKUP TABLES
-- =============================================================================

CREATE TABLE country (
  id             SERIAL PRIMARY KEY,
  name           VARCHAR(100) NOT NULL,
  seo_name       VARCHAR(100) UNIQUE NOT NULL,
  country_code   CHAR(2)      UNIQUE NOT NULL,
  regions_count  INT          NOT NULL CHECK (regions_count  >= 0) DEFAULT 0,
  users_count    INT          NOT NULL CHECK (users_count    >= 0) DEFAULT 0,
  wines_count    INT          NOT NULL CHECK (wines_count    >= 0) DEFAULT 0,
  wineries_count INT          NOT NULL CHECK (wineries_count >= 0) DEFAULT 0
);

CREATE TABLE region (
  id         SERIAL PRIMARY KEY,
  name       VARCHAR(150) NOT NULL,
  seo_name   VARCHAR(150) UNIQUE NOT NULL,
  country_id INT NOT NULL
);

CREATE TABLE wine_type (
  id       SERIAL PRIMARY KEY,
  name     VARCHAR(50) UNIQUE NOT NULL,
  seo_name VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE style (
  id                  SERIAL PRIMARY KEY,
  name                VARCHAR(100) NOT NULL,
  seo_name            VARCHAR(100) UNIQUE NOT NULL,
  description         TEXT,
  body_description    VARCHAR(100),
  acidity_description VARCHAR(100),
  wine_type_id        INT
);

-- =============================================================================
-- WINERY
-- =============================================================================

CREATE TABLE winery (
  id         SERIAL PRIMARY KEY,
  name       VARCHAR(200) NOT NULL,
  seo_name   VARCHAR(200) UNIQUE NOT NULL,
  region_id  INT,
  country_id INT
);

-- =============================================================================
-- WINE AND VINTAGE
-- =============================================================================

CREATE TABLE wine (
  id                  SERIAL PRIMARY KEY,
  name                VARCHAR(200) NOT NULL,
  seo_name            VARCHAR(200) UNIQUE NOT NULL,
  wine_type_id        INT          NOT NULL,
  is_natural          BOOLEAN      NOT NULL DEFAULT false,
  winery_id           INT          NOT NULL,
  region_id           INT,
  country_id          INT,
  style_id            INT,
  wine_rating_average NUMERIC(3,2) CHECK (wine_rating_average BETWEEN 0 AND 5),
  wine_rating_count   INT          NOT NULL CHECK (wine_rating_count >= 0) DEFAULT 0,
  last_reviewed_at    TIMESTAMPTZ
);

CREATE TABLE vintage (
  id               SERIAL PRIMARY KEY,
  name             VARCHAR(200) NOT NULL,
  seo_name         VARCHAR(200) UNIQUE NOT NULL,
  wine_id          INT          NOT NULL,
  year             SMALLINT     NOT NULL CHECK (year BETWEEN 1800 AND 2100),
  label_image_url  TEXT,
  price_amount     NUMERIC(10,2),
  price_currency   CHAR(3),
  average_rating   NUMERIC(3,2) CHECK (average_rating BETWEEN 0 AND 5),
  num_reviews      INT          NOT NULL CHECK (num_reviews >= 0) DEFAULT 0,
  last_reviewed_at TIMESTAMPTZ
);

-- =============================================================================
-- USERS & REVIEWS
-- =============================================================================

CREATE TABLE "user" (
  id           SERIAL PRIMARY KEY,
  username     VARCHAR(100) UNIQUE NOT NULL,
  email        VARCHAR(200),
  display_name VARCHAR(150),
  country_id   INT,
  review_count INT         NOT NULL CHECK (review_count >= 0) DEFAULT 0,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT (NOW())
);

CREATE TABLE wine_review (
  id         SERIAL PRIMARY KEY,
  wine_id    INT          NOT NULL,
  user_id    INT,
  rating     NUMERIC(3,2) CHECK (rating BETWEEN 0 AND 5),
  review     TEXT         NOT NULL,
  created_at TIMESTAMPTZ  NOT NULL DEFAULT (NOW())
);

-- =============================================================================
-- TASTE PROFILE
-- =============================================================================

CREATE TABLE wine_taste_structure (
  wine_id   INT PRIMARY KEY NOT NULL,
  acidity   NUMERIC(3,1),
  fizziness NUMERIC(3,1),
  intensity NUMERIC(3,1),
  sweetness NUMERIC(3,1),
  tannin    NUMERIC(3,1)
);

CREATE TABLE flavor_group (
  id       SERIAL PRIMARY KEY,
  name     VARCHAR(100) UNIQUE NOT NULL,
  seo_name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE flavor_keyword (
  id       SERIAL PRIMARY KEY,
  name     VARCHAR(100) UNIQUE NOT NULL,
  seo_name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE flavor_group_keyword (
  flavor_group_id   INT          NOT NULL,
  flavor_keyword_id INT          NOT NULL,
  keyword_role      keyword_role NOT NULL DEFAULT 'primary',
  PRIMARY KEY (flavor_group_id, flavor_keyword_id)
);

CREATE TABLE wine_flavor (
  wine_id           INT NOT NULL,
  flavor_keyword_id INT NOT NULL,
  count             INT NOT NULL CHECK (count > 0) DEFAULT 1,
  PRIMARY KEY (wine_id, flavor_keyword_id)
);

-- =============================================================================
-- GRAPE AND GRAPE ASSOCIATIONS
-- =============================================================================

CREATE TABLE grape (
  id          SERIAL PRIMARY KEY,
  name        VARCHAR(150) NOT NULL,
  seo_name    VARCHAR(150) UNIQUE NOT NULL,
  wines_count INT          NOT NULL CHECK (wines_count >= 0) DEFAULT 0
);

CREATE TABLE country_grape (
  country_id INT      NOT NULL,
  grape_id   INT      NOT NULL,
  sort_order SMALLINT NOT NULL DEFAULT 0,
  PRIMARY KEY (country_id, grape_id)
);

CREATE TABLE style_grape (
  style_id   INT      NOT NULL,
  grape_id   INT      NOT NULL,
  sort_order SMALLINT NOT NULL DEFAULT 0,
  PRIMARY KEY (style_id, grape_id)
);

CREATE TABLE vintage_grape (
  vintage_id INT      NOT NULL,
  grape_id   INT      NOT NULL,
  sort_order SMALLINT NOT NULL DEFAULT 0,
  PRIMARY KEY (vintage_id, grape_id)
);

-- =============================================================================
-- INVENTORY MANAGEMENT
-- =============================================================================

CREATE TABLE shop (
  id           SERIAL PRIMARY KEY,
  name         VARCHAR(200) NOT NULL,
  seo_name     VARCHAR(200) UNIQUE NOT NULL,
  shop_type    shop_type    NOT NULL,
  address_line VARCHAR(300),
  city         VARCHAR(100),
  country_id   INT,
  phone        VARCHAR(30),
  email        VARCHAR(200),
  website_url  TEXT,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT (NOW())
);

CREATE TABLE shop_inventory (
  id             SERIAL PRIMARY KEY,
  shop_id        INT            NOT NULL,
  wine_id        INT            NOT NULL,
  vintage_id     INT,
  quantity       INT            NOT NULL CHECK (quantity >= 0) DEFAULT 0,
  price_amount   NUMERIC(10,2),
  price_currency CHAR(3),
  in_stock       BOOLEAN        NOT NULL DEFAULT true,
  updated_at     TIMESTAMPTZ    NOT NULL DEFAULT (NOW())
);

CREATE TABLE shop_transaction (
  id               SERIAL PRIMARY KEY,
  shop_id          INT              NOT NULL,
  wine_id          INT              NOT NULL,
  vintage_id       INT,
  transaction_type transaction_type NOT NULL,
  quantity         INT              NOT NULL CHECK (quantity > 0),
  unit_price       NUMERIC(10,2),
  currency         CHAR(3),
  transacted_at    TIMESTAMPTZ      NOT NULL DEFAULT (NOW()),
  notes            TEXT
);

-- =============================================================================
-- INDEXES
-- =============================================================================

CREATE INDEX idx_country_seo_name         ON country (seo_name);
CREATE INDEX idx_country_code             ON country (country_code);
CREATE INDEX idx_region_seo_name          ON region (seo_name);
CREATE INDEX idx_style_seo_name           ON style (seo_name);
CREATE INDEX idx_style_wine_type          ON style (wine_type_id);
CREATE INDEX idx_winery_seo_name          ON winery (seo_name);
CREATE INDEX idx_wine_seo_name            ON wine (seo_name);
CREATE INDEX idx_wine_winery              ON wine (winery_id);
CREATE INDEX idx_wine_region              ON wine (region_id);
CREATE INDEX idx_wine_type                ON wine (wine_type_id);
CREATE INDEX idx_wine_style               ON wine (style_id);
CREATE INDEX idx_wine_last_review         ON wine (last_reviewed_at);
CREATE INDEX idx_vintage_seo_name         ON vintage (seo_name);
CREATE INDEX idx_vintage_wine             ON vintage (wine_id);
CREATE INDEX idx_vintage_year             ON vintage (year);
CREATE INDEX idx_vintage_last_review      ON vintage (last_reviewed_at);
CREATE INDEX idx_user_country             ON "user" (country_id);
CREATE INDEX idx_wine_review_wine         ON wine_review (wine_id);
CREATE INDEX idx_wine_review_user         ON wine_review (user_id);
CREATE INDEX idx_flavor_group_keyword_g   ON flavor_group_keyword (flavor_group_id);
CREATE INDEX idx_flavor_group_keyword_k   ON flavor_group_keyword (flavor_keyword_id);
CREATE INDEX idx_flavor_group_keyword_r   ON flavor_group_keyword (keyword_role);
CREATE INDEX idx_wine_flavor_wine         ON wine_flavor (wine_id);
CREATE INDEX idx_wine_flavor_keyword      ON wine_flavor (flavor_keyword_id);
CREATE INDEX idx_wine_flavor_count        ON wine_flavor (count);
CREATE INDEX idx_grape_seo_name           ON grape (seo_name);
CREATE INDEX idx_country_grape            ON country_grape (country_id);
CREATE INDEX idx_style_grape              ON style_grape (style_id);
CREATE INDEX idx_vintage_grape            ON vintage_grape (vintage_id);
CREATE UNIQUE INDEX ON shop_inventory     (shop_id, wine_id, vintage_id);
CREATE INDEX idx_shop_inventory_shop      ON shop_inventory (shop_id);
CREATE INDEX idx_shop_inventory_wine      ON shop_inventory (wine_id);

CREATE INDEX idx_txn_time           ON shop_transaction (transacted_at);
CREATE INDEX idx_txn_type_time      ON shop_transaction (transaction_type, transacted_at);
CREATE INDEX idx_txn_shop_time      ON shop_transaction (shop_id, transacted_at);
CREATE INDEX idx_txn_wine_time      ON shop_transaction (wine_id, transacted_at);
CREATE INDEX idx_txn_vintage_time   ON shop_transaction (vintage_id, transacted_at);
CREATE INDEX idx_txn_shop_type_time ON shop_transaction (shop_id, transaction_type, transacted_at);

-- =============================================================================
-- FOREIGN KEYS
-- =============================================================================

ALTER TABLE region               ADD FOREIGN KEY (country_id)         REFERENCES country (id)         ON DELETE RESTRICT   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE style                ADD FOREIGN KEY (wine_type_id)       REFERENCES wine_type (id)       ON DELETE SET NULL   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE winery               ADD FOREIGN KEY (region_id)          REFERENCES region (id)          ON DELETE SET NULL   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE winery               ADD FOREIGN KEY (country_id)         REFERENCES country (id)         ON DELETE SET NULL   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE wine                 ADD FOREIGN KEY (wine_type_id)       REFERENCES wine_type (id)       ON DELETE RESTRICT   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE wine                 ADD FOREIGN KEY (winery_id)          REFERENCES winery (id)          ON DELETE RESTRICT   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE wine                 ADD FOREIGN KEY (region_id)          REFERENCES region (id)          ON DELETE SET NULL   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE wine                 ADD FOREIGN KEY (country_id)         REFERENCES country (id)         ON DELETE SET NULL   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE wine                 ADD FOREIGN KEY (style_id)           REFERENCES style (id)           ON DELETE SET NULL   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE vintage              ADD FOREIGN KEY (wine_id)            REFERENCES wine (id)            ON DELETE RESTRICT   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE "user"               ADD FOREIGN KEY (country_id)         REFERENCES country (id)         ON DELETE SET NULL   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE wine_review          ADD FOREIGN KEY (wine_id)            REFERENCES wine (id)            ON DELETE CASCADE    DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE wine_review          ADD FOREIGN KEY (user_id)            REFERENCES "user" (id)          ON DELETE SET NULL   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE wine_taste_structure ADD FOREIGN KEY (wine_id)            REFERENCES wine (id)            ON DELETE CASCADE    DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE flavor_group_keyword ADD FOREIGN KEY (flavor_group_id)    REFERENCES flavor_group (id)   ON DELETE CASCADE    DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE flavor_group_keyword ADD FOREIGN KEY (flavor_keyword_id)  REFERENCES flavor_keyword (id) ON DELETE CASCADE    DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE wine_flavor          ADD FOREIGN KEY (wine_id)            REFERENCES wine (id)            ON DELETE CASCADE    DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE wine_flavor          ADD FOREIGN KEY (flavor_keyword_id)  REFERENCES flavor_keyword (id)  ON DELETE RESTRICT   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE country_grape        ADD FOREIGN KEY (country_id)         REFERENCES country (id)         ON DELETE CASCADE    DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE country_grape        ADD FOREIGN KEY (grape_id)           REFERENCES grape (id)           ON DELETE CASCADE    DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE style_grape          ADD FOREIGN KEY (style_id)           REFERENCES style (id)           ON DELETE CASCADE    DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE style_grape          ADD FOREIGN KEY (grape_id)           REFERENCES grape (id)           ON DELETE CASCADE    DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE vintage_grape        ADD FOREIGN KEY (vintage_id)         REFERENCES vintage (id)         ON DELETE CASCADE    DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE vintage_grape        ADD FOREIGN KEY (grape_id)           REFERENCES grape (id)           ON DELETE CASCADE    DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE shop                 ADD FOREIGN KEY (country_id)         REFERENCES country (id)         ON DELETE SET NULL   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE shop_inventory       ADD FOREIGN KEY (shop_id)            REFERENCES shop (id)            ON DELETE CASCADE    DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE shop_inventory       ADD FOREIGN KEY (wine_id)            REFERENCES wine (id)            ON DELETE RESTRICT   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE shop_inventory       ADD FOREIGN KEY (vintage_id)         REFERENCES vintage (id)         ON DELETE SET NULL   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE shop_transaction     ADD FOREIGN KEY (shop_id)            REFERENCES shop (id)            ON DELETE RESTRICT   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE shop_transaction     ADD FOREIGN KEY (wine_id)            REFERENCES wine (id)            ON DELETE RESTRICT   DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE shop_transaction     ADD FOREIGN KEY (vintage_id)         REFERENCES vintage (id)         ON DELETE SET NULL   DEFERRABLE INITIALLY IMMEDIATE;
