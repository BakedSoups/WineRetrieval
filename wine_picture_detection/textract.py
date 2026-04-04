from __future__ import annotations

import argparse
import math
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent

load_dotenv(ROOT_DIR / ".env")
load_dotenv(PACKAGE_DIR / ".env", override=True)

_database_path_value = os.getenv("DATABASE_PATH", "wine_flavor.db")
DATABASE_PATH = Path(_database_path_value)
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = ROOT_DIR / DATABASE_PATH

TOP_N = int(os.getenv("TOP_N", 5))
SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD", 0))
OCR_WAIT_FOR_CAPACITY = os.getenv("OCR_WAIT_FOR_CAPACITY", "false").lower() == "true"
OCR_PROVISION_TIMEOUT_S = int(os.getenv("OCR_PROVISION_TIMEOUT_S", 30))
DB_FIELDS = ("wine_name", "winery_name", "region_name", "country_name")


def _require_cv2():
    import cv2

    return cv2


def _require_determine_skew():
    from deskew import determine_skew

    return determine_skew


def _require_fuzz():
    from rapidfuzz import fuzz

    return fuzz


def _require_sie_sdk():
    from sie_sdk import Item, SIEClient

    return SIEClient, Item


def _deskew(image: np.ndarray) -> np.ndarray:
    cv2 = _require_cv2()
    determine_skew = _require_determine_skew()

    background = (0, 0, 0)
    skew = determine_skew(image)
    radian_skew = math.radians(skew)
    skew_height, skew_width = image.shape[:2]

    new_width = abs(np.sin(radian_skew) * skew_height) + abs(np.cos(radian_skew) * skew_width)
    new_height = abs(np.sin(radian_skew) * skew_width) + abs(np.cos(radian_skew) * skew_height)

    center = tuple(np.array(image.shape[1::-1]) / 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, skew, 1.0)
    rotation_matrix[0, 2] += (new_width - skew_width) / 2
    rotation_matrix[1, 2] += (new_height - skew_height) / 2

    return cv2.warpAffine(
        image,
        rotation_matrix,
        (int(round(new_width)), int(round(new_height))),
        borderValue=background,
    )


def normalize_image(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image

    if image.mode in {"RGBA", "LA"}:
        background = Image.new("RGB", image.size, (255, 255, 255))
        alpha = image.getchannel("A")
        background.paste(image.convert("RGBA"), mask=alpha)
        return background

    return image.convert("RGB")


def preprocess(image: Image.Image) -> Image.Image:
    cv2 = _require_cv2()

    image_array = np.array(normalize_image(image))
    image_array = cv2.resize(image_array, None, fx=1.2, fy=1.2, interpolation=cv2.INTER_CUBIC)
    image_array = _deskew(image_array)
    image_array = cv2.normalize(image_array, dst=None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)

    if len(image_array.shape) == 3:
        image_array = cv2.cvtColor(image_array, cv2.COLOR_BGR2GRAY)

    image_array = cv2.dilate(src=image_array, kernel=np.ones((1, 1), np.uint8), iterations=1)
    image_array = cv2.erode(src=image_array, kernel=np.ones((2, 2), np.uint8), iterations=2)
    image_array = cv2.bilateralFilter(src=image_array, d=5, sigmaColor=55, sigmaSpace=60)
    _, image_array = cv2.threshold(image_array, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return Image.fromarray(image_array)


def textract(image: Image.Image) -> dict[str, Any]:
    SIEClient, Item = _require_sie_sdk()

    cluster_url = os.getenv("CLUSTER_URL")
    api_key = os.getenv("API_KEY")
    if not cluster_url or not api_key:
        raise ValueError("CLUSTER_URL and API_KEY are required for OCR")

    sie_client = SIEClient(cluster_url, api_key=api_key)
    return sie_client.extract(
        "microsoft/Florence-2-base",
        Item(images=[{"data": image, "format": "png"}]),
        options={"task": "<OCR_WITH_REGION>"},
        gpu="l4-spot",
        wait_for_capacity=OCR_WAIT_FOR_CAPACITY,
        provision_timeout_s=OCR_PROVISION_TIMEOUT_S,
    )


def extract_blob(label_data: dict[str, Any]) -> str:
    raw = " ".join(entity["text"] for entity in label_data.get("entities", []) if entity.get("text"))
    return re.sub(r"</?\w+>", "", raw).strip()


def extract_vintage(blob: str) -> str | None:
    match = re.search(r"\b(1[89]\d{2}|20[0-2]\d)\b", blob)
    return match.group(0) if match else None


def fetch_wines(db_path: Path | str, vintage: str | None) -> list[dict[str, Any]]:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    if vintage:
        cursor.execute(
            """
            SELECT wine_id, winery_name, wine_name, vintage_year,
                   rating_average, ratings_count, country_name, region_name
            FROM wines
            WHERE vintage_year = ?
            """,
            (vintage,),
        )
    else:
        cursor.execute(
            """
            SELECT wine_id, winery_name, wine_name, vintage_year,
                   rating_average, ratings_count, country_name, region_name
            FROM wines
            """
        )

    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()
    return rows


def _field_score(query: str, target: str) -> float:
    fuzz = _require_fuzz()

    query_tokens = set(query.lower().split())
    target_tokens = set(target.lower().split())
    coverage = len(query_tokens & target_tokens) / len(query_tokens) if query_tokens else 0.0
    fuzzy = fuzz.token_sort_ratio(query.lower(), target.lower())
    return (fuzzy * 0.4) + (coverage * 100 * 0.6)


def score_wine(wine: dict[str, Any], entities: list[str]) -> float:
    entity_scores = [
        max(_field_score(entity, str(wine.get(field) or "")) for field in DB_FIELDS)
        for entity in entities
    ]

    if wine.get("vintage_year"):
        entity_scores.append(100.0 if any(entity == str(wine["vintage_year"]) for entity in entities) else 0.0)

    return sum(entity_scores) / len(entity_scores) if entity_scores else 0.0


def match_label(label_data: dict[str, Any], top_n: int = TOP_N) -> list[dict[str, Any]]:
    blob = extract_blob(label_data)
    if not blob:
        return []

    vintage = extract_vintage(blob)
    entities = [entity["text"].strip().lower() for entity in label_data.get("entities", []) if entity.get("text")]
    wines = fetch_wines(DATABASE_PATH, vintage)

    scored = sorted(
        [{**wine, "match_score": score_wine(wine, entities)} for wine in wines],
        key=lambda wine: wine["match_score"],
        reverse=True,
    )
    return [wine for wine in scored if wine["match_score"] >= SCORE_THRESHOLD][:top_n]


def extract_and_match_image(image: Image.Image, top_n: int = TOP_N) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized = normalize_image(image)
    extracted = textract(preprocess(normalized))
    matches = match_label(extracted, top_n=top_n)
    return extracted, matches


def main():
    parser = argparse.ArgumentParser(description="Run OCR against a wine label image.")
    parser.add_argument(
        "image",
        nargs="?",
        default=str(PACKAGE_DIR / "wine_test.webp"),
        help="Path to the image to OCR. Defaults to wine_picture_detection/wine_test.webp",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=TOP_N,
        help="Number of fuzzy-match results to print.",
    )
    args = parser.parse_args()

    image_path = Path(args.image)
    print(f"Image: {image_path}")
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    image = Image.open(image_path)
    image.load()
    print(f"Loaded: format={image.format} mode={image.mode} size={image.size}")

    extracted, matches = extract_and_match_image(image, top_n=args.top_n)
    print("\nOCR output:")
    print(extracted)

    print(f"\nTop {args.top_n} matches:")
    for match in matches:
        print(match)


if __name__ == "__main__":
    main()
