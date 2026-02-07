"""
Tests for exit signal evaluation with hard/soft split and AI overrides.

Covers:
- evaluate_exit_signals with hard exits (stop-loss, crisis, absolute max hold)
- evaluate_exit_signals with soft exits (take-profit, score-drop, max-hold)
- AI override for soft exits
- get_soft_exit_candidates identification
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from src.portfolio.manager import (
    PortfolioManager,
    Position,
    ExitSignal,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    MAX_HOLD_DAYS,
    ABSOLUTE_MAX_HOLD_DAYS,
)
from src.pipeline.market_config import US_MARKET


def _make_position(
    symbol="AAPL",
    strategy_mode="conservative",
    entry_price=100.0,
    hold_days=5,
) -> Position:
    return Position(
        id="test-id",
        strategy_mode=strategy_mode,
        symbol=symbol,
        entry_date="2025-01-01",
        entry_price=entry_price,
        shares=10.0,
        position_value=entry_price * 10.0,
        entry_score=70,
        hold_days=hold_days,
    )


@dataclass
class MockExitJudgment:
    """Mock ExitJudgmentOutput."""
    symbol: str
    decision: str  # "close" or "hold"
    confidence: float
    reasoning: str = "Test reasoning"


class TestEvaluateExitSignals:
    """Tests for evaluate_exit_signals."""

    def _make_manager(self, current_price: float) -> PortfolioManager:
        manager = PortfolioManager(
            supabase=MagicMock(),
            market_config=US_MARKET,
        )
        manager.get_current_price = MagicMock(return_value=current_price)
        return manager

    # --- Hard Exits ---

    def test_stop_loss_fires_as_hard_exit(self):
        """Stop loss fires regardless of AI judgment."""
        manager = self._make_manager(current_price=90.0)
        position = _make_position(entry_price=100.0)
        # Even with AI saying hold, stop loss should fire
        ai_hold = MockExitJudgment(symbol="AAPL", decision="hold", confidence=0.9)

        signals = manager.evaluate_exit_signals(
            positions=[position],
            exit_judgments={"AAPL": ai_hold},
        )
        assert len(signals) == 1
        assert signals[0].reason == "stop_loss"
        assert signals[0].pnl_pct <= STOP_LOSS_PCT

    def test_crisis_regime_fires_as_hard_exit(self):
        """Crisis regime forces exit regardless of AI."""
        manager = self._make_manager(current_price=105.0)
        position = _make_position(entry_price=100.0)

        signals = manager.evaluate_exit_signals(
            positions=[position],
            market_regime="crisis",
        )
        assert len(signals) == 1
        assert signals[0].reason == "regime_change"

    def test_absolute_max_hold_fires_as_hard_exit(self):
        """15-day absolute max hold fires regardless of AI."""
        manager = self._make_manager(current_price=105.0)
        position = _make_position(entry_price=100.0, hold_days=ABSOLUTE_MAX_HOLD_DAYS)

        signals = manager.evaluate_exit_signals(
            positions=[position],
        )
        assert len(signals) == 1
        assert signals[0].reason == "absolute_max_hold"

    # --- Soft Exits without AI ---

    def test_take_profit_fires_without_ai(self):
        """Take profit fires when no AI judgment provided."""
        manager = self._make_manager(current_price=120.0)
        position = _make_position(entry_price=100.0)

        signals = manager.evaluate_exit_signals(
            positions=[position],
        )
        assert len(signals) == 1
        assert signals[0].reason == "take_profit"

    def test_score_drop_fires_without_ai(self):
        """Score drop fires when no AI judgment provided."""
        manager = self._make_manager(current_price=105.0)
        position = _make_position(entry_price=100.0)

        signals = manager.evaluate_exit_signals(
            positions=[position],
            current_scores={"AAPL": 40},
            thresholds={"conservative": 60},
        )
        assert len(signals) == 1
        assert signals[0].reason == "score_drop"

    def test_max_hold_fires_without_ai(self):
        """Max hold fires when no AI judgment provided."""
        manager = self._make_manager(current_price=105.0)
        position = _make_position(entry_price=100.0, hold_days=MAX_HOLD_DAYS)

        signals = manager.evaluate_exit_signals(
            positions=[position],
        )
        assert len(signals) == 1
        assert signals[0].reason == "max_hold"

    # --- AI Override for Soft Exits ---

    def test_ai_hold_overrides_take_profit(self):
        """AI saying hold prevents take-profit exit."""
        manager = self._make_manager(current_price=120.0)
        position = _make_position(entry_price=100.0)
        ai_hold = MockExitJudgment(symbol="AAPL", decision="hold", confidence=0.8)

        signals = manager.evaluate_exit_signals(
            positions=[position],
            exit_judgments={"AAPL": ai_hold},
        )
        assert len(signals) == 0

    def test_ai_close_confirms_take_profit(self):
        """AI saying close confirms take-profit exit."""
        manager = self._make_manager(current_price=120.0)
        position = _make_position(entry_price=100.0)
        ai_close = MockExitJudgment(symbol="AAPL", decision="close", confidence=0.8)

        signals = manager.evaluate_exit_signals(
            positions=[position],
            exit_judgments={"AAPL": ai_close},
        )
        assert len(signals) == 1
        assert signals[0].reason == "take_profit"

    def test_ai_hold_overrides_score_drop(self):
        """AI saying hold prevents score-drop exit."""
        manager = self._make_manager(current_price=105.0)
        position = _make_position(entry_price=100.0)
        ai_hold = MockExitJudgment(symbol="AAPL", decision="hold", confidence=0.7)

        signals = manager.evaluate_exit_signals(
            positions=[position],
            current_scores={"AAPL": 40},
            thresholds={"conservative": 60},
            exit_judgments={"AAPL": ai_hold},
        )
        assert len(signals) == 0

    def test_ai_hold_overrides_max_hold(self):
        """AI saying hold prevents max-hold exit."""
        manager = self._make_manager(current_price=105.0)
        position = _make_position(entry_price=100.0, hold_days=MAX_HOLD_DAYS)
        ai_hold = MockExitJudgment(symbol="AAPL", decision="hold", confidence=0.6)

        signals = manager.evaluate_exit_signals(
            positions=[position],
            exit_judgments={"AAPL": ai_hold},
        )
        assert len(signals) == 0

    # --- No signal ---

    def test_no_signal_when_position_healthy(self):
        """No exit signal for a healthy position."""
        manager = self._make_manager(current_price=105.0)
        position = _make_position(entry_price=100.0, hold_days=3)

        signals = manager.evaluate_exit_signals(
            positions=[position],
            current_scores={"AAPL": 75},
            thresholds={"conservative": 60},
        )
        assert len(signals) == 0

    def test_skips_position_without_price(self):
        """Skips positions where current price is unavailable."""
        manager = PortfolioManager(supabase=MagicMock(), market_config=US_MARKET)
        manager.get_current_price = MagicMock(return_value=None)
        position = _make_position()

        signals = manager.evaluate_exit_signals(positions=[position])
        assert len(signals) == 0


class TestGetSoftExitCandidates:
    """Tests for get_soft_exit_candidates."""

    def _make_manager(self, current_price: float) -> PortfolioManager:
        manager = PortfolioManager(
            supabase=MagicMock(),
            market_config=US_MARKET,
        )
        manager.get_current_price = MagicMock(return_value=current_price)
        return manager

    def test_identifies_take_profit_candidate(self):
        manager = self._make_manager(current_price=120.0)
        position = _make_position(entry_price=100.0)

        candidates = manager.get_soft_exit_candidates(positions=[position])
        assert len(candidates) == 1
        assert candidates[0]["trigger_reason"] == "take_profit"
        assert candidates[0]["symbol"] == "AAPL"

    def test_identifies_score_drop_candidate(self):
        manager = self._make_manager(current_price=105.0)
        position = _make_position(entry_price=100.0)

        candidates = manager.get_soft_exit_candidates(
            positions=[position],
            current_scores={"AAPL": 40},
            thresholds={"conservative": 60},
        )
        assert len(candidates) == 1
        assert candidates[0]["trigger_reason"] == "score_drop"

    def test_identifies_max_hold_candidate(self):
        manager = self._make_manager(current_price=105.0)
        position = _make_position(entry_price=100.0, hold_days=MAX_HOLD_DAYS)

        candidates = manager.get_soft_exit_candidates(positions=[position])
        assert len(candidates) == 1
        assert candidates[0]["trigger_reason"] == "max_hold"

    def test_excludes_stop_loss(self):
        """Stop loss positions are not soft exit candidates."""
        manager = self._make_manager(current_price=90.0)
        position = _make_position(entry_price=100.0)

        candidates = manager.get_soft_exit_candidates(positions=[position])
        assert len(candidates) == 0

    def test_excludes_crisis_regime(self):
        """Crisis regime positions are not soft exit candidates."""
        manager = self._make_manager(current_price=105.0)
        position = _make_position(entry_price=100.0)

        candidates = manager.get_soft_exit_candidates(
            positions=[position],
            market_regime="crisis",
        )
        assert len(candidates) == 0

    def test_excludes_absolute_max_hold(self):
        """Absolute max hold positions are not soft exit candidates."""
        manager = self._make_manager(current_price=105.0)
        position = _make_position(
            entry_price=100.0, hold_days=ABSOLUTE_MAX_HOLD_DAYS,
        )

        candidates = manager.get_soft_exit_candidates(positions=[position])
        assert len(candidates) == 0

    def test_no_candidates_for_healthy_position(self):
        manager = self._make_manager(current_price=105.0)
        position = _make_position(entry_price=100.0, hold_days=3)

        candidates = manager.get_soft_exit_candidates(
            positions=[position],
            current_scores={"AAPL": 75},
            thresholds={"conservative": 60},
        )
        assert len(candidates) == 0
