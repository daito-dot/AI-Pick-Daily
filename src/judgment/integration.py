"""
Judgment Integration Module

Integrates JudgmentService with the daily scoring pipeline.
Handles data transformation and judgment persistence.
"""
import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any

from src.data.finnhub_client import FinnhubClient, NewsItem
from src.data.supabase_client import SupabaseClient
from .service import JudgmentService
from .models import JudgmentOutput, KeyFactor, ReasoningTrace


logger = logging.getLogger(__name__)


def prepare_stock_data_for_judgment(
    stock_data: Any,  # StockData or V2StockData
) -> dict:
    """
    Convert scoring StockData to judgment format.

    Args:
        stock_data: StockData or V2StockData instance

    Returns:
        Dict suitable for judgment prompt
    """
    prices = stock_data.prices or []
    volumes = stock_data.volumes or []

    # Calculate basic metrics
    current_price = prices[-1] if prices else 0
    change_pct = 0
    if len(prices) >= 2:
        change_pct = ((prices[-1] - prices[-2]) / prices[-2]) * 100

    # Calculate RSI
    rsi = None
    if len(prices) >= 15:
        rsi = _calculate_rsi(prices, 14)

    # Calculate volume ratio
    avg_volume = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else (sum(volumes) / len(volumes) if volumes else 0)
    current_volume = volumes[-1] if volumes else 0

    # Calculate moving averages
    sma_20 = sum(prices[-20:]) / 20 if len(prices) >= 20 else None
    sma_50 = sum(prices[-50:]) / 50 if len(prices) >= 50 else None

    return {
        "symbol": stock_data.symbol,
        "price": current_price,
        "change_pct": change_pct,
        "volume": current_volume,
        "avg_volume": avg_volume,
        "rsi": rsi,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "pe_ratio": stock_data.pe_ratio,
        "pb_ratio": stock_data.pb_ratio,
        "dividend_yield": stock_data.dividend_yield,
        "week_52_high": stock_data.week_52_high,
        "week_52_low": stock_data.week_52_low,
        # Include V2 specific data if available
        "vix_level": getattr(stock_data, "vix_level", None),
        "gap_pct": getattr(stock_data, "gap_pct", None),
    }


def fetch_news_for_judgment(
    finnhub: FinnhubClient,
    symbol: str,
    days: int = 7,
) -> list[dict]:
    """
    Fetch and format news for judgment.

    Args:
        finnhub: Finnhub client
        symbol: Stock symbol
        days: Days of news to fetch

    Returns:
        List of news dicts formatted for judgment
    """
    try:
        news_items = finnhub.get_company_news(symbol)

        news_data = []
        for item in news_items[:15]:  # Limit to recent 15 articles
            news_data.append({
                "headline": item.headline,
                "summary": item.summary[:500] if item.summary else "",  # Truncate long summaries
                "source": item.source,
                "datetime": item.datetime.isoformat() if item.datetime else None,
                "sentiment": item.sentiment,
            })

        return news_data

    except Exception as e:
        logger.warning(f"Failed to fetch news for {symbol}: {e}")
        return []


def prepare_scores_for_judgment(
    score: Any,  # ScoredStock
) -> dict:
    """
    Convert rule-based scores to judgment format.

    Args:
        score: ScoredStock instance

    Returns:
        Dict of scores for judgment
    """
    return {
        "trend_score": score.trend_score,
        "momentum_score": score.momentum_score,
        "value_score": score.value_score,
        "sentiment_score": score.sentiment_score,
        "composite_score": score.composite_score,
        "percentile_rank": score.percentile_rank,
        # V2 scores if available
        "momentum_12_1_score": getattr(score, "momentum_12_1_score", None),
        "breakout_score": getattr(score, "breakout_score", None),
        "catalyst_score": getattr(score, "catalyst_score", None),
        "risk_adjusted_score": getattr(score, "risk_adjusted_score", None),
    }


def save_judgment_to_db(
    supabase: SupabaseClient,
    judgment: JudgmentOutput,
    batch_date: str,
) -> dict:
    """
    Save a judgment to the database.

    Args:
        supabase: Supabase client
        judgment: JudgmentOutput instance
        batch_date: Date string

    Returns:
        Saved record
    """
    reasoning_dict = {
        "steps": judgment.reasoning.steps,
        "top_factors": judgment.reasoning.top_factors,
        "decision_point": judgment.reasoning.decision_point,
        "uncertainties": judgment.reasoning.uncertainties,
        "confidence_explanation": judgment.reasoning.confidence_explanation,
    }

    key_factors_list = [
        {
            "factor_type": f.factor_type,
            "description": f.description,
            "source": f.source,
            "impact": f.impact,
            "weight": f.weight,
            "verifiable": f.verifiable,
            "raw_data": f.raw_data,
        }
        for f in judgment.key_factors
    ]

    return supabase.save_judgment_record(
        symbol=judgment.symbol,
        batch_date=batch_date,
        strategy_mode=judgment.strategy_mode,
        decision=judgment.decision,
        confidence=judgment.confidence,
        score=judgment.score,
        reasoning=reasoning_dict,
        key_factors=key_factors_list,
        identified_risks=judgment.identified_risks,
        market_regime=judgment.market_regime,
        input_summary=judgment.input_summary,
        model_version=judgment.model_version,
        prompt_version=judgment.prompt_version,
        raw_llm_response=judgment.raw_llm_response,
        judged_at=judgment.judged_at.isoformat(),
    )


def run_judgment_for_candidates(
    judgment_service: JudgmentService,
    finnhub: FinnhubClient,
    supabase: SupabaseClient,
    candidates: list[tuple[Any, Any]],  # List of (stock_data, scored_stock)
    strategy_mode: str,
    market_regime: str,
    batch_date: str,
    top_n: int = 10,
) -> list[JudgmentOutput]:
    """
    Run LLM judgment for top candidates.

    Args:
        judgment_service: JudgmentService instance
        finnhub: Finnhub client for news
        supabase: Supabase client for persistence
        candidates: List of (stock_data, scored_stock) tuples, sorted by score
        strategy_mode: 'conservative' or 'aggressive'
        market_regime: Current market regime
        batch_date: Date string
        top_n: Number of top candidates to judge

    Returns:
        List of JudgmentOutput instances
    """
    judgments = []

    # Only judge top N candidates (LLM is expensive)
    top_candidates = candidates[:top_n]

    logger.info(f"Running LLM judgment for top {len(top_candidates)} {strategy_mode} candidates")

    for stock_data, score in top_candidates:
        symbol = stock_data.symbol

        try:
            # Prepare data
            stock_dict = prepare_stock_data_for_judgment(stock_data)
            news_data = fetch_news_for_judgment(finnhub, symbol)
            scores_dict = prepare_scores_for_judgment(score)

            # Generate judgment
            judgment = judgment_service.judge_stock(
                symbol=symbol,
                strategy_mode=strategy_mode,
                stock_data=stock_dict,
                news_data=news_data,
                rule_based_scores=scores_dict,
                market_regime=market_regime,
            )

            # Save to database
            save_judgment_to_db(supabase, judgment, batch_date)

            judgments.append(judgment)

            logger.info(
                f"{symbol}: {judgment.decision} "
                f"(confidence={judgment.confidence:.0%}, score={judgment.score})"
            )

        except Exception as e:
            logger.error(f"Failed to judge {symbol}: {e}")
            continue

    return judgments


def filter_picks_by_judgment(
    rule_based_picks: list[str],
    judgments: list[JudgmentOutput],
    min_confidence: float = 0.6,
) -> list[str]:
    """
    Filter rule-based picks using LLM judgment.

    Only include picks where LLM judgment agrees and has sufficient confidence.

    Args:
        rule_based_picks: Original picks from rule-based scoring
        judgments: LLM judgments for candidates
        min_confidence: Minimum confidence threshold

    Returns:
        Filtered list of picks
    """
    judgment_map = {j.symbol: j for j in judgments}

    filtered = []
    for symbol in rule_based_picks:
        judgment = judgment_map.get(symbol)

        if judgment is None:
            # No judgment available - include with caution
            logger.warning(f"{symbol}: No LLM judgment, including based on rule-based score")
            filtered.append(symbol)
            continue

        if judgment.decision == "buy" and judgment.confidence >= min_confidence:
            filtered.append(symbol)
            logger.info(f"{symbol}: LLM confirmed (confidence={judgment.confidence:.0%})")
        elif judgment.decision == "buy":
            logger.info(
                f"{symbol}: LLM says buy but low confidence "
                f"({judgment.confidence:.0%} < {min_confidence:.0%}), excluding"
            )
        else:
            logger.info(
                f"{symbol}: LLM says {judgment.decision}, excluding from picks"
            )

    return filtered


def _calculate_rsi(prices: list[float], period: int = 14) -> float:
    """Calculate RSI for a price series."""
    if len(prices) < period + 1:
        return 50.0  # Default to neutral

    changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]

    gains = [c if c > 0 else 0 for c in changes[-period:]]
    losses = [-c if c < 0 else 0 for c in changes[-period:]]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi
