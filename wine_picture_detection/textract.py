
""" Extract text from a wine label and fuzzy match against database """

import math
import numpy as np
from PIL import Image
import cv2
from deskew import determine_skew
import os
from pathlib import Path
from dotenv import load_dotenv
from sie_sdk import SIEClient, Item
import re
import sqlite3
from rapidfuzz import fuzz

load_dotenv(Path(__file__).parent.parent / "wine_flavor" / ".env")

DATABASE_PATH = os.getenv("DATABASE_PATH", "wine_flavor.db")
TOP_N = int(os.getenv("TOP_N", 5))
SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD", 0))
SIE_OCR_MODEL = os.getenv("SIE_OCR_MODEL")
ALLOWED_OCR_MODELS = os.getenv("ALLOWED_OCR_MODELS")
CLUSTER_URL = os.getenv("CLUSTER_URL")
API_KEY = os.getenv("API_KEY")
GPU = os.getenv("GPU")
PROVISION_TIMEOUT_S = int(os.getenv("PROVISION_TIMEOUT_S"))
DB_FIELDS = ["wine_name", "winery_name", "region_name", "country_name"]

# Image quality check >>>

def _is_blurry(img: np.ndarray, threshold_pct: float = 10.0) -> bool:
    # Laplacian variance empirical range 0–1000
    return bool(cv2.Laplacian(img, cv2.CV_64F).var() < (threshold_pct / 100) * 1000)

def _check_exposure(img: np.ndarray, min_pct: float = 19.6, max_pct: float = 78.4) -> str:
    mean = img.mean()
    if mean < (min_pct / 100) * 255: return "underexposed"
    if mean > (max_pct / 100) * 255: return "overexposed"
    return "ok"

def _is_noisy(img: np.ndarray, threshold_pct: float = 33.0) -> bool:
    # mean absolute difference empirical range 0–30
    denoised = cv2.GaussianBlur(img.astype(float), (5, 5), 0)
    return bool(np.mean(np.abs(img.astype(float) - denoised)) > (threshold_pct / 100) * 30)

def _is_low_contrast(img: np.ndarray, threshold_pct: float = 19.6) -> bool:
    # std dev on 0–255 scale
    return bool(img.std() < (threshold_pct / 100) * 255)

def _is_low_resolution(img: np.ndarray, min_resolution: tuple[int, int] = (640, 480)) -> bool:
    h, w = img.shape
    return bool(w < min_resolution[0] or h < min_resolution[1])

def check_quality(image: Image.Image) -> dict:
	
    """ validate that the image is good enough for OCR """
	
    gray_image: np.ndarray = np.array(image.convert("L"))
 
    return {
        "blurry":         _is_blurry(gray_image),
        "exposure":       _check_exposure(gray_image),
        "noisy":          _is_noisy(gray_image),
        "low_contrast":   _is_low_contrast(gray_image),
        "low_resolution": _is_low_resolution(gray_image),
    }
 
# Image quality check <<<

# Image Preprocessing >>>

def _deskew(image: np.ndarray) -> np.ndarray:
    
    background = (0, 0, 0)
    skew = determine_skew(image)
    radian_skew = math.radians(skew)

    # shape[:2] is (rows, cols) = (height, width)
    skew_height, skew_width = image.shape[:2]

    new_width = abs(np.sin(radian_skew) * skew_height) + abs(np.cos(radian_skew) * skew_width)
    new_height = abs(np.sin(radian_skew) * skew_width) + abs(np.cos(radian_skew) * skew_height)

    center = tuple(np.array(image.shape[1::-1]) / 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, skew, 1.0)

    # [0,2] is x-translation, [1,2] is y-translation
    rotation_matrix[0, 2] += (new_width - skew_width) / 2
    rotation_matrix[1, 2] += (new_height - skew_height) / 2

    # warpAffine dsize is (width, height)
    return cv2.warpAffine(
        image, rotation_matrix,
        (int(round(new_width)), int(round(new_height))),
        borderValue=background
    )


def preprocess(image: Image.Image) -> Image.Image:

    # convert to numpy array
    image_array: np.ndarray = np.array(image)
    
    # Resize
    image_array = cv2.resize(image_array, None, fx=1.2, fy=1.2, interpolation=cv2.INTER_CUBIC)
    
    # Deskew
    image_array = _deskew(image_array)

    # Normalize
    image_array = cv2.normalize(image_array, dst=None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX) 
        
    # Gray
    RGB = 3
    if len(image_array.shape) == RGB:
        image_array = cv2.cvtColor(image_array, cv2.COLOR_BGR2GRAY)
    
    #Dialate
    image_array = cv2.dilate(src=image_array, kernel=np.ones((1, 1), np.uint8), iterations=1)
    
    # Erode
    image_array = cv2.erode(src=image_array, kernel=np.ones((2, 2), np.uint8), iterations=2)

    # Denoise
    image_array = cv2.bilateralFilter(src=image_array, d=5, sigmaColor=55, sigmaSpace=60)
                
    # Binarize
    _, image_array = cv2.threshold(image_array, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                                
    # Convert back to Image and return
    return Image.fromarray(image_array)

# Image Preprocessing <<<

# Text Extraction >>>

def textract(image: Image.Image):
    return SIEClient(CLUSTER_URL, api_key=API_KEY).extract(
        SIE_OCR_MODEL,
        Item(images=[{"data": image, "format": "png"}]),
        options={"task": "<OCR_WITH_REGION>"}, gpu=GPU, wait_for_capacity=True, provision_timeout_s=PROVISION_TIMEOUT_S
    )

# Text Extraction <<<

# Fuzzy Match >>>

def extract_blob(label_data: dict) -> str:
    """Join all entity texts into one string, stripping XML artifacts."""
    raw = " ".join(e["text"] for e in label_data.get("entities", []) if e.get("text"))
    return re.sub(r"</?\w+>", "", raw).strip()


def extract_vintage(blob: str) -> str | None:
    """Pull first 4-digit year in valid wine vintage range via regex."""
    match = re.search(r"\b(1[89]\d{2}|20[0-2]\d)\b", blob)
    return match.group(0) if match else None


def fetch_wines(db_path: str, vintage: str | None) -> list[dict]:
    """Pre-filter by vintage if available, otherwise fetch all."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    if vintage:
        cursor.execute("""
            SELECT wine_id, winery_name, wine_name, vintage_year,
                   rating_average, rating_count, country_name, region_name
            FROM wines WHERE vintage_year = ?
        """, (vintage,))
    else:
        cursor.execute("""
            SELECT wine_id, winery_name, wine_name, vintage_year,
                   rating_average, ratings_count, country_name, region_name
            FROM wines
        """)

    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()
    return rows


def _field_score(query: str, target: str) -> float:
    """
	Score query against target. Rewards full word matches over partial overlap.
	Combines fuzzy ratio (handles OCR noise) with word coverage (penalizes missing words).
	"""
    query_tokens = set(query.lower().split())
    target_tokens = set(target.lower().split())
    
    # Jaccard: intersection / union — penalizes both missing and extra words
    coverage = len(query_tokens & target_tokens) / len(query_tokens | target_tokens)
    
    fuzzy = fuzz.token_sort_ratio(query.lower(), target.lower())

    # 60% coverage, 40% fuzzy — adjust if OCR quality is poor
    return (fuzzy * 0.4) + (coverage * 100 * 0.6)

def score_wine(wine: dict, entities: list[str]) -> float:
    """For each entity, take its best score across all DB fields, then average across entities.
    Vintage scored separately as exact match bonus."""
    entity_scores = [
        max(_field_score(entity, str(wine.get(field) or "")) for field in DB_FIELDS)
        for entity in entities
    ]

    if wine.get("vintage_year"):
        entity_scores.append(100 if any(entity == str(wine["vintage_year"]) for entity in entities) else 0)

    return sum(entity_scores) / len(entity_scores) if entity_scores else 0.0


def match_label(label_data: dict, top_n: int = TOP_N) -> list[dict]:
    """Match a raw label extraction dict against the wine database.

    Returns a list of up to top_n wine dicts sorted by match_score descending,
    each containing: wine_id, winery_name, wine_name, vintage_year,
    rating_average, rating_count, country_name, region_name, match_score (0-100).
    Returns an empty list if no text or wine fields could be extracted.
    """
    blob = extract_blob(label_data)

    if not blob:
        return []

    vintage = extract_vintage(blob)
    # Each entity is a separate matching unit against all DB fields
    entities = [e["text"].strip().lower() for e in label_data.get("entities", []) if e.get("text")]

    wines = fetch_wines(DATABASE_PATH, vintage)
    scored = sorted(
        [{**wine, "match_score": score_wine(wine, entities)} for wine in wines],
        key=lambda wine: wine["match_score"],
        reverse=True
    )

    return [wine for wine in scored if wine["match_score"] >= SCORE_THRESHOLD][:top_n]

# Fuzzy Match <<<

def main():

    if SIE_OCR_MODEL not in ALLOWED_OCR_MODELS:
        raise ValueError(f"SIE_OCR_MODEL '{SIE_OCR_MODEL}' not in ALLOWED_OCR_MODELS: {ALLOWED_OCR_MODELS}")

    # Load image
    wine_label = Image.open("wine_test.png")
    wine_label.show()
    print("\nLoaded image")

    # Check image quality
    image_quality = check_quality(wine_label)
    print(f"\nImage quality:\n{image_quality}")

    # Preprocess Image
    # preprocessed_label = preprocess(wine_label)
    # preprocessed_label.show()
    # print("Preprocessed image")

    # Extract text 
    extracted_text = textract(wine_label)
    print(f"\nExtracted Text:\n{extracted_text}\n")

    # Fuzzy match with known wines
    matched_labels: list[dict] = match_label(extracted_text)
    print(f"\nMatched Labels:")
    [print(dictionary) for dictionary in matched_labels] 
    
    ''' DEBUG >>>

    tries = 0
    
    for dictionary in matched_labels:
        
        if dictionary["wine_name"] == "Quinta de São Sebastião":
            print(dictionary)
            print(f"{tries=}")
            break
        
        tries += 1
    
    DEBUG <<< '''

if __name__ == "__main__":
    main()
