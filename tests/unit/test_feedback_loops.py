"""
Tests for learning feedback loop functions.

Covers:
- build_performance_stats: Structured data aggregation from judgment_outcomes
- adjust_factor_weights: Automatic factor weight adjustment based on correlations
"""
import pytest
from unittest.mock import MagicMock, patch

from src.pipeline.review import (
    build_performance_stats,
    adjust_factor_weights,
    WEIGHT_MIN,
    WEIGHT_MAX,
    WEIGHT_MAX_DELTA,
    V1_FACTOR_KEYS,
    V2_FACTOR_KEYS,
)


class TestBuildPerformanceStats:
    """Tests for build_performance_stats."""

    def _mock_outcomes(self, supabase, rows):
        """Set up mock to return judgment_outcomes data."""
        mock_result = MagicMock()
        mock_result.data = rows
        (
            supabase._client.table.return_value
            .select.return_value
            .gte.return_value
            .execute.return_value
        ) = mock_result

    def test_returns_empty_on_insufficient_data(self):
        supabase = MagicMock()
        self._mock_outcomes(supabase, [
            {
                "actual_return_5d": 2.0,
                "outcome_aligned": True,
                "judgment_records": {"symbol": "AAPL", "strategy_mode": "conservative", "decision": "buy", "batch_date": "2025-01-01"},
            }
        ])  # Only 1 row, need >= 5

        result = build_performance_stats(supabase, "conservative", days=30)
        assert result == {}

    def test_calculates_buy_stats(self):
        supabase = MagicMock()
        rows = [
            {
                "actual_return_5d": 3.0,
                "outcome_aligned": True,
                "judgment_records": {"symbol": f"S{i}", "strategy_mode": "conservative", "decision": "buy", "batch_date": "2025-01-01"},
            }
            for i in range(4)
        ] + [
            {
                "actual_return_5d": -2.0,
                "outcome_aligned": False,
                "judgment_records": {"symbol": "S4", "strategy_mode": "conservative", "decision": "buy", "batch_date": "2025-01-01"},
            }
        ] + [
            {
                "actual_return_5d": -1.0,
                "outcome_aligned": True,
                "judgment_records": {"symbol": "S5", "strategy_mode": "conservative", "decision": "avoid", "batch_date": "2025-01-01"},
            }
        ]
        self._mock_outcomes(supabase, rows)

        result = build_performance_stats(supabase, "conservative", days=30)
        assert result["buy_count"] == 5
        assert result["buy_win_count"] == 4
        assert result["buy_win_rate"] == 80.0
        # avg return = (3*4 + (-2)) / 5 = 10/5 = 2.0
        assert result["buy_avg_return"] == 2.0

    def test_skip_records_excluded_from_buy_stats(self):
        """Skip/avoid records should not be counted in buy stats."""
        supabase = MagicMock()
        rows = [
            {
                "actual_return_5d": -3.0,
                "outcome_aligned": True,
                "judgment_records": {"symbol": f"A{i}", "strategy_mode": "aggressive", "decision": "skip", "batch_date": "2025-01-01"},
            }
            for i in range(4)
        ] + [
            {
                "actual_return_5d": 2.0,
                "outcome_aligned": True,
                "judgment_records": {"symbol": "B0", "strategy_mode": "aggressive", "decision": "buy", "batch_date": "2025-01-01"},
            },
            {
                "actual_return_5d": 3.0,
                "outcome_aligned": True,
                "judgment_records": {"symbol": "B1", "strategy_mode": "aggressive", "decision": "buy", "batch_date": "2025-01-01"},
            },
        ]
        self._mock_outcomes(supabase, rows)

        result = build_performance_stats(supabase, "aggressive", days=30)
        assert result["buy_count"] == 2  # Only buy records counted
        assert "avoid_count" not in result

    def test_filters_by_strategy(self):
        supabase = MagicMock()
        # Mix of strategies — only conservative should be counted
        rows = [
            {
                "actual_return_5d": 3.0,
                "outcome_aligned": True,
                "judgment_records": {"symbol": f"S{i}", "strategy_mode": "conservative", "decision": "buy", "batch_date": "2025-01-01"},
            }
            for i in range(5)
        ] + [
            {
                "actual_return_5d": 1.0,
                "outcome_aligned": True,
                "judgment_records": {"symbol": "X0", "strategy_mode": "aggressive", "decision": "buy", "batch_date": "2025-01-01"},
            }
        ]
        self._mock_outcomes(supabase, rows)

        result = build_performance_stats(supabase, "conservative", days=30)
        assert result["buy_count"] == 5  # Only conservative rows

    def test_returns_empty_on_exception(self):
        supabase = MagicMock()
        supabase._client.table.side_effect = Exception("DB error")

        result = build_performance_stats(supabase, "conservative")
        assert result == {}


class TestAdjustFactorWeights:
    """Tests for adjust_factor_weights."""

    def _mock_trade_count(self, supabase, count):
        mock_result = MagicMock()
        mock_result.count = count
        supabase._client.table.return_value.select.return_value.execute.return_value = mock_result

    def _mock_scores_data(self, supabase, data):
        """Mock the chained query for stock_scores."""
        mock_result = MagicMock()
        mock_result.data = data
        (
            supabase._client.table.return_value
            .select.return_value
            .eq.return_value
            .gte.return_value
            .not_.return_value
            .execute.return_value
        ) = mock_result

    def test_skips_when_too_few_trades(self):
        supabase = MagicMock()
        self._mock_trade_count(supabase, 5)  # < 8

        adjust_factor_weights(supabase, "conservative")
        # Should not try to fetch scores_data
        # The table().select() is called once for trade count
        assert supabase._client.table.call_count == 1

    def test_skips_when_too_few_data_points(self):
        supabase = MagicMock()

        # First call: trade count (>= 8)
        trade_mock = MagicMock()
        trade_mock.count = 20
        trade_mock.data = []

        # Second call: scores data (< 20 points)
        scores_mock = MagicMock()
        scores_mock.data = [{"trend_score": 50, "return_5d": 1.0}] * 10  # Only 10

        supabase._client.table.return_value.select.return_value.execute.return_value = trade_mock
        (
            supabase._client.table.return_value
            .select.return_value
            .eq.return_value
            .gte.return_value
            .not_.return_value
            .execute.return_value
        ) = scores_mock

        adjust_factor_weights(supabase, "conservative")
        # Should not try to update weights
        supabase._client.table.return_value.update.assert_not_called()

    def test_weight_bounds_respected(self):
        """Verify WEIGHT_MIN and WEIGHT_MAX constants."""
        assert WEIGHT_MIN == 0.05
        assert WEIGHT_MAX == 0.60
        assert WEIGHT_MAX_DELTA == 0.05

    def test_factor_keys_defined(self):
        """Verify factor key lists match expected factors."""
        assert V1_FACTOR_KEYS == ["trend", "momentum", "value", "sentiment"]
        assert V2_FACTOR_KEYS == ["momentum_12_1", "breakout", "catalyst", "risk_adjusted"]

    def test_handles_exception_gracefully(self):
        supabase = MagicMock()
        supabase._client.table.side_effect = Exception("DB error")

        # Should not raise
        adjust_factor_weights(supabase, "conservative")
