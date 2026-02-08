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
from .models import (
    JudgmentOutput, KeyFactor, ReasoningTrace,
    PortfolioCandidateSummary, PortfolioHolding,
    PortfolioJudgmentOutput, StockAllocation,
    RiskAssessment, PortfolioRiskOutput, EnsembleResult,
)


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

    # Fetch dynamic prompt overrides from meta-monitor (once per batch)
    prompt_overrides = supabase.get_active_prompt_overrides(strategy_mode)
    if prompt_overrides:
        logger.info(f"Loaded {len(prompt_overrides)} active prompt override(s) for {strategy_mode}")

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
                prompt_overrides=prompt_overrides,
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


def _build_candidate_summary(
    stock_data: StockDataLike,
    score: ScoredStockLike,
) -> PortfolioCandidateSummary:
    """Convert stock data + score into a PortfolioCandidateSummary."""
    prices = stock_data.prices or []
    volumes = stock_data.volumes or []

    current_price = prices[-1] if prices else 0
    change_pct = 0.0
    if len(prices) >= 2 and prices[-2] > 0:
        change_pct = ((prices[-1] - prices[-2]) / prices[-2]) * 100

    rsi = None
    if len(prices) >= 15:
        rsi = calculate_rsi(prices, 14)

    avg_volume = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else (
        sum(volumes) / len(volumes) if volumes else 0
    )
    volume_ratio = (volumes[-1] / avg_volume) if (volumes and avg_volume > 0) else None

    # Determine key signal
    key_signal = "NEUTRAL"
    breakout_score = getattr(score, "breakout_score", None)
    if breakout_score is not None and breakout_score >= 70:
        key_signal = "BREAKOUT"
    elif rsi is not None and rsi < 30:
        key_signal = "OVERSOLD"
    elif rsi is not None and rsi > 70:
        key_signal = "OVERBOUGHT"
    elif score.momentum_score >= 70:
        key_signal = "MOMENTUM"

    return PortfolioCandidateSummary(
        symbol=stock_data.symbol,
        composite_score=score.composite_score,
        percentile_rank=score.percentile_rank,
        price=current_price,
        change_pct=change_pct,
        rsi=rsi,
        volume_ratio=volume_ratio,
        key_signal=key_signal,
        top_news_headline=None,
        news_sentiment=None,
        sector=None,
    )


def run_portfolio_judgment(
    judgment_service: JudgmentService,
    supabase: SupabaseClient,
    candidates: list[tuple[StockDataLike, ScoredStockLike]],
    strategy_mode: str,
    market_regime: str,
    batch_date: str,
    current_positions: list,
    available_slots: int,
    available_cash: float,
    finnhub: FinnhubClient | None = None,
    yfinance: "YFinanceClient | None" = None,
    performance_stats: dict | None = None,
    weekly_research: str | None = None,
    is_primary: bool = True,
) -> PortfolioJudgmentOutput:
    """Run portfolio-level judgment on all candidates at once.

    Transforms raw data into PortfolioCandidateSummary objects, fetches news
    for top candidates, calls judge_portfolio(), and saves individual
    judgment records for outcome tracking.

    No fallback: exceptions propagate to caller.

    Args:
        judgment_service: JudgmentService instance
        supabase: Supabase client
        candidates: List of (StockDataLike, ScoredStockLike) tuples
        strategy_mode: Strategy mode string
        market_regime: Current regime string
        batch_date: Date string
        current_positions: Open positions as PortfolioHolding list
        available_slots: Number of open slots
        available_cash: Available cash amount
        finnhub: Optional Finnhub client for news
        yfinance: Optional yfinance client for news
        performance_stats: Structured performance data
        weekly_research: Formatted weekly research context for prompt

    Returns:
        PortfolioJudgmentOutput

    Raises:
        Exception: Any LLM or parsing error (no fallback)
    """
    # Build candidate summaries
    summaries = []
    for stock_data, score in candidates:
        summaries.append(_build_candidate_summary(stock_data, score))

    # Fetch news for top candidates (by score)
    top_symbols = [s.symbol for s in sorted(summaries, key=lambda x: x.composite_score, reverse=True)[:10]]
    news_by_symbol: dict[str, list[dict]] = {}
    for symbol in top_symbols:
        news = fetch_news_for_judgment(finnhub, symbol, yfinance=yfinance)
        if news:
            news_by_symbol[symbol] = news[:3]
            # Inject top headline into candidate summary
            for s in summaries:
                if s.symbol == symbol:
                    s.top_news_headline = news[0].get("headline", "")[:100]
                    s.news_sentiment = news[0].get("sentiment")
                    break

    # Call portfolio-level judgment
    result = judgment_service.judge_portfolio(
        strategy_mode=strategy_mode,
        market_regime=market_regime,
        candidates=summaries,
        current_positions=current_positions,
        available_slots=available_slots,
        available_cash=available_cash,
        news_by_symbol=news_by_symbol,
        performance_stats=performance_stats,
        weekly_research=weekly_research,
    )

    # Save individual judgment records for each recommended buy
    # (needed for judgment_outcomes feedback loop)
    model_ver = judgment_service.model_name
    for alloc in result.recommended_buys:
        _save_portfolio_allocation_as_judgment(
            supabase, alloc, strategy_mode, market_regime, batch_date,
            decision="buy", portfolio_reasoning=result.portfolio_reasoning,
            model_version=model_ver, is_primary=is_primary,
        )

    for alloc in result.skipped:
        _save_portfolio_allocation_as_judgment(
            supabase, alloc, strategy_mode, market_regime, batch_date,
            decision="skip", portfolio_reasoning=result.portfolio_reasoning,
            model_version=model_ver, is_primary=is_primary,
        )

    return result


def _save_portfolio_allocation_as_judgment(
    supabase: SupabaseClient,
    alloc: StockAllocation,
    strategy_mode: str,
    market_regime: str,
    batch_date: str,
    decision: str,
    portfolio_reasoning: str,
    model_version: str = "",
    is_primary: bool = True,
) -> None:
    """Save a portfolio allocation as a judgment record for outcome tracking."""
    market_type = "jp" if strategy_mode.startswith("jp_") else "us"

    reasoning_dict = {
        "steps": [alloc.reasoning],
        "top_factors": [f"Portfolio-level: {alloc.allocation_hint}"],
        "decision_point": portfolio_reasoning[:200],
        "uncertainties": [],
        "confidence_explanation": f"Conviction: {alloc.conviction:.0%}",
    }

    try:
        supabase.save_judgment_record(
            symbol=alloc.symbol,
            batch_date=batch_date,
            strategy_mode=strategy_mode,
            decision=decision,
            confidence=alloc.conviction,
            score=int(alloc.conviction * 100),
            reasoning=reasoning_dict,
            key_factors=[],
            identified_risks=[],
            market_regime=market_regime,
            input_summary=f"Portfolio judgment: {alloc.action} ({alloc.allocation_hint})",
            model_version=model_version,
            prompt_version="v2_portfolio",
            raw_llm_response=None,
            judged_at=datetime.now().isoformat(),
            market_type=market_type,
            is_primary=is_primary,
        )
    except Exception as e:
        logger.warning(f"Failed to save judgment record for {alloc.symbol}: {e}")


def _fetch_news_for_candidates(
    candidates: list[tuple[StockDataLike, ScoredStockLike]],
    summaries: list[PortfolioCandidateSummary],
    finnhub: FinnhubClient | None,
    yfinance: "YFinanceClient | None" = None,
    max_news_symbols: int = 10,
) -> dict[str, list[dict]]:
    """Fetch news for top candidates and inject into summaries.

    Returns:
        Dict mapping symbol -> list of news dicts
    """
    top_symbols = [
        s.symbol for s in sorted(
            summaries, key=lambda x: x.composite_score, reverse=True
        )[:max_news_symbols]
    ]
    news_by_symbol: dict[str, list[dict]] = {}
    for symbol in top_symbols:
        news = fetch_news_for_judgment(finnhub, symbol, yfinance=yfinance)
        if news:
            news_by_symbol[symbol] = news[:3]
            for s in summaries:
                if s.symbol == symbol:
                    s.top_news_headline = news[0].get("headline", "")[:100]
                    s.news_sentiment = news[0].get("sentiment")
                    break
    return news_by_symbol


def run_risk_assessment(
    judgment_service: JudgmentService,
    supabase: SupabaseClient,
    candidates: list[tuple[StockDataLike, ScoredStockLike]],
    strategy_mode: str,
    market_regime: str,
    batch_date: str,
    current_positions: list,
    finnhub: FinnhubClient | None = None,
    yfinance: "YFinanceClient | None" = None,
    recent_mistakes: list[dict] | None = None,
    weekly_research: str | None = None,
    performance_stats: dict | None = None,
) -> tuple[PortfolioRiskOutput, list[PortfolioCandidateSummary], dict[str, list[dict]]]:
    """Run risk assessment for portfolio candidates (new ensemble architecture).

    Transforms raw data into summaries, fetches news, calls
    judgment_service.assess_portfolio_risk(), and returns the result.

    Unlike run_portfolio_judgment(), this does NOT save to DB — the caller
    saves after ensemble aggregation.

    Args:
        judgment_service: JudgmentService instance
        supabase: Supabase client
        candidates: List of (StockDataLike, ScoredStockLike) tuples
        strategy_mode: Strategy mode string
        market_regime: Current regime string
        batch_date: Date string
        current_positions: Open positions as PortfolioHolding list
        finnhub: Optional Finnhub client for news
        yfinance: Optional yfinance client for news
        recent_mistakes: Recent buy mistakes for feedback injection
        weekly_research: Formatted weekly research context
        performance_stats: Structured performance data

    Returns:
        Tuple of (PortfolioRiskOutput, summaries, news_by_symbol)
    """
    # Build candidate summaries
    summaries = [_build_candidate_summary(sd, sc) for sd, sc in candidates]

    # Fetch news
    news_by_symbol = _fetch_news_for_candidates(
        candidates, summaries, finnhub, yfinance,
    )

    # Call risk assessment
    result = judgment_service.assess_portfolio_risk(
        strategy_mode=strategy_mode,
        market_regime=market_regime,
        candidates=summaries,
        current_positions=current_positions,
        news_by_symbol=news_by_symbol,
        recent_mistakes=recent_mistakes,
        weekly_research=weekly_research,
        performance_stats=performance_stats,
    )

    return result, summaries, news_by_symbol


def save_risk_assessment_records(
    supabase: SupabaseClient,
    ensemble_results: list[EnsembleResult],
    risk_output: PortfolioRiskOutput,
    strategy_mode: str,
    market_regime: str,
    batch_date: str,
    model_version: str,
    is_primary: bool = True,
) -> None:
    """Save ensemble risk assessment results as judgment records.

    Maps ensemble results to the existing judgment_records schema:
    - decision: ensemble final_decision ("buy" / "skip")
    - confidence: (5 - avg_risk_score) / 4, clamped [0, 1]
    - score: composite_score from rule-based scoring
    - reasoning: JSON with risk details + ensemble info
    - identified_risks: negative_catalysts from risk assessment

    Args:
        supabase: Supabase client
        ensemble_results: List of EnsembleResult from aggregation
        risk_output: PortfolioRiskOutput for catalyst details
        strategy_mode: Strategy mode string
        market_regime: Current regime string
        batch_date: Date string
        model_version: Model identifier
        is_primary: Whether this is the primary model's assessment
    """
    market_type = "jp" if strategy_mode.startswith("jp_") else "us"

    # Build lookup for risk assessments
    assessment_map = {a.symbol: a for a in risk_output.assessments}

    for er in ensemble_results:
        assessment = assessment_map.get(er.symbol)
        negative_catalysts = assessment.negative_catalysts if assessment else []
        news_interp = assessment.news_interpretation if assessment else ""

        # Map risk score to confidence: low risk → high confidence
        confidence = max(0.0, min(1.0, (5 - er.avg_risk_score) / 4))

        reasoning_dict = {
            "risk_score": er.avg_risk_score,
            "risk_scores_by_model": er.risk_scores,
            "consensus_ratio": er.consensus_ratio,
            "negative_catalysts": negative_catalysts,
            "news_interpretation": news_interp,
            "decision_reason": er.decision_reason,
            "market_level_risks": risk_output.market_level_risks,
        }

        try:
            supabase.save_judgment_record(
                symbol=er.symbol,
                batch_date=batch_date,
                strategy_mode=strategy_mode,
                decision=er.final_decision,
                confidence=confidence,
                score=er.composite_score,
                reasoning=reasoning_dict,
                key_factors=[],
                identified_risks=negative_catalysts,
                market_regime=market_regime,
                input_summary=f"Ensemble: R{er.avg_risk_score:.1f} C{er.consensus_ratio:.0%}",
                model_version=model_version,
                prompt_version="v3_risk_ensemble",
                raw_llm_response=risk_output.raw_llm_response,
                judged_at=datetime.now().isoformat(),
                market_type=market_type,
                is_primary=is_primary,
            )
        except Exception as e:
            logger.warning(f"Failed to save risk assessment record for {er.symbol}: {e}")
