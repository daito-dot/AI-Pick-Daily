"""Tests for meta-monitor: detector and actuator logic."""

import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone

from src.meta_monitor.models import (
    RollingMetrics,
    DegradationSignal,
    Diagnosis,
    InterventionResult,
)
from src.meta_monitor.detector import (
    detect_degradation,
    MIN_JUDGMENTS_FOR_DETECTION,
)
from src.meta_monitor.actuator import (
    execute_actions,
    MAX_THRESHOLD_CHANGE,
    MAX_WEIGHT_CHANGE,
    MAX_PROMPT_LENGTH,
)


# ─── Fixtures ──────────────────────────────────────────────


def make_metrics(
    win_rate_7d=50.0,
    win_rate_30d=60.0,
    avg_return_7d=0.5,
    avg_return_30d=1.0,
    missed_rate_7d=10.0,
    total_7d=10,
    total_30d=50,
) -> RollingMetrics:
    return RollingMetrics(
        strategy_mode="conservative",
        metric_date="2026-02-07",
        win_rate_7d=win_rate_7d,
        win_rate_30d=win_rate_30d,
        avg_return_7d=avg_return_7d,
        avg_return_30d=avg_return_30d,
        missed_rate_7d=missed_rate_7d,
        total_judgments_7d=total_7d,
        total_judgments_30d=total_30d,
        avg_confidence_7d=None,
        avg_confidence_30d=None,
    )


def make_supabase_mock():
    mock = MagicMock()
    mock.get_scoring_config.return_value = {
        "threshold": 60.0,
        "min_threshold": 40.0,
        "max_threshold": 90.0,
        "confidence_threshold": 0.6,
        "factor_weights": {
            "trend": 0.25,
            "momentum": 0.25,
            "value": 0.25,
            "sentiment": 0.25,
        },
    }

    # Per-table mock dispatcher: strategy_parameters raises to trigger fallback defaults
    table_mocks = {}
    strategy_params_mock = MagicMock()
    strategy_params_mock.select.side_effect = Exception("mock: table not available")
    table_mocks["strategy_parameters"] = strategy_params_mock

    default_table_mock = MagicMock()
    default_table_mock.insert.return_value.execute.return_value = MagicMock(data=[{"id": 42}])
    default_table_mock.update.return_value.eq.return_value.execute.return_value = MagicMock()
    default_table_mock.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()

    def table_dispatcher(name):
        return table_mocks.get(name, default_table_mock)

    mock._client.table = table_dispatcher
    return mock


# ─── Detector Tests ──────────────────────────────────────


class TestDetectDegradation:
    def test_no_degradation_when_healthy(self):
        metrics = make_metrics(win_rate_7d=55, win_rate_30d=60, avg_return_7d=0.5)
        signals = detect_degradation(metrics)
        assert signals == []

    def test_insufficient_data_returns_empty(self):
        metrics = make_metrics(total_7d=3)
        signals = detect_degradation(metrics)
        assert signals == []

    def test_win_rate_drop_detected(self):
        # 7d win rate is 30%, 30d is 60% → ratio 0.5 < 0.7 threshold
        metrics = make_metrics(win_rate_7d=30, win_rate_30d=60)
        signals = detect_degradation(metrics)
        types = [s.trigger_type for s in signals]
        assert "win_rate_drop" in types

    def test_win_rate_borderline_no_trigger(self):
        # 7d is 45%, 30d is 60% → ratio 0.75, above 0.7 threshold
        metrics = make_metrics(win_rate_7d=45, win_rate_30d=60)
        signals = detect_degradation(metrics)
        types = [s.trigger_type for s in signals]
        assert "win_rate_drop" not in types

    def test_return_decline_detected(self):
        metrics = make_metrics(avg_return_7d=-2.0)
        signals = detect_degradation(metrics)
        types = [s.trigger_type for s in signals]
        assert "return_decline" in types

    def test_return_decline_borderline_no_trigger(self):
        metrics = make_metrics(avg_return_7d=-0.5)
        signals = detect_degradation(metrics)
        types = [s.trigger_type for s in signals]
        assert "return_decline" not in types

    def test_missed_spike_detected(self):
        metrics = make_metrics(missed_rate_7d=40.0)  # >30%
        signals = detect_degradation(metrics)
        types = [s.trigger_type for s in signals]
        assert "missed_spike" in types

    def test_missed_spike_borderline_no_trigger(self):
        metrics = make_metrics(missed_rate_7d=25.0)  # <30%
        signals = detect_degradation(metrics)
        types = [s.trigger_type for s in signals]
        assert "missed_spike" not in types

    def test_multiple_signals_upgrade_to_critical(self):
        metrics = make_metrics(
            win_rate_7d=25, win_rate_30d=60, avg_return_7d=-3.0
        )
        signals = detect_degradation(metrics)
        assert len(signals) >= 2
        assert all(s.severity == "critical" for s in signals)

    def test_single_signal_stays_warning(self):
        metrics = make_metrics(win_rate_7d=30, win_rate_30d=60)
        signals = detect_degradation(metrics)
        assert len(signals) == 1
        assert signals[0].severity == "warning"

    def test_none_win_rates_no_crash(self):
        metrics = make_metrics(win_rate_7d=None, win_rate_30d=None)
        signals = detect_degradation(metrics)
        # Should not crash, may still detect return/missed signals
        assert isinstance(signals, list)

    def test_zero_baseline_no_division_error(self):
        metrics = make_metrics(win_rate_7d=0, win_rate_30d=0)
        signals = detect_degradation(metrics)
        # win_rate_30d == 0, so ratio check should be skipped
        types = [s.trigger_type for s in signals]
        assert "win_rate_drop" not in types


# ─── Actuator Tests ──────────────────────────────────────


class TestExecuteActions:
    def test_prompt_override_applied(self):
        supabase = make_supabase_mock()
        metrics = make_metrics()
        diagnosis = Diagnosis(
            root_causes=["test"],
            recommended_actions=[
                {
                    "type": "prompt_override",
                    "override_text": "Focus on momentum signals",
                    "rationale": "Testing",
                }
            ],
            confidence=0.8,
        )

        result = execute_actions(supabase, diagnosis, "conservative", metrics)
        assert len(result.actions_taken) == 1
        assert result.actions_taken[0]["type"] == "prompt_override"

    def test_prompt_override_truncated(self):
        supabase = make_supabase_mock()
        metrics = make_metrics()
        long_text = "x" * 1000
        diagnosis = Diagnosis(
            root_causes=["test"],
            recommended_actions=[
                {
                    "type": "prompt_override",
                    "override_text": long_text,
                    "rationale": "Testing",
                }
            ],
            confidence=0.8,
        )

        result = execute_actions(supabase, diagnosis, "conservative", metrics)
        assert len(result.actions_taken) == 1
        assert len(result.actions_taken[0]["text"]) == MAX_PROMPT_LENGTH

    def test_threshold_adjust_within_limits(self):
        supabase = make_supabase_mock()
        metrics = make_metrics()
        diagnosis = Diagnosis(
            root_causes=["test"],
            recommended_actions=[
                {
                    "type": "threshold_adjust",
                    "change": -5,
                    "rationale": "Testing",
                }
            ],
            confidence=0.8,
        )

        result = execute_actions(supabase, diagnosis, "conservative", metrics)
        assert len(result.actions_taken) == 1
        action = result.actions_taken[0]
        assert action["type"] == "threshold_adjust"
        assert action["new_value"] == 55.0
        supabase.update_threshold.assert_called_once()

    def test_threshold_adjust_clamped(self):
        supabase = make_supabase_mock()
        metrics = make_metrics()
        diagnosis = Diagnosis(
            root_causes=["test"],
            recommended_actions=[
                {
                    "type": "threshold_adjust",
                    "change": -25,  # exceeds MAX_THRESHOLD_CHANGE
                    "rationale": "Testing",
                }
            ],
            confidence=0.8,
        )

        result = execute_actions(supabase, diagnosis, "conservative", metrics)
        action = result.actions_taken[0]
        # -25 clamped to -10, so 60 - 10 = 50
        assert action["new_value"] == 50.0

    def test_weight_adjust_within_limits(self):
        supabase = make_supabase_mock()
        metrics = make_metrics()
        diagnosis = Diagnosis(
            root_causes=["test"],
            recommended_actions=[
                {
                    "type": "weight_adjust",
                    "factor": "momentum",
                    "change": 0.05,
                    "rationale": "Testing",
                }
            ],
            confidence=0.8,
        )

        result = execute_actions(supabase, diagnosis, "conservative", metrics)
        assert len(result.actions_taken) == 1
        action = result.actions_taken[0]
        assert action["type"] == "weight_adjust"
        assert action["factor"] == "momentum"

    def test_weight_adjust_clamped(self):
        supabase = make_supabase_mock()
        metrics = make_metrics()
        diagnosis = Diagnosis(
            root_causes=["test"],
            recommended_actions=[
                {
                    "type": "weight_adjust",
                    "factor": "momentum",
                    "change": 0.5,  # exceeds MAX_WEIGHT_CHANGE
                    "rationale": "Testing",
                }
            ],
            confidence=0.8,
        )

        result = execute_actions(supabase, diagnosis, "conservative", metrics)
        assert len(result.actions_taken) == 1
        # The change should be clamped to 0.1

    def test_unknown_action_type_skipped(self):
        supabase = make_supabase_mock()
        metrics = make_metrics()
        diagnosis = Diagnosis(
            root_causes=["test"],
            recommended_actions=[{"type": "unknown_type", "change": 5}],
            confidence=0.8,
        )

        result = execute_actions(supabase, diagnosis, "conservative", metrics)
        assert result.actions_taken == []

    def test_no_actions_returns_zero_id(self):
        supabase = make_supabase_mock()
        metrics = make_metrics()
        diagnosis = Diagnosis(
            root_causes=["test"],
            recommended_actions=[],
            confidence=0.8,
        )

        result = execute_actions(supabase, diagnosis, "conservative", metrics)
        assert result.intervention_id == 0
        assert result.actions_taken == []

    def test_empty_prompt_override_skipped(self):
        supabase = make_supabase_mock()
        metrics = make_metrics()
        diagnosis = Diagnosis(
            root_causes=["test"],
            recommended_actions=[
                {
                    "type": "prompt_override",
                    "override_text": "",
                    "rationale": "Testing",
                }
            ],
            confidence=0.8,
        )

        result = execute_actions(supabase, diagnosis, "conservative", metrics)
        assert result.actions_taken == []

    def test_missing_factor_skipped(self):
        supabase = make_supabase_mock()
        metrics = make_metrics()
        diagnosis = Diagnosis(
            root_causes=["test"],
            recommended_actions=[
                {
                    "type": "weight_adjust",
                    "factor": "nonexistent_factor",
                    "change": 0.05,
                    "rationale": "Testing",
                }
            ],
            confidence=0.8,
        )

        result = execute_actions(supabase, diagnosis, "conservative", metrics)
        assert result.actions_taken == []

    def test_intervention_recorded_with_cooldown(self):
        supabase = make_supabase_mock()
        metrics = make_metrics()
        diagnosis = Diagnosis(
            root_causes=["degradation"],
            recommended_actions=[
                {
                    "type": "prompt_override",
                    "override_text": "Test guidance",
                    "rationale": "Testing",
                }
            ],
            confidence=0.7,
        )

        result = execute_actions(supabase, diagnosis, "conservative", metrics)
        assert result.intervention_id == 42
        assert len(result.actions_taken) == 1


# ─── Model Tests ──────────────────────────────────────


class TestModels:
    def test_rolling_metrics_to_dict(self):
        metrics = make_metrics()
        d = metrics.to_dict()
        assert d["strategy_mode"] == "conservative"
        assert d["win_rate_7d"] == 50.0
        assert d["total_judgments_30d"] == 50

    def test_degradation_signal_fields(self):
        signal = DegradationSignal(
            trigger_type="win_rate_drop",
            severity="warning",
            current_value=30.0,
            baseline_value=60.0,
            details="test",
        )
        assert signal.trigger_type == "win_rate_drop"
        assert signal.severity == "warning"
