from dataclasses import dataclass

DEMO_DETECTED_WINE_ID = 618


@dataclass
class DetectedWine:
    wine_id: int | None
    confidence: float
    detection_method: str


def detect_wine_from_image_bytes(image_bytes: bytes) -> DetectedWine:
    # Placeholder detector for the image-detection demo path.
    # The uploaded image is accepted but intentionally ignored.
    return DetectedWine(
        wine_id=DEMO_DETECTED_WINE_ID,
        confidence=0.99 if image_bytes else 0.0,
        detection_method="placeholder-fixed-wine",
    )
