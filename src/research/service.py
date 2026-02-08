"""
Deep Research Service - Implements comprehensive research analysis.

Uses LLM for:
- Sector analysis
- Thematic insights
- Macro outlook
- Company deep dives

This is a weekly/on-demand service due to cost and depth.
"""
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from src.llm import get_llm_client_for_model, LLMClient
from src.config import config
from .models import (
    ResearchReport,
    SectorAnalysis,
    ThematicInsight,
    MacroOutlook,
    CompanyDeepDive,
)
from .prompts import (
    RESEARCH_SYSTEM_PROMPT,
    build_sector_analysis_prompt,
    build_thematic_analysis_prompt,
    build_macro_outlook_prompt,
    build_company_deep_dive_prompt,
    PROMPT_VERSION,
)


logger = logging.getLogger(__name__)


class DeepResearchService:
    """
    Service for conducting deep research analysis.

    Uses Gemini Pro or Deep Research model for comprehensive analysis.
    """

    # Common sectors for analysis
    SECTORS = [
        "Technology",
        "Healthcare",
        "Financials",
        "Consumer Discretionary",
        "Industrials",
        "Energy",
        "Materials",
        "Utilities",
        "Real Estate",
        "Communication Services",
        "Consumer Staples",
    ]

    # Common themes
    THEMES = [
        "AI Infrastructure",
        "Interest Rate Sensitivity",
        "Reshoring/Supply Chain",
        "Clean Energy Transition",
        "Digital Transformation",
        "Healthcare Innovation",
        "Consumer Spending Trends",
    ]

    def __init__(self, llm_client: LLMClient | None = None):
        """
        Initialize the research service.

        Args:
            llm_client: Optional LLM client
        """
        self.model_name = config.llm.deep_research_model
        self.llm_client = llm_client or get_llm_client_for_model(self.model_name)

    def run_deep_research_query(
        self,
        query: str,
    ) -> str:
        """
        Run a deep research query.

        Args:
            query: The research query

        Returns:
            Research report as text
        """
        logger.info(f"Running Deep Research query: {query[:100]}...")

        prompt = f"""Conduct comprehensive research on the following topic:

{query}

Provide a detailed, well-structured report with:
1. Executive summary
2. Key findings
3. Supporting evidence
4. Implications
5. Recommendations

Be thorough and cite specific data points where possible."""

        response = self.llm_client.generate(
            prompt=prompt,
            model=self.model_name,
        )
        return response.content

    def run_weekly_research(
        self,
        market_context: dict,
        focus_sectors: list[str] | None = None,
        focus_themes: list[str] | None = None,
    ) -> ResearchReport:
        """
        Run comprehensive weekly research.

        Args:
            market_context: Current market context
            focus_sectors: Specific sectors to analyze (optional)
            focus_themes: Specific themes to analyze (optional)

        Returns:
            ResearchReport with complete analysis
        """
        logger.info("Starting weekly deep research")
        start_time = time.time()

        report_id = str(uuid.uuid4())[:8]
        sectors = focus_sectors or self.SECTORS[:5]  # Limit to top 5 for cost
        themes = focus_themes or self.THEMES[:3]  # Limit to top 3

        # Analyze sectors
        sector_analyses = []
        for sector in sectors:
            try:
                analysis = self.analyze_sector(sector, market_context)
                sector_analyses.append(analysis)
            except Exception as e:
                logger.error(f"Failed to analyze sector {sector}: {e}")

        # Analyze themes
        thematic_insights = []
        for theme in themes:
            try:
                insight = self.analyze_theme(theme)
                thematic_insights.append(insight)
            except Exception as e:
                logger.error(f"Failed to analyze theme {theme}: {e}")

        # Macro outlook
        macro_outlook = None
        try:
            macro_outlook = self.analyze_macro(market_context)
        except Exception as e:
            logger.error(f"Failed to analyze macro: {e}")

        # Build executive summary
        executive_summary = self._build_executive_summary(
            sector_analyses, thematic_insights, macro_outlook
        )

        # Extract actionable insights
        actionable_insights = self._extract_actionable_insights(
            sector_analyses, thematic_insights, macro_outlook
        )

        # Collect stocks to watch/avoid
        stocks_to_watch = []
        stocks_to_avoid = []
        for sa in sector_analyses:
            stocks_to_watch.extend(sa.top_opportunities)
            stocks_to_avoid.extend(sa.stocks_to_avoid)
        for ti in thematic_insights:
            stocks_to_watch.extend(ti.beneficiaries)
            stocks_to_avoid.extend(ti.at_risk)

        duration = time.time() - start_time

        return ResearchReport(
            report_id=report_id,
            report_date=datetime.now(),
            research_type="sector",  # Primary type
            title=f"Weekly Research Report - {datetime.now().strftime('%Y-%m-%d')}",
            executive_summary=executive_summary,
            detailed_analysis="See individual sector and thematic analyses",
            sector_analyses=sector_analyses,
            thematic_insights=thematic_insights,
            macro_outlook=macro_outlook,
            actionable_insights=actionable_insights,
            stocks_to_watch=list(set(stocks_to_watch)),
            stocks_to_avoid=list(set(stocks_to_avoid)),
            model_version=self.model_name,
            research_duration_seconds=duration,
        )

    def analyze_sector(
        self,
        sector: str,
        market_context: dict,
        recent_news: list[dict] | None = None,
        current_holdings: list[str] | None = None,
    ) -> SectorAnalysis:
        """
        Analyze a specific sector.

        Args:
            sector: Sector name
            market_context: Current market context
            recent_news: Recent news for the sector
            current_holdings: Current holdings in this sector

        Returns:
            SectorAnalysis
        """
        logger.info(f"Analyzing sector: {sector}")

        prompt = build_sector_analysis_prompt(
            sector=sector,
            recent_news=recent_news or [],
            market_context=market_context,
            current_holdings=current_holdings,
        )

        full_prompt = f"{RESEARCH_SYSTEM_PROMPT}\n\n{prompt}"

        response = self.llm_client.generate(
            prompt=full_prompt,
            model=self.model_name,
        )

        data = self._parse_json_response(response.content)

        return SectorAnalysis(
            sector=data.get("sector", sector),
            outlook=data.get("outlook", "neutral"),
            confidence=data.get("confidence", 0.5),
            tailwinds=data.get("tailwinds", []),
            headwinds=data.get("headwinds", []),
            vs_market_outlook=data.get("vs_market_outlook", "inline"),
            top_opportunities=data.get("top_opportunities", []),
            stocks_to_avoid=data.get("stocks_to_avoid", []),
            time_horizon=data.get("time_horizon", "1-3 months"),
            key_metrics=data.get("key_metrics", []),
        )

    def analyze_theme(
        self,
        theme: str,
        related_stocks: list[str] | None = None,
    ) -> ThematicInsight:
        """
        Analyze a specific investment theme.

        Args:
            theme: Theme to analyze
            related_stocks: Potentially related stocks

        Returns:
            ThematicInsight
        """
        logger.info(f"Analyzing theme: {theme}")

        prompt = build_thematic_analysis_prompt(
            theme=theme,
            related_stocks=related_stocks,
        )

        full_prompt = f"{RESEARCH_SYSTEM_PROMPT}\n\n{prompt}"

        response = self.llm_client.generate(
            prompt=full_prompt,
            model=self.model_name,
        )

        data = self._parse_json_response(response.content)

        return ThematicInsight(
            theme=data.get("theme", theme),
            description=data.get("description", ""),
            relevance=data.get("relevance", "medium"),
            stage=data.get("stage", "developing"),
            bullish_implications=data.get("bullish_implications", []),
            bearish_implications=data.get("bearish_implications", []),
            beneficiaries=data.get("beneficiaries", []),
            at_risk=data.get("at_risk", []),
            expected_duration=data.get("expected_duration", ""),
        )

    def analyze_macro(
        self,
        current_data: dict,
        recent_events: list[str] | None = None,
    ) -> MacroOutlook:
        """
        Analyze macro-economic outlook.

        Args:
            current_data: Current economic data
            recent_events: Recent macro events

        Returns:
            MacroOutlook
        """
        logger.info("Analyzing macro outlook")

        prompt = build_macro_outlook_prompt(
            current_data=current_data,
            recent_events=recent_events or [],
        )

        full_prompt = f"{RESEARCH_SYSTEM_PROMPT}\n\n{prompt}"

        response = self.llm_client.generate(
            prompt=full_prompt,
            model=self.model_name,
        )

        data = self._parse_json_response(response.content)

        return MacroOutlook(
            outlook_date=datetime.now(),
            horizon=data.get("horizon", "Q1 2025"),
            market_outlook=data.get("market_outlook", "neutral"),
            risk_level=data.get("risk_level", "moderate"),
            positive_factors=data.get("positive_factors", []),
            negative_factors=data.get("negative_factors", []),
            uncertainties=data.get("uncertainties", []),
            rate_outlook=data.get("rate_outlook", "stable"),
            inflation_outlook=data.get("inflation_outlook", "stable"),
            overweight_sectors=data.get("overweight_sectors", []),
            underweight_sectors=data.get("underweight_sectors", []),
            equity_allocation=data.get("equity_allocation", "neutral"),
            cash_recommendation=data.get("cash_recommendation", ""),
        )

    def deep_dive_company(
        self,
        symbol: str,
        company_name: str,
        financial_data: dict | None = None,
        recent_news: list[dict] | None = None,
    ) -> CompanyDeepDive:
        """
        Conduct deep dive analysis of a company.

        Args:
            symbol: Stock ticker
            company_name: Company name
            financial_data: Financial metrics
            recent_news: Recent company news

        Returns:
            CompanyDeepDive
        """
        logger.info(f"Deep diving: {symbol} ({company_name})")

        prompt = build_company_deep_dive_prompt(
            symbol=symbol,
            company_name=company_name,
            financial_data=financial_data or {},
            recent_news=recent_news or [],
        )

        full_prompt = f"{RESEARCH_SYSTEM_PROMPT}\n\n{prompt}"

        response = self.llm_client.generate(
            prompt=full_prompt,
            model=self.model_name,
        )

        data = self._parse_json_response(response.content)

        return CompanyDeepDive(
            symbol=data.get("symbol", symbol),
            company_name=data.get("company_name", company_name),
            analysis_date=datetime.now(),
            thesis=data.get("thesis", ""),
            thesis_confidence=data.get("thesis_confidence", 0.5),
            fundamental_score=data.get("fundamental_score", 50),
            fundamental_summary=data.get("fundamental_summary", ""),
            key_strengths=data.get("key_strengths", []),
            key_weaknesses=data.get("key_weaknesses", []),
            moat_rating=data.get("moat_rating", "narrow"),
            competitive_advantages=data.get("competitive_advantages", []),
            competitive_threats=data.get("competitive_threats", []),
            growth_outlook=data.get("growth_outlook", "stable"),
            growth_drivers=data.get("growth_drivers", []),
            valuation_verdict=data.get("valuation_verdict", "fair"),
            valuation_rationale=data.get("valuation_rationale", ""),
            upcoming_catalysts=data.get("upcoming_catalysts", []),
            key_risks=data.get("key_risks", []),
            risk_mitigation=data.get("risk_mitigation", []),
            recommendation=data.get("recommendation", "hold"),
            target_price=data.get("target_price"),
            time_horizon=data.get("time_horizon", "12 months"),
        )

    def _parse_json_response(self, response: str) -> dict:
        """Parse JSON from LLM response."""
        cleaned = response.strip()
        if "```json" in cleaned:
            start = cleaned.find("```json") + 7
            end = cleaned.find("```", start)
            cleaned = cleaned[start:end].strip()
        elif "```" in cleaned:
            start = cleaned.find("```") + 3
            end = cleaned.find("```", start)
            cleaned = cleaned[start:end].strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            return {}

    def _build_executive_summary(
        self,
        sectors: list[SectorAnalysis],
        themes: list[ThematicInsight],
        macro: MacroOutlook | None,
    ) -> str:
        """Build executive summary from analyses."""
        parts = []

        # Macro overview
        if macro:
            parts.append(
                f"**Macro Outlook**: {macro.market_outlook.title()} "
                f"(Risk: {macro.risk_level})"
            )

        # Sector highlights
        bullish_sectors = [s.sector for s in sectors if s.outlook == "bullish"]
        bearish_sectors = [s.sector for s in sectors if s.outlook == "bearish"]

        if bullish_sectors:
            parts.append(f"**Bullish Sectors**: {', '.join(bullish_sectors)}")
        if bearish_sectors:
            parts.append(f"**Bearish Sectors**: {', '.join(bearish_sectors)}")

        # Theme highlights
        high_relevance_themes = [t.theme for t in themes if t.relevance == "high"]
        if high_relevance_themes:
            parts.append(f"**Key Themes**: {', '.join(high_relevance_themes)}")

        return "\n".join(parts) if parts else "Analysis complete"

    def _extract_actionable_insights(
        self,
        sectors: list[SectorAnalysis],
        themes: list[ThematicInsight],
        macro: MacroOutlook | None,
    ) -> list[str]:
        """Extract actionable insights from analyses."""
        insights = []

        # From macro
        if macro:
            if macro.market_outlook == "bearish":
                insights.append("Consider defensive positioning")
            elif macro.risk_level in ["elevated", "high"]:
                insights.append("Increase portfolio hedging")

            for sector in macro.overweight_sectors[:2]:
                insights.append(f"Overweight {sector}")
            for sector in macro.underweight_sectors[:2]:
                insights.append(f"Underweight {sector}")

        # From sectors
        for s in sectors:
            if s.outlook == "bullish" and s.confidence >= 0.7:
                if s.top_opportunities:
                    insights.append(
                        f"Consider {s.top_opportunities[0]} in {s.sector}"
                    )
            elif s.outlook == "bearish" and s.confidence >= 0.7:
                if s.stocks_to_avoid:
                    insights.append(
                        f"Avoid {s.stocks_to_avoid[0]} in {s.sector}"
                    )

        # From themes
        for t in themes:
            if t.relevance == "high" and t.stage in ["emerging", "developing"]:
                if t.beneficiaries:
                    insights.append(
                        f"Theme play: {t.beneficiaries[0]} ({t.theme})"
                    )

        return insights[:10]  # Limit to top 10
