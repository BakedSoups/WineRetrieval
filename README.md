# WineRetrieval
A wine recommender that replaces vague free-text search with a structured, visual UX. Users select a reference wine they already like, then navigate a flavor tree built from that wine's actual tasting data  clicking the specific notes they want more of. Sliders derived from review language let them dial in style and occasion. The result is a precise flavor profile built through exploration rather than description, which maps cleanly onto the underlying data without any lossy NLP translation.

## Running the app

Use the helper scripts from the repo root:

- `./start.sh` starts the backend on the host and the frontend in Docker
- `./stop.sh` stops both

App URLs:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

## Why the backend runs on the host

The OCR image-detection flow calls an external SIE OCR endpoint defined by `CLUSTER_URL`.

In this project, the host machine can reach that endpoint, but the Docker container cannot. A Docker-side connectivity check resolves the OCR host correctly, but raw TCP connection attempts time out from inside the container. That means the issue is container network egress, not application code or `.env` loading.

Because of that, the reliable cross-platform setup is:

- backend on the host Python environment
- frontend in Docker

The frontend container talks to the host backend through `host.docker.internal`, which works on macOS and Windows and is mapped in `compose.yml` for Linux via `host-gateway`.
