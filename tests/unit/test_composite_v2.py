"""
Unit tests for composite_v2.py

Tests for:
- validate_weights()
- validate_score()
- calculate_dual_scores() symbol mismatch
- calculate_percentile_ranks()
- select_picks()
- get_threshold_passed_symbols()
- select_picks_with_llm()
"""
import logging
import pytest
from datetime import datetime
from dataclasses import dataclass

from tests.conftest import MockStockData, MockV2StockData, MockJudgmentOutput


@dataclass
class MockDualCompositeScore:
    """Mock DualCompositeScore for testing."""
    symbol: str
    strategy_mode: str
    trend_score: int
    momentum_score: int
    value_score: int
    sentiment_score: int
    momentum_12_1_score: int
    breakout_score: int
    catalyst_score: int
    risk_adjusted_score: int
    composite_score: int
    percentile_rank: int
    reasoning: str
    weights_used: dict
    timestamp: datetime


def create_mock_score(
    symbol: str,
    composite_score: int,
    percentile_rank: int = 0,
    strategy_mode: str = "conservative",
) -> MockDualCompositeScore:
    """Helper to create mock DualCompositeScore instances."""
    return MockDualCompositeScore(
        symbol=symbol,
        strategy_mode=strategy_mode,
        trend_score=50,
        momentum_score=50,
        value_score=50,
        sentiment_score=50,
        momentum_12_1_score=50,
        breakout_score=50,
        catalyst_score=50,
        risk_adjusted_score=50,
        composite_score=composite_score,
        percentile_rank=percentile_rank,
        reasoning="Test reasoning",
        weights_used={"trend": 0.35, "momentum": 0.35, "value": 0.20, "sentiment": 0.10},
        timestamp=datetime.utcnow(),
    )


class TestValidateWeights:
    """Tests for validate_weights function."""

    def test_valid_v1_weights(self, v1_weights):
        """Valid V1 weights should not raise."""
        from src.scoring.composite_v2 import validate_weights, V1_WEIGHT_KEYS

        # Should not raise
        validate_weights(v1_weights, V1_WEIGHT_KEYS)

    def test_valid_v2_weights(self, v2_weights):
        """Valid V2 weights should not raise."""
        from src.scoring.composite_v2 import validate_weights, V2_WEIGHT_KEYS

        # Should not raise
        validate_weights(v2_weights, V2_WEIGHT_KEYS)

    def test_weights_sum_below_threshold(self):
        """Weights summing below 0.99 should raise ValueError."""
        from src.scoring.composite_v2 import validate_weights, V1_WEIGHT_KEYS

        invalid_weights = {
            "trend": 0.30,
            "momentum": 0.30,
            "value": 0.20,
            "sentiment": 0.10,
        }  # Sum = 0.90

        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            validate_weights(invalid_weights, V1_WEIGHT_KEYS)

    def test_weights_sum_above_threshold(self):
        """Weights summing above 1.01 should raise ValueError."""
        from src.scoring.composite_v2 import validate_weights, V1_WEIGHT_KEYS

        invalid_weights = {
            "trend": 0.40,
            "momentum": 0.40,
            "value": 0.20,
            "sentiment": 0.15,
        }  # Sum = 1.15

        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            validate_weights(invalid_weights, V1_WEIGHT_KEYS)

    def test_weights_within_tolerance(self):
        """Weights within 0.01 tolerance should not raise."""
        from src.scoring.composite_v2 import validate_weights, V1_WEIGHT_KEYS

        # Sum = 1.005, within tolerance
        almost_valid_weights = {
            "trend": 0.355,
            "momentum": 0.35,
            "value": 0.20,
            "sentiment": 0.10,
        }

        # Should not raise
        validate_weights(almost_valid_weights, V1_WEIGHT_KEYS)

    def test_missing_weight_keys(self):
        """Missing weight keys should raise ValueError."""
        from src.scoring.composite_v2 import validate_weights, V1_WEIGHT_KEYS

        incomplete_weights = {
            "trend": 0.50,
            "momentum": 0.50,
            # Missing "value" and "sentiment"
        }

        with pytest.raises(ValueError, match="Missing weight keys"):
            validate_weights(incomplete_weights, V1_WEIGHT_KEYS)

    def test_extra_keys_allowed(self):
        """Extra weight keys should be allowed."""
        from src.scoring.composite_v2 import validate_weights, V1_WEIGHT_KEYS

        weights_with_extra = {
            "trend": 0.35,
            "momentum": 0.35,
            "value": 0.20,
            "sentiment": 0.10,
            "extra_key": 0.0,  # Extra key with zero weight
        }

        # Should not raise (sum still 1.0, all required keys present)
        validate_weights(weights_with_extra, V1_WEIGHT_KEYS)


class TestValidateScore:
    """Tests for validate_score function."""

    def test_valid_score_unchanged(self):
        """Score within range should be returned unchanged."""
        from src.scoring.composite_v2 import validate_score

        assert validate_score(50, "test") == 50
        assert validate_score(0, "test") == 0
        assert validate_score(100, "test") == 100

    def test_negative_score_clamped(self, caplog):
        """Negative score should be clamped to 0 with warning."""
        from src.scoring.composite_v2 import validate_score

        with caplog.at_level(logging.WARNING):
            result = validate_score(-10, "test_component")

        assert result == 0
        assert "test_component score -10 < 0" in caplog.text

    def test_score_above_100_clamped(self, caplog):
        """Score above 100 should be clamped to 100 with warning."""
        from src.scoring.composite_v2 import validate_score

        with caplog.at_level(logging.WARNING):
            result = validate_score(150, "test_component")

        assert result == 100
        assert "test_component score 150 > 100" in caplog.text

    def test_boundary_scores(self):
        """Boundary scores (0 and 100) should be valid."""
        from src.scoring.composite_v2 import validate_score

        assert validate_score(0, "test") == 0
        assert validate_score(100, "test") == 100


class TestSymbolMismatchValidation:
    """Tests for symbol mismatch validation in calculate_dual_scores."""

    def test_symbol_mismatch_raises_error(self):
        """Mismatched symbols should raise ValueError."""
        from src.scoring.composite_v2 import calculate_dual_scores

        stock_data = MockStockData(
            symbol="AAPL",
            prices=[100.0] * 60,
            volumes=[1000000.0] * 60,
        )
        v2_data = MockV2StockData(
            symbol="MSFT",  # Different symbol
            prices=[100.0] * 60,
            volumes=[1000000.0] * 60,
        )

        v1_weights = {"trend": 0.35, "momentum": 0.35, "value": 0.20, "sentiment": 0.10}
        v2_weights = {"momentum_12_1": 0.40, "breakout": 0.25, "catalyst": 0.20, "risk_adjusted": 0.15}

        with pytest.raises(ValueError, match="Symbol mismatch: AAPL != MSFT"):
            calculate_dual_scores(stock_data, v2_data, v1_weights, v2_weights)

    def test_matching_symbols_no_error(self):
        """Matching symbols should not raise."""
        from src.scoring.composite_v2 import calculate_dual_scores

        stock_data = MockStockData(
            symbol="AAPL",
            prices=[100.0] * 260,  # Need 260 days for momentum 12-1
            volumes=[1000000.0] * 260,
            week_52_high=110.0,
            week_52_low=90.0,
        )
        v2_data = MockV2StockData(
            symbol="AAPL",  # Same symbol
            prices=[100.0] * 260,
            volumes=[1000000.0] * 260,
            week_52_high=110.0,
            week_52_low=90.0,
            vix_level=18.0,  # Required for RiskAdjustedAgent
        )

        v1_weights = {"trend": 0.35, "momentum": 0.35, "value": 0.20, "sentiment": 0.10}
        v2_weights = {"momentum_12_1": 0.40, "breakout": 0.25, "catalyst": 0.20, "risk_adjusted": 0.15}

        # Should not raise
        v1_score, v2_score = calculate_dual_scores(stock_data, v2_data, v1_weights, v2_weights)
        assert v1_score.symbol == "AAPL"
        assert v2_score.symbol == "AAPL"


class TestCalculatePercentileRanks:
    """Tests for calculate_percentile_ranks function."""

    def test_empty_list(self):
        """Empty list should return empty list."""
        from src.scoring.composite_v2 import calculate_percentile_ranks

        result = calculate_percentile_ranks([])
        assert result == []

    def test_single_element(self):
        """Single element should get percentile rank of 100."""
        from src.scoring.composite_v2 import calculate_percentile_ranks, DualCompositeScore

        score = DualCompositeScore(
            symbol="AAPL",
            strategy_mode="conservative",
            trend_score=60,
            momentum_score=70,
            value_score=50,
            sentiment_score=40,
            momentum_12_1_score=65,
            breakout_score=55,
            catalyst_score=45,
            risk_adjusted_score=60,
            composite_score=75,
            percentile_rank=0,
            reasoning="Test",
            weights_used={"trend": 0.35},
            timestamp=datetime.utcnow(),
        )

        result = calculate_percentile_ranks([score])

        assert len(result) == 1
        assert result[0].percentile_rank == 100

    def test_multiple_elements_different_scores(self):
        """Multiple elements with different scores should have different percentile ranks."""
        from src.scoring.composite_v2 import calculate_percentile_ranks, DualCompositeScore

        scores = []
        for i, (symbol, composite) in enumerate([("AAPL", 80), ("MSFT", 60), ("GOOGL", 40)]):
            scores.append(DualCompositeScore(
                symbol=symbol,
                strategy_mode="conservative",
                trend_score=50,
                momentum_score=50,
                value_score=50,
                sentiment_score=50,
                momentum_12_1_score=50,
                breakout_score=50,
                catalyst_score=50,
                risk_adjusted_score=50,
                composite_score=composite,
                percentile_rank=0,
                reasoning="Test",
                weights_used={},
                timestamp=datetime.utcnow(),
            ))

        result = calculate_percentile_ranks(scores)

        assert len(result) == 3
        # Higher composite score should have higher percentile rank
        aapl = next(s for s in result if s.symbol == "AAPL")
        msft = next(s for s in result if s.symbol == "MSFT")
        googl = next(s for s in result if s.symbol == "GOOGL")

        assert aapl.percentile_rank > msft.percentile_rank
        assert msft.percentile_rank > googl.percentile_rank

    def test_identical_scores(self):
        """All identical scores should use rank-based percentile."""
        from src.scoring.composite_v2 import calculate_percentile_ranks, DualCompositeScore

        scores = []
        for symbol in ["AAPL", "MSFT", "GOOGL", "AMZN"]:
            scores.append(DualCompositeScore(
                symbol=symbol,
                strategy_mode="conservative",
                trend_score=50,
                momentum_score=50,
                value_score=50,
                sentiment_score=50,
                momentum_12_1_score=50,
                breakout_score=50,
                catalyst_score=50,
                risk_adjusted_score=50,
                composite_score=70,  # All same score
                percentile_rank=0,
                reasoning="Test",
                weights_used={},
                timestamp=datetime.utcnow(),
            ))

        result = calculate_percentile_ranks(scores)

        assert len(result) == 4
        # With identical scores (std < 1e-6), rank-based percentile is used
        # Percentiles should be assigned based on position
        percentiles = sorted([s.percentile_rank for s in result], reverse=True)
        assert percentiles == [100, 75, 50, 25]


class TestSelectPicks:
    """Tests for select_picks function."""

    def test_max_picks_zero(self):
        """max_picks=0 should return empty list."""
        from src.scoring.composite_v2 import select_picks, DualCompositeScore

        scores = [DualCompositeScore(
            symbol="AAPL",
            strategy_mode="conservative",
            trend_score=50,
            momentum_score=50,
            value_score=50,
            sentiment_score=50,
            momentum_12_1_score=50,
            breakout_score=50,
            catalyst_score=50,
            risk_adjusted_score=50,
            composite_score=80,
            percentile_rank=90,
            reasoning="Test",
            weights_used={},
            timestamp=datetime.utcnow(),
        )]

        result = select_picks(scores, max_picks=0, min_score=50)

        assert result == []

    def test_threshold_filter(self):
        """Only scores above threshold should be selected."""
        from src.scoring.composite_v2 import select_picks, DualCompositeScore

        scores = []
        for symbol, composite, percentile in [
            ("AAPL", 80, 95),
            ("MSFT", 60, 70),
            ("GOOGL", 40, 30),  # Below threshold
        ]:
            scores.append(DualCompositeScore(
                symbol=symbol,
                strategy_mode="conservative",
                trend_score=50,
                momentum_score=50,
                value_score=50,
                sentiment_score=50,
                momentum_12_1_score=50,
                breakout_score=50,
                catalyst_score=50,
                risk_adjusted_score=50,
                composite_score=composite,
                percentile_rank=percentile,
                reasoning="Test",
                weights_used={},
                timestamp=datetime.utcnow(),
            ))

        result = select_picks(scores, max_picks=5, min_score=50)

        assert len(result) == 2
        assert "GOOGL" not in result
        assert "AAPL" in result
        assert "MSFT" in result

    def test_sorted_by_percentile_rank(self):
        """Results should be sorted by percentile rank in descending order."""
        from src.scoring.composite_v2 import select_picks, DualCompositeScore

        scores = []
        for symbol, composite, percentile in [
            ("AAPL", 80, 70),  # Lower percentile
            ("MSFT", 75, 90),  # Higher percentile
            ("GOOGL", 85, 80),  # Medium percentile
        ]:
            scores.append(DualCompositeScore(
                symbol=symbol,
                strategy_mode="conservative",
                trend_score=50,
                momentum_score=50,
                value_score=50,
                sentiment_score=50,
                momentum_12_1_score=50,
                breakout_score=50,
                catalyst_score=50,
                risk_adjusted_score=50,
                composite_score=composite,
                percentile_rank=percentile,
                reasoning="Test",
                weights_used={},
                timestamp=datetime.utcnow(),
            ))

        result = select_picks(scores, max_picks=3, min_score=50)

        assert result == ["MSFT", "GOOGL", "AAPL"]

    def test_max_picks_limits_results(self):
        """Should return at most max_picks results."""
        from src.scoring.composite_v2 import select_picks, DualCompositeScore

        scores = []
        for i, symbol in enumerate(["AAPL", "MSFT", "GOOGL", "AMZN", "META"]):
            scores.append(DualCompositeScore(
                symbol=symbol,
                strategy_mode="conservative",
                trend_score=50,
                momentum_score=50,
                value_score=50,
                sentiment_score=50,
                momentum_12_1_score=50,
                breakout_score=50,
                catalyst_score=50,
                risk_adjusted_score=50,
                composite_score=80,
                percentile_rank=90 - i * 5,
                reasoning="Test",
                weights_used={},
                timestamp=datetime.utcnow(),
            ))

        result = select_picks(scores, max_picks=2, min_score=50)

        assert len(result) == 2


class TestGetThresholdPassedSymbols:
    """Tests for get_threshold_passed_symbols function."""

    def test_threshold_filter_returns_set(self):
        """Should return a set of symbols above threshold."""
        from src.scoring.composite_v2 import get_threshold_passed_symbols, DualCompositeScore

        scores = []
        for symbol, composite in [
            ("AAPL", 80),
            ("MSFT", 60),
            ("GOOGL", 40),
            ("AMZN", 70),
        ]:
            scores.append(DualCompositeScore(
                symbol=symbol,
                strategy_mode="conservative",
                trend_score=50,
                momentum_score=50,
                value_score=50,
                sentiment_score=50,
                momentum_12_1_score=50,
                breakout_score=50,
                catalyst_score=50,
                risk_adjusted_score=50,
                composite_score=composite,
                percentile_rank=0,
                reasoning="Test",
                weights_used={},
                timestamp=datetime.utcnow(),
            ))

        result = get_threshold_passed_symbols(scores, min_score=50)

        assert isinstance(result, set)
        assert result == {"AAPL", "MSFT", "AMZN"}
        assert "GOOGL" not in result

    def test_empty_scores(self):
        """Empty scores should return empty set."""
        from src.scoring.composite_v2 import get_threshold_passed_symbols

        result = get_threshold_passed_symbols([], min_score=50)

        assert result == set()

    def test_none_pass_threshold(self):
        """When no scores pass threshold, should return empty set."""
        from src.scoring.composite_v2 import get_threshold_passed_symbols, DualCompositeScore

        scores = [DualCompositeScore(
            symbol="AAPL",
            strategy_mode="conservative",
            trend_score=50,
            momentum_score=50,
            value_score=50,
            sentiment_score=50,
            momentum_12_1_score=50,
            breakout_score=50,
            catalyst_score=50,
            risk_adjusted_score=50,
            composite_score=40,
            percentile_rank=0,
            reasoning="Test",
            weights_used={},
            timestamp=datetime.utcnow(),
        )]

        result = get_threshold_passed_symbols(scores, min_score=50)

        assert result == set()

    def test_exact_threshold(self):
        """Score exactly at threshold should pass."""
        from src.scoring.composite_v2 import get_threshold_passed_symbols, DualCompositeScore

        scores = [DualCompositeScore(
            symbol="AAPL",
            strategy_mode="conservative",
            trend_score=50,
            momentum_score=50,
            value_score=50,
            sentiment_score=50,
            momentum_12_1_score=50,
            breakout_score=50,
            catalyst_score=50,
            risk_adjusted_score=50,
            composite_score=50,  # Exactly at threshold
            percentile_rank=0,
            reasoning="Test",
            weights_used={},
            timestamp=datetime.utcnow(),
        )]

        result = get_threshold_passed_symbols(scores, min_score=50)

        assert "AAPL" in result


class TestSelectPicksWithLlm:
    """Tests for select_picks_with_llm function."""

    def test_max_picks_zero(self):
        """max_picks=0 should return empty list."""
        from src.scoring.composite_v2 import select_picks_with_llm, DualCompositeScore

        scores = [DualCompositeScore(
            symbol="AAPL",
            strategy_mode="conservative",
            trend_score=50,
            momentum_score=50,
            value_score=50,
            sentiment_score=50,
            momentum_12_1_score=50,
            breakout_score=50,
            catalyst_score=50,
            risk_adjusted_score=50,
            composite_score=80,
            percentile_rank=90,
            reasoning="Test",
            weights_used={},
            timestamp=datetime.utcnow(),
        )]
        judgments = [MockJudgmentOutput(symbol="AAPL", decision="buy", confidence=0.9)]

        result = select_picks_with_llm(
            scores=scores,
            llm_judgments=judgments,
            max_picks=0,
            min_rule_score=50,
        )

        assert result == []

    def test_llm_buy_decision_filter(self):
        """Only 'buy' decisions should be selected."""
        from src.scoring.composite_v2 import select_picks_with_llm, DualCompositeScore

        scores = []
        for symbol in ["AAPL", "MSFT", "GOOGL"]:
            scores.append(DualCompositeScore(
                symbol=symbol,
                strategy_mode="conservative",
                trend_score=50,
                momentum_score=50,
                value_score=50,
                sentiment_score=50,
                momentum_12_1_score=50,
                breakout_score=50,
                catalyst_score=50,
                risk_adjusted_score=50,
                composite_score=80,
                percentile_rank=90,
                reasoning="Test",
                weights_used={},
                timestamp=datetime.utcnow(),
            ))

        judgments = [
            MockJudgmentOutput(symbol="AAPL", decision="buy", confidence=0.9),
            MockJudgmentOutput(symbol="MSFT", decision="hold", confidence=0.9),
            MockJudgmentOutput(symbol="GOOGL", decision="avoid", confidence=0.9),
        ]

        result = select_picks_with_llm(
            scores=scores,
            llm_judgments=judgments,
            max_picks=5,
            min_rule_score=50,
        )

        assert result == ["AAPL"]
        assert "MSFT" not in result
        assert "GOOGL" not in result

    def test_rule_based_threshold_filter(self):
        """Symbols must pass rule-based threshold."""
        from src.scoring.composite_v2 import select_picks_with_llm, DualCompositeScore

        scores = [
            DualCompositeScore(
                symbol="AAPL",
                strategy_mode="conservative",
                trend_score=50,
                momentum_score=50,
                value_score=50,
                sentiment_score=50,
                momentum_12_1_score=50,
                breakout_score=50,
                catalyst_score=50,
                risk_adjusted_score=50,
                composite_score=80,  # Above threshold
                percentile_rank=90,
                reasoning="Test",
                weights_used={},
                timestamp=datetime.utcnow(),
            ),
            DualCompositeScore(
                symbol="MSFT",
                strategy_mode="conservative",
                trend_score=50,
                momentum_score=50,
                value_score=50,
                sentiment_score=50,
                momentum_12_1_score=50,
                breakout_score=50,
                catalyst_score=50,
                risk_adjusted_score=50,
                composite_score=40,  # Below threshold
                percentile_rank=90,
                reasoning="Test",
                weights_used={},
                timestamp=datetime.utcnow(),
            ),
        ]

        judgments = [
            MockJudgmentOutput(symbol="AAPL", decision="buy", confidence=0.9),
            MockJudgmentOutput(symbol="MSFT", decision="buy", confidence=0.95),  # Higher confidence but below threshold
        ]

        result = select_picks_with_llm(
            scores=scores,
            llm_judgments=judgments,
            max_picks=5,
            min_rule_score=50,
        )

        assert result == ["AAPL"]
        assert "MSFT" not in result

    def test_confidence_threshold_filter(self):
        """Symbols must meet minimum confidence threshold."""
        from src.scoring.composite_v2 import select_picks_with_llm, DualCompositeScore

        scores = []
        for symbol in ["AAPL", "MSFT"]:
            scores.append(DualCompositeScore(
                symbol=symbol,
                strategy_mode="conservative",
                trend_score=50,
                momentum_score=50,
                value_score=50,
                sentiment_score=50,
                momentum_12_1_score=50,
                breakout_score=50,
                catalyst_score=50,
                risk_adjusted_score=50,
                composite_score=80,
                percentile_rank=90,
                reasoning="Test",
                weights_used={},
                timestamp=datetime.utcnow(),
            ))

        judgments = [
            MockJudgmentOutput(symbol="AAPL", decision="buy", confidence=0.7),
            MockJudgmentOutput(symbol="MSFT", decision="buy", confidence=0.4),  # Below min_confidence
        ]

        result = select_picks_with_llm(
            scores=scores,
            llm_judgments=judgments,
            max_picks=5,
            min_rule_score=50,
            min_confidence=0.5,
        )

        assert result == ["AAPL"]
        assert "MSFT" not in result

    def test_sorted_by_confidence(self):
        """Results should be sorted by LLM confidence, not rule score."""
        from src.scoring.composite_v2 import select_picks_with_llm, DualCompositeScore

        scores = []
        for symbol, composite in [("AAPL", 90), ("MSFT", 85), ("GOOGL", 80)]:
            scores.append(DualCompositeScore(
                symbol=symbol,
                strategy_mode="conservative",
                trend_score=50,
                momentum_score=50,
                value_score=50,
                sentiment_score=50,
                momentum_12_1_score=50,
                breakout_score=50,
                catalyst_score=50,
                risk_adjusted_score=50,
                composite_score=composite,
                percentile_rank=90,
                reasoning="Test",
                weights_used={},
                timestamp=datetime.utcnow(),
            ))

        judgments = [
            MockJudgmentOutput(symbol="AAPL", decision="buy", confidence=0.6),  # Lowest confidence
            MockJudgmentOutput(symbol="MSFT", decision="buy", confidence=0.9),  # Highest confidence
            MockJudgmentOutput(symbol="GOOGL", decision="buy", confidence=0.75),  # Medium confidence
        ]

        result = select_picks_with_llm(
            scores=scores,
            llm_judgments=judgments,
            max_picks=5,
            min_rule_score=50,
        )

        # Should be sorted by confidence, not composite score
        assert result == ["MSFT", "GOOGL", "AAPL"]

    def test_max_picks_limits_results(self):
        """Should return at most max_picks results."""
        from src.scoring.composite_v2 import select_picks_with_llm, DualCompositeScore

        scores = []
        for symbol in ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]:
            scores.append(DualCompositeScore(
                symbol=symbol,
                strategy_mode="conservative",
                trend_score=50,
                momentum_score=50,
                value_score=50,
                sentiment_score=50,
                momentum_12_1_score=50,
                breakout_score=50,
                catalyst_score=50,
                risk_adjusted_score=50,
                composite_score=80,
                percentile_rank=90,
                reasoning="Test",
                weights_used={},
                timestamp=datetime.utcnow(),
            ))

        judgments = [
            MockJudgmentOutput(symbol=s, decision="buy", confidence=0.9 - i * 0.05)
            for i, s in enumerate(["AAPL", "MSFT", "GOOGL", "AMZN", "META"])
        ]

        result = select_picks_with_llm(
            scores=scores,
            llm_judgments=judgments,
            max_picks=2,
            min_rule_score=50,
        )

        assert len(result) == 2

    def test_integration_with_sample_judgments(self, sample_judgments):
        """Integration test using fixtures from conftest.py."""
        from src.scoring.composite_v2 import select_picks_with_llm, DualCompositeScore

        # Create scores for all symbols in sample_judgments
        scores = []
        for j in sample_judgments:
            scores.append(DualCompositeScore(
                symbol=j.symbol,
                strategy_mode="conservative",
                trend_score=50,
                momentum_score=50,
                value_score=50,
                sentiment_score=50,
                momentum_12_1_score=50,
                breakout_score=50,
                catalyst_score=50,
                risk_adjusted_score=50,
                composite_score=70,  # All pass threshold
                percentile_rank=70,
                reasoning="Test",
                weights_used={},
                timestamp=datetime.utcnow(),
            ))

        result = select_picks_with_llm(
            scores=scores,
            llm_judgments=sample_judgments,
            max_picks=3,
            min_rule_score=50,
            min_confidence=0.5,
        )

        # Expected: AAPL(0.85), MSFT(0.75), GOOGL(0.65) - top 3 by confidence with "buy" decision
        # META has confidence 0.55 (above threshold but not top 3)
        # AMZN is "hold", NVDA is "avoid"
        assert len(result) == 3
        assert result[0] == "AAPL"  # Highest confidence
        assert result[1] == "MSFT"
        assert result[2] == "GOOGL"
        assert "AMZN" not in result  # "hold" decision
        assert "NVDA" not in result  # "avoid" decision
