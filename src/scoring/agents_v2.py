"""
V2 Aggressive Scoring Agents

Four specialized agents for high-return stock evaluation:
- Momentum12_1Agent: 12-month momentum (excluding last month)
- BreakoutAgent: Breakout detection from consolidation
- CatalystAgent: News/earnings catalyst detection
- RiskAdjustedAgent: VIX-based risk adjustment
"""
from dataclasses import dataclass

import numpy as np

from .agents import AgentScore, StockData, calculate_sma, calculate_rsi


@dataclass
class V2StockData(StockData):
    """Extended stock data for V2 agents."""
    # Additional fields for V2
    price_1m_ago: float | None = None
    price_12m_ago: float | None = None
    earnings_surprise_pct: float | None = None  # Latest earnings surprise %
    analyst_revision_score: float | None = None  # Target price revision %
    short_interest_pct: float | None = None  # Short interest as % of float
    gap_pct: float | None = None  # Today's gap %
    premarket_volume_ratio: float | None = None  # Premarket vol / avg vol
    vix_level: float = 20.0  # Current VIX


def calculate_momentum_12_1(prices: list[float]) -> float:
    """
    Calculate 12-1 momentum (12-month return excluding last month).

    This is the classic momentum factor used in academic research.
    """
    if len(prices) < 252:  # Need ~1 year of daily data
        return 0.0

    # Price 12 months ago (252 trading days)
    price_12m = prices[-252] if len(prices) >= 252 else prices[0]
    # Price 1 month ago (21 trading days)
    price_1m = prices[-21] if len(prices) >= 21 else prices[-1]

    if price_12m <= 0:
        return 0.0

    # 12-1 momentum: return from 12m ago to 1m ago
    momentum = (price_1m - price_12m) / price_12m * 100
    return momentum


def detect_breakout(prices: list[float], volumes: list[float]) -> dict:
    """
    Detect if stock is breaking out from a consolidation base.

    Returns dict with breakout characteristics.
    """
    if len(prices) < 50:
        return {"is_breakout": False, "strength": 0}

    current_price = prices[-1]

    # Find recent high (last 50 days)
    recent_high = max(prices[-50:])

    # Find consolidation range (days 50-20)
    if len(prices) >= 50:
        consolidation_prices = prices[-50:-20]
        consolidation_high = max(consolidation_prices)
        consolidation_low = min(consolidation_prices)
        # Avoid division by zero for penny stocks or bad data
        if consolidation_low <= 0:
            return {"is_breakout": False, "strength": 0}
        consolidation_range = (consolidation_high - consolidation_low) / consolidation_low
    else:
        return {"is_breakout": False, "strength": 0}

    # Volume surge check
    avg_volume_20d = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
    current_volume = volumes[-1] if volumes else 0
    volume_ratio = current_volume / avg_volume_20d if avg_volume_20d > 0 else 1

    # Breakout conditions
    is_new_high = current_price >= recent_high * 0.98  # Within 2% of recent high
    is_tight_base = consolidation_range < 0.15  # Less than 15% range
    has_volume = volume_ratio > 1.5  # 50% above average volume

    is_breakout = is_new_high and has_volume

    # Breakout strength (0-100)
    strength = 0
    if is_breakout:
        strength = min(100, int(
            (30 if is_new_high else 0) +
            (30 if is_tight_base else 15) +
            (min(40, volume_ratio * 20))
        ))

    return {
        "is_breakout": is_breakout,
        "strength": strength,
        "is_new_high": is_new_high,
        "is_tight_base": is_tight_base,
        "volume_ratio": volume_ratio,
    }


class Momentum12_1Agent:
    """
    Momentum 12-1 Agent: Classic momentum factor.

    The 12-1 momentum factor has been one of the strongest predictors
    of future returns in academic finance research.
    """

    def score(self, data: V2StockData) -> AgentScore:
        """Calculate 12-1 momentum score."""
        components = {}
        reasons = []

        prices = data.prices

        # 1. 12-1 Momentum (60 points max)
        momentum = calculate_momentum_12_1(prices)
        components["momentum_12_1"] = momentum

        momentum_score = 0
        if momentum > 50:
            momentum_score = 60
            reasons.append(f"Strong 12-1 momentum +{momentum:.0f}%")
        elif momentum > 30:
            momentum_score = 50
            reasons.append(f"Good 12-1 momentum +{momentum:.0f}%")
        elif momentum > 15:
            momentum_score = 40
            reasons.append(f"Positive 12-1 momentum +{momentum:.0f}%")
        elif momentum > 0:
            momentum_score = 25
        else:
            momentum_score = 10
            reasons.append(f"Negative momentum {momentum:.0f}%")

        # 2. Momentum Rank vs Peers (implied, 20 points)
        # This would need peer comparison - simplified here
        rank_score = 20 if momentum > 20 else 10

        # 3. Trend Confirmation (20 points)
        trend_score = 0
        if len(prices) >= 50:
            sma20 = calculate_sma(prices, 20)
            sma50 = calculate_sma(prices, 50)
            current = prices[-1]

            if current > sma20 > sma50:
                trend_score = 20
                reasons.append("Trend aligned (price > SMA20 > SMA50)")
            elif current > sma20:
                trend_score = 10

        components["trend_confirmation"] = trend_score

        total_score = min(100, momentum_score + rank_score + trend_score)

        return AgentScore(
            name="momentum_12_1",
            score=total_score,
            components=components,
            reasoning="; ".join(reasons) if reasons else "Weak momentum",
        )


class BreakoutAgent:
    """
    Breakout Agent: Detects breakouts from consolidation bases.

    Focuses on stocks breaking to new highs with volume confirmation.
    """

    def score(self, data: V2StockData) -> AgentScore:
        """Calculate breakout score."""
        components = {}
        reasons = []

        prices = data.prices
        volumes = data.volumes

        # 1. Breakout Detection (50 points max)
        breakout = detect_breakout(prices, volumes)
        components["breakout_detected"] = breakout["is_breakout"]
        components["breakout_strength"] = breakout["strength"]

        breakout_score = 0
        if breakout["is_breakout"]:
            breakout_score = min(50, breakout["strength"])
            reasons.append(f"Breakout detected (strength: {breakout['strength']})")

            if breakout["is_new_high"]:
                reasons.append("New high")
            if breakout["is_tight_base"]:
                reasons.append("Tight consolidation base")

        # 2. Volume Confirmation (25 points max)
        volume_score = 0
        vol_ratio = breakout.get("volume_ratio", 1)
        if vol_ratio > 3:
            volume_score = 25
            reasons.append(f"Volume surge {vol_ratio:.1f}x")
        elif vol_ratio > 2:
            volume_score = 20
            reasons.append(f"Strong volume {vol_ratio:.1f}x")
        elif vol_ratio > 1.5:
            volume_score = 15

        components["volume_score"] = volume_score

        # 3. 52-Week High Proximity (25 points max)
        high_score = 0
        if data.week_52_high and data.week_52_high > 0:
            current = prices[-1] if prices else 0
            proximity = current / data.week_52_high if data.week_52_high > 0 else 0

            if proximity > 0.98:
                high_score = 25
                reasons.append("At 52-week high")
            elif proximity > 0.95:
                high_score = 20
            elif proximity > 0.90:
                high_score = 10

        components["high_proximity"] = high_score

        total_score = min(100, breakout_score + volume_score + high_score)

        return AgentScore(
            name="breakout",
            score=total_score,
            components=components,
            reasoning="; ".join(reasons) if reasons else "No breakout signal",
        )


class CatalystAgent:
    """
    Catalyst Agent: Detects news and earnings catalysts.

    Focuses on stocks with positive fundamental catalysts.
    """

    def score(self, data: V2StockData) -> AgentScore:
        """Calculate catalyst score."""
        components = {}
        reasons = []

        # 1. Earnings Surprise (40 points max)
        # Neutral score (15) when no data - don't penalize missing data
        earnings_score = 15  # Neutral default
        if data.earnings_surprise_pct is not None:
            surprise = data.earnings_surprise_pct
            if surprise > 20:
                earnings_score = 40
                reasons.append(f"Strong earnings beat +{surprise:.0f}%")
            elif surprise > 10:
                earnings_score = 30
                reasons.append(f"Earnings beat +{surprise:.0f}%")
            elif surprise > 5:
                earnings_score = 20
            elif surprise > 0:
                earnings_score = 15
            else:
                earnings_score = 5
                if surprise < -10:
                    reasons.append(f"Earnings miss {surprise:.0f}%")

        components["earnings_surprise"] = earnings_score

        # 2. Analyst Revisions (30 points max)
        # Neutral score (10) when no data
        revision_score = 10  # Neutral default
        if data.analyst_revision_score is not None:
            rev = data.analyst_revision_score
            if rev > 10:
                revision_score = 30
                reasons.append(f"Target raised +{rev:.0f}%")
            elif rev > 5:
                revision_score = 20
            elif rev > 0:
                revision_score = 15
            elif rev < -5:
                revision_score = 5

        components["analyst_revision"] = revision_score

        # 3. Gap Up / News Reaction (30 points max)
        # Neutral score (10) when no data
        gap_score = 10  # Neutral default
        if data.gap_pct is not None:
            gap = data.gap_pct
            if gap > 10:
                gap_score = 30
                reasons.append(f"Strong gap up +{gap:.0f}%")
            elif gap > 5:
                gap_score = 25
                reasons.append(f"Gap up +{gap:.0f}%")
            elif gap > 3:
                gap_score = 15
            elif gap < -5:
                gap_score = 5
                reasons.append(f"Gap down {gap:.0f}%")

        components["gap_reaction"] = gap_score

        # 4. Short Squeeze Potential (bonus)
        if data.short_interest_pct is not None and data.short_interest_pct > 20:
            reasons.append(f"High short interest {data.short_interest_pct:.0f}%")

        total_score = min(100, earnings_score + revision_score + gap_score)

        return AgentScore(
            name="catalyst",
            score=total_score,
            components=components,
            reasoning="; ".join(reasons) if reasons else "No catalyst detected",
        )


class RiskAdjustedAgent:
    """
    Risk-Adjusted Agent: Adjusts scores based on market conditions.

    Reduces exposure in high-volatility environments.
    """

    def score(self, data: V2StockData) -> AgentScore:
        """Calculate risk-adjusted score."""
        components = {}
        reasons = []

        vix = data.vix_level
        prices = data.prices

        # 1. VIX-Based Risk Score (40 points max)
        vix_score = 0
        if vix < 15:
            vix_score = 40
            reasons.append(f"Low volatility (VIX {vix:.0f})")
        elif vix < 20:
            vix_score = 35
            reasons.append(f"Normal volatility (VIX {vix:.0f})")
        elif vix < 25:
            vix_score = 25
            reasons.append(f"Elevated volatility (VIX {vix:.0f})")
        elif vix < 30:
            vix_score = 15
            reasons.append(f"High volatility (VIX {vix:.0f})")
        else:
            vix_score = 5
            reasons.append(f"Extreme volatility (VIX {vix:.0f})")

        components["vix_score"] = vix_score

        # 2. Stock Volatility (30 points max)
        stock_vol_score = 0
        if len(prices) >= 20:
            returns = np.diff(prices[-20:]) / prices[-20:-1]
            daily_vol = np.std(returns) * 100
            annualized_vol = daily_vol * np.sqrt(252)

            if annualized_vol < 20:
                stock_vol_score = 30
            elif annualized_vol < 30:
                stock_vol_score = 25
            elif annualized_vol < 40:
                stock_vol_score = 15
            else:
                stock_vol_score = 5
                reasons.append(f"High stock volatility ({annualized_vol:.0f}%)")

        components["stock_volatility"] = stock_vol_score

        # 3. Drawdown Risk (30 points max)
        drawdown_score = 0
        if len(prices) >= 20:
            peak = max(prices[-60:]) if len(prices) >= 60 else max(prices)
            current = prices[-1]
            drawdown = (peak - current) / peak * 100

            if drawdown < 5:
                drawdown_score = 30
            elif drawdown < 10:
                drawdown_score = 25
            elif drawdown < 15:
                drawdown_score = 15
            else:
                drawdown_score = 5
                reasons.append(f"In drawdown ({drawdown:.0f}%)")

        components["drawdown_risk"] = drawdown_score

        total_score = min(100, vix_score + stock_vol_score + drawdown_score)

        return AgentScore(
            name="risk_adjusted",
            score=total_score,
            components=components,
            reasoning="; ".join(reasons) if reasons else "Favorable risk conditions",
        )


def get_v2_agents() -> list:
    """Get instances of all V2 scoring agents."""
    return [
        Momentum12_1Agent(),
        BreakoutAgent(),
        CatalystAgent(),
        RiskAdjustedAgent(),
    ]
