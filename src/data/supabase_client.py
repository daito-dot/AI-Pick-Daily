"""
Supabase Client

Handles all database operations:
- Daily picks storage
- Stock scores
- Market regime history
- Performance tracking
"""
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from supabase import create_client, Client

from src.config import config
from src.scoring.market_regime import MarketRegime


@dataclass
class DailyPick:
    """Daily stock pick record."""
    batch_date: str
    symbols: list[str]
    pick_count: int
    market_regime: str
    status: str = "generated"


@dataclass
class StockScore:
    """Stock scoring record."""
    batch_date: str
    symbol: str
    trend_score: int
    momentum_score: int
    value_score: int
    sentiment_score: int
    composite_score: int
    percentile_rank: int
    reasoning: str
    price_at_time: float
    market_regime_at_time: str
    earnings_date: str | None = None
    cutoff_timestamp: str | None = None


@dataclass
class MarketRegimeRecord:
    """Market regime history record."""
    check_date: str
    vix_level: float
    market_regime: str
    sp500_sma20_deviation_pct: float
    volatility_cluster_flag: bool
    notes: str


class SupabaseClient:
    """Supabase database client."""

    def __init__(self):
        """Initialize the Supabase client."""
        url = config.supabase.url
        key = config.supabase.service_role_key or config.supabase.anon_key

        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")

        self._client: Client = create_client(url, key)

    # ============ Daily Picks ============

    def save_daily_picks(self, picks: DailyPick) -> dict[str, Any]:
        """
        Save daily picks to database.

        Args:
            picks: DailyPick record

        Returns:
            Inserted record
        """
        data = {
            "batch_date": picks.batch_date,
            "symbols": picks.symbols,
            "pick_count": picks.pick_count,
            "market_regime": picks.market_regime,
            "status": picks.status,
        }

        result = self._client.table("daily_picks").upsert(
            data,
            on_conflict="batch_date",
        ).execute()

        return result.data[0] if result.data else {}

    def get_daily_picks(self, batch_date: str) -> dict[str, Any] | None:
        """
        Get daily picks for a specific date.

        Args:
            batch_date: Date in YYYY-MM-DD format

        Returns:
            Daily picks record or None
        """
        result = self._client.table("daily_picks").select("*").eq(
            "batch_date", batch_date
        ).execute()

        return result.data[0] if result.data else None

    def get_recent_picks(self, days: int = 30) -> list[dict[str, Any]]:
        """
        Get recent daily picks.

        Args:
            days: Number of days to look back

        Returns:
            List of daily picks records
        """
        result = self._client.table("daily_picks").select("*").order(
            "batch_date", desc=True
        ).limit(days).execute()

        return result.data or []

    # ============ Stock Scores ============

    def save_stock_scores(self, scores: list[StockScore]) -> list[dict[str, Any]]:
        """
        Save stock scores to database.

        Args:
            scores: List of StockScore records

        Returns:
            Inserted records
        """
        data = [
            {
                "batch_date": s.batch_date,
                "symbol": s.symbol,
                "trend_score": s.trend_score,
                "momentum_score": s.momentum_score,
                "value_score": s.value_score,
                "sentiment_score": s.sentiment_score,
                "composite_score": s.composite_score,
                "percentile_rank": s.percentile_rank,
                "reasoning": s.reasoning,
                "price_at_time": s.price_at_time,
                "market_regime_at_time": s.market_regime_at_time,
                "earnings_date": s.earnings_date,
                "cutoff_timestamp": s.cutoff_timestamp,
            }
            for s in scores
        ]

        result = self._client.table("stock_scores").upsert(
            data,
            on_conflict="batch_date,symbol",
        ).execute()

        return result.data or []

    def get_stock_scores(
        self,
        batch_date: str,
        min_percentile: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Get stock scores for a specific date.

        Args:
            batch_date: Date in YYYY-MM-DD format
            min_percentile: Minimum percentile to filter

        Returns:
            List of stock score records
        """
        result = self._client.table("stock_scores").select("*").eq(
            "batch_date", batch_date
        ).gte(
            "percentile_rank", min_percentile
        ).order(
            "percentile_rank", desc=True
        ).execute()

        return result.data or []

    # ============ Market Regime ============

    def save_market_regime(self, record: MarketRegimeRecord) -> dict[str, Any]:
        """
        Save market regime record.

        Args:
            record: MarketRegimeRecord

        Returns:
            Inserted record
        """
        data = {
            "check_date": record.check_date,
            "vix_level": record.vix_level,
            "market_regime": record.market_regime,
            "sp500_sma20_deviation_pct": record.sp500_sma20_deviation_pct,
            "volatility_cluster_flag": record.volatility_cluster_flag,
            "notes": record.notes,
        }

        result = self._client.table("market_regime_history").upsert(
            data,
            on_conflict="check_date",
        ).execute()

        return result.data[0] if result.data else {}

    def get_market_regime(self, check_date: str) -> dict[str, Any] | None:
        """
        Get market regime for a specific date.

        Args:
            check_date: Date in YYYY-MM-DD format

        Returns:
            Market regime record or None
        """
        result = self._client.table("market_regime_history").select("*").eq(
            "check_date", check_date
        ).execute()

        return result.data[0] if result.data else None

    # ============ Performance Tracking ============

    def save_performance_log(self, log: dict[str, Any]) -> dict[str, Any]:
        """
        Save performance log entry.

        Args:
            log: Performance log data

        Returns:
            Inserted record
        """
        result = self._client.table("performance_log").upsert(
            log,
            on_conflict="pick_date,symbol",
        ).execute()

        return result.data[0] if result.data else {}

    def get_performance_logs(
        self,
        days: int = 30,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get performance logs.

        Args:
            days: Number of days to look back
            symbol: Optional symbol to filter

        Returns:
            List of performance log records
        """
        query = self._client.table("performance_log").select("*").order(
            "pick_date", desc=True
        ).limit(days * 5)  # Approximate

        if symbol:
            query = query.eq("symbol", symbol)

        result = query.execute()
        return result.data or []

    # ============ Earnings ============

    def get_upcoming_earnings(
        self,
        symbols: list[str],
        within_days: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Check for upcoming earnings within specified days.

        Args:
            symbols: List of symbols to check
            within_days: Days to look ahead

        Returns:
            List of earnings records
        """
        today = date.today().isoformat()
        end_date = (date.today().replace(day=date.today().day + within_days)).isoformat()

        result = self._client.table("stock_scores").select(
            "symbol, earnings_date"
        ).in_(
            "symbol", symbols
        ).gte(
            "earnings_date", today
        ).lte(
            "earnings_date", end_date
        ).execute()

        return result.data or []

    # ============ News Archive ============

    def save_news(self, news_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Save news items to archive.

        Args:
            news_items: List of news data

        Returns:
            Inserted records
        """
        result = self._client.table("news_archive").upsert(
            news_items,
            on_conflict="finnhub_news_id",
        ).execute()

        return result.data or []
