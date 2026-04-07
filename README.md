# WineRetrieval

This repo is mostly a demo app, not a scaled production system.

It wires together two separate prototype capabilities:

- `wine_picture_detection/`: OCR-based wine label detection
- `wine_flavor/`: wine retrieval and reranking from flavor + structure preferences

Those two pieces are connected through the root `app.py` so you can try them in one UI, but they are also meant to be runnable on their own from inside their own folders.

The duplicated database files and local `.env` setup are intentional. The goal is to let someone open either subproject directly and run it in isolation without depending on the full root app setup.

## Project Structure

- Root `app.py`: demo backend that wires OCR and retrieval into one FastAPI app
- `app/`: Next.js frontend for the demo UI
- `wine_picture_detection/`: standalone OCR and label-matching prototype
- `wine_flavor/`: standalone retrieval and reranking prototype

## Running the Full Demo

Use the helper scripts from the repo root:

- `./start.sh` starts the backend on the host and the frontend in Docker
- `./stop.sh` stops both

App URLs:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

## Environment Files

- Root `app.py` uses the root `.env`
- `wine_picture_detection/` can also use its own local `.env` / `.env.example`
- The duplicated setup is intentional so the subprojects can be run separately

If you are running the full demo, put the required backend keys in the root `.env`.

## Why the Backend Runs on the Host

The OCR flow calls an external SIE OCR endpoint defined by `CLUSTER_URL`.

In this project, the host machine can reach that endpoint, but the Docker container cannot. The reliable setup for the demo is therefore:

- backend on the host Python environment
- frontend in Docker

The browser talks to the backend at `http://localhost:8000`. The frontend container only hosts the Next.js dev server on `http://localhost:3000`.

## Running the Subprojects Directly

If you only want one feature, run it from its own folder:

- OCR flow: see `wine_picture_detection/README.md`
- Retrieval flow: see `wine_flavor/README.md`
