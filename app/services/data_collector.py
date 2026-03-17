"""
Market Data Collector — fetches news and market data for a given sector.
Uses DuckDuckGo Search API (free, no key required) with optional Serper fallback.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("trade_api.collector")

# Curated static context per sector (fallback when search is unavailable)
SECTOR_CONTEXT = {
    "pharmaceuticals": {
        "key_facts": [
            "India is the world's largest generic drug exporter (20% global supply)",
            "Pharma exports worth $25 billion in FY2023",
            "Key export markets: USA (31%), UK, South Africa, Russia",
            "PLI scheme boosting API manufacturing with ₹15,000 crore incentive",
            "USFDA approvals growing — India has most USFDA-approved plants outside US",
        ],
        "top_companies": ["Sun Pharma", "Cipla", "Dr. Reddy's", "Lupin", "Aurobindo"],
        "regulatory_bodies": ["CDSCO", "USFDA", "EMA", "WHO-GMP"],
        "trade_corridors": ["US", "EU", "Africa", "Southeast Asia", "Russia"],
    },
    "technology": {
        "key_facts": [
            "IT-BPM industry revenue: $245 billion in FY2024",
            "India exports 60% of world's offshore IT services",
            "Bangalore, Hyderabad, Pune are major tech hubs",
            "Digital India initiative driving domestic demand",
            "Growing SaaS and AI/ML startup ecosystem",
        ],
        "top_companies": ["TCS", "Infosys", "Wipro", "HCL Tech", "Tech Mahindra"],
        "regulatory_bodies": ["MeitY", "NASSCOM", "CERT-In"],
        "trade_corridors": ["USA", "UK", "Europe", "Australia", "Middle East"],
    },
    "agriculture": {
        "key_facts": [
            "India is the 2nd largest agricultural producer globally",
            "Agri exports reached $53 billion in FY2023",
            "Top exports: Rice, Spices, Marine products, Cotton",
            "PM-KISAN and FPO schemes supporting farmers",
            "Organic farming growing at 25% YoY",
        ],
        "top_companies": ["ITC", "Adani Agri", "Godrej Agrovet", "UPL", "Kaveri Seeds"],
        "regulatory_bodies": ["APEDA", "FSSAI", "SFAC", "NABARD"],
        "trade_corridors": ["Middle East", "USA", "EU", "Bangladesh", "China"],
    },
    "textiles": {
        "key_facts": [
            "India is 2nd largest textile exporter globally",
            "Textile exports: $44 billion in FY2023",
            "PLI scheme for technical textiles with ₹10,683 crore outlay",
            "India has competitive advantage in cotton (2nd largest producer)",
            "Growing demand for sustainable/eco-friendly textiles",
        ],
        "top_companies": ["Arvind Mills", "Raymond", "Welspun", "Vardhman", "Trident"],
        "regulatory_bodies": ["AEPC", "TEXPROCIL", "Ministry of Textiles"],
        "trade_corridors": ["USA", "EU", "UK", "UAE", "Bangladesh"],
    },
    "automotive": {
        "key_facts": [
            "India is 3rd largest automobile market globally",
            "Auto exports: $21.2 billion in FY2023",
            "EV adoption growing — Govt targeting 30% EV by 2030",
            "PLI for auto sector: ₹25,938 crore incentive",
            "India emerging as global auto component hub",
        ],
        "top_companies": ["Tata Motors", "Maruti Suzuki", "Mahindra", "Bajaj Auto", "Hero MotoCorp"],
        "regulatory_bodies": ["SIAM", "ACMA", "BIS", "MoRTH"],
        "trade_corridors": ["USA", "EU", "Africa", "Mexico", "ASEAN"],
    },
    "renewable energy": {
        "key_facts": [
            "India targets 500 GW renewable capacity by 2030",
            "Solar capacity at 73 GW as of 2024 (4th globally)",
            "₹19,500 crore PLI for solar PV manufacturing",
            "Green hydrogen mission: $2.3 billion investment",
            "Wind energy capacity: 44 GW (4th largest globally)",
        ],
        "top_companies": ["Adani Green", "Tata Power", "ReNew Power", "NTPC Renewable", "Greenko"],
        "regulatory_bodies": ["MNRE", "SECI", "CERC", "BEE"],
        "trade_corridors": ["EU", "USA", "Middle East", "ASEAN", "Africa"],
    },
}


class MarketDataCollector:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)

    async def collect(self, sector: str) -> dict[str, Any]:
        """Collect market data for a sector from multiple sources."""
        logger.info(f"Collecting data for: {sector}")

        tasks = [
            self._search_duckduckgo(f"India {sector} trade export opportunities 2024"),
            self._search_duckduckgo(f"India {sector} market growth challenges 2024"),
            self._get_static_context(sector),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        articles = []
        for r in results[:2]:
            if isinstance(r, list):
                articles.extend(r)

        static_ctx = results[2] if not isinstance(results[2], Exception) else {}

        return {
            "sector": sector,
            "collected_at": datetime.utcnow().isoformat(),
            "articles": articles[:12],
            "static_context": static_ctx,
            "search_successful": len(articles) > 0,
        }

    async def _search_duckduckgo(self, query: str) -> list[dict]:
        """Search using DuckDuckGo instant answer API."""
        try:
            url = "https://api.duckduckgo.com/"
            params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            articles = []

            # Abstract
            if data.get("Abstract"):
                articles.append({
                    "title": data.get("Heading", query),
                    "snippet": data["Abstract"],
                    "source": data.get("AbstractSource", "DuckDuckGo"),
                    "url": data.get("AbstractURL", ""),
                })

            # Related topics
            for topic in data.get("RelatedTopics", [])[:6]:
                if isinstance(topic, dict) and topic.get("Text"):
                    articles.append({
                        "title": topic.get("Text", "")[:80],
                        "snippet": topic.get("Text", ""),
                        "source": "DuckDuckGo",
                        "url": topic.get("FirstURL", ""),
                    })

            logger.info(f"DuckDuckGo returned {len(articles)} results for: {query[:50]}")
            return articles

        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")
            return []

    async def _get_static_context(self, sector: str) -> dict:
        """Return curated static sector context."""
        # Try exact match first, then partial match
        ctx = SECTOR_CONTEXT.get(sector, {})
        if not ctx:
            for key in SECTOR_CONTEXT:
                if key in sector or sector in key:
                    ctx = SECTOR_CONTEXT[key]
                    break
        return ctx

    async def close(self):
        await self.client.aclose()
