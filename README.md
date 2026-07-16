# Media Analysis Pipeline

## System Overview

This project is an asynchronous media processing architecture designed to extract, transcribe, and analyze audio from YouTube video links. It utilizes a microservices approach containerized via Docker, optimized for single-port deployment environments such as Hugging Face Spaces.

## Architecture

| Component | Technology |
|---|---|
| **Frontend** | Next.js (TypeScript) compiled as a static export (`out/`) |
| **API Gateway** | FastAPI serving both the static frontend assets and RESTful API routes on a unified port |
| **Message Broker** | Redis |
| **Task Execution** | Celery worker handling media extraction (`yt-dlp`, `ffmpeg`), transcription (OpenAI Whisper), and structural analysis (Google Gemini API) |

## Prerequisites

- Docker Engine and Docker Compose
- Google Gemini API Key
- Exported YouTube session cookies (required to bypass `403 Forbidden` and bot-mitigation restrictions)

## Environment Configuration

Create a `.env` file in the root directory. This file dictates the execution parameters for the containerized services.

```env
# .env
API_KEY=your_google_gemini_api_key_here
```

## Cookie Authentication

To enable successful media extraction without triggering network bans, a valid YouTube session must be mounted into the worker container.

1. Extract YouTube session cookies using a browser extension (e.g., "Get cookies.txt LOCALLY").
2. Save the exact output as `cookies.txt` in the root directory, adjacent to the `docker-compose.yml` file.

## Initialization and Execution

Execute the following commands to construct the image layers and initialize the container stack.

```bash
# Halt any existing execution and clear dangling networks
docker compose down

# Build the image layers and start the services in detached mode
docker compose up -d --build

# Optional: To monitor the Celery worker and FastAPI logs
docker compose logs -f
```

## Service Access

Upon successful initialization, the unified service is accessible via the host machine:

- **Web Interface:** [`http://localhost:8000/`](http://localhost:8000/) — Serves the compiled Next.js static application
- **API Documentation:** [`http://localhost:8000/docs`](http://localhost:8000/docs) — Interactive Swagger UI

## Primary API Endpoints

### `POST /api/analyze`

Accepts a JSON payload and dispatches the background Celery task.

**Request body:**
```json
{
  "url": "<youtube_link>"
}
```

**Response:** Returns a `task_id`.

### `GET /api/status/{task_id}`

Polls the Redis broker for the execution state:

- `PENDING`
- `PROCESSING`
- `COMPLETED`
- `FAILED`

Upon the `COMPLETED` state, it returns the synthesized metadata array containing:

- Transcription summary
- Technical jargon
- Topic timeline
- Recommended exploration resources