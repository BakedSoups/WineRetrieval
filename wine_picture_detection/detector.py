from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from .textract import match_label, preprocess, textract


@dataclass
class DetectedWine:
    wine_id: int | None
    confidence: float
    detection_method: str


def detect_wine_from_image_bytes(image_bytes: bytes) -> DetectedWine:
    if not image_bytes:
        return DetectedWine(wine_id=None, confidence=0.0, detection_method="empty-image")

    try:
        image = Image.open(BytesIO(image_bytes))
        image.load()
    except (UnidentifiedImageError, OSError):
        return DetectedWine(wine_id=None, confidence=0.0, detection_method="invalid-image")

    try:
        extracted_text = textract(preprocess(image))
        matched_labels = match_label(extracted_text, top_n=1)
    except Exception:
        return DetectedWine(wine_id=None, confidence=0.0, detection_method="ocr-error")

    if not matched_labels:
        return DetectedWine(wine_id=None, confidence=0.0, detection_method="sie-florence-no-match")

    best_match = matched_labels[0]
    return DetectedWine(
        wine_id=int(best_match["wine_id"]) if best_match.get("wine_id") is not None else None,
        confidence=max(0.0, min(1.0, float(best_match.get("match_score", 0.0)) / 100.0)),
        detection_method="sie-florence-fuzzy-match",
    )
