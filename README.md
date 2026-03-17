# 🇮🇳 India Trade Opportunities API

> AI-powered FastAPI service that analyzes Indian market sectors and delivers structured trade opportunity reports — complete with authentication, rate limiting, caching, a web UI, Docker support, and a full test suite.

---

## ✨ Features

| Feature | Detail |
|---|---|
| **Core Endpoint** | `GET /analyze/{sector}` → full Markdown trade report |
| **AI Engine** | Google Gemini 1.5 Flash with structured prompt engineering |
| **Live Data** | DuckDuckGo search + curated sector intelligence |
| **Auth** | JWT guest sessions + API-key login (24h expiry) |
| **Rate Limiting** | 10 req/min per session — sliding window, in-memory |
| **Caching** | 10-minute response cache (per sector) |
| **Validation** | Pydantic schemas + regex input sanitisation |
| **Web UI** | India-themed interactive frontend at `/` |
| **API Docs** | Swagger UI `/docs` · ReDoc `/redoc` |
| **Docker** | Single-command deployment |
| **Tests** | 40+ pytest tests covering all layers |

---

## Project Structure

```
trade-api/
├── app/
│   ├── main.py                  # FastAPI app — routes, auth, rate limiting, caching
│   ├── config.py                # Env-based settings (.env support)
│   ├── models.py                # Pydantic request/response schemas
│   └── services/
│       ├── data_collector.py    # DuckDuckGo search + curated sector context
│       └── analyzer.py          # Gemini AI report generation + template fallback
├── templates/
│   └── index.html               # Interactive web UI (served at /)
├── static/                      # Static assets
├── tests/
│   └── test_api.py              # 40+ tests across 8 test classes
├── .env.example                 # Environment variable template
├── Dockerfile
├── docker-compose.yml
├── pytest.ini
├── requirements.txt
├── run.py
└── README.md
```

---

## Quick Start

### Option A — Local Python

```bash
# 1. Clone & enter
git clone <repo-url> && cd trade-api

# 2. Install
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env — set GEMINI_API_KEY (free: https://aistudio.google.com/app/apikey)

# 4. Run
python run.py
# Open http://localhost:8000
or python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Option B — Docker

```bash
cp .env.example .env   # edit GEMINI_API_KEY
docker-compose up --build
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | **Yes** (for AI) | `""` | Google Gemini API key |
| `SECRET_KEY` | Recommended | built-in | JWT signing secret |
| `MASTER_API_KEY` | Optional | `trade-master-key-2024` | Authenticated login key |

> Without `GEMINI_API_KEY` the API uses high-quality template reports. Set the key for AI-powered analysis.

---

## API Reference

### POST /auth/guest
```bash
curl -X POST http://localhost:8000/auth/guest
# → { "token": "eyJ...", "session_id": "uuid", "expires_in": 86400 }
```

### POST /auth/login
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"api_key": "trade-master-key-2024"}'
```

### GET /analyze/{sector}  ← Main Endpoint
```bash
TOKEN="eyJ..."
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/analyze/pharmaceuticals
```

Response:
```json
{
  "sector": "pharmaceuticals",
  "report": "# India Trade Opportunity Report...",
  "generated_at": "2024-01-15T10:30:00",
  "cached": false,
  "rate_limit": { "limit": 10, "remaining": 9, "window_seconds": 60 },
  "session_id": "uuid"
}
```

### Other Endpoints

| Path | Auth | Description |
|---|---|---|
| `GET /` | No | Web UI |
| `GET /sectors` | No | Pre-configured sectors list |
| `GET /health` | No | Health check |
| `GET /session/info` | Yes | Session metadata |
| `DELETE /session` | Yes | Logout |
| `GET /docs` | No | Swagger UI |

---

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v

# By class
pytest tests/ -v -k "TestAuthentication"
pytest tests/ -v -k "TestRateLimiting"
pytest tests/ -v -k "TestSecurity"
```

Test classes: `TestSystem`, `TestAuthentication`, `TestInputValidation`, `TestAnalysisEndpoint`, `TestRateLimiting`, `TestDataCollectorService`, `TestAnalyzerService`, `TestSecurity`, `TestEdgeCases`

---

## Data Flow

```
Request → JWT Auth → Rate Limit → Cache Check
    → Data Collection (DuckDuckGo + Static Context)
    → Gemini AI Analysis (or Template Fallback)
    → Cache Store → JSON Response
```

---

## Security

- JWT HS256 authentication with 24h expiry
- Per-session rate limiting (10 req/60s, sliding window)
- Input validation: letters + spaces only, 2-60 chars
- No stack traces exposed in error responses
- Non-root user in Docker container

---

## License
MIT
