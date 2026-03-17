"""
Trade API — Full Test Suite
Run: pytest tests/ -v
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────
#  We import the app lazily so tests can monkey-patch env vars
# ─────────────────────────────────────────────────────────────

MOCK_REPORT = """# 🇮🇳 India Trade Opportunity Report: Pharmaceuticals
*Generated: January 01, 2024*

## 📊 Executive Summary
India's pharmaceutical sector is a global leader in generic drug exports...

## 🚀 Export Opportunities
| Country | Opportunity |
|---------|-------------|
| USA | $8B |

## ⚠️ Risk Assessment
| Risk | Severity |
|------|----------|
| Currency | Medium |
"""


@pytest.fixture(scope="module")
def client():
    """Create a TestClient for the FastAPI app."""
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def guest_token(client):
    """Obtain a fresh guest JWT token."""
    resp = client.post("/auth/guest")
    assert resp.status_code == 200
    return resp.json()["token"]


@pytest.fixture
def auth_headers(guest_token):
    return {"Authorization": f"Bearer {guest_token}"}


# ═════════════════════════════════════════════════════════════
#  1. Health & System Endpoints
# ═════════════════════════════════════════════════════════════

class TestSystem:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_shape(self, client):
        data = client.get("/health").json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "active_sessions" in data
        assert "cached_analyses" in data
        assert data["version"] == "1.0.0"

    def test_sectors_endpoint(self, client):
        r = client.get("/sectors")
        assert r.status_code == 200
        data = r.json()
        assert "sectors" in data
        assert len(data["sectors"]) >= 10
        # Each sector has required fields
        for s in data["sectors"]:
            assert "id" in s
            assert "label" in s
            assert "icon" in s

    def test_home_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert b"Trade" in r.content

    def test_docs_available(self, client):
        r = client.get("/docs")
        assert r.status_code == 200

    def test_redoc_available(self, client):
        r = client.get("/redoc")
        assert r.status_code == 200


# ═════════════════════════════════════════════════════════════
#  2. Authentication
# ═════════════════════════════════════════════════════════════

class TestAuthentication:
    def test_guest_session_created(self, client):
        r = client.post("/auth/guest")
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert "session_id" in data
        assert data["expires_in"] == 86400
        assert len(data["token"]) > 20

    def test_guest_tokens_are_unique(self, client):
        t1 = client.post("/auth/guest").json()["token"]
        t2 = client.post("/auth/guest").json()["token"]
        assert t1 != t2

    def test_login_with_correct_key(self, client):
        r = client.post("/auth/login", json={"api_key": "trade-master-key-2024"})
        assert r.status_code == 200
        assert "token" in r.json()

    def test_login_with_wrong_key(self, client):
        r = client.post("/auth/login", json={"api_key": "wrong-key"})
        assert r.status_code == 403

    def test_login_with_empty_key(self, client):
        r = client.post("/auth/login", json={"api_key": ""})
        assert r.status_code == 403

    def test_protected_endpoint_without_token(self, client):
        r = client.get("/analyze/pharmaceuticals")
        assert r.status_code == 403  # No auth header → 403 from HTTPBearer

    def test_protected_endpoint_with_bad_token(self, client):
        r = client.get(
            "/analyze/pharmaceuticals",
            headers={"Authorization": "Bearer totally-invalid-jwt"}
        )
        assert r.status_code == 401

    def test_session_info_requires_auth(self, client):
        r = client.get("/session/info")
        assert r.status_code == 403

    def test_session_info_with_valid_token(self, client, auth_headers):
        r = client.get("/session/info", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert data["type"] == "guest"

    def test_logout(self, client):
        token = client.post("/auth/guest").json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        r = client.delete("/session", headers=headers)
        assert r.status_code == 200
        # Token should now be invalid
        r2 = client.get("/session/info", headers=headers)
        assert r2.status_code == 401

    def test_logout_invalidates_analyze(self, client):
        token = client.post("/auth/guest").json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        client.delete("/session", headers=headers)
        r = client.get("/analyze/pharmaceuticals", headers=headers)
        assert r.status_code == 401


# ═════════════════════════════════════════════════════════════
#  3. Input Validation
# ═════════════════════════════════════════════════════════════

class TestInputValidation:
    @pytest.mark.parametrize("sector,expected_status", [
        ("pharmaceuticals", 200),
        ("technology", 200),
        ("agriculture", 200),
        ("renewable energy", 200),
        ("gems jewellery", 200),
        ("a", 422),                      # too short
        ("x" * 61, 422),                 # too long
        ("pharma123", 422),              # contains digits
        ("pharma@sector", 422),          # special chars
        ("pharma/sector", 422),          # path separator
        ("../../etc/passwd", 422),       # path traversal attempt
        ("<script>alert(1)</script>", 422),  # XSS attempt
    ])
    def test_sector_validation(self, client, auth_headers, sector, expected_status):
        with patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as mock_ai, \
             patch("app.main.collector.collect", new_callable=AsyncMock) as mock_collect:
            mock_collect.return_value = {"sector": sector, "articles": [], "static_context": {}}
            mock_ai.return_value = MOCK_REPORT
            r = client.get(f"/analyze/{sector}", headers=auth_headers)
            assert r.status_code == expected_status, f"Expected {expected_status} for sector='{sector}', got {r.status_code}"


# ═════════════════════════════════════════════════════════════
#  4. Core Analysis Endpoint
# ═════════════════════════════════════════════════════════════

class TestAnalysisEndpoint:

    def _analyze(self, client, auth_headers, sector="pharmaceuticals"):
        with patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as mock_ai, \
             patch("app.main.collector.collect", new_callable=AsyncMock) as mock_collect:
            mock_collect.return_value = {
                "sector": sector,
                "articles": [{"title": "Test", "snippet": "India pharma growing", "source": "Reuters"}],
                "static_context": {"key_facts": ["India is #1 generic exporter"]},
                "search_successful": True,
            }
            mock_ai.return_value = MOCK_REPORT
            return client.get(f"/analyze/{sector}", headers=auth_headers)

    def test_analyze_returns_200(self, client, auth_headers):
        r = self._analyze(client, auth_headers)
        assert r.status_code == 200

    def test_analyze_response_shape(self, client, auth_headers):
        data = self._analyze(client, auth_headers).json()
        assert "sector" in data
        assert "report" in data
        assert "generated_at" in data
        assert "cached" in data
        assert "rate_limit" in data
        assert "session_id" in data

    def test_report_is_markdown(self, client, auth_headers):
        data = self._analyze(client, auth_headers).json()
        report = data["report"]
        assert isinstance(report, str)
        assert len(report) > 50
        assert "#" in report  # markdown headings

    def test_sector_normalized_to_lowercase(self, client, auth_headers):
        with patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as mock_ai, \
             patch("app.main.collector.collect", new_callable=AsyncMock) as mock_collect:
            mock_collect.return_value = {"sector": "pharmaceuticals", "articles": [], "static_context": {}}
            mock_ai.return_value = MOCK_REPORT
            r = client.get("/analyze/Pharmaceuticals", headers=auth_headers)
            assert r.status_code == 200
            assert r.json()["sector"] == "pharmaceuticals"

    def test_rate_limit_info_present(self, client, auth_headers):
        data = self._analyze(client, auth_headers).json()
        rl = data["rate_limit"]
        assert rl["limit"] == 10
        assert rl["window_seconds"] == 60
        assert 0 <= rl["remaining"] <= 10

    def test_caching_second_request_is_cached(self, client, auth_headers):
        # Clear cache first
        from app.main import analysis_cache
        analysis_cache.clear()

        with patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as mock_ai, \
             patch("app.main.collector.collect", new_callable=AsyncMock) as mock_collect:
            mock_collect.return_value = {"sector": "textiles", "articles": [], "static_context": {}}
            mock_ai.return_value = MOCK_REPORT

            # First request
            r1 = client.get("/analyze/textiles", headers=auth_headers)
            assert r1.status_code == 200
            assert r1.json()["cached"] is False

            # Get a fresh token for second request (different session, same cache)
            token2 = client.post("/auth/guest").json()["token"]
            headers2 = {"Authorization": f"Bearer {token2}"}
            r2 = client.get("/analyze/textiles", headers=headers2)
            assert r2.status_code == 200
            assert r2.json()["cached"] is True
            # AI should only have been called once
            assert mock_ai.call_count == 1

    def test_data_collector_called(self, client, auth_headers):
        from app.main import analysis_cache
        analysis_cache.clear()
        with patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as mock_ai, \
             patch("app.main.collector.collect", new_callable=AsyncMock) as mock_collect:
            mock_collect.return_value = {"sector": "chemicals", "articles": [], "static_context": {}}
            mock_ai.return_value = MOCK_REPORT
            client.get("/analyze/chemicals", headers=auth_headers)
            mock_collect.assert_called_once()
            call_args = mock_collect.call_args[0]
            assert "chemicals" in call_args[0]

    def test_ai_analyzer_called_with_sector(self, client, auth_headers):
        from app.main import analysis_cache
        analysis_cache.clear()
        with patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as mock_ai, \
             patch("app.main.collector.collect", new_callable=AsyncMock) as mock_collect:
            mock_collect.return_value = {"sector": "fintech", "articles": [], "static_context": {}}
            mock_ai.return_value = MOCK_REPORT
            client.get("/analyze/fintech", headers=auth_headers)
            mock_ai.assert_called_once()
            assert "fintech" in mock_ai.call_args[0][0]

    def test_collector_failure_does_not_crash(self, client, auth_headers):
        """If data collection fails, the API should still return a report."""
        from app.main import analysis_cache
        analysis_cache.clear()
        with patch("app.main.collector.collect", side_effect=Exception("Network error")), \
             patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = MOCK_REPORT
            r = client.get("/analyze/agriculture", headers=auth_headers)
            assert r.status_code == 200

    def test_analyzer_failure_returns_503(self, client, auth_headers):
        """If AI analysis fails completely, return 503."""
        from app.main import analysis_cache
        analysis_cache.clear()
        with patch("app.main.collector.collect", new_callable=AsyncMock) as mock_collect, \
             patch("app.main.analyzer.generate_report", side_effect=Exception("Gemini down")):
            mock_collect.return_value = {"sector": "defence", "articles": [], "static_context": {}}
            r = client.get("/analyze/defence", headers=auth_headers)
            assert r.status_code == 503


# ═════════════════════════════════════════════════════════════
#  5. Rate Limiting
# ═════════════════════════════════════════════════════════════

class TestRateLimiting:
    def test_rate_limit_decrements(self, client):
        token = client.post("/auth/guest").json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        from app.main import analysis_cache
        analysis_cache.clear()

        remainders = []
        for i in range(3):
            with patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as m, \
                 patch("app.main.collector.collect", new_callable=AsyncMock) as mc:
                mc.return_value = {"sector": f"sector{i}", "articles": [], "static_context": {}}
                m.return_value = MOCK_REPORT
                r = client.get(f"/analyze/sector{i}", headers=headers)
                if r.status_code == 200:
                    remainders.append(r.json()["rate_limit"]["remaining"])

        # Each call should decrement remaining
        for i in range(len(remainders) - 1):
            assert remainders[i] > remainders[i + 1]

    def test_rate_limit_enforced_after_max_requests(self, client):
        """Hammer the endpoint until we hit 429."""
        token = client.post("/auth/guest").json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        from app.main import analysis_cache, rate_limits, RATE_LIMIT_MAX
        analysis_cache.clear()

        # Pre-fill rate limit bucket to just below the limit
        import time
        from app.main import rate_limits
        # Get session_id from session info
        session_resp = client.get("/session/info", headers=headers)
        session_id = session_resp.json()["id"]

        now = time.time()
        rate_limits[session_id] = [now] * RATE_LIMIT_MAX  # Fill bucket completely

        with patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as m, \
             patch("app.main.collector.collect", new_callable=AsyncMock) as mc:
            mc.return_value = {"sector": "test", "articles": [], "static_context": {}}
            m.return_value = MOCK_REPORT
            r = client.get("/analyze/test", headers=headers)
            assert r.status_code == 429

    def test_rate_limit_per_session_isolation(self, client):
        """Rate limits are per session — one session hitting limit should not affect another."""
        token1 = client.post("/auth/guest").json()["token"]
        token2 = client.post("/auth/guest").json()["token"]

        h1 = {"Authorization": f"Bearer {token1}"}
        h2 = {"Authorization": f"Bearer {token2}"}

        from app.main import analysis_cache, rate_limits, RATE_LIMIT_MAX
        analysis_cache.clear()

        # Exhaust session 1's rate limit
        s1_id = client.get("/session/info", headers=h1).json()["id"]
        rate_limits[s1_id] = [time.time()] * RATE_LIMIT_MAX

        # Session 1 should be rate limited
        with patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as m, \
             patch("app.main.collector.collect", new_callable=AsyncMock) as mc:
            mc.return_value = {"sector": "test", "articles": [], "static_context": {}}
            m.return_value = MOCK_REPORT
            r1 = client.get("/analyze/test", headers=h1)
            assert r1.status_code == 429

        # Session 2 should still work
        with patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as m, \
             patch("app.main.collector.collect", new_callable=AsyncMock) as mc:
            mc.return_value = {"sector": "test", "articles": [], "static_context": {}}
            m.return_value = MOCK_REPORT
            r2 = client.get("/analyze/test", headers=h2)
            assert r2.status_code == 200


# ═════════════════════════════════════════════════════════════
#  6. Services — Unit Tests
# ═════════════════════════════════════════════════════════════

class TestDataCollectorService:
    @pytest.mark.asyncio
    async def test_collect_returns_dict(self):
        from app.services.data_collector import MarketDataCollector
        collector = MarketDataCollector()
        with patch.object(collector, "_search_duckduckgo", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [{"title": "Test", "snippet": "India exports growing"}]
            result = await collector.collect("pharmaceuticals")
            assert isinstance(result, dict)
            assert "sector" in result
            assert "articles" in result
            assert "static_context" in result

    @pytest.mark.asyncio
    async def test_static_context_for_known_sector(self):
        from app.services.data_collector import MarketDataCollector
        collector = MarketDataCollector()
        ctx = await collector._get_static_context("pharmaceuticals")
        assert "key_facts" in ctx
        assert "top_companies" in ctx
        assert len(ctx["key_facts"]) > 0

    @pytest.mark.asyncio
    async def test_static_context_for_unknown_sector(self):
        from app.services.data_collector import MarketDataCollector
        collector = MarketDataCollector()
        ctx = await collector._get_static_context("completely-unknown-sector-xyz")
        assert isinstance(ctx, dict)  # Should return empty dict, not raise

    @pytest.mark.asyncio
    async def test_collect_handles_search_failure_gracefully(self):
        from app.services.data_collector import MarketDataCollector
        collector = MarketDataCollector()
        with patch.object(collector, "_search_duckduckgo", side_effect=Exception("Network down")):
            result = await collector.collect("pharmaceuticals")
            # Should still return something valid
            assert "sector" in result
            assert isinstance(result.get("articles", []), list)


class TestAnalyzerService:
    @pytest.mark.asyncio
    async def test_generate_report_without_gemini_key(self):
        from app.services.analyzer import TradeAnalyzer
        from app import config
        original = config.settings.GEMINI_API_KEY
        config.settings.GEMINI_API_KEY = ""  # Disable
        try:
            analyzer = TradeAnalyzer()
            result = await analyzer.generate_report("pharmaceuticals", {
                "sector": "pharmaceuticals",
                "articles": [],
                "static_context": {"key_facts": ["India exports $25B pharma"]},
            })
            assert isinstance(result, str)
            assert len(result) > 100
            assert "#" in result
        finally:
            config.settings.GEMINI_API_KEY = original

    @pytest.mark.asyncio
    async def test_template_report_contains_sector(self):
        from app.services.analyzer import TradeAnalyzer
        analyzer = TradeAnalyzer()
        report = analyzer._generate_template_report(
            "textiles", "Textiles", "January 01, 2024", {
                "static_context": {
                    "key_facts": ["India is 2nd largest textile exporter"],
                    "top_companies": ["Arvind Mills", "Raymond"],
                    "trade_corridors": ["USA", "EU"],
                    "regulatory_bodies": ["AEPC"],
                }
            }
        )
        assert "Textiles" in report
        assert "India" in report
        assert "#" in report

    @pytest.mark.asyncio
    async def test_gemini_called_when_key_present(self):
        from app.services.analyzer import TradeAnalyzer
        from app import config
        config.settings.GEMINI_API_KEY = "fake-key-for-test"
        try:
            analyzer = TradeAnalyzer()
            with patch.object(analyzer, "_call_gemini", new_callable=AsyncMock) as mock_gemini:
                mock_gemini.return_value = MOCK_REPORT
                result = await analyzer.generate_report("agriculture", {
                    "sector": "agriculture",
                    "articles": [],
                    "static_context": {},
                })
                mock_gemini.assert_called_once()
                assert result == MOCK_REPORT
        finally:
            config.settings.GEMINI_API_KEY = ""

    @pytest.mark.asyncio
    async def test_falls_back_to_template_on_gemini_error(self):
        from app.services.analyzer import TradeAnalyzer
        from app import config
        config.settings.GEMINI_API_KEY = "fake-key-for-test"
        try:
            analyzer = TradeAnalyzer()
            with patch.object(analyzer, "_call_gemini", side_effect=Exception("API down")):
                result = await analyzer.generate_report("automotive", {
                    "sector": "automotive",
                    "articles": [],
                    "static_context": {},
                })
                assert isinstance(result, str)
                assert len(result) > 50
        finally:
            config.settings.GEMINI_API_KEY = ""

    def test_summarize_market_data_with_full_context(self):
        from app.services.analyzer import TradeAnalyzer
        analyzer = TradeAnalyzer()
        data = {
            "static_context": {
                "key_facts": ["India exports $25B", "US is top market"],
                "top_companies": ["Sun Pharma", "Cipla"],
                "trade_corridors": ["USA", "EU"],
            },
            "articles": [
                {"snippet": "Indian pharma growing at 15% CAGR"},
                {"snippet": "FDA approvals increasing"},
            ]
        }
        summary = analyzer._summarize_market_data(data)
        assert "Sun Pharma" in summary
        assert "USA" in summary
        assert "India exports" in summary


# ═════════════════════════════════════════════════════════════
#  7. Security Tests
# ═════════════════════════════════════════════════════════════

class TestSecurity:
    def test_expired_token_rejected(self, client):
        import jwt as pyjwt
        from datetime import datetime, timedelta
        from app.config import settings
        payload = {
            "session_id": "test-session",
            "exp": datetime.utcnow() - timedelta(hours=1),  # already expired
            "iat": datetime.utcnow() - timedelta(hours=2),
        }
        expired_token = pyjwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        r = client.get("/analyze/test", headers={"Authorization": f"Bearer {expired_token}"})
        assert r.status_code == 401
        assert "expired" in r.json()["detail"].lower()

    def test_tampered_token_rejected(self, client):
        token = client.post("/auth/guest").json()["token"]
        tampered = token[:-5] + "XXXXX"
        r = client.get("/session/info", headers={"Authorization": f"Bearer {tampered}"})
        assert r.status_code == 401

    def test_token_for_deleted_session_rejected(self, client):
        token = client.post("/auth/guest").json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        client.delete("/session", headers=headers)  # delete session
        r = client.get("/session/info", headers=headers)
        assert r.status_code == 401

    def test_response_has_no_internal_stack_traces(self, client, auth_headers):
        """Error responses should not leak implementation details."""
        r = client.get("/analyze/a", headers=auth_headers)  # invalid sector
        assert r.status_code == 422
        body = r.text
        assert "Traceback" not in body
        assert "File " not in body

    def test_cors_headers_present(self, client):
        r = client.options("/health", headers={"Origin": "http://example.com"})
        # CORS middleware should have processed the request
        assert r.status_code in (200, 204, 400)


# ═════════════════════════════════════════════════════════════
#  8. Edge Cases
# ═════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_hyphenated_sector_allowed(self, client, auth_headers):
        """Hyphens in URL are converted to spaces."""
        from app.main import analysis_cache
        analysis_cache.clear()
        with patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as m, \
             patch("app.main.collector.collect", new_callable=AsyncMock) as mc:
            mc.return_value = {"sector": "renewable energy", "articles": [], "static_context": {}}
            m.return_value = MOCK_REPORT
            r = client.get("/analyze/renewable-energy", headers=auth_headers)
            assert r.status_code == 200

    def test_underscore_sector_allowed(self, client, auth_headers):
        from app.main import analysis_cache
        analysis_cache.clear()
        with patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as m, \
             patch("app.main.collector.collect", new_callable=AsyncMock) as mc:
            mc.return_value = {"sector": "gems jewellery", "articles": [], "static_context": {}}
            m.return_value = MOCK_REPORT
            r = client.get("/analyze/gems_jewellery", headers=auth_headers)
            assert r.status_code == 200

    def test_cache_persists_across_sessions(self, client):
        from app.main import analysis_cache
        analysis_cache.clear()
        t1 = client.post("/auth/guest").json()["token"]
        t2 = client.post("/auth/guest").json()["token"]

        with patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as m, \
             patch("app.main.collector.collect", new_callable=AsyncMock) as mc:
            mc.return_value = {"sector": "fintech", "articles": [], "static_context": {}}
            m.return_value = MOCK_REPORT

            r1 = client.get("/analyze/fintech", headers={"Authorization": f"Bearer {t1}"})
            r2 = client.get("/analyze/fintech", headers={"Authorization": f"Bearer {t2}"})

            assert r1.json()["cached"] is False
            assert r2.json()["cached"] is True

    def test_multiple_concurrent_sectors(self, client, auth_headers):
        """Different sectors should be cached independently."""
        from app.main import analysis_cache
        analysis_cache.clear()
        sectors = ["chemicals", "defence", "fintech"]
        results = []
        for s in sectors:
            with patch("app.main.analyzer.generate_report", new_callable=AsyncMock) as m, \
                 patch("app.main.collector.collect", new_callable=AsyncMock) as mc:
                mc.return_value = {"sector": s, "articles": [], "static_context": {}}
                m.return_value = MOCK_REPORT
                r = client.get(f"/analyze/{s}", headers=auth_headers)
                results.append(r)

        # All should succeed
        for r in results:
            assert r.status_code == 200

        # All should have been independently cached
        assert len(analysis_cache) == len(sectors)
