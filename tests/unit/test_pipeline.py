"""
Tests for the shared pipeline module (src/pipeline/).

Covers:
- MarketConfig dataclass and constants
- populate_judgment_outcomes logic
- adjust_thresholds_for_strategies logic
- _format_past_lessons helper
- load_dynamic_thresholds
"""
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import FrozenInstanceError

from src.pipeline.market_config import MarketConfig, US_MARKET, JP_MARKET


# ============================================================
# MarketConfig Tests
# ============================================================


class TestMarketConfig:
    """Tests for MarketConfig dataclass."""

    def test_us_market_values(self):
        assert US_MARKET.v1_strategy_mode == "conservative"
        assert US_MARKET.v2_strategy_mode == "aggressive"
        assert US_MARKET.market_type == "us"
        assert US_MARKET.benchmark_symbol == "SPY"
        assert US_MARKET.use_finnhub is True

    def test_jp_market_values(self):
        assert JP_MARKET.v1_strategy_mode == "jp_conservative"
        assert JP_MARKET.v2_strategy_mode == "jp_aggressive"
        assert JP_MARKET.market_type == "jp"
        assert JP_MARKET.benchmark_symbol == "^N225"
        assert JP_MARKET.use_finnhub is False

    def test_frozen(self):
        with pytest.raises(FrozenInstanceError):
            US_MARKET.market_type = "jp"

    def test_custom_config(self):
        custom = MarketConfig(
            v1_strategy_mode="custom_v1",
            v2_strategy_mode="custom_v2",
            market_type="custom",
            benchmark_symbol="QQQ",
            use_finnhub=False,
        )
        assert custom.market_type == "custom"


# ============================================================
# populate_judgment_outcomes Tests
# ============================================================


class TestPopulateJudgmentOutcomes:
    """Tests for populate_judgment_outcomes."""

    def _make_results(self, picked=None, not_picked=None, error=None, date="2025-01-01"):
        r = {"date": date, "picked_returns": picked or [], "not_picked_returns": not_picked or []}
        if error:
            r["error"] = error
        return r

    def test_skips_on_error(self):
        from src.pipeline.review import populate_judgment_outcomes
        supabase = MagicMock()
        result = populate_judgment_outcomes(supabase, {"error": "No data"})
        assert result == 0
        supabase.get_judgment_records.assert_not_called()

    def test_skips_on_no_date(self):
        from src.pipeline.review import populate_judgment_outcomes
        supabase = MagicMock()
        result = populate_judgment_outcomes(supabase, {"picked_returns": []})
        assert result == 0

    def test_skips_on_empty_returns(self):
        from src.pipeline.review import populate_judgment_outcomes
        supabase = MagicMock()
        result = populate_judgment_outcomes(
            supabase, self._make_results(picked=[], not_picked=[])
        )
        assert result == 0

    def test_saves_outcome_for_buy_positive_return(self):
        from src.pipeline.review import populate_judgment_outcomes
        supabase = MagicMock()
        supabase.get_judgment_records.return_value = [
            {"id": "j1", "symbol": "AAPL", "strategy_mode": "conservative", "decision": "buy"}
        ]
        results = self._make_results(
            picked=[{"symbol": "AAPL", "strategy": "conservative", "return_pct": 5.0}]
        )
        count = populate_judgment_outcomes(supabase, results, return_field="5d")
        assert count == 1
        supabase.save_judgment_outcome.assert_called_once()
        call_kwargs = supabase.save_judgment_outcome.call_args[1]
        assert call_kwargs["judgment_id"] == "j1"
        assert call_kwargs["actual_return_5d"] == 5.0
        assert call_kwargs["outcome_aligned"] is True

    def test_buy_negative_return_not_aligned(self):
        from src.pipeline.review import populate_judgment_outcomes
        supabase = MagicMock()
        supabase.get_judgment_records.return_value = [
            {"id": "j1", "symbol": "TSLA", "strategy_mode": "aggressive", "decision": "buy"}
        ]
        results = self._make_results(
            picked=[{"symbol": "TSLA", "strategy": "aggressive", "return_pct": -3.0}]
        )
        count = populate_judgment_outcomes(supabase, results, return_field="5d")
        assert count == 1
        call_kwargs = supabase.save_judgment_outcome.call_args[1]
        assert call_kwargs["outcome_aligned"] is False

    def test_avoid_negative_return_aligned(self):
        from src.pipeline.review import populate_judgment_outcomes
        supabase = MagicMock()
        supabase.get_judgment_records.return_value = [
            {"id": "j2", "symbol": "XYZ", "strategy_mode": "conservative", "decision": "avoid"}
        ]
        results = self._make_results(
            not_picked=[{"symbol": "XYZ", "strategy": "conservative", "return_pct": -5.0}]
        )
        count = populate_judgment_outcomes(supabase, results, return_field="1d")
        call_kwargs = supabase.save_judgment_outcome.call_args[1]
        assert call_kwargs["outcome_aligned"] is True
        assert call_kwargs["actual_return_1d"] == -5.0

    def test_skip_positive_return_not_aligned(self):
        """Skip/hold with positive return = we missed a winner → not aligned."""
        from src.pipeline.review import populate_judgment_outcomes
        supabase = MagicMock()
        supabase.get_judgment_records.return_value = [
            {"id": "j3", "symbol": "IBM", "strategy_mode": "conservative", "decision": "skip"}
        ]
        results = self._make_results(
            not_picked=[{"symbol": "IBM", "strategy": "conservative", "return_pct": 1.5}]
        )
        populate_judgment_outcomes(supabase, results)
        call_kwargs = supabase.save_judgment_outcome.call_args[1]
        assert call_kwargs["outcome_aligned"] is False  # return > 0 → missed winner

    def test_skip_negative_return_aligned(self):
        """Skip/hold with negative return = correctly avoided loser → aligned."""
        from src.pipeline.review import populate_judgment_outcomes
        supabase = MagicMock()
        supabase.get_judgment_records.return_value = [
            {"id": "j4", "symbol": "GME", "strategy_mode": "aggressive", "decision": "skip"}
        ]
        results = self._make_results(
            not_picked=[{"symbol": "GME", "strategy": "aggressive", "return_pct": -5.0}]
        )
        populate_judgment_outcomes(supabase, results)
        call_kwargs = supabase.save_judgment_outcome.call_args[1]
        assert call_kwargs["outcome_aligned"] is True  # return < 0 → correct skip

    def test_no_matching_judgment_skipped(self):
        from src.pipeline.review import populate_judgment_outcomes
        supabase = MagicMock()
        supabase.get_judgment_records.return_value = [
            {"id": "j1", "symbol": "MSFT", "strategy_mode": "conservative", "decision": "buy"}
        ]
        results = self._make_results(
            picked=[{"symbol": "AAPL", "strategy": "conservative", "return_pct": 5.0}]
        )
        count = populate_judgment_outcomes(supabase, results)
        assert count == 0
        supabase.save_judgment_outcome.assert_not_called()

    def test_save_failure_continues(self):
        from src.pipeline.review import populate_judgment_outcomes
        supabase = MagicMock()
        supabase.get_judgment_records.return_value = [
            {"id": "j1", "symbol": "AAPL", "strategy_mode": "conservative", "decision": "buy"},
            {"id": "j2", "symbol": "MSFT", "strategy_mode": "conservative", "decision": "buy"},
        ]
        supabase.save_judgment_outcome.side_effect = [Exception("DB error"), MagicMock()]
        results = self._make_results(
            picked=[
                {"symbol": "AAPL", "strategy": "conservative", "return_pct": 2.0},
                {"symbol": "MSFT", "strategy": "conservative", "return_pct": 3.0},
            ]
        )
        count = populate_judgment_outcomes(supabase, results)
        assert count == 1  # Second one succeeded


# ============================================================
# load_dynamic_thresholds Tests
# ============================================================


class TestLoadDynamicThresholds:
    """Tests for load_dynamic_thresholds."""

    def test_returns_thresholds_from_config(self):
        from src.pipeline.scoring import load_dynamic_thresholds
        supabase = MagicMock()
        supabase.get_scoring_config.side_effect = [
            {"threshold": "65"},  # v1
            {"threshold": "80"},  # v2
        ]
        v1, v2 = load_dynamic_thresholds(supabase, US_MARKET)
        assert v1 == 65
        assert v2 == 80

    def test_returns_none_on_missing_config(self):
        from src.pipeline.scoring import load_dynamic_thresholds
        supabase = MagicMock()
        supabase.get_scoring_config.side_effect = [None, None]
        v1, v2 = load_dynamic_thresholds(supabase, JP_MARKET)
        assert v1 is None
        assert v2 is None

    def test_returns_none_on_exception(self):
        from src.pipeline.scoring import load_dynamic_thresholds
        supabase = MagicMock()
        supabase.get_scoring_config.side_effect = Exception("DB down")
        v1, v2 = load_dynamic_thresholds(supabase, US_MARKET)
        assert v1 is None
        assert v2 is None

    def test_handles_float_threshold(self):
        from src.pipeline.scoring import load_dynamic_thresholds
        supabase = MagicMock()
        supabase.get_scoring_config.side_effect = [
            {"threshold": 62.5},
            {"threshold": 77.8},
        ]
        v1, v2 = load_dynamic_thresholds(supabase, US_MARKET)
        assert v1 == 62
        assert v2 == 77


# ============================================================
# load_factor_weights Tests
# ============================================================


class TestLoadFactorWeights:
    """Tests for load_factor_weights."""

    def test_returns_weights_from_config(self):
        from src.pipeline.scoring import load_factor_weights
        supabase = MagicMock()
        supabase.get_scoring_config.side_effect = [
            {"factor_weights": {"trend": 0.30, "momentum": 0.40, "value": 0.20, "sentiment": 0.10}},
            {"factor_weights": {"momentum_12_1": 0.35, "breakout": 0.30, "catalyst": 0.20, "risk_adjusted": 0.15}},
        ]
        v1, v2 = load_factor_weights(supabase, US_MARKET)
        assert v1["trend"] == 0.30
        assert v2["momentum_12_1"] == 0.35

    def test_returns_none_when_no_weights(self):
        from src.pipeline.scoring import load_factor_weights
        supabase = MagicMock()
        supabase.get_scoring_config.side_effect = [
            {"threshold": 60},  # No factor_weights key
            None,
        ]
        v1, v2 = load_factor_weights(supabase, JP_MARKET)
        assert v1 is None
        assert v2 is None

    def test_returns_none_on_exception(self):
        from src.pipeline.scoring import load_factor_weights
        supabase = MagicMock()
        supabase.get_scoring_config.side_effect = Exception("DB down")
        v1, v2 = load_factor_weights(supabase, US_MARKET)
        assert v1 is None
        assert v2 is None


# ============================================================
# adjust_thresholds_for_strategies Tests
# ============================================================


class TestAdjustThresholdsForStrategies:
    """Tests for adjust_thresholds_for_strategies."""

    def _make_results(self, picked=None, not_picked=None, missed=None):
        return {
            "picked_returns": picked or [],
            "not_picked_returns": not_picked or [],
            "missed_opportunities": missed or [],
        }

    def test_skips_on_error(self):
        from src.pipeline.review import adjust_thresholds_for_strategies
        supabase = MagicMock()
        adjust_thresholds_for_strategies(supabase, {"error": "No data"}, ["conservative"])
        supabase.get_scoring_config.assert_not_called()

    def test_skips_when_no_config_and_no_create(self):
        from src.pipeline.review import adjust_thresholds_for_strategies
        supabase = MagicMock()
        supabase.get_scoring_config.return_value = None
        # Mock threshold_history and trade_history
        mock_result = MagicMock()
        mock_result.data = []
        mock_result.count = 0
        supabase._client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = mock_result
        supabase._client.table.return_value.select.return_value.execute.return_value = mock_result

        adjust_thresholds_for_strategies(
            supabase, self._make_results(), ["conservative"], create_default_config=False
        )
        # Should not attempt to create config
        supabase._client.table.return_value.insert.assert_not_called()

    def test_creates_default_config_when_flagged(self):
        from src.pipeline.review import adjust_thresholds_for_strategies
        supabase = MagicMock()
        supabase.get_scoring_config.return_value = None

        # Mock DB queries for threshold_history and trade count
        mock_empty = MagicMock()
        mock_empty.data = []
        mock_empty.count = 0
        supabase._client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = mock_empty
        supabase._client.table.return_value.select.return_value.execute.return_value = mock_empty
        supabase._client.table.return_value.insert.return_value.execute.return_value = MagicMock()

        # Mock threshold optimizer functions to avoid real logic
        with patch("src.pipeline.review.check_overfitting_protection") as mock_check, \
             patch("src.pipeline.review.calculate_optimal_threshold") as mock_calc, \
             patch("src.pipeline.review.should_apply_adjustment") as mock_should, \
             patch("src.pipeline.review.format_adjustment_log") as mock_log:

            mock_check.return_value = MagicMock(can_adjust=False, reason="Not enough data")
            mock_calc.return_value = MagicMock()
            mock_should.return_value = False
            mock_log.return_value = "log"

            adjust_thresholds_for_strategies(
                supabase, self._make_results(), ["jp_conservative"], create_default_config=True
            )
            # Should insert default config
            supabase._client.table.return_value.insert.assert_called()
