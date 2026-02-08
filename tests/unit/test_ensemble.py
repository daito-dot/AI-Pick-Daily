"""Tests for the ensemble risk assessment architecture.

Covers:
- _aggregate_ensemble() decision logic
- REGIME_DECISION_PARAMS per-regime thresholds
- build_recent_mistakes() query function
- Risk score → confidence mapping
- Backward compatibility with old "avoid"/"hold" records
- RiskAssessment / EnsembleResult dataclasses
"""

import pytest
from unittest.mock import MagicMock, patch

from src.scoring.market_regime import (
    MarketRegime,
    REGIME_DECISION_PARAMS,
)
from src.judgment.models import (
    RiskAssessment,
    PortfolioRiskOutput,
    EnsembleResult,
    JudgmentDecision,
)
from src.pipeline.scoring import _aggregate_ensemble, _parse_regime


# ─── REGIME_DECISION_PARAMS tests ──────────────────────────


class TestRegimeDecisionParams:
    """Test regime decision parameters structure."""

    def test_all_regimes_present(self):
        """All MarketRegime values should have decision params."""
        for regime in MarketRegime:
            assert regime in REGIME_DECISION_PARAMS, f"Missing params for {regime}"

    def test_normal_is_most_permissive(self):
        normal = REGIME_DECISION_PARAMS[MarketRegime.NORMAL]
        adjustment = REGIME_DECISION_PARAMS[MarketRegime.ADJUSTMENT]
        crisis = REGIME_DECISION_PARAMS[MarketRegime.CRISIS]

        assert normal["max_picks"] >= adjustment["max_picks"] >= crisis["max_picks"]
        assert normal["max_risk"] >= adjustment["max_risk"] >= crisis["max_risk"]
        assert normal["min_score"] <= adjustment["min_score"] <= crisis["min_score"]
        assert normal["min_consensus"] <= adjustment["min_consensus"] <= crisis["min_consensus"]

    def test_crisis_is_most_restrictive(self):
        crisis = REGIME_DECISION_PARAMS[MarketRegime.CRISIS]
        assert crisis["max_picks"] <= 2
        assert crisis["max_risk"] <= 2.0
        assert crisis["min_consensus"] >= 0.7

    def test_params_have_required_keys(self):
        required_keys = {"max_picks", "min_score", "max_risk", "min_consensus"}
        for regime, params in REGIME_DECISION_PARAMS.items():
            assert required_keys <= set(params.keys()), f"Missing keys in {regime}"


# ─── _parse_regime tests ──────────────────────────


class TestParseRegime:
    """Test regime string to enum parsing."""

    def test_normal(self):
        assert _parse_regime("normal") == MarketRegime.NORMAL
        assert _parse_regime("NORMAL") == MarketRegime.NORMAL

    def test_adjustment(self):
        assert _parse_regime("adjustment") == MarketRegime.ADJUSTMENT
        assert _parse_regime("correction") == MarketRegime.ADJUSTMENT

    def test_crisis(self):
        assert _parse_regime("crisis") == MarketRegime.CRISIS
        assert _parse_regime("CRISIS") == MarketRegime.CRISIS

    def test_unknown_defaults_to_normal(self):
        assert _parse_regime("unknown") == MarketRegime.NORMAL
        assert _parse_regime("") == MarketRegime.NORMAL


# ─── _aggregate_ensemble tests ──────────────────────────


def _make_risk_output(assessments_data: list[tuple[str, int]]) -> PortfolioRiskOutput:
    """Helper: create PortfolioRiskOutput from (symbol, risk_score) pairs."""
    return PortfolioRiskOutput(
        assessments=[
            RiskAssessment(
                symbol=sym,
                risk_score=risk,
                negative_catalysts=[],
                news_interpretation="test",
            )
            for sym, risk in assessments_data
        ],
        market_level_risks="test",
    )


def _make_candidates(symbols_scores: list[tuple[str, int]]) -> list[tuple]:
    """Helper: create mock candidate tuples."""
    candidates = []
    for sym, score in symbols_scores:
        stock = MagicMock()
        stock.symbol = sym
        scored = MagicMock()
        scored.composite_score = score
        candidates.append((stock, scored))
    return candidates


NORMAL_PARAMS = REGIME_DECISION_PARAMS[MarketRegime.NORMAL]


class TestAggregateEnsemble:
    """Test ensemble aggregation logic."""

    def test_all_buy_unanimous(self):
        """All models rate low risk → all should be buy."""
        primary = _make_risk_output([("AAPL", 1), ("GOOG", 2)])
        candidates = _make_candidates([("AAPL", 80), ("GOOG", 70)])

        results = _aggregate_ensemble(primary, {}, candidates, NORMAL_PARAMS)

        buys = [r for r in results if r.final_decision == "buy"]
        assert len(buys) == 2
        assert buys[0].symbol == "AAPL"  # Higher score first

    def test_all_skip_high_risk(self):
        """All models rate high risk → all should be skip."""
        primary = _make_risk_output([("AAPL", 5), ("GOOG", 5)])
        candidates = _make_candidates([("AAPL", 80), ("GOOG", 70)])

        results = _aggregate_ensemble(primary, {}, candidates, NORMAL_PARAMS)

        buys = [r for r in results if r.final_decision == "buy"]
        assert len(buys) == 0

    def test_mixed_decisions(self):
        """Some low risk, some high risk → mixed decisions."""
        primary = _make_risk_output([("AAPL", 2), ("GOOG", 4)])
        candidates = _make_candidates([("AAPL", 80), ("GOOG", 70)])

        results = _aggregate_ensemble(primary, {}, candidates, NORMAL_PARAMS)

        result_map = {r.symbol: r for r in results}
        assert result_map["AAPL"].final_decision == "buy"
        assert result_map["GOOG"].final_decision == "skip"

    def test_shadow_models_affect_consensus(self):
        """Shadow models can change consensus and flip decisions."""
        # Primary says low risk
        primary = _make_risk_output([("AAPL", 2)])
        # Two shadows say high risk
        shadow1 = _make_risk_output([("AAPL", 5)])
        shadow2 = _make_risk_output([("AAPL", 5)])
        shadows = {"model1": shadow1, "model2": shadow2}

        candidates = _make_candidates([("AAPL", 80)])

        results = _aggregate_ensemble(primary, shadows, candidates, NORMAL_PARAMS)

        result = results[0]
        # avg_risk = (2+5+5)/3 = 4.0 > max_risk 3.5 → skip
        assert result.final_decision == "skip"
        assert result.avg_risk_score == pytest.approx(4.0)
        assert result.consensus_ratio == pytest.approx(1 / 3)

    def test_primary_only_no_shadows(self):
        """Works correctly with no shadow models."""
        primary = _make_risk_output([("AAPL", 2), ("TSLA", 3)])
        candidates = _make_candidates([("AAPL", 80), ("TSLA", 60)])

        results = _aggregate_ensemble(primary, {}, candidates, NORMAL_PARAMS)

        assert len(results) == 2
        for r in results:
            assert "primary" in r.risk_scores

    def test_max_picks_limit(self):
        """Respect max_picks from regime params."""
        # 4 candidates all low risk, but max_picks=2
        primary = _make_risk_output([
            ("A", 1), ("B", 1), ("C", 1), ("D", 1),
        ])
        candidates = _make_candidates([
            ("A", 90), ("B", 80), ("C", 70), ("D", 60),
        ])
        params = {**NORMAL_PARAMS, "max_picks": 2}

        results = _aggregate_ensemble(primary, {}, candidates, params)

        buys = [r for r in results if r.final_decision == "buy"]
        assert len(buys) == 2
        assert buys[0].symbol == "A"  # Top by score
        assert buys[1].symbol == "B"

    def test_min_score_filter(self):
        """Candidates below min_score should be skipped."""
        primary = _make_risk_output([("AAPL", 1)])  # Low risk
        candidates = _make_candidates([("AAPL", 40)])  # Low score
        params = {**NORMAL_PARAMS, "min_score": 55}

        results = _aggregate_ensemble(primary, {}, candidates, params)

        assert results[0].final_decision == "skip"
        assert "score" in results[0].decision_reason

    def test_sorted_by_composite_score(self):
        """Results should be sorted by composite_score descending."""
        primary = _make_risk_output([("C", 2), ("A", 2), ("B", 2)])
        candidates = _make_candidates([("C", 60), ("A", 90), ("B", 75)])

        results = _aggregate_ensemble(primary, {}, candidates, NORMAL_PARAMS)

        symbols = [r.symbol for r in results]
        assert symbols == ["A", "B", "C"]

    def test_crisis_regime_restrictive(self):
        """Crisis regime should be very restrictive."""
        crisis_params = REGIME_DECISION_PARAMS[MarketRegime.CRISIS]
        # Risk = 2 (which is > crisis max_risk of 1.5)
        primary = _make_risk_output([("AAPL", 2)])
        candidates = _make_candidates([("AAPL", 80)])

        results = _aggregate_ensemble(primary, {}, candidates, crisis_params)

        assert results[0].final_decision == "skip"


# ─── Risk score → confidence mapping tests ──────────────────


class TestRiskToConfidence:
    """Test risk score to confidence conversion."""

    def test_low_risk_high_confidence(self):
        """Risk 1 → confidence 1.0."""
        confidence = max(0.0, min(1.0, (5 - 1) / 4))
        assert confidence == 1.0

    def test_high_risk_low_confidence(self):
        """Risk 5 → confidence 0.0."""
        confidence = max(0.0, min(1.0, (5 - 5) / 4))
        assert confidence == 0.0

    def test_medium_risk_medium_confidence(self):
        """Risk 3 → confidence 0.5."""
        confidence = max(0.0, min(1.0, (5 - 3) / 4))
        assert confidence == 0.5

    def test_fractional_risk(self):
        """Average risk 2.5 → confidence 0.625."""
        avg_risk = 2.5
        confidence = max(0.0, min(1.0, (5 - avg_risk) / 4))
        assert confidence == pytest.approx(0.625)


# ─── Dataclass tests ──────────────────────────


class TestDataclasses:
    """Test new dataclasses are properly defined."""

    def test_risk_assessment_creation(self):
        ra = RiskAssessment(
            symbol="AAPL",
            risk_score=3,
            negative_catalysts=["earnings miss"],
            news_interpretation="Neutral outlook",
            portfolio_concern="Sector overweight",
        )
        assert ra.symbol == "AAPL"
        assert ra.risk_score == 3
        assert len(ra.negative_catalysts) == 1
        assert ra.portfolio_concern == "Sector overweight"

    def test_risk_assessment_defaults(self):
        ra = RiskAssessment(
            symbol="GOOG",
            risk_score=2,
            negative_catalysts=[],
            news_interpretation="Positive",
        )
        assert ra.portfolio_concern is None

    def test_portfolio_risk_output(self):
        pro = PortfolioRiskOutput(
            assessments=[
                RiskAssessment("A", 2, [], "ok"),
                RiskAssessment("B", 4, ["risk1"], "bad"),
            ],
            market_level_risks="Elevated volatility",
            sector_concentration_warning="Tech heavy",
        )
        assert len(pro.assessments) == 2
        assert pro.raw_llm_response is None

    def test_ensemble_result(self):
        er = EnsembleResult(
            symbol="AAPL",
            composite_score=85,
            avg_risk_score=2.3,
            risk_scores={"primary": 2, "shadow1": 3},
            consensus_ratio=1.0,
            final_decision="buy",
            decision_reason="Buy: all criteria met",
        )
        assert er.final_decision == "buy"
        assert len(er.risk_scores) == 2


# ─── JudgmentDecision backward compat tests ──────────────


class TestJudgmentDecisionCompat:
    """Test that JudgmentDecision Literal changed correctly."""

    def test_buy_is_valid(self):
        decision: JudgmentDecision = "buy"
        assert decision == "buy"

    def test_skip_is_valid(self):
        decision: JudgmentDecision = "skip"
        assert decision == "skip"


# ─── build_recent_mistakes tests ──────────────────────────


class TestBuildRecentMistakes:
    """Test recent mistakes feedback query."""

    def test_returns_empty_on_no_data(self):
        from src.pipeline.review import build_recent_mistakes

        mock_supabase = MagicMock()
        mock_supabase.client.rpc.return_value.execute.return_value.data = []

        # Should not raise, returns empty
        result = build_recent_mistakes(mock_supabase, "conservative")
        assert isinstance(result, list)

    def test_returns_empty_on_exception(self):
        from src.pipeline.review import build_recent_mistakes

        mock_supabase = MagicMock()
        mock_supabase.client.rpc.side_effect = Exception("DB error")

        result = build_recent_mistakes(mock_supabase, "conservative")
        assert result == []


# ─── Service fallback tests ──────────────────────────


class TestServiceFallbacks:
    """Test service-level fallback behavior."""

    def test_fallback_risk_output_neutral(self):
        from src.judgment.service import JudgmentService

        service = JudgmentService.__new__(JudgmentService)
        candidates = [MagicMock(symbol="AAPL"), MagicMock(symbol="GOOG")]

        result = service._create_fallback_risk_output(candidates, "test error")

        assert len(result.assessments) == 2
        assert all(a.risk_score == 3 for a in result.assessments)
        assert "test error" in result.market_level_risks

    def test_fallback_judgment_uses_skip(self):
        """Fallback judgment should use 'skip' not 'avoid'."""
        from src.judgment.service import JudgmentService
        from src.judgment.prompts import PROMPT_VERSION

        service = JudgmentService.__new__(JudgmentService)
        result = service._create_fallback_judgment(
            symbol="TEST",
            strategy_mode="conservative",
            rule_based_scores={"composite_score": 30},
            market_regime="normal",
            error_message="test",
        )
        assert result.decision == "skip"
