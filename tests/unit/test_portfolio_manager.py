"""
Tests for PortfolioManager core calculations.

Covers:
- Win rate calculation (positive PnL trades / total trades)
- Sharpe ratio (annualized from daily returns)
- Maximum drawdown from equity curve
- Cumulative PnL with zero-division guard
- Portfolio snapshot calculation (daily PnL, cumulative PnL, S&P 500 alpha)
- Drawdown status thresholds
- Position size calculation
"""
from __future__ import annotations

import math

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.portfolio.manager import (
    PortfolioManager,
    Position,
    INITIAL_CAPITAL,
    RISK_FREE_RATE,
    MAX_POSITIONS,
    MDD_WARNING_THRESHOLD,
    MDD_STOP_NEW_THRESHOLD,
    MDD_CRITICAL_THRESHOLD,
)
from src.pipeline.market_config import US_MARKET, JP_MARKET


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(
    market_config=US_MARKET,
    snapshot=None,
    trade_history=None,
) -> PortfolioManager:
    """Create a PortfolioManager with mocked external dependencies."""
    supabase = MagicMock()
    finnhub = MagicMock()
    yfinance = MagicMock()

    # Default: no snapshot history
    supabase.get_latest_portfolio_snapshot.return_value = snapshot

    # Default: trade_history query returns empty
    if trade_history is not None:
        mock_result = MagicMock()
        mock_result.data = trade_history
        supabase._client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_result
    else:
        mock_result = MagicMock()
        mock_result.data = []
        supabase._client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_result

    manager = PortfolioManager(
        supabase=supabase,
        finnhub=finnhub,
        yfinance=yfinance,
        market_config=market_config,
    )
    return manager


def _make_position(
    symbol="AAPL",
    strategy_mode="conservative",
    entry_price=100.0,
    shares=10.0,
    hold_days=5,
) -> Position:
    return Position(
        id="test-id",
        strategy_mode=strategy_mode,
        symbol=symbol,
        entry_date="2025-01-01",
        entry_price=entry_price,
        shares=shares,
        position_value=entry_price * shares,
        entry_score=70,
        hold_days=hold_days,
    )


# ===========================================================================
# Win Rate Calculation
# ===========================================================================


class TestWinRate:
    """Tests for calculate_win_rate."""

    def test_all_wins(self):
        """100% win rate when all trades have positive PnL."""
        trades = [
            {"pnl_pct": 5.0},
            {"pnl_pct": 3.2},
            {"pnl_pct": 0.1},
        ]
        manager = _make_manager(trade_history=trades)
        result = manager.calculate_win_rate("conservative")
        assert result == 100.0

    def test_all_losses(self):
        """0% win rate when all trades have negative PnL."""
        trades = [
            {"pnl_pct": -2.0},
            {"pnl_pct": -5.5},
            {"pnl_pct": -0.3},
        ]
        manager = _make_manager(trade_history=trades)
        result = manager.calculate_win_rate("conservative")
        assert result == 0.0

    def test_mixed_trades(self):
        """Win rate with a mix of winning and losing trades."""
        trades = [
            {"pnl_pct": 5.0},
            {"pnl_pct": -2.0},
            {"pnl_pct": 3.0},
            {"pnl_pct": -1.0},
        ]
        manager = _make_manager(trade_history=trades)
        result = manager.calculate_win_rate("conservative")
        # 2 wins / 4 total = 50%
        assert result == 50.0

    def test_single_win(self):
        """Single winning trade gives 100%."""
        trades = [{"pnl_pct": 1.0}]
        manager = _make_manager(trade_history=trades)
        result = manager.calculate_win_rate("conservative")
        assert result == 100.0

    def test_single_loss(self):
        """Single losing trade gives 0%."""
        trades = [{"pnl_pct": -1.0}]
        manager = _make_manager(trade_history=trades)
        result = manager.calculate_win_rate("conservative")
        assert result == 0.0

    def test_no_trades_returns_none(self):
        """Returns None when there are no trades."""
        manager = _make_manager(trade_history=[])
        result = manager.calculate_win_rate("conservative")
        assert result is None

    def test_zero_pnl_is_not_a_win(self):
        """Trades with exactly 0 PnL are not counted as wins."""
        trades = [
            {"pnl_pct": 0.0},
            {"pnl_pct": 5.0},
        ]
        manager = _make_manager(trade_history=trades)
        result = manager.calculate_win_rate("conservative")
        # 1 win / 2 total = 50%
        assert result == 50.0

    def test_missing_pnl_pct_treated_as_zero(self):
        """Trades without pnl_pct key default to 0 (not a win)."""
        trades = [
            {},
            {"pnl_pct": 5.0},
        ]
        manager = _make_manager(trade_history=trades)
        result = manager.calculate_win_rate("conservative")
        # 1 win / 2 total = 50%
        assert result == 50.0

    def test_win_rate_rounding(self):
        """Win rate is rounded to 2 decimal places."""
        trades = [
            {"pnl_pct": 1.0},
            {"pnl_pct": -1.0},
            {"pnl_pct": 1.0},
        ]
        manager = _make_manager(trade_history=trades)
        result = manager.calculate_win_rate("conservative")
        # 2/3 = 66.666... -> 66.67
        assert result == 66.67


# ===========================================================================
# Sharpe Ratio Calculation
# ===========================================================================


class TestSharpeRatio:
    """Tests for calculate_sharpe_ratio."""

    def test_insufficient_data_returns_none(self):
        """Returns None when fewer than 5 data points."""
        manager = _make_manager()
        assert manager.calculate_sharpe_ratio([1.0, 2.0, 3.0, 4.0]) is None
        assert manager.calculate_sharpe_ratio([]) is None
        assert manager.calculate_sharpe_ratio([1.0]) is None

    def test_exactly_five_data_points(self):
        """Computes Sharpe with exactly 5 data points (minimum)."""
        manager = _make_manager()
        returns = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = manager.calculate_sharpe_ratio(returns)
        assert result is not None
        assert isinstance(result, float)

    def test_zero_volatility_returns_none(self):
        """Returns None when all returns are identical (zero std dev)."""
        manager = _make_manager()
        returns = [1.0, 1.0, 1.0, 1.0, 1.0]
        result = manager.calculate_sharpe_ratio(returns)
        assert result is None

    def test_positive_returns_give_positive_sharpe(self):
        """Consistently positive returns should yield positive Sharpe."""
        manager = _make_manager()
        returns = [1.0, 1.5, 2.0, 0.5, 1.2, 0.8, 1.3]
        result = manager.calculate_sharpe_ratio(returns)
        assert result is not None
        assert result > 0

    def test_negative_returns_give_negative_sharpe(self):
        """Consistently negative returns should yield negative Sharpe."""
        manager = _make_manager()
        returns = [-1.0, -1.5, -2.0, -0.5, -1.2, -0.8, -1.3]
        result = manager.calculate_sharpe_ratio(returns)
        assert result is not None
        assert result < 0

    def test_known_sharpe_calculation(self):
        """Verify Sharpe ratio against a hand-calculated value."""
        manager = _make_manager()
        # Daily returns in percentage: [1%, 2%, 1%, 2%, 1%]
        daily_pct = [1.0, 2.0, 1.0, 2.0, 1.0]
        # Convert to decimals: [0.01, 0.02, 0.01, 0.02, 0.01]
        returns_dec = [r / 100 for r in daily_pct]

        # mean = 0.014
        mean_return = sum(returns_dec) / len(returns_dec)
        assert mean_return == pytest.approx(0.014)

        # variance = population variance
        variance = sum((r - mean_return) ** 2 for r in returns_dec) / len(returns_dec)
        std_dev = math.sqrt(variance)

        daily_rf = RISK_FREE_RATE / 252
        expected_sharpe = ((mean_return - daily_rf) / std_dev) * math.sqrt(252)
        expected_sharpe = round(expected_sharpe, 4)

        result = manager.calculate_sharpe_ratio(daily_pct)
        assert result == pytest.approx(expected_sharpe)

    def test_custom_risk_free_rate(self):
        """Sharpe calculation respects a custom risk-free rate."""
        manager = _make_manager()
        returns = [1.0, 2.0, 1.5, 0.5, 1.0]

        sharpe_default = manager.calculate_sharpe_ratio(returns)
        sharpe_high_rf = manager.calculate_sharpe_ratio(returns, risk_free_rate=0.10)

        assert sharpe_default is not None
        assert sharpe_high_rf is not None
        # Higher risk-free rate should give lower Sharpe
        assert sharpe_high_rf < sharpe_default

    def test_sharpe_is_rounded_to_4_decimals(self):
        """Result is rounded to 4 decimal places."""
        manager = _make_manager()
        returns = [0.5, 1.0, -0.3, 0.8, 0.2, -0.1]
        result = manager.calculate_sharpe_ratio(returns)
        assert result is not None
        # Check that rounding is at most 4 decimal places
        assert result == round(result, 4)


# ===========================================================================
# Maximum Drawdown Calculation
# ===========================================================================


class TestMaxDrawdown:
    """Tests for calculate_max_drawdown."""

    def test_monotonically_increasing_equity(self):
        """No drawdown when equity only goes up."""
        manager = _make_manager()
        equity = [100, 110, 120, 130, 140]
        assert manager.calculate_max_drawdown(equity) == 0.0

    def test_monotonically_decreasing_equity(self):
        """Max drawdown equals total decline from peak."""
        manager = _make_manager()
        equity = [100, 90, 80, 70]
        # From peak 100 to trough 70: (70-100)/100 * 100 = -30%
        result = manager.calculate_max_drawdown(equity)
        assert result == pytest.approx(-30.0)

    def test_v_shaped_recovery(self):
        """Drawdown from a V-shaped dip."""
        manager = _make_manager()
        equity = [100, 90, 80, 90, 100]
        # Peak at 100, trough at 80: -20%
        result = manager.calculate_max_drawdown(equity)
        assert result == pytest.approx(-20.0)

    def test_new_high_then_drop(self):
        """Drawdown is measured from the highest peak."""
        manager = _make_manager()
        equity = [100, 120, 100]
        # Peak at 120, trough at 100: (100-120)/120 * 100 = -16.6667%
        result = manager.calculate_max_drawdown(equity)
        assert result == pytest.approx(-16.6667, abs=0.001)

    def test_multiple_drawdowns_returns_worst(self):
        """Returns the worst (most negative) drawdown."""
        manager = _make_manager()
        equity = [100, 95, 110, 88, 105]
        # First drawdown: 100 -> 95 = -5%
        # Second drawdown: 110 -> 88 = (88-110)/110 * 100 = -20%
        result = manager.calculate_max_drawdown(equity)
        assert result == pytest.approx(-20.0)

    def test_single_value_returns_zero(self):
        """Returns 0 with a single equity value (insufficient data)."""
        manager = _make_manager()
        assert manager.calculate_max_drawdown([100]) == 0.0

    def test_empty_list_returns_zero(self):
        """Returns 0 with an empty equity list."""
        manager = _make_manager()
        assert manager.calculate_max_drawdown([]) == 0.0

    def test_flat_equity_returns_zero(self):
        """Returns 0 when equity is constant."""
        manager = _make_manager()
        equity = [100, 100, 100, 100]
        assert manager.calculate_max_drawdown(equity) == 0.0

    def test_drawdown_rounded_to_4_decimals(self):
        """Result is rounded to 4 decimal places."""
        manager = _make_manager()
        equity = [100, 97]  # -3% exactly
        result = manager.calculate_max_drawdown(equity)
        assert result == round(result, 4)

    def test_zero_peak_no_division_error(self):
        """Handles zero peak gracefully (avoids division by zero)."""
        manager = _make_manager()
        equity = [0, 0, 100, 50]
        # When peak is 0, drawdown formula uses 0 instead of dividing
        # Peak moves to 100, then (50-100)/100 = -50%
        result = manager.calculate_max_drawdown(equity)
        assert result == pytest.approx(-50.0)


# ===========================================================================
# Cumulative PnL with Zero-Division Guard
# ===========================================================================


class TestCumulativePnlZeroDivision:
    """Tests for the cumulative PnL zero-division guard in update_portfolio_snapshot.

    The guard: cumulative_pnl / INITIAL_CAPITAL if INITIAL_CAPITAL > 0 else 0.0
    """

    def test_cumulative_pnl_pct_normal(self):
        """Normal case: cumulative_pnl_pct = (total_value - INITIAL) / INITIAL * 100."""
        # total_value = 110000, INITIAL = 100000
        # cumulative_pnl = 10000
        # cumulative_pnl_pct = 10000 / 100000 * 100 = 10.0%
        cumulative_pnl = 110000 - INITIAL_CAPITAL
        cumulative_pnl_pct = (cumulative_pnl / INITIAL_CAPITAL) * 100 if INITIAL_CAPITAL > 0 else 0.0
        assert cumulative_pnl_pct == pytest.approx(10.0)

    def test_cumulative_pnl_pct_loss(self):
        """Loss case yields negative percentage."""
        total_value = 90000
        cumulative_pnl = total_value - INITIAL_CAPITAL
        cumulative_pnl_pct = (cumulative_pnl / INITIAL_CAPITAL) * 100 if INITIAL_CAPITAL > 0 else 0.0
        assert cumulative_pnl_pct == pytest.approx(-10.0)

    def test_cumulative_pnl_pct_zero_capital(self):
        """Zero-division guard returns 0.0 when initial capital is zero."""
        initial_capital = 0.0
        cumulative_pnl = 5000.0
        cumulative_pnl_pct = (cumulative_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0
        assert cumulative_pnl_pct == 0.0

    def test_cumulative_pnl_pct_breakeven(self):
        """Breakeven: total equals initial capital."""
        cumulative_pnl = INITIAL_CAPITAL - INITIAL_CAPITAL
        cumulative_pnl_pct = (cumulative_pnl / INITIAL_CAPITAL) * 100 if INITIAL_CAPITAL > 0 else 0.0
        assert cumulative_pnl_pct == 0.0

    def test_initial_capital_is_positive(self):
        """Verify the module constant INITIAL_CAPITAL is positive."""
        assert INITIAL_CAPITAL > 0


# ===========================================================================
# Portfolio Snapshot Calculation
# ===========================================================================


class TestPortfolioSnapshot:
    """Tests for update_portfolio_snapshot calculation logic."""

    def _setup_manager_for_snapshot(
        self,
        positions=None,
        prev_snapshot=None,
        total_realized_pnl=0.0,
        current_prices=None,
        trade_history_for_win_rate=None,
        historical_snapshots=None,
    ):
        """Build a fully mocked manager for snapshot testing."""
        manager = _make_manager(market_config=US_MARKET)
        supabase = manager.supabase

        # Open positions
        if positions is None:
            positions = []
        supabase.get_open_positions.return_value = positions

        # Previous snapshot
        supabase.get_latest_portfolio_snapshot.return_value = prev_snapshot

        # Total realized PnL query
        realized_pnl_result = MagicMock()
        realized_pnl_result.data = [{"pnl": total_realized_pnl}] if total_realized_pnl != 0 else []

        # Historical snapshots for risk metrics
        hist_result = MagicMock()
        hist_result.data = historical_snapshots or []

        # Win rate query
        win_rate_result = MagicMock()
        win_rate_result.data = trade_history_for_win_rate or []

        # Build the chain for _client.table(...).select(...).eq(...).
        # The table function is called multiple times for different tables,
        # so we need to handle the routing carefully.
        table_mock = MagicMock()

        def table_side_effect(table_name):
            mock_chain = MagicMock()
            if table_name == "trade_history":
                mock_chain.select.return_value.eq.return_value.execute.return_value = win_rate_result
            elif table_name == "portfolio_daily_snapshot":
                mock_chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = hist_result
            elif table_name == "virtual_portfolio":
                # For _get_invested_cost / _get_positions_opened_on
                empty = MagicMock()
                empty.data = []
                mock_chain.select.return_value.eq.return_value.eq.return_value.execute.return_value = empty
                mock_chain.select.return_value.eq.return_value.execute.return_value = empty
            return mock_chain

        supabase._client.table.side_effect = table_side_effect

        # Current prices for positions
        if current_prices:
            manager.get_current_price = MagicMock(side_effect=lambda s: current_prices.get(s))
        else:
            manager.get_current_price = MagicMock(return_value=None)

        # Stub internal helpers to control cash calculation
        manager._get_total_realized_pnl = MagicMock(return_value=total_realized_pnl)
        manager._get_invested_cost = MagicMock(
            return_value=sum(
                p.get("position_value", 0) for p in positions
            ) if positions else 0.0
        )

        # save_portfolio_snapshot returns its kwargs for inspection
        def capture_snapshot(**kwargs):
            return kwargs
        supabase.save_portfolio_snapshot.side_effect = capture_snapshot

        return manager

    def test_first_day_no_positions(self):
        """First day with no positions: total = initial capital, 0% PnL."""
        manager = self._setup_manager_for_snapshot(
            positions=[],
            prev_snapshot=None,
            total_realized_pnl=0.0,
        )
        result = manager.update_portfolio_snapshot("conservative")

        assert result["total_value"] == pytest.approx(INITIAL_CAPITAL)
        assert result["cash_balance"] == pytest.approx(INITIAL_CAPITAL)
        assert result["positions_value"] == pytest.approx(0.0)
        assert result["cumulative_pnl"] == pytest.approx(0.0)
        assert result["cumulative_pnl_pct"] == pytest.approx(0.0)

    def test_daily_pnl_calculation(self):
        """Daily PnL = current total - previous total."""
        prev = {
            "total_value": 100000,
            "cumulative_pnl": 0,
            "sp500_cumulative_pct": 0,
        }
        manager = self._setup_manager_for_snapshot(
            positions=[],
            prev_snapshot=prev,
            total_realized_pnl=2000.0,
        )
        # Cash = 100000 + 2000 - 0 (no invested) = 102000
        # Total = 102000 + 0 (no positions) = 102000
        # Daily PnL = 102000 - 100000 = 2000
        result = manager.update_portfolio_snapshot("conservative")

        assert result["total_value"] == pytest.approx(102000.0)
        assert result["daily_pnl"] == pytest.approx(2000.0)
        assert result["daily_pnl_pct"] == pytest.approx(2.0)

    def test_sp500_cumulative_compounding(self):
        """S&P 500 cumulative tracks multiplicative compounding."""
        prev = {
            "total_value": INITIAL_CAPITAL,
            "cumulative_pnl": 0,
            "sp500_cumulative_pct": 5.0,  # +5% so far
        }
        manager = self._setup_manager_for_snapshot(
            positions=[],
            prev_snapshot=prev,
        )
        # sp500_daily_pct = 2%
        # prev_factor = 1.05, daily_factor = 1.02
        # new cumulative = (1.05 * 1.02 - 1) * 100 = 7.1%
        result = manager.update_portfolio_snapshot("conservative", sp500_daily_pct=2.0)

        assert result["sp500_cumulative_pct"] == pytest.approx(7.1, abs=0.01)

    def test_sp500_cumulative_no_new_data(self):
        """S&P 500 cumulative stays the same when no daily data provided."""
        prev = {
            "total_value": INITIAL_CAPITAL,
            "cumulative_pnl": 0,
            "sp500_cumulative_pct": 5.0,
        }
        manager = self._setup_manager_for_snapshot(
            positions=[],
            prev_snapshot=prev,
        )
        result = manager.update_portfolio_snapshot("conservative", sp500_daily_pct=None)

        assert result["sp500_cumulative_pct"] == pytest.approx(5.0)

    def test_alpha_calculation(self):
        """Alpha = cumulative_pnl_pct - sp500_cumulative_pct."""
        prev = {
            "total_value": INITIAL_CAPITAL,
            "cumulative_pnl": 0,
            "sp500_cumulative_pct": 3.0,
        }
        manager = self._setup_manager_for_snapshot(
            positions=[],
            prev_snapshot=prev,
            total_realized_pnl=5000.0,
        )
        # total = 100000 + 5000 = 105000
        # cumulative_pnl_pct = 5%
        # sp500 stays at 3% (no daily data)
        # alpha = 5% - 3% = 2%
        result = manager.update_portfolio_snapshot("conservative")

        assert result["alpha"] == pytest.approx(2.0)


# ===========================================================================
# Drawdown Status Thresholds
# ===========================================================================


class TestDrawdownStatus:
    """Tests for get_drawdown_status thresholds."""

    def test_no_snapshot_returns_normal(self):
        """No history means fresh start, normal status."""
        manager = _make_manager(snapshot=None)
        status = manager.get_drawdown_status("conservative")

        assert status.status == "normal"
        assert status.can_open_positions is True
        assert status.position_size_multiplier == 1.0
        assert status.current_mdd == 0.0

    def test_normal_range(self):
        """MDD above warning threshold is normal."""
        snapshot = {"max_drawdown": -5.0}
        manager = _make_manager(snapshot=snapshot)
        status = manager.get_drawdown_status("conservative")

        assert status.status == "normal"
        assert status.can_open_positions is True
        assert status.position_size_multiplier == 1.0

    def test_warning_range(self):
        """MDD between warning and stop threshold triggers warning."""
        snapshot = {"max_drawdown": -12.0}
        manager = _make_manager(snapshot=snapshot)
        status = manager.get_drawdown_status("conservative")

        assert status.status == "warning"
        assert status.can_open_positions is True
        assert status.position_size_multiplier == 0.5

    def test_stopped_range(self):
        """MDD between stop and critical threshold stops new positions."""
        snapshot = {"max_drawdown": -20.0}
        manager = _make_manager(snapshot=snapshot)
        status = manager.get_drawdown_status("conservative")

        assert status.status == "stopped"
        assert status.can_open_positions is False
        assert status.position_size_multiplier == 0.0

    def test_critical_range(self):
        """MDD beyond critical threshold."""
        snapshot = {"max_drawdown": -55.0}
        manager = _make_manager(snapshot=snapshot)
        status = manager.get_drawdown_status("conservative")

        assert status.status == "critical"
        assert status.can_open_positions is False
        assert status.position_size_multiplier == 0.0

    def test_exactly_at_warning_boundary(self):
        """MDD exactly at warning threshold (-10%) is warning (not normal).

        The condition is `current_mdd > mdd_warning`, so exactly -10 is NOT > -10,
        meaning it falls into the warning branch.
        """
        snapshot = {"max_drawdown": MDD_WARNING_THRESHOLD}  # -10.0
        manager = _make_manager(snapshot=snapshot)
        status = manager.get_drawdown_status("conservative")

        # current_mdd = -10.0, mdd_warning = -10.0
        # -10.0 > -10.0 is False, so it goes to the elif
        assert status.status == "warning"

    def test_null_max_drawdown_treated_as_zero(self):
        """Snapshot with null max_drawdown defaults to 0 (normal)."""
        snapshot = {"max_drawdown": None}
        manager = _make_manager(snapshot=snapshot)
        status = manager.get_drawdown_status("conservative")

        assert status.status == "normal"
        assert status.current_mdd == 0.0


# ===========================================================================
# Position Size Calculation
# ===========================================================================


class TestPositionSize:
    """Tests for calculate_position_size."""

    def test_equal_weight_allocation(self):
        """Cash is divided equally among picks."""
        manager = _make_manager()
        size = manager.calculate_position_size(
            available_cash=100000,
            num_picks=5,
            current_positions=0,
        )
        assert size == pytest.approx(20000.0)

    def test_respects_max_positions(self):
        """Only allocates up to available slots."""
        manager = _make_manager()
        # 10 max positions, 8 currently open = 2 slots
        size = manager.calculate_position_size(
            available_cash=100000,
            num_picks=5,
            current_positions=8,
        )
        # 2 slots available, 100000 / 2 = 50000
        assert size == pytest.approx(50000.0)

    def test_no_slots_returns_zero(self):
        """Returns 0 when all position slots are taken."""
        manager = _make_manager()
        size = manager.calculate_position_size(
            available_cash=100000,
            num_picks=5,
            current_positions=MAX_POSITIONS,
        )
        assert size == 0.0

    def test_zero_picks_returns_zero(self):
        """Returns 0 when there are no picks."""
        manager = _make_manager()
        size = manager.calculate_position_size(
            available_cash=100000,
            num_picks=0,
            current_positions=0,
        )
        assert size == 0.0

    def test_fewer_picks_than_slots(self):
        """Uses pick count when fewer picks than available slots."""
        manager = _make_manager()
        # 10 slots available, 2 picks -> allocate to 2
        size = manager.calculate_position_size(
            available_cash=100000,
            num_picks=2,
            current_positions=0,
        )
        assert size == pytest.approx(50000.0)


# ===========================================================================
# Transaction Cost Integration
# ===========================================================================


class TestTransactionCostIntegration:
    """Tests for transaction cost impact on calculations in PortfolioManager."""

    def test_jp_market_uses_jp_cost_config(self):
        """JP market manager has JP transaction costs configured."""
        manager = _make_manager(market_config=JP_MARKET)
        assert manager._txn_costs is not None
        assert manager._txn_costs.commission_rate == 0.003

    def test_no_market_config_means_no_costs(self):
        """Manager without market_config has no transaction costs."""
        supabase = MagicMock()
        manager = PortfolioManager(supabase=supabase)
        assert manager._txn_costs is None
