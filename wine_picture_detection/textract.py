
import math
import numpy as np
from PIL import Image
import cv2
from deskew import determine_skew
import os
from pathlib import Path
from dotenv import load_dotenv
from sie_sdk import SIEClient, Item

load_dotenv(Path(__file__).parent.parent / "wine_flavor" / ".env")

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

    # convert to np array
    image_array: np.ndarray = np.array(image)
    
    # Resize
    image_array = cv2.resize(image_array, None, fx=1.2, fy=1.2, interpolation=cv2.INTER_CUBIC)
    
    # Deskew
    image_array = _deskew(image_array)

    # Normalize
    image_array = cv2.normalize(image_array, dst=None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX) 
        
    # Gray
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



def textract(image: Image.Image):

    client = SIEClient(os.getenv("CLUSTER_URL"), api_key=os.getenv("API_KEY"))

    result = client.extract(
        "microsoft/Florence-2-base",
        Item(images=[{"data": image, "format": "png"}]),
        options={"task": "<OCR_WITH_REGION>"}, gpu="l4-spot", wait_for_capacity=True, provision_timeout_s=900
    )

    return result


# def match():
    # """ fuzzy match extracted text with known whines to find same whine or most similar """
    # - wine name
    # - vintage year
    # - winery name


def debug():

    # Load image
    wine_label = Image.open("label1.png")
    wine_label.show()
    print("Loaded image")

    # Check image quality
    image_quality = check_quality(wine_label)
    print(f"Image quality:\n\t{image_quality}")
    return 

    # Preprocess Image
    preprocessed_label = preprocess(wine_label)
    preprocessed_label.show()
    print("Preprocessed image")

    # Extract text 
    extracted_text = textract(preprocessed_label)
    print(f"Extracted Text:\n\t{extracted_text}")


if __name__ == "__main__":
    debug()
