"""
Trade Analyzer — uses Google Gemini API to generate structured market reports.
Falls back to a structured template if the API key is not configured.
"""

import json
import logging
from datetime import datetime
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("trade_api.analyzer")

REPORT_PROMPT = """You are a senior trade analyst specializing in Indian export and import markets. 
Generate a comprehensive, data-rich trade opportunity report for the "{sector}" sector in India.

Use the following collected market data as context:
{market_data}

Produce a detailed markdown report with EXACTLY this structure:

# 🇮🇳 India Trade Opportunity Report: {sector_title}
*Generated: {date} | Source: AI-Powered Market Intelligence*

---

## 📊 Executive Summary
[3-4 sentence overview of the sector's current trade standing and top 2-3 opportunities]

---

## 🌍 Market Overview
### Current Market Size & Growth
[Market size, CAGR, key growth drivers]

### India's Position
[India's global rank, market share, competitive advantages]

---

## 🚀 Export Opportunities

### Top Export Destinations
| Country | Opportunity Size | Growth Rate | Key Products |
|---------|-----------------|-------------|--------------|
[5 rows with real/estimated data]

### High-Potential Product Categories
1. **[Category 1]** — [Description, $ opportunity, growth driver]
2. **[Category 2]** — [Description, $ opportunity, growth driver]
3. **[Category 3]** — [Description, $ opportunity, growth driver]

---

## 📥 Import Opportunities & Dependencies

### Critical Imports
[What India imports in this sector, from where, and strategic implications]

### Import Substitution Opportunities
[Areas where India can reduce import dependency]

---

## 🏭 Key Industry Players

### Domestic Leaders
[Top 5 Indian companies with brief notes on their trade activities]

### Global Partners & Competitors
[Key international players, FDI trends, joint ventures]

---

## ⚖️ Regulatory Landscape

### Favorable Policies
- [Policy 1 with details]
- [Policy 2 with details]
- [Policy 3 with details]

### Government Schemes & Incentives
[PLI, export incentives, SEZs, tax benefits relevant to this sector]

---

## 📈 Market Trends & Drivers

1. **[Trend 1]** — [Explanation and trade impact]
2. **[Trend 2]** — [Explanation and trade impact]
3. **[Trend 3]** — [Explanation and trade impact]

---

## ⚠️ Risk Assessment

| Risk | Severity | Mitigation Strategy |
|------|----------|---------------------|
[5 rows]

---

## 💡 Strategic Recommendations

### Immediate Actions (0-6 months)
1. [Specific actionable recommendation]
2. [Specific actionable recommendation]
3. [Specific actionable recommendation]

### Medium-Term Strategy (6-18 months)
1. [Recommendation]
2. [Recommendation]

### Long-Term Vision (18+ months)
[2-3 sentences on long-term positioning]

---

## 📌 Key Contacts & Resources
- **Ministry/Regulator:** [Name + website]
- **Export Promotion Council:** [Name + website]
- **Trade Association:** [Name + website]

---

*Report Confidence: High | Data Freshness: Current | Analysis by: Gemini AI*

Be specific with numbers, percentages, and dollar/rupee figures."""


class TradeAnalyzer:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=60.0)
        self.gemini_url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent"
        )

    async def generate_report(self, sector: str, market_data: dict[str, Any]) -> str:
        sector_title = sector.title()
        date = datetime.utcnow().strftime("%B %d, %Y")
        data_summary = self._summarize_market_data(market_data)

        prompt = REPORT_PROMPT.format(
            sector=sector,
            sector_title=sector_title,
            date=date,
            market_data=data_summary,
        )

        if settings.GEMINI_API_KEY:
            try:
                report = await self._call_gemini(prompt)
                logger.info(f"Gemini report generated for: {sector}")
                return report
            except Exception as e:
                logger.error(f"Gemini API error: {e}")

        logger.warning(f"Using template fallback for: {sector} (no Gemini key or API error)")
        return self._generate_template_report(sector, sector_title, date, market_data)

    async def _call_gemini(self, prompt: str) -> str:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 4096,
                "topK": 40,
                "topP": 0.95,
            },
        }
        resp = await self.client.post(
            f"{self.gemini_url}?key={settings.GEMINI_API_KEY}",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise ValueError(f"Unexpected Gemini response structure: {e}")

    def _summarize_market_data(self, data: dict) -> str:
        lines = []
        ctx = data.get("static_context", {})

        if ctx.get("key_facts"):
            lines.append("KEY FACTS:")
            for f in ctx["key_facts"]:
                lines.append(f"  - {f}")

        if ctx.get("top_companies"):
            lines.append(f"TOP COMPANIES: {', '.join(ctx['top_companies'])}")

        if ctx.get("trade_corridors"):
            lines.append(f"TRADE CORRIDORS: {', '.join(ctx['trade_corridors'])}")

        articles = data.get("articles", [])
        if articles:
            lines.append("\nRECENT NEWS/DATA:")
            for a in articles[:6]:
                if a.get("snippet"):
                    lines.append(f"  • {a['snippet'][:200]}")

        return "\n".join(lines) or f"General analysis for India's {data.get('sector')} sector."

    def _generate_template_report(
        self, sector: str, sector_title: str, date: str, market_data: dict
    ) -> str:
        ctx = market_data.get("static_context", {})
        facts = ctx.get("key_facts", [f"India is a major player in the {sector} sector"])
        companies = ctx.get("top_companies", ["Various leading companies"])
        corridors = ctx.get("trade_corridors", ["USA", "EU", "Asia"])

        facts_md = "\n".join(f"- {f}" for f in facts)
        companies_md = ", ".join(f"**{c}**" for c in companies)
        corridors_str = ", ".join(corridors)

        return f"""# 🇮🇳 India Trade Opportunity Report: {sector_title}
*Generated: {date} | Source: Market Intelligence Engine*

---

## 📊 Executive Summary

India's **{sector_title}** sector represents a significant and growing trade opportunity. With strong government support through PLI schemes and export promotion councils, this sector is poised for robust growth. Key opportunities exist in exports to {corridors_str}.

---

## 🌍 Market Overview

### Key Facts
{facts_md}

### India's Competitive Advantages
- Large, skilled workforce at competitive costs
- Established supply chain infrastructure
- Strong domestic demand as a launchpad
- Government policy support and incentives

---

## 🚀 Export Opportunities

### Top Export Destinations
| Country | Opportunity | Growth Trend | Notes |
|---------|-------------|--------------|-------|
| USA | High | ↑ Growing | Largest market |
| EU | High | ↑ Growing | Sustainability focus |
| UAE | Medium | ↑ Growing | Middle East gateway |
| ASEAN | Medium | ↑↑ Fast | Proximity advantage |
| Africa | Emerging | ↑↑ High | Untapped potential |

---

## 🏭 Key Industry Players

### Domestic Leaders
{companies_md}

---

## ⚖️ Regulatory Landscape

### Government Schemes
- **PLI Scheme**: Production Linked Incentives
- **DPIIT Initiatives**: Ease of doing business
- **Export Promotion Councils**: Dedicated exporter support

---

## ⚠️ Risk Assessment

| Risk | Severity | Mitigation Strategy |
|------|----------|---------------------|
| Currency Fluctuation | Medium | Forward contracts |
| Geopolitical Tensions | Medium | Diversify markets |
| Regulatory Changes | Low | Engage trade bodies |
| Supply Chain Disruption | Medium | Multi-source inputs |
| Global Demand Slowdown | Medium | Focus on essentials |

---

## 💡 Strategic Recommendations

### Immediate Actions (0-6 months)
1. Register with the Export Promotion Council
2. Apply for PLI scheme benefits
3. Conduct compliance audit for target markets

### Medium-Term Strategy (6-18 months)
1. Build international certifications
2. Establish partnerships in {corridors_str}

### Long-Term Vision (18+ months)
Position as a premium, reliable supplier in global value chains. Invest in R&D and branding to move up from commodity to branded products.

---

## 📌 Key Contacts & Resources
- **Ministry:** Ministry of Commerce & Industry — commerce.gov.in
- **Export Body:** FIEO — fieo.org
- **Data:** DGFT — dgft.gov.in

---

*⚙️ Configure GEMINI_API_KEY for AI-powered analysis | Template Version*
"""

    async def close(self):
        await self.client.aclose()
