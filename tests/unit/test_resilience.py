"""Tests for system resilience to missed daily runs.

Covers:
- Portfolio snapshot cash calculation (first principles, gap-resilient)
- Unprocessed outcome date detection for backfill
- Batch gap detection logging
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock

from src.pipeline.review import (
    get_unprocessed_outcome_dates,
    check_batch_gap,
)


# ─── Cash balance first-principles tests ──────────────────


class TestCashFirstPrinciples:
    """Test that portfolio snapshot uses first-principles cash calculation."""

    def _make_manager(self, realized_pnl=0.0, invested_cost=0.0, positions=None):
        """Create a PortfolioManager with mocked dependencies."""
        from src.portfolio.manager import PortfolioManager, INITIAL_CAPITAL

        manager = PortfolioManager.__new__(PortfolioManager)
        manager.supabase = MagicMock()
        manager._finnhub = None
        manager._yfinance = MagicMock()
        manager._txn_costs = {"base_fee": 0, "rate": 0}

        # Mock helpers
        manager._get_total_realized_pnl = MagicMock(return_value=realized_pnl)
        manager._get_invested_cost = MagicMock(return_value=invested_cost)
        manager.get_open_positions = MagicMock(return_value=positions or [])
        manager.get_current_price = MagicMock(return_value=None)
        manager._get_params = MagicMock(return_value={
            "position_size_pct": 0.10,
            "max_positions": 10,
            "absolute_max_hold_days": 15,
            "stop_loss_pct": 7.0,
            "take_profit_pct": 15.0,
        })

        # save_portfolio_snapshot should return its kwargs as a dict
        manager.supabase.save_portfolio_snapshot = MagicMock(
            side_effect=lambda **kwargs: kwargs
        )

        # Historical snapshots query for risk metrics (return empty)
        (
            manager.supabase._client.table.return_value
            .select.return_value
            .eq.return_value
            .order.return_value
            .limit.return_value
            .execute.return_value
        ).data = []

        return manager, INITIAL_CAPITAL

    def test_cash_no_positions_no_trades(self):
        """First snapshot with no activity: cash = INITIAL_CAPITAL."""
        manager, initial = self._make_manager()
        manager.supabase.get_latest_portfolio_snapshot.return_value = None

        result = manager.update_portfolio_snapshot("conservative")

        expected_cash = initial
        assert result["cash_balance"] == expected_cash

    def test_cash_with_open_positions(self):
        """Cash = INITIAL - invested_cost when positions are open."""
        manager, initial = self._make_manager(
            realized_pnl=0.0,
            invested_cost=30000.0,
        )
        manager.supabase.get_latest_portfolio_snapshot.return_value = None

        result = manager.update_portfolio_snapshot("conservative")

        expected_cash = initial + 0.0 - 30000.0  # 70000
        assert result["cash_balance"] == expected_cash

    def test_cash_with_realized_pnl(self):
        """Cash includes realized profits from closed trades."""
        manager, initial = self._make_manager(
            realized_pnl=5000.0,
            invested_cost=20000.0,
        )
        manager.supabase.get_latest_portfolio_snapshot.return_value = None

        result = manager.update_portfolio_snapshot("conservative")

        expected_cash = initial + 5000.0 - 20000.0  # 85000
        assert result["cash_balance"] == expected_cash

    def test_cash_after_skipped_day(self):
        """Cash is correct even when previous snapshot is 3 days old."""
        manager, initial = self._make_manager(
            realized_pnl=2000.0,
            invested_cost=15000.0,
        )
        # Previous snapshot is from 3 days ago with stale cash
        manager.supabase.get_latest_portfolio_snapshot.return_value = {
            "snapshot_date": "2026-02-06",  # 3 days ago
            "total_value": 95000,
            "cash_balance": 80000,  # Stale value — should NOT be used
            "cumulative_pnl": -5000,
            "sp500_cumulative_pct": 1.5,
        }

        result = manager.update_portfolio_snapshot("conservative")

        # Cash should be from first principles, NOT from prev_snapshot
        expected_cash = initial + 2000.0 - 15000.0  # 87000
        assert result["cash_balance"] == expected_cash

    def test_cash_all_positions_closed(self):
        """When all positions are closed: cash = INITIAL + realized_pnl."""
        manager, initial = self._make_manager(
            realized_pnl=12000.0,
            invested_cost=0.0,  # No open positions
        )
        manager.supabase.get_latest_portfolio_snapshot.return_value = {
            "snapshot_date": "2026-02-08",
            "total_value": 112000,
            "cash_balance": 112000,
            "cumulative_pnl": 12000,
            "sp500_cumulative_pct": 2.0,
        }

        result = manager.update_portfolio_snapshot("conservative")

        expected_cash = initial + 12000.0 - 0.0  # 112000
        assert result["cash_balance"] == expected_cash


# ─── Unprocessed outcome dates tests ──────────────────


class TestGetUnprocessedOutcomeDates:
    """Test detection of missed judgment outcome dates."""

    def test_no_missing_dates(self):
        """When all outcomes exist, returns empty list."""
        supabase = MagicMock()
        supabase._client.table.return_value.select.return_value.gte.return_value.lte.return_value.execute.return_value.data = [
            {
                "id": "j1",
                "batch_date": "2026-02-01",
                "judgment_outcomes": [{"actual_return_5d": 2.5}],
            },
            {
                "id": "j2",
                "batch_date": "2026-02-01",
                "judgment_outcomes": [{"actual_return_5d": -1.0}],
            },
        ]

        result = get_unprocessed_outcome_dates(supabase, return_field="5d")
        assert result == []

    def test_detects_missing_5d_outcome(self):
        """Finds dates where actual_return_5d is NULL."""
        supabase = MagicMock()
        supabase._client.table.return_value.select.return_value.gte.return_value.lte.return_value.execute.return_value.data = [
            {
                "id": "j1",
                "batch_date": "2026-02-01",
                "judgment_outcomes": [{"actual_return_5d": 2.5}],
            },
            {
                "id": "j2",
                "batch_date": "2026-02-02",
                "judgment_outcomes": [],  # Missing!
            },
            {
                "id": "j3",
                "batch_date": "2026-02-03",
                "judgment_outcomes": [{"actual_return_5d": None}],  # NULL
            },
        ]

        result = get_unprocessed_outcome_dates(supabase, return_field="5d")
        assert "2026-02-02" in result
        assert "2026-02-03" in result
        assert "2026-02-01" not in result

    def test_detects_missing_1d_outcome(self):
        """Finds dates where actual_return_1d is NULL."""
        supabase = MagicMock()
        supabase._client.table.return_value.select.return_value.gte.return_value.lte.return_value.execute.return_value.data = [
            {
                "id": "j1",
                "batch_date": "2026-02-05",
                "judgment_outcomes": [{"actual_return_1d": None}],
            },
        ]

        result = get_unprocessed_outcome_dates(supabase, return_field="1d", min_age_days=1)
        assert "2026-02-05" in result

    def test_handles_exception_gracefully(self):
        """Returns empty list on DB error."""
        supabase = MagicMock()
        supabase._client.table.side_effect = Exception("DB error")

        result = get_unprocessed_outcome_dates(supabase)
        assert result == []

    def test_returns_sorted_dates(self):
        """Dates should be sorted ascending."""
        supabase = MagicMock()
        supabase._client.table.return_value.select.return_value.gte.return_value.lte.return_value.execute.return_value.data = [
            {"id": "j1", "batch_date": "2026-02-03", "judgment_outcomes": []},
            {"id": "j2", "batch_date": "2026-02-01", "judgment_outcomes": []},
            {"id": "j3", "batch_date": "2026-02-02", "judgment_outcomes": []},
        ]

        result = get_unprocessed_outcome_dates(supabase, return_field="5d")
        assert result == ["2026-02-01", "2026-02-02", "2026-02-03"]


# ─── Batch gap detection tests ──────────────────


class TestCheckBatchGap:
    """Test batch gap detection logging."""

    def test_no_history_returns_none(self):
        """Returns None when no batch history exists."""
        supabase = MagicMock()
        # Chain: table.select.eq(batch_type).in_(status).eq(metadata->>market).order.limit.execute
        supabase._client.table.return_value.select.return_value.eq.return_value.in_.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []

        result = check_batch_gap(supabase, market_type="us")
        assert result is None

    def test_detects_gap(self):
        """Detects multi-day gap from last successful run."""
        supabase = MagicMock()
        three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        supabase._client.table.return_value.select.return_value.eq.return_value.in_.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
            {"started_at": three_days_ago, "status": "success"},
        ]

        result = check_batch_gap(supabase, market_type="us")
        assert result == 3

    def test_no_gap(self):
        """Returns 0-1 when last run was recent."""
        supabase = MagicMock()
        today = datetime.now(timezone.utc).isoformat()
        supabase._client.table.return_value.select.return_value.eq.return_value.in_.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
            {"started_at": today, "status": "success"},
        ]

        result = check_batch_gap(supabase, market_type="jp")
        assert result is not None
        assert result <= 1

    def test_handles_exception_gracefully(self):
        """Returns None on DB error."""
        supabase = MagicMock()
        supabase._client.table.side_effect = Exception("DB error")

        result = check_batch_gap(supabase)
        assert result is None
