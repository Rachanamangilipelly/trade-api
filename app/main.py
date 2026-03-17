"""
Trade Opportunities API - FastAPI Service
Analyzes market data and provides trade opportunity insights for Indian sectors.
"""

import asyncio
import hashlib
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import httpx
import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, validator

from app.config import settings
from app.models import (
    AnalysisResponse,
    AuthRequest,
    AuthResponse,
    RateLimitInfo,
    SessionInfo,
)
from app.services.analyzer import TradeAnalyzer
from app.services.data_collector import MarketDataCollector

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("trade_api")

# ── In-Memory Stores ───────────────────────────────────────────────────────────
sessions: dict[str, dict] = {}          # session_id → session data
rate_limits: dict[str, list] = defaultdict(list)   # session_id → [timestamps]
analysis_cache: dict[str, dict] = {}    # cache_key → {result, timestamp}

CACHE_TTL = 600          # 10 min cache
RATE_LIMIT_WINDOW = 60   # 1-minute window
RATE_LIMIT_MAX = 10      # requests per window

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="🇮🇳 India Trade Opportunities API",
    description="AI-powered market analysis for Indian trade sectors",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

security = HTTPBearer(auto_error=False)

# ── Services ───────────────────────────────────────────────────────────────────
collector = MarketDataCollector()
analyzer = TradeAnalyzer()


# ── Helpers ────────────────────────────────────────────────────────────────────
def create_token(session_id: str) -> str:
    payload = {
        "session_id": session_id,
        "exp": datetime.utcnow() + timedelta(hours=24),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload["session_id"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def check_rate_limit(session_id: str) -> RateLimitInfo:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    timestamps = rate_limits[session_id]
    rate_limits[session_id] = [t for t in timestamps if t > window_start]
    remaining = RATE_LIMIT_MAX - len(rate_limits[session_id])
    if remaining <= 0:
        reset_at = int(rate_limits[session_id][0] + RATE_LIMIT_WINDOW)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Resets at {datetime.fromtimestamp(reset_at).isoformat()}",
            headers={"Retry-After": str(reset_at - int(now))},
        )
    rate_limits[session_id].append(now)
    return RateLimitInfo(
        limit=RATE_LIMIT_MAX,
        remaining=remaining - 1,
        window_seconds=RATE_LIMIT_WINDOW,
        reset_at=int(window_start + RATE_LIMIT_WINDOW),
    )


def get_current_session(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    session_id = verify_token(credentials.credentials)
    if session_id not in sessions:
        raise HTTPException(status_code=401, detail="Session not found or expired")
    sessions[session_id]["last_active"] = datetime.utcnow().isoformat()
    return session_id


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/auth/guest", response_model=AuthResponse, tags=["Authentication"])
async def create_guest_session(request: Request):
    """Create a guest session and receive a JWT token."""
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "id": session_id,
        "type": "guest",
        "created_at": datetime.utcnow().isoformat(),
        "last_active": datetime.utcnow().isoformat(),
        "ip": request.client.host,
        "requests_made": 0,
    }
    token = create_token(session_id)
    logger.info(f"New guest session: {session_id[:8]}...")
    return AuthResponse(
        token=token,
        session_id=session_id,
        expires_in=86400,
        message="Guest session created. Token valid for 24 hours.",
    )


@app.post("/auth/login", response_model=AuthResponse, tags=["Authentication"])
async def login(body: AuthRequest, request: Request):
    """Login with API key for extended access."""
    if body.api_key != settings.MASTER_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "id": session_id,
        "type": "authenticated",
        "created_at": datetime.utcnow().isoformat(),
        "last_active": datetime.utcnow().isoformat(),
        "ip": request.client.host,
        "requests_made": 0,
    }
    token = create_token(session_id)
    logger.info(f"Authenticated session: {session_id[:8]}...")
    return AuthResponse(
        token=token,
        session_id=session_id,
        expires_in=86400,
        message="Authenticated session created.",
    )


@app.get(
    "/analyze/{sector}",
    response_model=AnalysisResponse,
    tags=["Analysis"],
    summary="Analyze trade opportunities for a sector",
)
async def analyze_sector(
    sector: str,
    session_id: str = Depends(get_current_session),
):
    """
    Analyze trade opportunities for a given Indian market sector.

    **sector**: Sector name (e.g., pharmaceuticals, technology, agriculture,
    textiles, automotive, chemicals, fintech, renewable-energy)

    Returns a structured markdown report with:
    - Market overview
    - Export/import opportunities
    - Key players
    - Regulatory landscape
    - Risk assessment
    - Actionable recommendations
    """
    # Validate sector name
    sector_clean = sector.strip().lower().replace("-", " ").replace("_", " ")
    if len(sector_clean) < 2 or len(sector_clean) > 60:
        raise HTTPException(status_code=422, detail="Sector name must be 2-60 characters")
    if not all(c.isalpha() or c.isspace() for c in sector_clean):
        raise HTTPException(status_code=422, detail="Sector name must contain only letters and spaces")

    # Rate limiting
    rate_info = check_rate_limit(session_id)

    # Cache check
    cache_key = hashlib.md5(sector_clean.encode()).hexdigest()
    if cache_key in analysis_cache:
        cached = analysis_cache[cache_key]
        if time.time() - cached["timestamp"] < CACHE_TTL:
            logger.info(f"Cache hit for sector: {sector_clean}")
            sessions[session_id]["requests_made"] = sessions[session_id].get("requests_made", 0) + 1
            return AnalysisResponse(
                sector=sector_clean,
                report=cached["report"],
                generated_at=cached["generated_at"],
                cached=True,
                rate_limit=rate_info,
                session_id=session_id,
            )

    logger.info(f"Analyzing sector: {sector_clean} | session: {session_id[:8]}...")

    # Collect market data
    try:
        market_data = await collector.collect(sector_clean)
    except Exception as e:
        logger.error(f"Data collection failed: {e}")
        market_data = {"sector": sector_clean, "articles": [], "error": str(e)}

    # AI analysis
    try:
        report = await analyzer.generate_report(sector_clean, market_data)
    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"AI analysis service unavailable: {str(e)}",
        )

    generated_at = datetime.utcnow().isoformat()
    analysis_cache[cache_key] = {
        "report": report,
        "timestamp": time.time(),
        "generated_at": generated_at,
    }
    sessions[session_id]["requests_made"] = sessions[session_id].get("requests_made", 0) + 1

    return AnalysisResponse(
        sector=sector_clean,
        report=report,
        generated_at=generated_at,
        cached=False,
        rate_limit=rate_info,
        session_id=session_id,
    )


@app.get("/session/info", tags=["Session"])
async def session_info(session_id: str = Depends(get_current_session)):
    """Get current session metadata and usage stats."""
    return SessionInfo(**sessions[session_id])


@app.delete("/session", tags=["Session"])
async def logout(session_id: str = Depends(get_current_session)):
    """Invalidate the current session."""
    sessions.pop(session_id, None)
    rate_limits.pop(session_id, None)
    return {"message": "Session terminated successfully"}


@app.get("/health", tags=["System"])
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "active_sessions": len(sessions),
        "cached_analyses": len(analysis_cache),
        "version": "1.0.0",
    }


@app.get("/sectors", tags=["System"])
async def list_sectors():
    """List supported Indian trade sectors."""
    return {
        "sectors": [
            {"id": "pharmaceuticals", "label": "Pharmaceuticals", "icon": "💊"},
            {"id": "technology", "label": "Technology & IT", "icon": "💻"},
            {"id": "agriculture", "label": "Agriculture", "icon": "🌾"},
            {"id": "textiles", "label": "Textiles & Apparel", "icon": "🧵"},
            {"id": "automotive", "label": "Automotive", "icon": "🚗"},
            {"id": "chemicals", "label": "Chemicals", "icon": "⚗️"},
            {"id": "fintech", "label": "Fintech", "icon": "💳"},
            {"id": "renewable-energy", "label": "Renewable Energy", "icon": "☀️"},
            {"id": "gems-jewellery", "label": "Gems & Jewellery", "icon": "💎"},
            {"id": "defence", "label": "Defence & Aerospace", "icon": "🛡️"},
        ]
    }
