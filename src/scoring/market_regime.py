"""
Market Regime Detection

Determines the current market environment:
- Normal: Standard conditions, full recommendations
- Adjustment: Elevated volatility, reduced recommendations
- Crisis: Extreme conditions, minimal or no recommendations

Based on VIX, S&P 500 deviation, and volatility clustering.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal

import numpy as np
import pandas as pd


class MarketRegime(str, Enum):
    """Market regime classification."""
    NORMAL = "normal"
    ADJUSTMENT = "adjustment"
    CRISIS = "crisis"


@dataclass
class MarketRegimeResult:
    """Result of market regime analysis."""
    regime: MarketRegime
    vix_level: float
    sp500_deviation_pct: float
    volatility_cluster: bool
    max_picks: int
    weight_adjustments: dict[str, float]
    notes: str
    timestamp: datetime


@dataclass
class AgentWeightAdjustment:
    """Weight adjustment per agent based on regime."""
    trend: float
    momentum: float
    value: float
    sentiment: float


# Default weights (from requirements)
DEFAULT_WEIGHTS = {
    "trend": 0.35,
    "momentum": 0.35,
    "value": 0.20,
    "sentiment": 0.10,
}

# Weight adjustments by regime
REGIME_WEIGHT_ADJUSTMENTS = {
    MarketRegime.NORMAL: AgentWeightAdjustment(
        trend=0.0,
        momentum=0.0,
        value=0.0,
        sentiment=0.0,
    ),
    MarketRegime.ADJUSTMENT: AgentWeightAdjustment(
        trend=0.05,
        momentum=0.05,
        value=0.0,
        sentiment=-0.10,
    ),
    MarketRegime.CRISIS: AgentWeightAdjustment(
        trend=-0.10,
        momentum=-0.10,
        value=0.15,
        sentiment=0.0,
    ),
}

# Max picks by regime (legacy — use REGIME_DECISION_PARAMS instead)
REGIME_MAX_PICKS = {
    MarketRegime.NORMAL: 5,
    MarketRegime.ADJUSTMENT: 3,
    MarketRegime.CRISIS: 0,  # No recommendations in crisis
}

# Decision parameters by regime — controls the deterministic decision function
REGIME_DECISION_PARAMS = {
    MarketRegime.NORMAL: {
        "max_picks": 5,
        "min_score": 55,        # Rule-based score minimum
        "max_risk": 3.5,        # Max acceptable LLM risk score (1-5)
        "min_consensus": 0.5,   # Minimum ensemble agreement ratio
    },
    MarketRegime.ADJUSTMENT: {
        "max_picks": 3,
        "min_score": 65,
        "max_risk": 2.5,
        "min_consensus": 0.6,
    },
    MarketRegime.CRISIS: {
        "max_picks": 1,
        "min_score": 75,
        "max_risk": 1.5,
        "min_consensus": 0.8,
    },
}


def calculate_sma(prices: list[float], period: int = 20) -> float:
    """
    Calculate Simple Moving Average.

    Args:
        prices: List of closing prices (newest last)
        period: SMA period

    Returns:
        SMA value
    """
    if len(prices) < period:
        return prices[-1] if prices else 0.0
    return sum(prices[-period:]) / period


def calculate_volatility(prices: list[float], period: int = 5) -> float:
    """
    Calculate price volatility (standard deviation of returns).

    Args:
        prices: List of closing prices
        period: Period for calculation

    Returns:
        Volatility (annualized)
    """
    if len(prices) < period + 1:
        return 0.0

    returns = []
    for i in range(1, min(period + 1, len(prices))):
        ret = (prices[-i] - prices[-i - 1]) / prices[-i - 1]
        returns.append(ret)

    if not returns:
        return 0.0

    return float(np.std(returns)) * np.sqrt(252)  # Annualized


def detect_volatility_cluster(
    volatility_5d: float,
    volatility_30d: float,
    threshold: float = 1.5,
) -> bool:
    """
    Detect if there's a volatility cluster (recent vol > threshold * long-term vol).

    Args:
        volatility_5d: 5-day volatility
        volatility_30d: 30-day volatility
        threshold: Multiplier threshold

    Returns:
        True if volatility cluster detected
    """
    if volatility_30d == 0:
        return False
    return volatility_5d > (volatility_30d * threshold)


def decide_market_regime(
    vix: float,
    sp500_price_today: float,
    sp500_sma20: float,
    volatility_5d_avg: float,
    volatility_30d_avg: float,
    nyse_ad_ratio: float | None = None,  # Phase 2
) -> MarketRegimeResult:
    """
    Determine the current market regime.

    Args:
        vix: Current VIX level
        sp500_price_today: Current S&P 500 price
        sp500_sma20: 20-day SMA of S&P 500
        volatility_5d_avg: 5-day average volatility
        volatility_30d_avg: 30-day average volatility
        nyse_ad_ratio: NYSE Advance/Decline ratio (Phase 2)

    Returns:
        MarketRegimeResult with regime and adjustments
    """
    flags = {"crisis": 0, "adjustment": 0}
    notes = []

    # 1) VIX Check
    if vix > 30:
        flags["crisis"] += 1
        notes.append(f"VIX > 30 ({vix:.1f}): CRISIS signal")
    elif 20 < vix <= 30:
        flags["adjustment"] += 1
        notes.append(f"VIX 20-30 ({vix:.1f}): ADJUSTMENT signal")
    else:
        notes.append(f"VIX normal ({vix:.1f})")

    # 2) S&P 500 Deviation from SMA20
    deviation_pct = ((sp500_price_today - sp500_sma20) / sp500_sma20) * 100 if sp500_sma20 > 0 else 0
    if deviation_pct < -3:
        flags["adjustment"] += 1
        notes.append(f"S&P 500 deviation {deviation_pct:.1f}% < -3%: ADJUSTMENT signal")
    else:
        notes.append(f"S&P 500 deviation {deviation_pct:.1f}%: normal")

    # 3) Volatility Cluster
    volatility_cluster = detect_volatility_cluster(volatility_5d_avg, volatility_30d_avg)
    if volatility_cluster:
        flags["adjustment"] += 1
        notes.append(f"Volatility cluster detected (5d: {volatility_5d_avg:.2f}, 30d: {volatility_30d_avg:.2f})")
    else:
        notes.append("No volatility cluster")

    # 4) Market Breadth (Phase 2)
    if nyse_ad_ratio is not None and nyse_ad_ratio < 0.7:
        flags["adjustment"] += 1
        notes.append(f"NYSE A/D ratio {nyse_ad_ratio:.2f} < 0.7: ADJUSTMENT signal")

    # Final Decision
    if flags["crisis"] >= 1:
        regime = MarketRegime.CRISIS
    elif flags["adjustment"] >= 2:
        regime = MarketRegime.ADJUSTMENT
    else:
        regime = MarketRegime.NORMAL

    notes.append(f"Final regime: {regime.value.upper()}")

    # Calculate weight adjustments
    adjustments = REGIME_WEIGHT_ADJUSTMENTS[regime]
    weight_adjustments = {
        "trend": DEFAULT_WEIGHTS["trend"] + adjustments.trend,
        "momentum": DEFAULT_WEIGHTS["momentum"] + adjustments.momentum,
        "value": DEFAULT_WEIGHTS["value"] + adjustments.value,
        "sentiment": DEFAULT_WEIGHTS["sentiment"] + adjustments.sentiment,
    }

    return MarketRegimeResult(
        regime=regime,
        vix_level=vix,
        sp500_deviation_pct=deviation_pct,
        volatility_cluster=volatility_cluster,
        max_picks=REGIME_MAX_PICKS[regime],
        weight_adjustments=weight_adjustments,
        notes="\n".join(notes),
        timestamp=datetime.utcnow(),
    )


def get_adjusted_weights(
    regime_result: MarketRegimeResult,
    base_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Get the final adjusted weights for scoring agents.

    Args:
        regime_result: MarketRegimeResult from decide_market_regime
        base_weights: Optional custom base weights

    Returns:
        Dict of agent weights that sum to 1.0
    """
    if base_weights is None:
        base_weights = DEFAULT_WEIGHTS.copy()

    weights = regime_result.weight_adjustments.copy()

    # Normalize to ensure sum = 1.0
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}

    return weights
