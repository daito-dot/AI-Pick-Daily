"""
Deep Research Models - Data structures for research outputs.

These models capture the output of deep research analysis,
which provides strategic context for daily judgments.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


ResearchType = Literal["sector", "thematic", "macro", "company"]


@dataclass
class SectorAnalysis:
    """
    Analysis of a market sector.

    Provides context for stocks within the sector.
    """
    sector: str
    outlook: Literal["bullish", "neutral", "bearish"]
    confidence: float  # 0-1

    # Key drivers
    tailwinds: list[str] = field(default_factory=list)
    headwinds: list[str] = field(default_factory=list)

    # Relative performance
    vs_market_outlook: Literal["outperform", "inline", "underperform"] = "inline"

    # Top picks in sector
    top_opportunities: list[str] = field(default_factory=list)  # Stock symbols
    stocks_to_avoid: list[str] = field(default_factory=list)

    # Time horizon
    time_horizon: str = "1-3 months"

    # Key metrics to watch
    key_metrics: list[str] = field(default_factory=list)


@dataclass
class ThematicInsight:
    """
    Insight on a specific investment theme.

    E.g., "AI infrastructure", "interest rate sensitivity", "reshoring"
    """
    theme: str
    description: str
    relevance: Literal["high", "medium", "low"]

    # Stage of theme
    stage: Literal["emerging", "developing", "mature", "declining"]

    # Investment implications
    bullish_implications: list[str] = field(default_factory=list)
    bearish_implications: list[str] = field(default_factory=list)

    # Related stocks
    beneficiaries: list[str] = field(default_factory=list)  # Stocks that benefit
    at_risk: list[str] = field(default_factory=list)  # Stocks at risk

    # Timeline
    expected_duration: str = ""


@dataclass
class MacroOutlook:
    """
    Macro-economic outlook analysis.

    Provides context for overall market positioning.
    """
    outlook_date: datetime
    horizon: str  # e.g., "Q1 2025"

    # Overall stance
    market_outlook: Literal["bullish", "neutral", "bearish"]
    risk_level: Literal["low", "moderate", "elevated", "high"]

    # Key factors
    positive_factors: list[str] = field(default_factory=list)
    negative_factors: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)

    # Rate outlook
    rate_outlook: Literal["rising", "stable", "falling"] = "stable"
    inflation_outlook: Literal["rising", "stable", "falling"] = "stable"

    # Sector recommendations
    overweight_sectors: list[str] = field(default_factory=list)
    underweight_sectors: list[str] = field(default_factory=list)

    # Asset allocation suggestions
    equity_allocation: Literal["overweight", "neutral", "underweight"] = "neutral"
    cash_recommendation: str = ""


@dataclass
class CompanyDeepDive:
    """
    Comprehensive analysis of a single company.

    Used for detailed investigation of specific opportunities.
    """
    symbol: str
    company_name: str
    analysis_date: datetime

    # Investment thesis
    thesis: str
    thesis_confidence: float  # 0-1

    # Fundamental analysis
    fundamental_score: int  # 0-100
    fundamental_summary: str
    key_strengths: list[str] = field(default_factory=list)
    key_weaknesses: list[str] = field(default_factory=list)

    # Competitive position
    moat_rating: Literal["wide", "narrow", "none"] = "narrow"
    competitive_advantages: list[str] = field(default_factory=list)
    competitive_threats: list[str] = field(default_factory=list)

    # Growth analysis
    growth_outlook: Literal["accelerating", "stable", "decelerating"] = "stable"
    growth_drivers: list[str] = field(default_factory=list)

    # Valuation
    valuation_verdict: Literal["undervalued", "fair", "overvalued"] = "fair"
    valuation_rationale: str = ""

    # Catalysts
    upcoming_catalysts: list[dict] = field(default_factory=list)  # {"event": str, "date": str, "impact": str}

    # Risks
    key_risks: list[str] = field(default_factory=list)
    risk_mitigation: list[str] = field(default_factory=list)

    # Recommendation
    recommendation: Literal["strong_buy", "buy", "hold", "sell", "strong_sell"] = "hold"
    target_price: float | None = None
    time_horizon: str = "12 months"


@dataclass
class ResearchReport:
    """
    Complete research report output.

    This is the primary output of Layer 4.
    """
    # Metadata
    report_id: str
    report_date: datetime
    research_type: ResearchType
    title: str

    # Content
    executive_summary: str
    detailed_analysis: str

    # Specific analyses (populated based on type)
    sector_analyses: list[SectorAnalysis] = field(default_factory=list)
    thematic_insights: list[ThematicInsight] = field(default_factory=list)
    macro_outlook: MacroOutlook | None = None
    company_deep_dives: list[CompanyDeepDive] = field(default_factory=list)

    # Action items
    actionable_insights: list[str] = field(default_factory=list)
    stocks_to_watch: list[str] = field(default_factory=list)
    stocks_to_avoid: list[str] = field(default_factory=list)

    # Meta
    model_version: str = ""
    research_duration_seconds: float = 0
    raw_llm_response: str | None = None

    def get_investment_implications(self) -> dict[str, Any]:
        """Extract investment implications from the report."""
        implications = {
            "bullish_stocks": [],
            "bearish_stocks": [],
            "sectors_to_overweight": [],
            "sectors_to_underweight": [],
            "themes_to_follow": [],
        }

        # From sector analyses
        for sa in self.sector_analyses:
            if sa.outlook == "bullish":
                implications["sectors_to_overweight"].append(sa.sector)
                implications["bullish_stocks"].extend(sa.top_opportunities)
            elif sa.outlook == "bearish":
                implications["sectors_to_underweight"].append(sa.sector)
                implications["bearish_stocks"].extend(sa.stocks_to_avoid)

        # From thematic insights
        for ti in self.thematic_insights:
            if ti.relevance == "high":
                implications["themes_to_follow"].append(ti.theme)
                implications["bullish_stocks"].extend(ti.beneficiaries)
                implications["bearish_stocks"].extend(ti.at_risk)

        # From macro outlook
        if self.macro_outlook:
            implications["sectors_to_overweight"].extend(
                self.macro_outlook.overweight_sectors
            )
            implications["sectors_to_underweight"].extend(
                self.macro_outlook.underweight_sectors
            )

        # Deduplicate
        for key in implications:
            implications[key] = list(set(implications[key]))

        return implications
