"""
Supabase Client

Handles all database operations:
- Daily picks storage
- Stock scores
- Market regime history
- Performance tracking
"""
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from supabase import create_client, Client

logger = logging.getLogger(__name__)

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
    market_type: str | None = None  # 'us' or 'jp' (None for legacy US records)


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
    market_type: str | None = None  # 'us' or 'jp' (None for legacy US records)


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
        if picks.market_type:
            data["market_type"] = picks.market_type

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

    def delete_daily_picks_for_date(
        self,
        batch_date: str,
        strategy_modes: list[str] | None = None,
    ) -> int:
        """
        Delete daily picks for a specific date (for idempotent re-runs).

        Args:
            batch_date: Date in YYYY-MM-DD format
            strategy_modes: Optional list of strategy modes to delete.
                           If None, deletes all picks for that date.

        Returns:
            Number of records deleted
        """
        query = self._client.table("daily_picks").delete().eq(
            "batch_date", batch_date
        )

        if strategy_modes:
            query = query.in_("strategy_mode", strategy_modes)

        result = query.execute()
        return len(result.data) if result.data else 0

    def save_daily_picks_batch(
        self,
        picks_list: list[DailyPick],
        delete_existing: bool = True,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Save multiple daily picks as a batch with idempotency support.

        This method provides atomic-like behavior by:
        1. Optionally deleting existing records for the same date/strategy combinations
        2. Inserting all new picks via upsert

        Args:
            picks_list: List of DailyPick records to save
            delete_existing: If True, delete existing records first for clean upsert

        Returns:
            Tuple of (saved_records, errors)
            - saved_records: List of successfully saved records
            - errors: List of error messages (empty if all succeeded)
        """
        if not picks_list:
            return [], []

        saved_records = []
        errors = []

        # Group by batch_date for potential cleanup
        batch_date = picks_list[0].batch_date
        strategy_modes = [p.strategy_mode for p in picks_list]

        # Step 1: Delete existing records if requested (for idempotency)
        if delete_existing:
            try:
                deleted_count = self.delete_daily_picks_for_date(
                    batch_date, strategy_modes
                )
                if deleted_count > 0:
                    # Log deletion for debugging (caller should log via BatchLogger)
                    pass
            except Exception as e:
                logger.warning(f"Failed to delete existing picks for {batch_date}: {e}")
                errors.append(f"Failed to delete existing picks: {str(e)}")
                # Continue with upsert anyway - it will overwrite

        # Step 2: Save all picks
        for pick in picks_list:
            try:
                result = self.save_daily_picks(pick)
                saved_records.append(result)
            except Exception as e:
                logger.warning(f"Failed to save {pick.strategy_mode} picks: {e}")
                errors.append(
                    f"Failed to save {pick.strategy_mode} picks: {str(e)}"
                )

        return saved_records, errors

    # ============ Stock Scores ============

    def save_stock_scores(self, scores: list[StockScore]) -> list[dict[str, Any]]:
        """
        Save stock scores to database.

        Args:
            scores: List of StockScore records

        Returns:
            Inserted records
        """
        data = []
        for s in scores:
            record = {
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
            if s.market_type:
                record["market_type"] = s.market_type
            data.append(record)

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
            on_conflict="pick_date,symbol,strategy_mode",
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
        end_date = (date.today() + timedelta(days=within_days)).isoformat()

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
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
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

    # ============ Scoring Config (Dynamic Thresholds) ============

    def get_scoring_config(
        self,
        strategy_mode: str,
    ) -> dict[str, Any]:
        """
        Get current scoring configuration for a strategy.

        Args:
            strategy_mode: 'conservative', 'aggressive', 'jp_conservative', or 'jp_aggressive'

        Returns:
            Config dict with threshold and limits, or empty dict if not found
        """
        try:
            result = self._client.table("scoring_config").select("*").eq(
                "strategy_mode", strategy_mode
            ).single().execute()
            return result.data or {}
        except Exception as e:
            logger.debug(f"No scoring_config for {strategy_mode}: {e}")
            return {}

    def get_all_scoring_configs(self) -> list[dict[str, Any]]:
        """
        Get all scoring configurations.

        Returns:
            List of config dicts
        """
        result = self._client.table("scoring_config").select("*").execute()
        return result.data or []

    def update_threshold(
        self,
        strategy_mode: str,
        new_threshold: float,
        reason: str,
    ) -> dict[str, Any]:
        """
        Update the scoring threshold for a strategy.

        Args:
            strategy_mode: 'conservative' or 'aggressive'
            new_threshold: New threshold value
            reason: Reason for the change

        Returns:
            Updated config
        """
        result = self._client.table("scoring_config").update({
            "threshold": new_threshold,
            "last_adjustment_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "last_adjustment_reason": reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq(
            "strategy_mode", strategy_mode
        ).execute()

        return result.data[0] if result.data else {}

    def save_threshold_history(
        self,
        strategy_mode: str,
        old_threshold: float,
        new_threshold: float,
        reason: str,
        missed_opportunities_count: int | None = None,
        missed_avg_return: float | None = None,
        missed_avg_score: float | None = None,
        picked_count: int | None = None,
        picked_avg_return: float | None = None,
        not_picked_count: int | None = None,
        not_picked_avg_return: float | None = None,
        wfe_score: float | None = None,
    ) -> dict[str, Any]:
        """
        Save a threshold change to history for audit and rollback.

        Args:
            strategy_mode: 'conservative' or 'aggressive'
            old_threshold: Previous threshold value
            new_threshold: New threshold value
            reason: Reason for the change
            (optional) Performance metrics at time of change

        Returns:
            Inserted record
        """
        record = {
            "strategy_mode": strategy_mode,
            "old_threshold": old_threshold,
            "new_threshold": new_threshold,
            "adjustment_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "reason": reason,
        }

        if missed_opportunities_count is not None:
            record["missed_opportunities_count"] = missed_opportunities_count
        if missed_avg_return is not None:
            record["missed_avg_return"] = round(missed_avg_return, 4)
        if missed_avg_score is not None:
            record["missed_avg_score"] = round(missed_avg_score, 2)
        if picked_count is not None:
            record["picked_count"] = picked_count
        if picked_avg_return is not None:
            record["picked_avg_return"] = round(picked_avg_return, 4)
        if not_picked_count is not None:
            record["not_picked_count"] = not_picked_count
        if not_picked_avg_return is not None:
            record["not_picked_avg_return"] = round(not_picked_avg_return, 4)
        if wfe_score is not None:
            record["wfe_score"] = round(wfe_score, 2)

        result = self._client.table("threshold_history").insert(record).execute()
        return result.data[0] if result.data else {}

    # ============ Virtual Portfolio ============

    def get_open_positions(
        self,
        strategy_mode: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get all open positions in the virtual portfolio.

        Args:
            strategy_mode: Optional filter by strategy

        Returns:
            List of open position records
        """
        query = self._client.table("virtual_portfolio").select("*").eq(
            "status", "open"
        )

        if strategy_mode:
            query = query.eq("strategy_mode", strategy_mode)

        result = query.order("entry_date", desc=True).execute()
        return result.data or []

    def open_position(
        self,
        strategy_mode: str,
        symbol: str,
        entry_date: str,
        entry_price: float,
        shares: float,
        position_value: float,
        entry_score: int | None = None,
        market_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Open a new position in the virtual portfolio.

        Args:
            strategy_mode: 'conservative', 'aggressive', 'jp_conservative', or 'jp_aggressive'
            symbol: Stock symbol
            entry_date: Date of entry (YYYY-MM-DD)
            entry_price: Entry price
            shares: Number of shares
            position_value: Total position value
            entry_score: Score at entry time
            market_type: 'us' or 'jp' (auto-derived from strategy_mode if not provided)

        Returns:
            Inserted record
        """
        # Auto-derive market_type from strategy_mode if not provided
        if market_type is None:
            market_type = "jp" if strategy_mode.startswith("jp_") else "us"

        record = {
            "strategy_mode": strategy_mode,
            "symbol": symbol,
            "entry_date": entry_date,
            "entry_price": entry_price,
            "shares": shares,
            "position_value": position_value,
            "status": "open",
            "market_type": market_type,
        }

        if entry_score is not None:
            record["entry_score"] = entry_score

        result = self._client.table("virtual_portfolio").upsert(
            record,
            on_conflict="strategy_mode,symbol,entry_date",
        ).execute()

        return result.data[0] if result.data else {}

    def close_position(
        self,
        position_id: str,
        exit_date: str,
        exit_price: float,
        exit_reason: str,
        realized_pnl: float,
        realized_pnl_pct: float,
    ) -> dict[str, Any]:
        """
        Close an existing position.

        Args:
            position_id: UUID of the position
            exit_date: Date of exit (YYYY-MM-DD)
            exit_price: Exit price
            exit_reason: Reason for closing
            realized_pnl: Realized P&L in currency
            realized_pnl_pct: Realized P&L percentage

        Returns:
            Updated record
        """
        result = self._client.table("virtual_portfolio").update({
            "status": "closed",
            "exit_date": exit_date,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "realized_pnl": realized_pnl,
            "realized_pnl_pct": realized_pnl_pct,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq(
            "id", position_id
        ).execute()

        return result.data[0] if result.data else {}

    def save_trade_history(
        self,
        strategy_mode: str,
        symbol: str,
        entry_date: str,
        entry_price: float,
        entry_score: int | None,
        exit_date: str,
        exit_price: float,
        shares: float,
        hold_days: int,
        pnl: float,
        pnl_pct: float,
        exit_reason: str,
        market_regime_at_entry: str | None = None,
        market_regime_at_exit: str | None = None,
        market_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Save a completed trade to history.

        Args:
            strategy_mode: 'conservative', 'aggressive', 'jp_conservative', or 'jp_aggressive'
            market_type: 'us' or 'jp' (auto-derived from strategy_mode if not provided)

        Returns:
            Inserted record
        """
        # Auto-derive market_type from strategy_mode if not provided
        if market_type is None:
            market_type = "jp" if strategy_mode.startswith("jp_") else "us"

        record = {
            "strategy_mode": strategy_mode,
            "symbol": symbol,
            "entry_date": entry_date,
            "entry_price": entry_price,
            "exit_date": exit_date,
            "exit_price": exit_price,
            "shares": shares,
            "hold_days": hold_days,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "exit_reason": exit_reason,
            "market_type": market_type,
        }

        if entry_score is not None:
            record["entry_score"] = entry_score
        if market_regime_at_entry:
            record["market_regime_at_entry"] = market_regime_at_entry
        if market_regime_at_exit:
            record["market_regime_at_exit"] = market_regime_at_exit

        result = self._client.table("trade_history").insert(record).execute()
        return result.data[0] if result.data else {}

    def get_symbols_closed_on_date(
        self,
        strategy_mode: str,
        exit_date: str,
    ) -> list[str]:
        """
        Get symbols that were closed (exited) on a specific date.

        Used to prevent same-day re-entry after position closure.

        Args:
            strategy_mode: 'conservative', 'aggressive', etc.
            exit_date: Date string in YYYY-MM-DD format

        Returns:
            List of symbols that were closed on that date
        """
        result = (
            self._client.table("trade_history")
            .select("symbol")
            .eq("strategy_mode", strategy_mode)
            .eq("exit_date", exit_date)
            .execute()
        )
        return [row["symbol"] for row in result.data] if result.data else []

    def get_unreviewed_batch(
        self,
        strategy_mode: str,
    ) -> dict[str, Any] | None:
        """
        Get the latest Post-Market batch that hasn't been reviewed yet.

        This links Pre-Market Review to the correct Post-Market Scoring batch
        instead of using date-based matching.

        Args:
            strategy_mode: 'conservative', 'aggressive', etc.

        Returns:
            Batch info dict with id, batch_date, symbols, or None if no unreviewed batch

        Note:
            Falls back to latest batch if reviewed_at column doesn't exist
            (migration 011 not applied yet).
        """
        try:
            # Try with reviewed_at filter (requires migration 011)
            result = (
                self._client.table("daily_picks")
                .select("id, batch_date, symbols, pick_count")
                .eq("strategy_mode", strategy_mode)
                .eq("status", "published")
                .is_("reviewed_at", "null")
                .order("batch_date", desc=True)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            # Fallback: column doesn't exist, get latest batch by date
            if "reviewed_at" in str(e) and "does not exist" in str(e):
                result = (
                    self._client.table("daily_picks")
                    .select("id, batch_date, symbols, pick_count")
                    .eq("strategy_mode", strategy_mode)
                    .eq("status", "published")
                    .order("batch_date", desc=True)
                    .limit(1)
                    .execute()
                )
                return result.data[0] if result.data else None
            raise

    def mark_batch_reviewed(
        self,
        batch_id: str,
    ) -> bool:
        """
        Mark a Post-Market batch as reviewed by Pre-Market Review.

        Args:
            batch_id: UUID of the daily_picks record

        Returns:
            True if successful

        Note:
            Silently succeeds if reviewed_at column doesn't exist
            (migration 011 not applied yet).
        """
        from datetime import datetime, timezone

        try:
            result = (
                self._client.table("daily_picks")
                .update({"reviewed_at": datetime.now(timezone.utc).isoformat()})
                .eq("id", batch_id)
                .execute()
            )
            return bool(result.data)
        except Exception as e:
            # Column doesn't exist yet - silently succeed
            if "reviewed_at" in str(e) and "does not exist" in str(e):
                return True
            raise

    def get_scores_for_batch(
        self,
        batch_date: str,
        strategy_mode: str,
    ) -> dict[str, int]:
        """
        Get scores for a specific batch (date + strategy_mode).

        Returns a dict of symbol -> composite_score for the given batch.

        Args:
            batch_date: Date string in YYYY-MM-DD format
            strategy_mode: 'conservative', 'aggressive', etc.

        Returns:
            Dict mapping symbol to composite_score
        """
        result = (
            self._client.table("stock_scores")
            .select("symbol, composite_score")
            .eq("batch_date", batch_date)
            .eq("strategy_mode", strategy_mode)
            .execute()
        )
        return {
            row["symbol"]: row["composite_score"]
            for row in result.data
            if row.get("composite_score") is not None
        } if result.data else {}

    def get_latest_portfolio_snapshot(
        self,
        strategy_mode: str,
    ) -> dict[str, Any]:
        """
        Get the most recent portfolio snapshot.

        Args:
            strategy_mode: 'conservative' or 'aggressive'

        Returns:
            Latest snapshot record
        """
        result = self._client.table("portfolio_daily_snapshot").select("*").eq(
            "strategy_mode", strategy_mode
        ).order(
            "snapshot_date", desc=True
        ).limit(1).execute()

        return result.data[0] if result.data else {}

    def save_portfolio_snapshot(
        self,
        snapshot_date: str,
        strategy_mode: str,
        total_value: float,
        cash_balance: float,
        positions_value: float,
        daily_pnl: float | None = None,
        daily_pnl_pct: float | None = None,
        cumulative_pnl: float | None = None,
        cumulative_pnl_pct: float | None = None,
        benchmark_daily_pct: float | None = None,
        benchmark_cumulative_pct: float | None = None,
        alpha: float | None = None,
        open_positions: int = 0,
        closed_today: int = 0,
        max_drawdown: float | None = None,
        sharpe_ratio: float | None = None,
        win_rate: float | None = None,
        market_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Save a daily portfolio snapshot.

        Args:
            strategy_mode: 'conservative', 'aggressive', 'jp_conservative', or 'jp_aggressive'
            benchmark_daily_pct: Daily return of benchmark index (S&P500 for US, Nikkei 225 for JP)
            benchmark_cumulative_pct: Cumulative return of benchmark index
            market_type: 'us' or 'jp' (auto-derived from strategy_mode if not provided)

        Returns:
            Upserted record
        """
        # Auto-derive market_type from strategy_mode if not provided
        if market_type is None:
            market_type = "jp" if strategy_mode.startswith("jp_") else "us"

        record = {
            "snapshot_date": snapshot_date,
            "strategy_mode": strategy_mode,
            "total_value": total_value,
            "cash_balance": cash_balance,
            "positions_value": positions_value,
            "open_positions": open_positions,
            "closed_today": closed_today,
            "market_type": market_type,
        }

        if daily_pnl is not None:
            record["daily_pnl"] = daily_pnl
        if daily_pnl_pct is not None:
            record["daily_pnl_pct"] = round(daily_pnl_pct, 4)
        if cumulative_pnl is not None:
            record["cumulative_pnl"] = cumulative_pnl
        if cumulative_pnl_pct is not None:
            record["cumulative_pnl_pct"] = round(cumulative_pnl_pct, 4)
        if benchmark_daily_pct is not None:
            record["sp500_daily_pct"] = round(benchmark_daily_pct, 4)
        if benchmark_cumulative_pct is not None:
            record["sp500_cumulative_pct"] = round(benchmark_cumulative_pct, 4)
        if alpha is not None:
            record["alpha"] = round(alpha, 4)
        if max_drawdown is not None:
            record["max_drawdown"] = round(max_drawdown, 4)
        if sharpe_ratio is not None:
            record["sharpe_ratio"] = round(sharpe_ratio, 4)
        if win_rate is not None:
            record["win_rate"] = round(win_rate, 2)

        result = self._client.table("portfolio_daily_snapshot").upsert(
            record,
            on_conflict="snapshot_date,strategy_mode",
        ).execute()

        return result.data[0] if result.data else {}

    # ============ Judgment Records (Layer 2) ============

    def save_judgment_record(
        self,
        symbol: str,
        batch_date: str,
        strategy_mode: str,
        decision: str,
        confidence: float,
        score: int,
        reasoning: dict[str, Any],
        key_factors: list[dict[str, Any]],
        identified_risks: list[str],
        market_regime: str,
        input_summary: str,
        model_version: str,
        prompt_version: str,
        raw_llm_response: str | None = None,
        judged_at: str | None = None,
        market_type: str = "us",
        is_primary: bool = True,
    ) -> dict[str, Any]:
        """
        Save an LLM judgment record to the database.

        Args:
            symbol: Stock ticker symbol
            batch_date: Date of the judgment (YYYY-MM-DD)
            strategy_mode: 'conservative', 'aggressive', 'jp_conservative', or 'jp_aggressive'
            decision: 'buy', 'hold', or 'avoid'
            confidence: Model confidence (0.0-1.0)
            score: Composite score (0-100)
            reasoning: Reasoning trace dict
            key_factors: List of key factor dicts
            identified_risks: List of risk descriptions
            market_regime: Market regime at judgment time
            input_summary: Brief summary of input data
            model_version: Model used for judgment
            prompt_version: Prompt version used
            raw_llm_response: Optional raw response for debugging
            judged_at: Optional timestamp (uses now if not provided)
            market_type: 'us' or 'jp' (default: 'us')
            is_primary: True for primary model, False for shadow models

        Returns:
            Inserted record
        """
        import json

        record = {
            "symbol": symbol,
            "batch_date": batch_date,
            "strategy_mode": strategy_mode,
            "decision": decision,
            "confidence": round(confidence, 4),
            "score": score,
            "reasoning": reasoning,  # Supabase handles JSONB natively
            "key_factors": key_factors,  # Supabase handles JSONB natively
            "identified_risks": identified_risks,  # Supabase handles JSONB natively
            "market_regime": market_regime,
            "input_summary": input_summary,
            "model_version": model_version,
            "prompt_version": prompt_version,
            "market_type": market_type,
            "is_primary": is_primary,
        }

        if raw_llm_response:
            record["raw_llm_response"] = raw_llm_response
        if judged_at:
            record["judged_at"] = judged_at

        result = self._client.table("judgment_records").upsert(
            record,
            on_conflict="symbol,batch_date,strategy_mode,model_version",
        ).execute()

        return result.data[0] if result.data else {}

    def get_judgment_records(
        self,
        batch_date: str | None = None,
        symbol: str | None = None,
        strategy_mode: str | None = None,
        decision: str | None = None,
        min_confidence: float | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get judgment records with optional filters.

        Args:
            batch_date: Optional date filter
            symbol: Optional symbol filter
            strategy_mode: Optional strategy filter
            decision: Optional decision filter
            min_confidence: Optional minimum confidence filter
            limit: Maximum records to return

        Returns:
            List of judgment records
        """
        query = self._client.table("judgment_records").select("*")

        if batch_date:
            query = query.eq("batch_date", batch_date)
        if symbol:
            query = query.eq("symbol", symbol)
        if strategy_mode:
            query = query.eq("strategy_mode", strategy_mode)
        if decision:
            query = query.eq("decision", decision)
        if min_confidence is not None:
            query = query.gte("confidence", min_confidence)

        result = query.order("batch_date", desc=True).limit(limit).execute()
        return result.data or []

    def get_recent_judgments_for_reflection(
        self,
        strategy_mode: str,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """
        Get recent judgments for reflection analysis.

        Args:
            strategy_mode: Strategy to analyze
            days: Number of days to look back

        Returns:
            List of judgment records with outcome data
        """
        from datetime import date, timedelta

        start_date = (date.today() - timedelta(days=days)).isoformat()

        result = self._client.table("judgment_records").select(
            "*, judgment_outcomes(*)"
        ).eq(
            "strategy_mode", strategy_mode
        ).gte(
            "batch_date", start_date
        ).order(
            "batch_date", desc=True
        ).execute()

        return result.data or []

    def save_judgment_outcome(
        self,
        judgment_id: str,
        outcome_date: str,
        actual_return_1d: float | None = None,
        actual_return_5d: float | None = None,
        actual_return_10d: float | None = None,
        outcome_aligned: bool | None = None,
        key_factors_validated: dict[str, Any] | None = None,
        missed_factors: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Save outcome data for a judgment.

        Args:
            judgment_id: UUID of the judgment record
            outcome_date: Date of the outcome measurement
            actual_return_1d: 1-day return
            actual_return_5d: 5-day return
            actual_return_10d: 10-day return
            outcome_aligned: Whether outcome matched prediction
            key_factors_validated: Which factors proved correct
            missed_factors: Factors that were missed

        Returns:
            Inserted/updated record
        """
        import json

        record: dict[str, Any] = {
            "judgment_id": judgment_id,
            "outcome_date": outcome_date,
        }

        if actual_return_1d is not None:
            record["actual_return_1d"] = round(actual_return_1d, 4)
        if actual_return_5d is not None:
            record["actual_return_5d"] = round(actual_return_5d, 4)
        if actual_return_10d is not None:
            record["actual_return_10d"] = round(actual_return_10d, 4)
        if outcome_aligned is not None:
            record["outcome_aligned"] = outcome_aligned
        if key_factors_validated is not None:
            record["key_factors_validated"] = json.dumps(key_factors_validated)
        if missed_factors is not None:
            record["missed_factors"] = json.dumps(missed_factors)

        result = self._client.table("judgment_outcomes").upsert(
            record,
            on_conflict="judgment_id,outcome_date",
        ).execute()

        return result.data[0] if result.data else {}

    def get_recent_ai_lessons(
        self,
        market_type: str = "us",
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Get recent AI lessons for injection into judgment prompts.

        Args:
            market_type: 'us' or 'jp'
            limit: Max lessons to return

        Returns:
            List of lesson dicts with lesson_text, miss_analysis, lesson_date
        """
        try:
            result = self._client.table("ai_lessons").select(
                "lesson_date, lesson_text, miss_analysis, biggest_miss_symbols"
            ).eq(
                "market_type", market_type
            ).order(
                "lesson_date", desc=True
            ).limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.warning(f"Failed to fetch ai_lessons: {e}")
            return []

    def get_latest_weekly_research(self) -> dict[str, Any] | None:
        """Get the most recent weekly research report for judgment context.

        Returns:
            Dict with content, metadata, research_date, symbols_mentioned or None
        """
        try:
            result = self._client.table("research_logs").select(
                "content, metadata, research_date, symbols_mentioned"
            ).eq(
                "research_type", "market"
            ).order(
                "research_date", desc=True
            ).limit(1).execute()
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch weekly research: {e}")
            return None

    def save_reflection_record(
        self,
        reflection_date: str,
        strategy_mode: str,
        reflection_type: str,
        period_start: str,
        period_end: str,
        total_judgments: int,
        correct_judgments: int,
        accuracy_rate: float,
        patterns_identified: dict[str, Any],
        improvement_suggestions: list[dict[str, Any]],
        model_version: str,
        raw_llm_response: str | None = None,
    ) -> dict[str, Any]:
        """
        Save a reflection analysis record.

        Args:
            reflection_date: Date of reflection
            strategy_mode: Strategy being reflected on
            reflection_type: 'weekly', 'monthly', or 'post_trade'
            period_start: Start of analysis period
            period_end: End of analysis period
            total_judgments: Total judgments in period
            correct_judgments: Number of correct judgments
            accuracy_rate: Accuracy percentage (0.0-1.0)
            patterns_identified: Pattern analysis results
            improvement_suggestions: List of suggestions
            model_version: Model used for reflection
            raw_llm_response: Optional raw response

        Returns:
            Inserted record
        """
        import json

        record = {
            "reflection_date": reflection_date,
            "strategy_mode": strategy_mode,
            "reflection_type": reflection_type,
            "period_start": period_start,
            "period_end": period_end,
            "total_judgments": total_judgments,
            "correct_judgments": correct_judgments,
            "accuracy_rate": round(accuracy_rate, 4),
            "patterns_identified": json.dumps(patterns_identified),
            "improvement_suggestions": json.dumps(improvement_suggestions),
            "model_version": model_version,
        }

        if raw_llm_response:
            record["raw_llm_response"] = raw_llm_response

        result = self._client.table("reflection_records").upsert(
            record,
            on_conflict="reflection_date,strategy_mode,reflection_type",
        ).execute()

        return result.data[0] if result.data else {}

    def get_reflection_records(
        self,
        strategy_mode: str | None = None,
        reflection_type: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Get reflection records with optional filters.

        Args:
            strategy_mode: Optional strategy filter
            reflection_type: Optional type filter
            limit: Maximum records to return

        Returns:
            List of reflection records
        """
        query = self._client.table("reflection_records").select("*")

        if strategy_mode:
            query = query.eq("strategy_mode", strategy_mode)
        if reflection_type:
            query = query.eq("reflection_type", reflection_type)

        result = query.order("reflection_date", desc=True).limit(limit).execute()
        return result.data or []

    # ============ Stock Universe ============

    def get_stock_universe(
        self,
        market_type: str | None = None,
        enabled_only: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Get stock universe from database.

        Args:
            market_type: Filter by market type ('us' or 'jp')
            enabled_only: If True, only return enabled symbols

        Returns:
            List of stock universe records
        """
        query = self._client.table("stock_universe").select("*")

        if market_type:
            query = query.eq("market_type", market_type)

        if enabled_only:
            query = query.eq("enabled", True)

        result = query.order("symbol").execute()
        return result.data or []

    def add_symbol_to_universe(
        self,
        symbol: str,
        market_type: str,
        company_name: str | None = None,
        sector: str | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """
        Add a symbol to the stock universe.

        Args:
            symbol: Stock ticker symbol
            market_type: 'us' or 'jp'
            company_name: Optional company name
            sector: Optional sector classification
            enabled: Whether the symbol is enabled for trading

        Returns:
            Inserted/updated record
        """
        record: dict[str, Any] = {
            "symbol": symbol,
            "market_type": market_type,
            "enabled": enabled,
        }

        if company_name:
            record["company_name"] = company_name
        if sector:
            record["sector"] = sector

        result = self._client.table("stock_universe").upsert(
            record,
            on_conflict="symbol,market_type",
        ).execute()

        return result.data[0] if result.data else {}

    def update_symbol_status(
        self,
        symbol: str,
        market_type: str,
        enabled: bool,
    ) -> dict[str, Any]:
        """
        Enable or disable a symbol in the stock universe.

        Args:
            symbol: Stock ticker symbol
            market_type: 'us' or 'jp'
            enabled: New enabled status

        Returns:
            Updated record
        """
        result = self._client.table("stock_universe").update({
            "enabled": enabled,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq(
            "symbol", symbol
        ).eq(
            "market_type", market_type
        ).execute()

        return result.data[0] if result.data else {}

    def remove_symbol_from_universe(
        self,
        symbol: str,
        market_type: str,
    ) -> bool:
        """
        Remove a symbol from the stock universe.

        Args:
            symbol: Stock ticker symbol
            market_type: 'us' or 'jp'

        Returns:
            True if deleted, False otherwise
        """
        result = self._client.table("stock_universe").delete().eq(
            "symbol", symbol
        ).eq(
            "market_type", market_type
        ).execute()

        return len(result.data) > 0 if result.data else False

    def bulk_add_symbols(
        self,
        symbols: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Bulk add symbols to the stock universe.

        Args:
            symbols: List of symbol dicts with keys:
                - symbol: Stock ticker symbol (required)
                - market_type: 'us' or 'jp' (required)
                - company_name: Optional company name
                - sector: Optional sector
                - enabled: Optional enabled status (default True)

        Returns:
            List of inserted/updated records
        """
        records = []
        for s in symbols:
            record = {
                "symbol": s["symbol"],
                "market_type": s["market_type"],
                "enabled": s.get("enabled", True),
            }
            if s.get("company_name"):
                record["company_name"] = s["company_name"]
            if s.get("sector"):
                record["sector"] = s["sector"]
            records.append(record)

        result = self._client.table("stock_universe").upsert(
            records,
            on_conflict="symbol,market_type",
        ).execute()

        return result.data or []

    def get_symbol_count_by_market(self) -> dict[str, int]:
        """
        Get count of enabled symbols by market type.

        Returns:
            Dict with market_type as key and count as value
        """
        result = self._client.table("stock_universe").select(
            "market_type"
        ).eq(
            "enabled", True
        ).execute()

        counts: dict[str, int] = {}
        for row in result.data or []:
            market = row.get("market_type", "unknown")
            counts[market] = counts.get(market, 0) + 1

        return counts

    # ─── Meta-monitor helpers ──────────────────────────────────

    def get_active_prompt_overrides(self, strategy_mode: str) -> list[dict]:
        """Get currently active and non-expired prompt overrides for a strategy.

        Used by judgment prompts to inject dynamic guidance.
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        try:
            result = (
                self._client.table("prompt_overrides")
                .select("id, override_text, reason, expires_at")
                .eq("strategy_mode", strategy_mode)
                .eq("active", True)
                .gt("expires_at", now)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.debug(f"No prompt overrides for {strategy_mode}: {e}")
            return []
