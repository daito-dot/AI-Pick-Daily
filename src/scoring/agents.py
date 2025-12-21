"""
Scoring Agents

Four specialized agents for stock evaluation:
- Trend Agent: Technical trend analysis (SMA, MACD)
- Momentum Agent: Short-term momentum (RSI, volume)
- Value Agent: Fundamental valuation (PE, PB, dividend)
- Sentiment Agent: Market sentiment (news, insider activity)
"""
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class AgentScore:
    """Score from a single agent."""
    name: str
    score: int  # 0-100
    components: dict[str, float]
    reasoning: str


@dataclass
class StockData:
    """Input data for scoring a stock."""
    symbol: str
    prices: list[float]  # Historical closing prices (newest last)
    volumes: list[float]  # Historical volumes
    open_price: float  # Current day open
    pe_ratio: float | None
    pb_ratio: float | None
    dividend_yield: float | None
    week_52_high: float | None
    week_52_low: float | None
    news_count_7d: int
    news_sentiment: float | None  # -1 to 1
    sector_avg_pe: float | None


def calculate_sma(prices: list[float], period: int) -> float:
    """Calculate Simple Moving Average."""
    if len(prices) < period:
        return prices[-1] if prices else 0.0
    return sum(prices[-period:]) / period


def calculate_ema(prices: list[float], period: int) -> float:
    """Calculate Exponential Moving Average."""
    if len(prices) < period:
        return prices[-1] if prices else 0.0

    multiplier = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = (price * multiplier) + (ema * (1 - multiplier))
    return ema


def calculate_rsi(prices: list[float], period: int = 14) -> float:
    """Calculate Relative Strength Index."""
    if len(prices) < period + 1:
        return 50.0  # Neutral

    gains = []
    losses = []

    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(prices: list[float]) -> tuple[float, float, float]:
    """
    Calculate MACD indicator.

    Returns:
        (macd_line, signal_line, histogram)
    """
    if len(prices) < 26:
        return 0.0, 0.0, 0.0

    # Calculate MACD line history for signal line EMA
    macd_history = []
    for i in range(26, len(prices) + 1):
        ema12 = calculate_ema(prices[:i], 12)
        ema26 = calculate_ema(prices[:i], 26)
        macd_history.append(ema12 - ema26)

    macd_line = macd_history[-1]

    # Signal line is 9-day EMA of MACD line
    if len(macd_history) >= 9:
        signal_line = calculate_ema(macd_history, 9)
    else:
        signal_line = sum(macd_history) / len(macd_history)

    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


class TrendAgent:
    """
    Trend Agent: Analyzes price trends using technical indicators.

    Key metrics:
    - SMA alignment (20 > 50 > 200 = strong uptrend)
    - MACD momentum
    - New high proximity
    """

    def score(self, data: StockData) -> AgentScore:
        """Calculate trend score for a stock."""
        components = {}
        reasons = []

        prices = data.prices
        current_price = prices[-1] if prices else 0

        # 1. SMA Alignment (40 points max)
        sma20 = calculate_sma(prices, 20)
        sma50 = calculate_sma(prices, 50)
        sma200 = calculate_sma(prices, 200) if len(prices) >= 200 else sma50

        sma_score = 0
        if current_price > sma20:
            sma_score += 15
            reasons.append("Price above SMA20")
        if current_price > sma50:
            sma_score += 15
            reasons.append("Price above SMA50")
        if sma20 > sma50:
            sma_score += 10
            reasons.append("SMA20 > SMA50 (bullish)")

        components["sma_alignment"] = sma_score

        # 2. MACD Momentum (30 points max)
        macd_line, signal, histogram = calculate_macd(prices)
        macd_score = 0
        if macd_line > 0:
            macd_score += 15
            reasons.append("MACD positive")
        if histogram > 0:
            macd_score += 15
            reasons.append("MACD histogram positive")

        components["macd"] = macd_score

        # 3. 52-Week High Proximity (30 points max)
        high_score = 0
        if data.week_52_high and data.week_52_high > 0:
            proximity = current_price / data.week_52_high
            if proximity > 0.95:
                high_score = 30
                reasons.append("Within 5% of 52-week high")
            elif proximity > 0.90:
                high_score = 20
                reasons.append("Within 10% of 52-week high")
            elif proximity > 0.80:
                high_score = 10

        components["high_proximity"] = high_score

        total_score = min(100, sma_score + macd_score + high_score)

        return AgentScore(
            name="trend",
            score=total_score,
            components=components,
            reasoning="; ".join(reasons) if reasons else "No strong trend signals",
        )


class MomentumAgent:
    """
    Momentum Agent: Analyzes short-term price momentum.

    Key metrics:
    - RSI (not overbought/oversold)
    - Volume surge
    - Price momentum
    """

    def score(self, data: StockData) -> AgentScore:
        """Calculate momentum score for a stock."""
        components = {}
        reasons = []

        prices = data.prices
        volumes = data.volumes

        # 1. RSI Score (40 points max)
        rsi = calculate_rsi(prices, 14)
        rsi_score = 0

        if 40 <= rsi <= 70:
            rsi_score = 40  # Healthy momentum zone
            reasons.append(f"RSI {rsi:.0f} in healthy range")
        elif 30 <= rsi < 40:
            rsi_score = 30  # Potentially oversold, bounce expected
            reasons.append(f"RSI {rsi:.0f} near oversold")
        elif 70 < rsi <= 80:
            rsi_score = 20  # Overbought but still momentum
            reasons.append(f"RSI {rsi:.0f} overbought")
        else:
            rsi_score = 10
            reasons.append(f"RSI {rsi:.0f} extreme")

        components["rsi"] = rsi_score

        # 2. Volume Surge (30 points max)
        volume_score = 0
        if len(volumes) >= 5:
            avg_volume_5d = sum(volumes[-5:]) / 5
            avg_volume_20d = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else avg_volume_5d
            volume_ratio = avg_volume_5d / avg_volume_20d if avg_volume_20d > 0 else 1

            if volume_ratio > 2.0:
                volume_score = 30
                reasons.append(f"Volume surge {volume_ratio:.1f}x")
            elif volume_ratio > 1.5:
                volume_score = 20
                reasons.append(f"Elevated volume {volume_ratio:.1f}x")
            elif volume_ratio > 1.2:
                volume_score = 10

        components["volume"] = volume_score

        # 3. Price Momentum (30 points max)
        momentum_score = 0
        if len(prices) >= 5:
            pct_change_5d = (prices[-1] - prices[-5]) / prices[-5] * 100 if prices[-5] > 0 else 0

            if 2 <= pct_change_5d <= 10:
                momentum_score = 30
                reasons.append(f"5-day gain +{pct_change_5d:.1f}%")
            elif 0 < pct_change_5d < 2:
                momentum_score = 20
            elif pct_change_5d > 10:
                momentum_score = 15  # Too fast, potential reversal
                reasons.append(f"5-day gain +{pct_change_5d:.1f}% (extended)")

        components["price_momentum"] = momentum_score

        total_score = min(100, rsi_score + volume_score + momentum_score)

        return AgentScore(
            name="momentum",
            score=total_score,
            components=components,
            reasoning="; ".join(reasons) if reasons else "No strong momentum signals",
        )


class ValueAgent:
    """
    Value Agent: Analyzes fundamental valuation.

    Key metrics:
    - PE ratio vs sector average
    - PB ratio
    - Dividend yield
    """

    def score(self, data: StockData) -> AgentScore:
        """Calculate value score for a stock."""
        components = {}
        reasons = []

        # 1. PE Ratio Score (40 points max)
        pe_score = 0
        if data.pe_ratio is not None and data.pe_ratio > 0:
            sector_pe = data.sector_avg_pe or 25  # Default sector average

            pe_ratio = data.pe_ratio / sector_pe
            if pe_ratio < 0.5:
                pe_score = 40
                reasons.append(f"PE {data.pe_ratio:.1f} < 50% of sector avg")
            elif pe_ratio < 0.75:
                pe_score = 30
                reasons.append(f"PE {data.pe_ratio:.1f} undervalued")
            elif pe_ratio < 1.0:
                pe_score = 20
                reasons.append(f"PE {data.pe_ratio:.1f} fairly valued")
            elif pe_ratio < 1.5:
                pe_score = 10
            else:
                pe_score = 5
                reasons.append(f"PE {data.pe_ratio:.1f} overvalued")

        components["pe_ratio"] = pe_score

        # 2. PB Ratio Score (30 points max)
        pb_score = 0
        if data.pb_ratio is not None and data.pb_ratio > 0:
            if data.pb_ratio < 1.0:
                pb_score = 30
                reasons.append(f"PB {data.pb_ratio:.1f} < 1 (deep value)")
            elif data.pb_ratio < 2.0:
                pb_score = 20
                reasons.append(f"PB {data.pb_ratio:.1f} reasonable")
            elif data.pb_ratio < 3.0:
                pb_score = 10
            else:
                pb_score = 5

        components["pb_ratio"] = pb_score

        # 3. Dividend Yield Score (30 points max)
        div_score = 0
        if data.dividend_yield is not None and data.dividend_yield > 0:
            if data.dividend_yield > 4.0:
                div_score = 30
                reasons.append(f"Dividend yield {data.dividend_yield:.1f}%")
            elif data.dividend_yield > 2.5:
                div_score = 20
                reasons.append(f"Dividend yield {data.dividend_yield:.1f}%")
            elif data.dividend_yield > 1.0:
                div_score = 10

        components["dividend"] = div_score

        total_score = min(100, pe_score + pb_score + div_score)

        return AgentScore(
            name="value",
            score=total_score,
            components=components,
            reasoning="; ".join(reasons) if reasons else "No strong value signals",
        )


class SentimentAgent:
    """
    Sentiment Agent: Analyzes market sentiment.

    Key metrics:
    - News volume (7 days)
    - News sentiment score
    - Buzz factor
    """

    def score(self, data: StockData) -> AgentScore:
        """Calculate sentiment score for a stock."""
        components = {}
        reasons = []

        # 1. News Volume Score (40 points max)
        news_score = 0
        news_count = data.news_count_7d

        if news_count >= 20:
            news_score = 40
            reasons.append(f"High news coverage ({news_count} articles)")
        elif news_count >= 10:
            news_score = 30
            reasons.append(f"Good news coverage ({news_count} articles)")
        elif news_count >= 5:
            news_score = 20
        elif news_count >= 1:
            news_score = 10
        else:
            news_score = 5
            reasons.append("Low news coverage")

        components["news_volume"] = news_score

        # 2. Sentiment Score (60 points max)
        sentiment_score = 0
        if data.news_sentiment is not None:
            # Sentiment ranges from -1 (bearish) to +1 (bullish)
            sentiment = data.news_sentiment

            if sentiment > 0.5:
                sentiment_score = 60
                reasons.append(f"Strong positive sentiment ({sentiment:.2f})")
            elif sentiment > 0.2:
                sentiment_score = 45
                reasons.append(f"Positive sentiment ({sentiment:.2f})")
            elif sentiment > 0:
                sentiment_score = 30
            elif sentiment > -0.2:
                sentiment_score = 20  # Neutral
            else:
                sentiment_score = 10
                reasons.append(f"Negative sentiment ({sentiment:.2f})")

        components["sentiment"] = sentiment_score

        total_score = min(100, news_score + sentiment_score)

        return AgentScore(
            name="sentiment",
            score=total_score,
            components=components,
            reasoning="; ".join(reasons) if reasons else "Limited sentiment data",
        )


# Convenience function to get all agents
def get_all_agents() -> list:
    """Get instances of all scoring agents."""
    return [
        TrendAgent(),
        MomentumAgent(),
        ValueAgent(),
        SentimentAgent(),
    ]
