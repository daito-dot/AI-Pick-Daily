"""
Composite Score Calculator

Combines scores from all agents into a final recommendation score.
Handles:
- Weighted aggregation
- Percentile ranking
- Final pick selection
"""
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy import stats

from .agents import AgentScore, StockData, get_all_agents, TrendAgent, MomentumAgent, ValueAgent, SentimentAgent
from .market_regime import MarketRegimeResult, get_adjusted_weights


@dataclass
class CompositeScore:
    """Final composite score for a stock."""
    symbol: str
    trend_score: int
    momentum_score: int
    value_score: int
    sentiment_score: int
    composite_score: int
    percentile_rank: int
    reasoning: str
    agent_details: dict[str, AgentScore]
    weights_used: dict[str, float]
    timestamp: datetime


@dataclass
class ScoringResult:
    """Result of scoring multiple stocks."""
    scores: list[CompositeScore]
    market_regime: MarketRegimeResult
    top_picks: list[str]
    cutoff_timestamp: datetime


def calculate_composite_score(
    stock_data: StockData,
    weights: dict[str, float],
) -> CompositeScore:
    """
    Calculate composite score for a single stock.

    Args:
        stock_data: Stock data for scoring
        weights: Agent weights from market regime

    Returns:
        CompositeScore with all details
    """
    # Score with each agent
    trend_agent = TrendAgent()
    momentum_agent = MomentumAgent()
    value_agent = ValueAgent()
    sentiment_agent = SentimentAgent()

    trend_score = trend_agent.score(stock_data)
    momentum_score = momentum_agent.score(stock_data)
    value_score = value_agent.score(stock_data)
    sentiment_score = sentiment_agent.score(stock_data)

    # Calculate weighted composite
    composite = (
        trend_score.score * weights.get("trend", 0.35) +
        momentum_score.score * weights.get("momentum", 0.35) +
        value_score.score * weights.get("value", 0.20) +
        sentiment_score.score * weights.get("sentiment", 0.10)
    )

    # Combine reasoning
    reasons = []
    if trend_score.reasoning:
        reasons.append(f"Trend: {trend_score.reasoning}")
    if momentum_score.reasoning:
        reasons.append(f"Momentum: {momentum_score.reasoning}")
    if value_score.reasoning:
        reasons.append(f"Value: {value_score.reasoning}")
    if sentiment_score.reasoning:
        reasons.append(f"Sentiment: {sentiment_score.reasoning}")

    return CompositeScore(
        symbol=stock_data.symbol,
        trend_score=trend_score.score,
        momentum_score=momentum_score.score,
        value_score=value_score.score,
        sentiment_score=sentiment_score.score,
        composite_score=int(round(composite)),
        percentile_rank=0,  # Will be calculated later
        reasoning=" | ".join(reasons),
        agent_details={
            "trend": trend_score,
            "momentum": momentum_score,
            "value": value_score,
            "sentiment": sentiment_score,
        },
        weights_used=weights,
        timestamp=datetime.utcnow(),
    )


def calculate_percentile_ranks(scores: list[CompositeScore]) -> list[CompositeScore]:
    """
    Calculate percentile ranks for all scores.

    Handles edge cases:
    - All same score
    - Small number of candidates

    Args:
        scores: List of CompositeScore objects

    Returns:
        Updated list with percentile_rank filled
    """
    if not scores:
        return scores

    # Extract composite scores
    raw_scores = [s.composite_score for s in scores]

    # Calculate Z-scores with failsafe
    mean_score = np.mean(raw_scores)
    std_score = np.std(raw_scores)

    if std_score < 1e-6:
        # All scores are the same, use rank-based percentile
        sorted_scores = sorted(scores, key=lambda x: x.composite_score, reverse=True)
        n = len(sorted_scores)
        for i, score in enumerate(sorted_scores):
            score.percentile_rank = int(100 * (n - i) / n)
    else:
        # Use proper normal CDF for accurate percentile conversion
        for score in scores:
            z = (score.composite_score - mean_score) / std_score
            # Convert Z-score to percentile using normal CDF
            percentile = int(stats.norm.cdf(z) * 100)
            score.percentile_rank = max(1, min(99, percentile))

    return scores


def select_top_picks(
    scores: list[CompositeScore],
    max_picks: int,
    min_score: int = 60,
) -> list[str]:
    """
    Select top stock picks.

    Args:
        scores: List of scored stocks
        max_picks: Maximum number of picks (from market regime)
        min_score: Minimum composite score threshold

    Returns:
        List of selected symbols
    """
    if max_picks == 0:
        return []

    # Filter by minimum score
    qualified = [s for s in scores if s.composite_score >= min_score]

    # Sort by percentile rank (descending)
    qualified.sort(key=lambda x: x.percentile_rank, reverse=True)

    # Take top N
    picks = [s.symbol for s in qualified[:max_picks]]

    return picks


def run_full_scoring(
    stocks_data: list[StockData],
    market_regime: MarketRegimeResult,
) -> ScoringResult:
    """
    Run full scoring pipeline for all stocks.

    Args:
        stocks_data: List of StockData for all candidates
        market_regime: Current market regime result

    Returns:
        ScoringResult with all scores and picks
    """
    # Get adjusted weights
    weights = get_adjusted_weights(market_regime)

    # Score all stocks
    scores = [calculate_composite_score(data, weights) for data in stocks_data]

    # Calculate percentile ranks
    scores = calculate_percentile_ranks(scores)

    # Select top picks
    top_picks = select_top_picks(scores, market_regime.max_picks)

    return ScoringResult(
        scores=scores,
        market_regime=market_regime,
        top_picks=top_picks,
        cutoff_timestamp=datetime.utcnow(),
    )
