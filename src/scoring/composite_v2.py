"""
Dual Strategy Composite Score Calculator

Supports both V1 (Conservative) and V2 (Aggressive) strategies.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import numpy as np
from scipy import stats

from .agents import TrendAgent, MomentumAgent, ValueAgent, SentimentAgent, AgentScore, StockData
from .agents_v2 import Momentum12_1Agent, BreakoutAgent, CatalystAgent, RiskAdjustedAgent, V2StockData
from .market_regime import MarketRegimeResult, get_adjusted_weights
from src.config import config

logger = logging.getLogger(__name__)


# Expected weight keys for validation
V1_WEIGHT_KEYS = ["trend", "momentum", "value", "sentiment"]
V2_WEIGHT_KEYS = ["momentum_12_1", "breakout", "catalyst", "risk_adjusted"]


def validate_weights(weights: dict[str, float], expected_keys: list[str]) -> None:
    """Validate that weights sum to 1.0 and contain expected keys."""
    total = sum(weights.values())
    if abs(total - 1.0) > 0.01:
        raise ValueError(f"Weights must sum to 1.0, got {total:.3f}")

    missing = set(expected_keys) - set(weights.keys())
    if missing:
        raise ValueError(f"Missing weight keys: {missing}")


def validate_score(score: int, name: str) -> int:
    """Ensure score is within valid range."""
    if score < 0:
        logger.warning(f"{name} score {score} < 0, clamping to 0")
        return 0
    if score > 100:
        logger.warning(f"{name} score {score} > 100, clamping to 100")
        return 100
    return score


StrategyType = Literal["conservative", "aggressive"]


@dataclass
class DualCompositeScore:
    """Composite score with strategy mode."""
    symbol: str
    strategy_mode: StrategyType

    # V1 scores (always calculated for comparison)
    trend_score: int
    momentum_score: int
    value_score: int
    sentiment_score: int

    # V2 scores (always calculated for comparison)
    momentum_12_1_score: int
    breakout_score: int
    catalyst_score: int
    risk_adjusted_score: int

    # Final scores
    composite_score: int
    percentile_rank: int
    reasoning: str
    weights_used: dict[str, float]
    timestamp: datetime


@dataclass
class DualScoringResult:
    """Result containing both V1 and V2 scores."""
    v1_scores: list[DualCompositeScore]
    v2_scores: list[DualCompositeScore]
    v1_picks: list[str]
    v2_picks: list[str]
    market_regime: MarketRegimeResult
    cutoff_timestamp: datetime


def calculate_v1_score(stock_data: StockData, weights: dict[str, float]) -> dict:
    """Calculate V1 (Conservative) component scores."""
    validate_weights(weights, V1_WEIGHT_KEYS)

    trend_agent = TrendAgent()
    momentum_agent = MomentumAgent()
    value_agent = ValueAgent()
    sentiment_agent = SentimentAgent()

    trend = trend_agent.score(stock_data)
    momentum = momentum_agent.score(stock_data)
    value = value_agent.score(stock_data)
    sentiment = sentiment_agent.score(stock_data)

    composite = (
        trend.score * weights.get("trend", 0.35) +
        momentum.score * weights.get("momentum", 0.35) +
        value.score * weights.get("value", 0.20) +
        sentiment.score * weights.get("sentiment", 0.10)
    )

    reasons = []
    if trend.reasoning:
        reasons.append(f"Trend: {trend.reasoning}")
    if momentum.reasoning:
        reasons.append(f"Momentum: {momentum.reasoning}")

    return {
        "trend_score": trend.score,
        "momentum_score": momentum.score,
        "value_score": value.score,
        "sentiment_score": sentiment.score,
        "composite_score": int(round(composite)),
        "reasoning": " | ".join(reasons[:2]),  # Limit reasoning length
    }


def calculate_v2_score(stock_data: V2StockData, weights: dict[str, float]) -> dict:
    """Calculate V2 (Aggressive) component scores."""
    validate_weights(weights, V2_WEIGHT_KEYS)

    momentum_agent = Momentum12_1Agent()
    breakout_agent = BreakoutAgent()
    catalyst_agent = CatalystAgent()
    risk_agent = RiskAdjustedAgent()

    momentum = momentum_agent.score(stock_data)
    breakout = breakout_agent.score(stock_data)
    catalyst = catalyst_agent.score(stock_data)
    risk = risk_agent.score(stock_data)

    composite = (
        momentum.score * weights.get("momentum_12_1", 0.40) +
        breakout.score * weights.get("breakout", 0.25) +
        catalyst.score * weights.get("catalyst", 0.20) +
        risk.score * weights.get("risk_adjusted", 0.15)
    )

    reasons = []
    if momentum.reasoning:
        reasons.append(f"Mom12-1: {momentum.reasoning}")
    if breakout.reasoning and breakout.score > 30:
        reasons.append(f"Breakout: {breakout.reasoning}")

    return {
        "momentum_12_1_score": momentum.score,
        "breakout_score": breakout.score,
        "catalyst_score": catalyst.score,
        "risk_adjusted_score": risk.score,
        "composite_score": int(round(composite)),
        "reasoning": " | ".join(reasons[:2]),
    }


def calculate_dual_scores(
    stock_data: StockData,
    v2_data: V2StockData,
    v1_weights: dict[str, float],
    v2_weights: dict[str, float],
) -> tuple[DualCompositeScore, DualCompositeScore]:
    """
    Calculate both V1 and V2 scores for a single stock.

    Returns tuple of (v1_score, v2_score).
    """
    if stock_data.symbol != v2_data.symbol:
        raise ValueError(f"Symbol mismatch: {stock_data.symbol} != {v2_data.symbol}")

    v1_result = calculate_v1_score(stock_data, v1_weights)
    v2_result = calculate_v2_score(v2_data, v2_weights)

    now = datetime.now(timezone.utc)

    v1_score = DualCompositeScore(
        symbol=stock_data.symbol,
        strategy_mode="conservative",
        trend_score=v1_result["trend_score"],
        momentum_score=v1_result["momentum_score"],
        value_score=v1_result["value_score"],
        sentiment_score=v1_result["sentiment_score"],
        momentum_12_1_score=v2_result["momentum_12_1_score"],
        breakout_score=v2_result["breakout_score"],
        catalyst_score=v2_result["catalyst_score"],
        risk_adjusted_score=v2_result["risk_adjusted_score"],
        composite_score=v1_result["composite_score"],
        percentile_rank=0,
        reasoning=v1_result["reasoning"],
        weights_used=v1_weights,
        timestamp=now,
    )

    v2_score = DualCompositeScore(
        symbol=stock_data.symbol,
        strategy_mode="aggressive",
        trend_score=v1_result["trend_score"],
        momentum_score=v1_result["momentum_score"],
        value_score=v1_result["value_score"],
        sentiment_score=v1_result["sentiment_score"],
        momentum_12_1_score=v2_result["momentum_12_1_score"],
        breakout_score=v2_result["breakout_score"],
        catalyst_score=v2_result["catalyst_score"],
        risk_adjusted_score=v2_result["risk_adjusted_score"],
        composite_score=v2_result["composite_score"],
        percentile_rank=0,
        reasoning=v2_result["reasoning"],
        weights_used=v2_weights,
        timestamp=now,
    )

    return v1_score, v2_score


def calculate_percentile_ranks(scores: list[DualCompositeScore]) -> list[DualCompositeScore]:
    """Calculate percentile ranks for scores."""
    if not scores:
        return scores

    raw_scores = [s.composite_score for s in scores]
    mean_score = np.mean(raw_scores)
    std_score = np.std(raw_scores)

    if std_score < 1e-6:
        sorted_scores = sorted(scores, key=lambda x: x.composite_score, reverse=True)
        n = len(sorted_scores)
        for i, score in enumerate(sorted_scores):
            score.percentile_rank = int(100 * (n - i) / n)
    else:
        for score in scores:
            z = (score.composite_score - mean_score) / std_score
            percentile = int(stats.norm.cdf(z) * 100)
            score.percentile_rank = max(1, min(99, percentile))

    return scores


def select_picks(
    scores: list[DualCompositeScore],
    max_picks: int,
    min_score: int,
) -> list[str]:
    """
    Select picks based on percentile rank (legacy method).

    Note: This is the original selection logic. For LLM-integrated selection,
    use select_picks_with_llm() instead.
    """
    if max_picks == 0:
        return []

    qualified = [s for s in scores if s.composite_score >= min_score]
    qualified.sort(key=lambda x: x.percentile_rank, reverse=True)
    return [s.symbol for s in qualified[:max_picks]]


def get_threshold_passed_symbols(
    scores: list[DualCompositeScore],
    min_score: int,
) -> set[str]:
    """
    Get symbols that passed the rule-based threshold.

    This is used to determine which stocks should be:
    1. Evaluated by LLM
    2. Tracked for performance

    Args:
        scores: Rule-based scores
        min_score: Minimum score threshold (risk filter)

    Returns:
        Set of symbols that passed the threshold
    """
    return {s.symbol for s in scores if s.composite_score >= min_score}


def select_picks_with_llm(
    scores: list[DualCompositeScore],
    llm_judgments: list,  # list[JudgmentOutput] - imported in integration
    max_picks: int,
    min_rule_score: int,
    min_confidence: float = 0.5,
) -> list[str]:
    """
    Select picks using LLM judgment (new LLM-first selection logic).

    Flow:
    1. Rule threshold filters for risk (pass/fail only)
    2. LLM BUY decision & confidence filters
    3. Sort by LLM confidence (not rule score)
    4. Return top N picks

    Args:
        scores: Rule-based composite scores (for threshold filter)
        llm_judgments: LLM JudgmentOutput instances
        max_picks: Maximum number of picks to return
        min_rule_score: Minimum rule score (risk filter threshold)
        min_confidence: Minimum LLM confidence to accept

    Returns:
        List of selected symbols (sorted by LLM confidence)
    """
    if max_picks == 0:
        return []

    # Step 1: Get symbols that passed rule-based risk filter
    risk_cleared = get_threshold_passed_symbols(scores, min_rule_score)

    # Step 2: Filter LLM judgments
    # - Must be 'buy' decision
    # - Must meet confidence threshold
    # - Must have passed rule-based threshold
    qualified_judgments = [
        j for j in llm_judgments
        if j.decision == "buy"
        and j.confidence >= min_confidence
        and j.symbol in risk_cleared
    ]

    # Step 3: Sort by LLM confidence (not rule score!)
    qualified_judgments.sort(key=lambda x: x.confidence, reverse=True)

    # Step 4: Return top N picks
    return [j.symbol for j in qualified_judgments[:max_picks]]


def run_dual_scoring(
    stocks_data: list[StockData],
    v2_stocks_data: list[V2StockData],
    market_regime: MarketRegimeResult,
    v1_threshold: int | None = None,
    v2_threshold: int | None = None,
    v1_factor_weights: dict[str, float] | None = None,
    v2_factor_weights: dict[str, float] | None = None,
) -> DualScoringResult:
    """
    Run both V1 and V2 scoring pipelines.

    Args:
        stocks_data: V1 stock data
        v2_stocks_data: V2 extended stock data
        market_regime: Current market regime
        v1_threshold: Optional dynamic threshold for V1 (from DB). Falls back to config if None.
        v2_threshold: Optional dynamic threshold for V2 (from DB). Falls back to config if None.
        v1_factor_weights: Optional DB-loaded factor weights for V1. Falls back to regime-adjusted defaults.
        v2_factor_weights: Optional DB-loaded factor weights for V2. Falls back to config defaults.

    Returns:
        DualScoringResult with both strategies
    """
    strategy_config = config.strategy
    v1_weights = v1_factor_weights if v1_factor_weights else get_adjusted_weights(market_regime)
    v2_weights = v2_factor_weights if v2_factor_weights else strategy_config.v2_weights

    # Use dynamic thresholds if provided, otherwise fall back to config
    v1_min_score = v1_threshold if v1_threshold is not None else strategy_config.v1_min_score
    v2_min_score = v2_threshold if v2_threshold is not None else strategy_config.v2_min_score

    # Create mapping for V2 data
    v2_data_map = {d.symbol: d for d in v2_stocks_data}

    v1_scores = []
    v2_scores = []

    for stock_data in stocks_data:
        # Get corresponding V2 data or create from V1 data
        v2_data = v2_data_map.get(stock_data.symbol)
        if v2_data is None:
            # Create V2 data from V1 data with defaults
            v2_data = V2StockData(
                symbol=stock_data.symbol,
                prices=stock_data.prices,
                volumes=stock_data.volumes,
                open_price=stock_data.open_price,
                pe_ratio=stock_data.pe_ratio,
                pb_ratio=stock_data.pb_ratio,
                dividend_yield=stock_data.dividend_yield,
                week_52_high=stock_data.week_52_high,
                week_52_low=stock_data.week_52_low,
                news_count_7d=stock_data.news_count_7d,
                news_sentiment=stock_data.news_sentiment,
                sector_avg_pe=stock_data.sector_avg_pe,
                vix_level=market_regime.vix_level,
            )

        v1_score, v2_score = calculate_dual_scores(
            stock_data, v2_data, v1_weights, v2_weights
        )
        v1_scores.append(v1_score)
        v2_scores.append(v2_score)

    # Calculate percentile ranks separately for each strategy
    v1_scores = calculate_percentile_ranks(v1_scores)
    v2_scores = calculate_percentile_ranks(v2_scores)

    # Select picks for each strategy
    v1_max_picks = market_regime.max_picks  # V1 respects regime
    v2_max_picks = strategy_config.v2_max_picks if market_regime.max_picks > 0 else 0

    v1_picks = select_picks(v1_scores, v1_max_picks, v1_min_score)
    v2_picks = select_picks(v2_scores, v2_max_picks, v2_min_score)

    return DualScoringResult(
        v1_scores=v1_scores,
        v2_scores=v2_scores,
        v1_picks=v1_picks,
        v2_picks=v2_picks,
        market_regime=market_regime,
        cutoff_timestamp=datetime.now(timezone.utc),
    )
