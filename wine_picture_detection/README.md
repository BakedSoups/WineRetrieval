# Wine Picture Detection

This folder contains the standalone OCR-based wine label detection prototype used by the demo app.

## What It Does

This module takes a wine label image, runs OCR on it, extracts the readable text, and then fuzzy-matches that text against the local wine database to find the most likely bottle.

The main demo app uses this same flow through `wine_picture_detection/detector.py`, but this folder is meant to be runnable by itself as a separate project.


## Setup

From this folder:

```bash
cd wine_picture_detection
```

Install the Python dependencies you need for this module, then create a local `.env` if you want to run it independently from the repo root.

The OCR flow expects SIE access through environment variables such as:

```env
CLUSTER_URL=https://your-sie-cluster-url
API_KEY=your-sie-api-key
SIE_OCR_MODEL=microsoft/Florence-2-base
DATABASE_PATH=wine_flavor.db
```

## Run

Run the OCR script directly:

```bash
python textract.py
```

You can also pass a specific image:

```bash
python textract.py path/to/image.webp --top-n 3
```

`textract.py` will:

- load and preprocess the image
- send it to the configured SIE OCR model
- extract text from the label
- fuzzy-match the text against the local wine database
- print the top match candidates



## Why SIE Fits This Use Case

SIE is a good fit here because OCR is the core task, not just string matching.

The hard part is getting usable text out of messy wine-label photos:

- labels have decorative typography
- images can be tilted, noisy, or poorly lit
- the bottle photo often includes partial or imperfect text

Using SIE for OCR lets this prototype focus on extracting structured text from the image first, then doing local matching against the wine database.
