"""
Information Models - Data structures for time-sensitive information.

Based on research findings:
- Immediate (<24h): Breaking news, earnings surprises - highest impact
- Short-term (1-5d): Recent developments, price movements
- Medium-term (1-4w): Trend formation, sector rotations
- Older (>4w): Background context, historical patterns

Lead time research insights:
- News impact: 3-5 hours (fast decay)
- Technical patterns: 5-20 days
- Fundamental changes: up to 13 weeks
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal


class TimeCategory(str, Enum):
    """Time categories based on research-backed lead times."""
    IMMEDIATE = "immediate"  # <24 hours - breaking news, earnings
    SHORT_TERM = "short_term"  # 1-5 days - recent developments
    MEDIUM_TERM = "medium_term"  # 1-4 weeks - trends forming
    OLDER = "older"  # >4 weeks - historical context


# Type aliases
NewsSource = Literal["finnhub", "yahoo", "sec", "twitter", "other"]
SentimentLevel = Literal["very_positive", "positive", "neutral", "negative", "very_negative"]
ImpactLevel = Literal["high", "medium", "low"]


@dataclass
class NewsItem:
    """
    Structured news item with time sensitivity.

    Research insight: News has 3-5 hour peak impact window,
    but effects can persist 1-5 days for significant events.
    """
    headline: str
    summary: str
    source: NewsSource
    published_at: datetime
    category: TimeCategory

    # Calculated fields
    hours_ago: float = 0.0
    decay_weight: float = 1.0  # Exponential decay based on age

    # Optional enrichment
    sentiment: SentimentLevel | None = None
    sentiment_score: float | None = None  # -1.0 to 1.0
    relevance_score: float | None = None  # 0.0 to 1.0

    # Impact assessment
    is_earnings_related: bool = False
    is_guidance_related: bool = False
    is_analyst_action: bool = False
    is_insider_activity: bool = False
    is_macro_event: bool = False

    # Raw data for audit
    url: str | None = None
    raw_data: dict[str, Any] | None = None

    def __post_init__(self):
        """Calculate time-based metrics after initialization."""
        if self.published_at:
            now = datetime.now()
            delta = now - self.published_at
            self.hours_ago = delta.total_seconds() / 3600

            # Exponential decay: half-life of 4 hours for news
            # After 4h: 0.5, 8h: 0.25, 12h: 0.125, 24h: 0.016
            self.decay_weight = 0.5 ** (self.hours_ago / 4)


@dataclass
class TechnicalContext:
    """
    Technical analysis context.

    Research insight: Technical signals have 5-20 day lead times.
    """
    # Price action
    current_price: float
    previous_close: float
    change_pct: float

    # Moving averages
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None

    # Above/below key levels
    above_sma_20: bool | None = None
    above_sma_50: bool | None = None
    above_sma_200: bool | None = None

    # Momentum
    rsi_14: float | None = None
    macd_signal: Literal["bullish", "bearish", "neutral"] | None = None

    # Volume
    volume: float | None = None
    avg_volume_20d: float | None = None
    volume_ratio: float | None = None  # current / avg

    # Volatility
    atr_14: float | None = None
    historical_volatility_20d: float | None = None

    # Support/Resistance
    week_52_high: float | None = None
    week_52_low: float | None = None
    distance_from_52w_high_pct: float | None = None
    distance_from_52w_low_pct: float | None = None

    # Pattern signals
    breakout_signal: bool = False
    breakdown_signal: bool = False
    consolidation: bool = False


@dataclass
class FundamentalContext:
    """
    Fundamental analysis context.

    Research insight: Fundamental factors have up to 13-week lead times.
    """
    # Valuation
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    peg_ratio: float | None = None

    # Relative to sector
    pe_vs_sector: Literal["premium", "inline", "discount"] | None = None

    # Growth
    revenue_growth_yoy: float | None = None
    earnings_growth_yoy: float | None = None

    # Quality
    roe: float | None = None
    debt_to_equity: float | None = None
    free_cash_flow: float | None = None

    # Dividend
    dividend_yield: float | None = None

    # Earnings
    earnings_date: datetime | None = None
    days_to_earnings: int | None = None
    last_earnings_surprise: float | None = None  # % beat/miss

    # Analyst coverage
    analyst_rating_avg: float | None = None  # 1-5 scale
    price_target_avg: float | None = None
    price_target_upside_pct: float | None = None


@dataclass
class MarketContext:
    """
    Broader market context for the information.

    Provides regime awareness for proper judgment.
    """
    regime: Literal["risk_on", "normal", "caution", "risk_off", "crisis"]
    vix_level: float
    sp500_trend: Literal["up", "flat", "down"]

    # Sector context
    sector: str | None = None
    sector_performance_1d: float | None = None
    sector_vs_market: Literal["outperforming", "inline", "underperforming"] | None = None


@dataclass
class TimedInformation:
    """
    Complete time-structured information package for a stock.

    This is the primary output of Layer 1, consumed by Layer 2 (Judgment).
    """
    # Identification
    symbol: str
    collected_at: datetime = field(default_factory=datetime.now)

    # News by time category
    immediate_news: list[NewsItem] = field(default_factory=list)  # <24h
    short_term_news: list[NewsItem] = field(default_factory=list)  # 1-5d
    medium_term_news: list[NewsItem] = field(default_factory=list)  # 1-4w
    older_news: list[NewsItem] = field(default_factory=list)  # >4w

    # Context
    technical: TechnicalContext | None = None
    fundamental: FundamentalContext | None = None
    market: MarketContext | None = None

    # Summary statistics
    total_news_count: int = 0
    immediate_news_count: int = 0
    avg_sentiment: float | None = None

    # Data quality
    data_freshness_score: float = 1.0  # 0-1, how fresh is the data
    data_completeness_score: float = 1.0  # 0-1, how complete is the data

    def __post_init__(self):
        """Calculate summary statistics."""
        self.total_news_count = (
            len(self.immediate_news) +
            len(self.short_term_news) +
            len(self.medium_term_news) +
            len(self.older_news)
        )
        self.immediate_news_count = len(self.immediate_news)

        # Calculate average sentiment
        all_news = (
            self.immediate_news +
            self.short_term_news +
            self.medium_term_news +
            self.older_news
        )
        sentiments = [n.sentiment_score for n in all_news if n.sentiment_score is not None]
        if sentiments:
            self.avg_sentiment = sum(sentiments) / len(sentiments)

    def get_weighted_news_summary(self) -> dict[str, Any]:
        """
        Get a time-weighted summary of news.

        Applies exponential decay to weight recent news higher.
        """
        summary = {
            "immediate": {
                "count": len(self.immediate_news),
                "weight": 1.0,  # Full weight for immediate
                "headlines": [n.headline for n in self.immediate_news[:3]],
            },
            "short_term": {
                "count": len(self.short_term_news),
                "weight": 0.5,  # Half weight for short-term
                "headlines": [n.headline for n in self.short_term_news[:2]],
            },
            "medium_term": {
                "count": len(self.medium_term_news),
                "weight": 0.2,  # Lower weight for medium-term
                "headlines": [n.headline for n in self.medium_term_news[:1]],
            },
            "older": {
                "count": len(self.older_news),
                "weight": 0.1,  # Minimal weight for older
                "headlines": [],  # Don't include old headlines
            },
        }

        # Calculate weighted sentiment
        weighted_sum = 0.0
        total_weight = 0.0

        for news_list, weight in [
            (self.immediate_news, 1.0),
            (self.short_term_news, 0.5),
            (self.medium_term_news, 0.2),
            (self.older_news, 0.1),
        ]:
            for news in news_list:
                if news.sentiment_score is not None:
                    weighted_sum += news.sentiment_score * weight * news.decay_weight
                    total_weight += weight * news.decay_weight

        summary["weighted_sentiment"] = (
            weighted_sum / total_weight if total_weight > 0 else None
        )

        return summary

    def has_breaking_news(self) -> bool:
        """Check if there's breaking news (within last 6 hours)."""
        for news in self.immediate_news:
            if news.hours_ago < 6:
                return True
        return False

    def has_earnings_catalyst(self) -> bool:
        """Check if there's an earnings-related catalyst."""
        for news in self.immediate_news + self.short_term_news:
            if news.is_earnings_related or news.is_guidance_related:
                return True
        return False
