"""
Judgment Integration Module

Integrates JudgmentService with the daily scoring pipeline.
Handles data transformation and judgment persistence.
"""
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Protocol, TYPE_CHECKING, runtime_checkable

from src.data.finnhub_client import FinnhubClient, NewsItem
from src.data.supabase_client import SupabaseClient
from src.utils.technical import calculate_rsi
from .service import JudgmentService
from .models import JudgmentOutput, KeyFactor, ReasoningTrace


@runtime_checkable
class StockDataLike(Protocol):
    """Protocol for stock data objects (StockData or V2StockData)."""

    symbol: str
    prices: list[float]
    volumes: list[float]
    pe_ratio: float | None
    pb_ratio: float | None
    dividend_yield: float | None
    week_52_high: float | None
    week_52_low: float | None


@runtime_checkable
class ScoredStockLike(Protocol):
    """Protocol for scored stock objects (CompositeScore or DualCompositeScore)."""

    trend_score: int
    momentum_score: int
    value_score: int
    sentiment_score: int
    composite_score: int
    percentile_rank: int


@dataclass
class JudgmentResult:
    """
    Result container for batch judgment execution.

    Tracks both successful judgments and failures for better
    error visibility and debugging.
    """
    successful: list[JudgmentOutput] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (symbol, error_message)

    @property
    def failure_rate(self) -> float:
        """Calculate the failure rate as a proportion of total attempts."""
        total = len(self.successful) + len(self.failed)
        return len(self.failed) / total if total > 0 else 0.0

    @property
    def total_count(self) -> int:
        """Total number of judgment attempts."""
        return len(self.successful) + len(self.failed)

    @property
    def success_count(self) -> int:
        """Number of successful judgments."""
        return len(self.successful)

    @property
    def failure_count(self) -> int:
        """Number of failed judgments."""
        return len(self.failed)

if TYPE_CHECKING:
    from src.data.yfinance_client import YFinanceClient
    from src.scoring.agents import StockData
    from src.scoring.agents_v2 import V2StockData
    from src.scoring.composite import CompositeScore
    from src.scoring.composite_v2 import DualCompositeScore


logger = logging.getLogger(__name__)


def prepare_stock_data_for_judgment(
    stock_data: StockDataLike,
) -> dict:
    """
    Convert scoring StockData to judgment format.

    Args:
        stock_data: Object conforming to StockDataLike protocol (StockData or V2StockData)

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
        rsi = calculate_rsi(prices, 14)

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
    finnhub: FinnhubClient | None,
    symbol: str,
    days: int = 7,
    yfinance: "YFinanceClient | None" = None,
) -> list[dict]:
    """
    Fetch and format news for judgment.

    Args:
        finnhub: Finnhub client (can be None for markets without Finnhub support)
        symbol: Stock symbol
        days: Days of news to fetch
        yfinance: Optional yfinance client as fallback for markets without Finnhub

    Returns:
        List of news dicts formatted for judgment
    """
    # Try yfinance first if finnhub is not available
    if finnhub is None:
        if yfinance is not None:
            logger.debug(f"Using yfinance for news: {symbol}")
            try:
                yf_news = yfinance.get_news(symbol, max_items=15)
                if yf_news:
                    news_data = []
                    for item in yf_news:
                        news_data.append({
                            "headline": item.get("headline", ""),
                            "summary": item.get("summary", "")[:500] if item.get("summary") else "",
                            "datetime": item.get("datetime"),
                            "source": item.get("source", "Yahoo Finance"),
                            "sentiment": None,  # yfinance doesn't provide sentiment
                        })
                    logger.info(f"Fetched {len(news_data)} news items from yfinance for {symbol}")
                    return news_data
            except Exception as e:
                logger.warning(f"yfinance news fetch failed for {symbol}: {e}")

        logger.debug(f"No news client available for {symbol}, skipping news fetch")
        return []

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
    score: ScoredStockLike,
) -> dict:
    """
    Convert rule-based scores to judgment format.

    Args:
        score: Object conforming to ScoredStockLike protocol (CompositeScore or DualCompositeScore)

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

    # Derive market_type from strategy_mode
    market_type = "jp" if judgment.strategy_mode.startswith("jp_") else "us"

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
        market_type=market_type,
    )


def run_judgment_for_candidates(
    judgment_service: JudgmentService,
    finnhub: FinnhubClient | None,
    supabase: SupabaseClient,
    candidates: list[tuple[StockDataLike, ScoredStockLike]],
    strategy_mode: str,
    market_regime: str,
    batch_date: str,
    top_n: int | None = None,  # None = judge all candidates
    yfinance: "YFinanceClient | None" = None,
    past_lessons: str | None = None,
) -> JudgmentResult:
    """
    Run LLM judgment for candidates that passed rule-based threshold.

    Note: With the new LLM-first selection logic, all threshold-passed
    candidates should be judged. The top_n limit is kept for backward
    compatibility but should be set to None for new logic.

    Args:
        judgment_service: JudgmentService instance
        finnhub: Finnhub client for news (can be None for JP stocks)
        supabase: Supabase client for persistence
        candidates: List of (StockDataLike, ScoredStockLike) tuples that passed threshold
        strategy_mode: 'conservative' or 'aggressive'
        market_regime: Current market regime
        batch_date: Date string
        top_n: Max candidates to judge (None = all candidates, for LLM-first selection)
        yfinance: Optional yfinance client for news fallback (used for JP stocks)

    Returns:
        JudgmentResult containing successful judgments and failed attempts
    """
    result = JudgmentResult()

    # Apply top_n limit only if specified (backward compatibility)
    # For LLM-first selection, pass top_n=None to judge all candidates
    if top_n is not None:
        target_candidates = candidates[:top_n]
    else:
        target_candidates = candidates

    logger.info(f"Running LLM judgment for {len(target_candidates)} {strategy_mode} candidates")

    for stock_data, score in target_candidates:
        symbol = stock_data.symbol

        try:
            # Prepare data
            stock_dict = prepare_stock_data_for_judgment(stock_data)
            news_data = fetch_news_for_judgment(finnhub, symbol, yfinance=yfinance)
            scores_dict = prepare_scores_for_judgment(score)

            # Generate judgment
            judgment = judgment_service.judge_stock(
                symbol=symbol,
                strategy_mode=strategy_mode,
                stock_data=stock_dict,
                news_data=news_data,
                rule_based_scores=scores_dict,
                market_regime=market_regime,
                past_lessons=past_lessons,
            )

            # Save to database
            save_judgment_to_db(supabase, judgment, batch_date)

            result.successful.append(judgment)

            logger.info(
                f"{symbol}: {judgment.decision} "
                f"(confidence={judgment.confidence:.0%}, score={judgment.score})"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to judge {symbol}: {error_msg}")
            result.failed.append((symbol, error_msg))
            continue

    # Log summary with failure information
    if result.failed:
        logger.warning(
            f"Judgment completed with {result.failure_count} failures "
            f"(failure rate: {result.failure_rate:.1%}): "
            f"{[sym for sym, _ in result.failed]}"
        )
    else:
        logger.info(f"Judgment completed successfully for all {result.success_count} candidates")

    return result


def filter_picks_by_judgment(
    rule_based_picks: list[str],
    judgments: list[JudgmentOutput],
    min_confidence: float = 0.6,
) -> list[str]:
    """
    Filter rule-based picks using LLM judgment (legacy method).

    DEPRECATED: Use select_picks_with_llm() from composite_v2.py for new logic.

    Note: This function is kept for backward compatibility. The new LLM-first
    selection logic should use select_picks_with_llm() instead.

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
            # NEW BEHAVIOR: No LLM judgment = exclude from picks
            # This ensures all picks have been validated by LLM
            logger.info(f"{symbol}: No LLM judgment available, excluding from picks")
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


def select_final_picks(
    scores: list,  # list[DualCompositeScore]
    judgments: list[JudgmentOutput],
    max_picks: int,
    min_rule_score: int,
    min_confidence: float = 0.5,
) -> list[str]:
    """
    Select final picks using LLM-first selection logic.

    This is the new selection logic where:
    1. Rule score is only a risk filter (pass/fail)
    2. LLM decision and confidence drive selection
    3. Sorting is by LLM confidence, not rule score

    Args:
        scores: Rule-based DualCompositeScore list
        judgments: LLM JudgmentOutput list
        max_picks: Maximum picks to return
        min_rule_score: Minimum rule score (risk filter)
        min_confidence: Minimum LLM confidence

    Returns:
        List of selected symbols
    """
    # Import here to avoid circular dependency
    from src.scoring.composite_v2 import select_picks_with_llm

    return select_picks_with_llm(
        scores=scores,
        llm_judgments=judgments,
        max_picks=max_picks,
        min_rule_score=min_rule_score,
        min_confidence=min_confidence,
    )
