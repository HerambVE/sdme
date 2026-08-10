# 🧠 Semantic Drift Media Engine (SDME)

> An AI-powered media analysis platform that transcribes any YouTube video using OpenAI Whisper and performs deep semantic analysis using Google Gemini — extracting topics, jargon, proofs, summaries, and academic references from Wikipedia, arXiv, and OpenAlex.

---

## 📸 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser / Client                      │
│              Next.js Static Export (served at /)             │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP
┌───────────────────────▼─────────────────────────────────────┐
│                   FastAPI (main.py)                          │
│   /health/  /process-media/  /task-status/{id}  (static/)   │
└───────────┬────────────────────────────┬────────────────────┘
            │ Celery .delay()            │ SQLite (aiosqlite)
┌───────────▼────────────┐   ┌──────────▼──────────────────┐
│   Redis (Broker)        │   │  media_engine.db             │
│   Task Queue            │   │  MediaAnalysis table         │
└───────────┬────────────┘   └──────────────────────────────┘
            │
┌───────────▼────────────────────────────────────────────────┐
│                  Celery Worker (worker.py)                   │
│  yt-dlp → FFmpeg → Whisper (STT) → Gemini API → Wikipedia   │
│                    arXiv + OpenAlex external indexing        │
└────────────────────────────────────────────────────────────┘
```

---

## ✨ Features

- 🎙️ **Audio Transcription** — Downloads and transcribes YouTube videos using OpenAI Whisper (`base` model, CPU-only).
- 🤖 **AI Semantic Analysis** — Extracts Tags, Jargon, Summary, Topics, Proofs, and Explore terms using Google Gemini.
- 📚 **Academic Indexing** — Cross-references extracted terms with Wikipedia, arXiv, and OpenAlex in parallel.
- 🔑 **BYOK (Bring Your Own Key)** — Users can supply their own Gemini API key in the UI. Keys are never stored server-side.
- 🔄 **Force Re-Analyse** — Any previously processed video can be re-analysed on demand.
- 🗄️ **Result Caching** — SQLite database caches results. Re-submitting the same URL returns instantly.
- 🐳 **Dockerised Stack** — Fully containerised with Docker Compose (Redis, WARP proxy, Web, Worker).

---

## 🚀 Quick Start (Local with Docker)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
- A **Google Gemini API Key** (free tier available at [aistudio.google.com](https://aistudio.google.com/)).

### 1. Clone the repository

```bash
git clone https://github.com/HerambVE/sdme.git
cd sdme
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
API_KEY=your_google_gemini_api_key_here
REDIS_URL=redis://redis:6379/0
REMOVE_DB_ON_STARTUP=true
REMOVE_DB_ON_SHUTDOWN=true
```

> ⚠️ **Never commit your `.env` file.** It is already excluded by `.gitignore`.

### 3. Start the full stack

```bash
docker compose up -d
```

This starts 4 containers:

| Container | Purpose |
|---|---|
| `sdme-redis-1` | Celery task broker |
| `sdme-warp-1` | Cloudflare WARP SOCKS5 proxy (bypasses YouTube datacenter bans) |
| `sdme-web-1` | FastAPI web server + static frontend |
| `sdme-worker-1` | Celery background worker (Whisper + Gemini) |

### 4. Open the app

Navigate to **[http://localhost:8000](http://localhost:8000)** in your browser.

### 5. Stop and clean up

```bash
docker compose down
```

> The SQLite database is automatically deleted on shutdown and recreated fresh on the next startup.

---

## 🔑 API Keys & Secrets

### Google Gemini API Key

| Setting | Details |
|---|---|
| **Where to get it** | [Google AI Studio](https://aistudio.google.com/) → *Get API Key* |
| **Free tier** | 15 requests/minute, 1,500 requests/day |
| **Server-side config** | Set `API_KEY=...` in `.env` file |
| **Client-side BYOK** | Click `🔑 Set Gemini Key` in the UI — stored in browser `localStorage`, sent via `X-Gemini-API-Key` HTTP header, **never saved to disk or database** |

> 💡 If `API_KEY` is left empty in the server environment, all users **must** supply their own key via the BYOK modal. This is the recommended setup for public deployments to preserve your free-tier quota.

### YouTube Cookies (Optional)

Some age-restricted or region-locked YouTube videos require authentication cookies.

1. Export your YouTube cookies from your browser using the [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) Chrome extension.
2. Save the file as `cookies.txt` in the project root.
3. `yt-dlp` will automatically use it if present.

> ⚠️ `cookies.txt` is excluded by `.gitignore` and will never be committed to the repository.

---

## 🌐 API Reference

### `GET /health/`
Returns the backend health status.

**Response:**
```json
{ "status": "ok", "service": "SDME Engine" }
```

---

### `POST /process-media/`
Submits a YouTube URL for analysis.

**Headers (optional):**
```
X-Gemini-API-Key: your_key_here
```

**Request Body:**
```json
{
  "media_url": ["https://www.youtube.com/watch?v=VIDEO_ID"],
  "force_reanalyse": false
}
```

| Field | Type | Description |
|---|---|---|
| `media_url` | `list[str]` | List of YouTube URLs to process |
| `force_reanalyse` | `bool` | Set `true` to bypass cache and re-process a video |

**Response (`202 Accepted`):**
```json
{ "status": "Task Queued", "Task_id": "abc123-..." }
```

---

### `GET /task-status/{task_id}`
Polls the status of a processing task.

**Response:**
```json
{
  "Task_id": "abc123-...",
  "task_status": "SUCCESS",
  "result": [
    {
      "Name": "https://youtube.com/...",
      "Status": "COMPLETED",
      "Transcript": "Full transcribed text...",
      "Meta_Analysis": {
        "tnj": { "categories": [...], "jargons": [...] },
        "summary": "Dense paragraph summary...",
        "topics": [...],
        "proof": [...],
        "explore": [...],
        "external_indexing": {
          "wikipedia_jargon_results": {...},
          "arxiv_proof_results": {...},
          "openalex_explore_results": {...}
        }
      },
      "Timestamped_Transcript": [...]
    }
  ]
}
```

---

## ⚙️ Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `API_KEY` | ✅ (or BYOK) | — | Google Gemini API key for server-side processing |
| `REDIS_URL` | ✅ | `redis://redis:6379/0` | Redis connection URL for Celery broker and backend |
| `REMOVE_DB_ON_STARTUP` | Optional | `true` | Deletes and recreates the SQLite DB on every startup |
| `REMOVE_DB_ON_SHUTDOWN` | Optional | `true` | Deletes the SQLite DB on container shutdown |
| `WARP_PROXY` | Optional | `socks5://warp:1080` | SOCKS5 proxy used by yt-dlp to bypass YouTube IP bans |

---

## 🐳 Docker Compose Services

```yaml
services:
  redis:    # Message broker for Celery
  warp:     # Cloudflare WARP SOCKS5 proxy (NET_ADMIN cap required)
  web:      # FastAPI + static frontend server
  worker:   # Celery worker (Whisper + Gemini + external APIs)
```

---

## 🏗️ Project Structure

```
sdme/
├── main.py              # FastAPI app, API routes, lifespan handlers
├── worker.py            # Celery task: yt-dlp → Whisper → Gemini → Wikipedia
├── database.py          # SQLAlchemy async engine, session factory, DB cleanup
├── models.py            # SQLAlchemy ORM model (MediaAnalysis)
├── entrypoint.sh        # Container startup: launches Celery + Uvicorn
├── Dockerfile           # Multi-step Docker build
├── docker-compose.yml   # Full local stack (Redis, WARP, Web, Worker)
├── requirements.txt     # Python dependencies
├── out/                 # Next.js static export (served at /)
├── .env                 # ⚠️ Local secrets — never committed
└── cookies.txt          # ⚠️ Optional YouTube cookies — never committed
```

---

## 🛡️ Security Notes

- **API keys are never persisted.** The `X-Gemini-API-Key` header is read per-request from RAM and discarded immediately after the Celery task is dispatched.
- **Keys are masked in all server logs.** Only key length is printed for debug purposes.
- **`.env` and `cookies.txt` are gitignored** — they will never be accidentally committed.
- **CORS is open (`*`)** for development flexibility. For production, restrict `allow_origins` in `main.py` to your frontend domain.

---

## 📦 Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Next.js (Static Export), TypeScript, Vanilla CSS |
| **Backend** | FastAPI, Python 3.11, Uvicorn |
| **Task Queue** | Celery 5, Redis |
| **Database** | SQLite (async via aiosqlite + SQLAlchemy) |
| **Speech-to-Text** | OpenAI Whisper (`base` model, CPU) |
| **AI Analysis** | Google Gemini API (`google-genai`) |
| **Media Download** | yt-dlp + FFmpeg |
| **Proxy** | Cloudflare WARP (WireGuard SOCKS5) |
| **External APIs** | Wikipedia REST, arXiv Atom, OpenAlex |
| **Containerisation** | Docker, Docker Compose |

---

## 📄 License

MIT License — feel free to use, modify, and distribute.