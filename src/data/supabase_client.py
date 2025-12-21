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
    strategy_mode: str = "conservative"  # 'conservative' or 'aggressive'
    status: str = "generated"


@dataclass
class StockScore:
    """Stock scoring record."""
    batch_date: str
    symbol: str
    strategy_mode: str  # 'conservative' or 'aggressive'
    trend_score: int
    momentum_score: int
    value_score: int
    sentiment_score: int
    composite_score: int
    percentile_rank: int
    reasoning: str
    price_at_time: float
    market_regime_at_time: str
    # V2 scores
    momentum_12_1_score: int | None = None
    breakout_score: int | None = None
    catalyst_score: int | None = None
    risk_adjusted_score: int | None = None
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
            "strategy_mode": picks.strategy_mode,
            "status": picks.status,
        }

        result = self._client.table("daily_picks").upsert(
            data,
            on_conflict="batch_date,strategy_mode",
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
                "strategy_mode": s.strategy_mode,
                "trend_score": int(s.trend_score),
                "momentum_score": int(s.momentum_score),
                "value_score": int(s.value_score),
                "sentiment_score": int(s.sentiment_score),
                "composite_score": int(s.composite_score),
                "percentile_rank": int(s.percentile_rank),
                "reasoning": s.reasoning,
                "price_at_time": float(s.price_at_time),
                "market_regime_at_time": s.market_regime_at_time,
                # V2 scores
                "momentum_12_1_score": int(s.momentum_12_1_score) if s.momentum_12_1_score is not None else None,
                "breakout_score": int(s.breakout_score) if s.breakout_score is not None else None,
                "catalyst_score": int(s.catalyst_score) if s.catalyst_score is not None else None,
                "risk_adjusted_score": int(s.risk_adjusted_score) if s.risk_adjusted_score is not None else None,
                "earnings_date": s.earnings_date,
                "cutoff_timestamp": s.cutoff_timestamp,
            }
            for s in scores
        ]

        result = self._client.table("stock_scores").upsert(
            data,
            on_conflict="batch_date,symbol,strategy_mode",
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
            "vix_level": float(record.vix_level),
            "market_regime": record.market_regime,
            "sp500_sma20_deviation_pct": float(record.sp500_sma20_deviation_pct),
            "volatility_cluster_flag": bool(record.volatility_cluster_flag),
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

    # ============ Return Tracking ============

    def get_scores_for_review(
        self,
        batch_date: str,
        strategy_mode: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get all stock scores for a date that need return calculation.

        Args:
            batch_date: Date in YYYY-MM-DD format
            strategy_mode: Optional strategy filter

        Returns:
            List of stock score records
        """
        query = self._client.table("stock_scores").select("*").eq(
            "batch_date", batch_date
        )

        if strategy_mode:
            query = query.eq("strategy_mode", strategy_mode)

        result = query.order("composite_score", desc=True).execute()
        return result.data or []

    def update_stock_returns(
        self,
        batch_date: str,
        symbol: str,
        strategy_mode: str,
        return_1d: float | None = None,
        return_5d: float | None = None,
        price_1d: float | None = None,
        price_5d: float | None = None,
        was_picked: bool = False,
    ) -> dict[str, Any]:
        """
        Update return data for a scored stock.

        Args:
            batch_date: Original score date
            symbol: Stock symbol
            strategy_mode: Strategy mode
            return_1d: 1-day return percentage
            return_5d: 5-day return percentage
            price_1d: Price at 1-day review
            price_5d: Price at 5-day review
            was_picked: Whether this was a picked stock

        Returns:
            Updated record
        """
        update_data: dict[str, Any] = {
            "reviewed_at": datetime.utcnow().isoformat(),
        }

        if return_1d is not None:
            update_data["return_1d"] = round(return_1d, 4)
        if return_5d is not None:
            update_data["return_5d"] = round(return_5d, 4)
        if price_1d is not None:
            update_data["price_1d"] = round(price_1d, 4)
        if price_5d is not None:
            update_data["price_5d"] = round(price_5d, 4)
        if was_picked:
            update_data["was_picked"] = was_picked

        result = self._client.table("stock_scores").update(
            update_data
        ).eq(
            "batch_date", batch_date
        ).eq(
            "symbol", symbol
        ).eq(
            "strategy_mode", strategy_mode
        ).execute()

        return result.data[0] if result.data else {}

    def bulk_update_returns(
        self,
        updates: list[dict[str, Any]],
    ) -> int:
        """
        Bulk update returns for multiple stocks.

        Args:
            updates: List of dicts with batch_date, symbol, strategy_mode, and return data

        Returns:
            Number of records updated
        """
        updated = 0
        for u in updates:
            self.update_stock_returns(
                batch_date=u["batch_date"],
                symbol=u["symbol"],
                strategy_mode=u["strategy_mode"],
                return_1d=u.get("return_1d"),
                return_5d=u.get("return_5d"),
                price_1d=u.get("price_1d"),
                price_5d=u.get("price_5d"),
                was_picked=u.get("was_picked", False),
            )
            updated += 1
        return updated

    def get_missed_opportunities(
        self,
        batch_date: str,
        min_return: float = 3.0,
        strategy_mode: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get stocks that weren't picked but performed well.

        Args:
            batch_date: Date to check
            min_return: Minimum return percentage to consider
            strategy_mode: Optional strategy filter

        Returns:
            List of missed opportunity records
        """
        query = self._client.table("stock_scores").select("*").eq(
            "batch_date", batch_date
        ).eq(
            "was_picked", False
        ).gte(
            "return_5d", min_return
        )

        if strategy_mode:
            query = query.eq("strategy_mode", strategy_mode)

        result = query.order("return_5d", desc=True).execute()
        return result.data or []

    def get_performance_summary(
        self,
        days: int = 30,
        strategy_mode: str | None = None,
    ) -> dict[str, Any]:
        """
        Get summary statistics for picked vs non-picked stocks.

        Args:
            days: Number of days to analyze
            strategy_mode: Optional strategy filter

        Returns:
            Summary statistics
        """
        # Get all reviewed scores
        query = self._client.table("stock_scores").select(
            "was_picked, return_5d, composite_score"
        ).not_.is_("return_5d", "null")

        if strategy_mode:
            query = query.eq("strategy_mode", strategy_mode)

        result = query.execute()
        data = result.data or []

        if not data:
            return {"error": "No reviewed data"}

        picked = [d for d in data if d.get("was_picked")]
        not_picked = [d for d in data if not d.get("was_picked")]

        def avg(lst: list, key: str) -> float:
            vals = [d[key] for d in lst if d.get(key) is not None]
            return sum(vals) / len(vals) if vals else 0

        return {
            "picked_count": len(picked),
            "picked_avg_return": avg(picked, "return_5d"),
            "picked_avg_score": avg(picked, "composite_score"),
            "not_picked_count": len(not_picked),
            "not_picked_avg_return": avg(not_picked, "return_5d"),
            "not_picked_avg_score": avg(not_picked, "composite_score"),
            "missed_opportunities": len([d for d in not_picked if d.get("return_5d", 0) > 3]),
        }

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
