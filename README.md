# 🔍 ClueZero

**Background Screenshot → AI Processing System**

A headless desktop agent that captures screenshots via global hotkey, sends them to a scalable backend for AI analysis, and copies the result to your clipboard — all within 60–120 seconds.

---

## Architecture

```
Client (Desktop Agent)          Backend (Docker)
┌──────────────────┐            ┌──────────────────────────────────┐
│  Hotkey Listener │            │  ┌──────────┐    ┌───────────┐  │
│  Screenshot (mss)│──POST───→  │  │ FastAPI  │───→│   Redis   │  │
│  Image Compress  │  /submit   │  │  API     │    │   Queue   │  │
│                  │            │  └──────────┘    └─────┬─────┘  │
│  WebSocket/Poll  │←─result──  │                       │         │
│  Clipboard Copy  │            │  ┌──────────┐    ┌────▼────┐    │
└──────────────────┘            │  │  Result   │←──│ Workers │    │
                                │  │  Store    │   │ (LLM)   │    │
                                │  └──────────┘   └─────────┘    │
                                └──────────────────────────────────┘
```

---

## Quick Start

### 1. Clone & Configure

```bash
cp .env.example .env
# Edit .env — set your LLM_PROVIDER and API key
```

### 2. Start Backend (Docker)

```bash
cd backend
docker-compose up --build
# Starts: Redis + FastAPI (port 8000) + 3 RQ workers

# Scale workers as needed:
docker-compose up --scale worker=10
```

### 3. Run Client Agent

```bash
cd client
pip install -r requirements.txt
python agent.py
# Press Ctrl+Shift+O to capture & process
```

---

## Configuration

All settings live in `.env` (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai` or `gemini` |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `RATE_LIMIT_SECONDS` | `15` | Min interval between requests per user |
| `IMAGE_MAX_RESOLUTION` | `720` | Max image dimension (px) |
| `IMAGE_QUALITY` | `65` | JPEG compression quality |
| `HOTKEY` | `ctrl+shift+o` | Global hotkey trigger |
| `CLIENT_TIMEOUT` | `120` | Max wait for result (seconds) |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/submit` | Submit screenshot for processing |
| `GET` | `/result/{job_id}` | Poll for job result |
| `WS` | `/ws/{job_id}` | WebSocket real-time result |
| `GET` | `/health` | Liveness check |

---

## Running Tests

```bash
cd backend
pip install -r requirements.txt
pip install pytest httpx
python -m pytest tests/ -v
```

---

## Project Structure

```
ClueZero/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app
│   │   ├── config.py        # Settings
│   │   ├── models.py        # Pydantic models
│   │   ├── routes/          # API endpoints
│   │   ├── queue/           # RQ worker tasks
│   │   ├── services/        # LLM, image, dedup
│   │   └── middleware/      # Rate limiting
│   ├── tests/               # Pytest test suite
│   ├── Dockerfile
│   └── docker-compose.yml
├── client/
│   ├── agent.py             # Main entry point
│   ├── capture.py           # Screenshot capture
│   ├── hotkey.py            # Global hotkey listener
│   ├── api_client.py        # HTTP + WebSocket client
│   └── clipboard.py         # Clipboard + notifications
└── .env.example
```
