"""Shared scoring pipeline functions for US and JP markets.

Extracts duplicated logic from daily_scoring.py and daily_scoring_jp.py
into reusable functions parameterized by MarketConfig.
"""
import logging
from dataclasses import dataclass

from src.config import config
from src.batch_logger import BatchLogger, BatchType
from src.judgment import (
    JudgmentService,
    PortfolioHolding,
    run_portfolio_judgment,
)
from src.scoring.composite_v2 import get_threshold_passed_symbols
from src.pipeline.market_config import MarketConfig
from src.pipeline.review import build_performance_stats

logger = logging.getLogger(__name__)


@dataclass
class JudgmentStats:
    """Statistics from LLM judgment phase."""
    total_candidates: int = 0
    successful_judgments: int = 0
    failed_judgments: int = 0


def load_dynamic_thresholds(
    supabase,
    market_config: MarketConfig,
) -> tuple[int | None, int | None]:
    """Load dynamic thresholds from scoring_config table.

    Returns:
        (v1_threshold, v2_threshold) - None values mean use defaults
    """
    try:
        v1_config = supabase.get_scoring_config(market_config.v1_strategy_mode)
        v2_config = supabase.get_scoring_config(market_config.v2_strategy_mode)
        v1_threshold = int(float(v1_config.get("threshold", 60))) if v1_config else None
        v2_threshold = int(float(v2_config.get("threshold", 45))) if v2_config else None
        logger.info(f"Dynamic thresholds: V1={v1_threshold}, V2={v2_threshold}")
        return v1_threshold, v2_threshold
    except Exception as e:
        logger.warning(f"Failed to fetch dynamic thresholds, using defaults: {e}")
        return None, None


def load_factor_weights(
    supabase,
    market_config: MarketConfig,
) -> tuple[dict[str, float] | None, dict[str, float] | None]:
    """Load dynamic factor weights from scoring_config table.

    Returns:
        (v1_weights, v2_weights) - None values mean use defaults
    """
    try:
        v1_config = supabase.get_scoring_config(market_config.v1_strategy_mode)
        v2_config = supabase.get_scoring_config(market_config.v2_strategy_mode)
        v1_weights = v1_config.get("factor_weights") if v1_config else None
        v2_weights = v2_config.get("factor_weights") if v2_config else None
        if v1_weights:
            logger.info(f"DB factor weights V1: {v1_weights}")
        if v2_weights:
            logger.info(f"DB factor weights V2: {v2_weights}")
        return v1_weights, v2_weights
    except Exception as e:
        logger.warning(f"Failed to fetch factor weights, using defaults: {e}")
        return None, None


def run_llm_judgment_phase(
    dual_result,
    v1_stocks_data: list,
    v2_stocks_data: list,
    v1_threshold: int | None,
    v2_threshold: int | None,
    market_regime_str: str,
    market_config: MarketConfig,
    today: str,
    max_picks: int,
    finnhub=None,
    yfinance=None,
    supabase=None,
    portfolio=None,
) -> tuple[list[str], list[str], JudgmentStats]:
    """Run portfolio-level LLM judgment on threshold-passed candidates.

    Uses a single LLM call per strategy to evaluate all candidates
    simultaneously, enabling comparative evaluation and portfolio-aware
    decision making.

    No fallback: if LLM fails, exception propagates to caller.
    Set config.llm.enable_judgment = false to use rule-based only (intentional).

    Returns:
        (v1_final_picks, v2_final_picks, judgment_stats)
    """
    use_llm_judgment = config.llm.enable_judgment
    v1_final_picks = dual_result.v1_picks
    v2_final_picks = dual_result.v2_picks
    stats = JudgmentStats()

    if not use_llm_judgment:
        logger.info("LLM judgment disabled, using rule-based picks only")
        return v1_final_picks, v2_final_picks, stats

    judgment_ctx = BatchLogger.start(
        BatchType.LLM_JUDGMENT,
        model=config.llm.analysis_model,
    )

    try:
        judgment_service = JudgmentService()

        v1_min_score = v1_threshold if v1_threshold is not None else config.strategy.v1_min_score
        v2_min_score = v2_threshold if v2_threshold is not None else config.strategy.v2_min_score

        # Filter candidates by threshold (safety valve — AI can't buy sub-threshold stocks)
        v1_passed_symbols = get_threshold_passed_symbols(dual_result.v1_scores, v1_min_score)
        v2_passed_symbols = get_threshold_passed_symbols(dual_result.v2_scores, v2_min_score)

        logger.info(f"V1 threshold-passed candidates: {len(v1_passed_symbols)}")
        logger.info(f"V2 threshold-passed candidates: {len(v2_passed_symbols)}")

        # Build candidate lists
        v1_score_map = {s.symbol: s for s in dual_result.v1_scores}
        v1_candidates = [
            (sd, v1_score_map[sd.symbol])
            for sd in v1_stocks_data if sd.symbol in v1_passed_symbols
        ]

        v2_score_map = {s.symbol: s for s in dual_result.v2_scores}
        v2_candidates = [
            (sd, v2_score_map[sd.symbol])
            for sd in v2_stocks_data if sd.symbol in v2_passed_symbols
        ]

        # Get portfolio state for context
        v1_positions = _get_portfolio_holdings(portfolio, market_config.v1_strategy_mode)
        v2_positions = _get_portfolio_holdings(portfolio, market_config.v2_strategy_mode)

        max_positions = config.strategy.max_positions if hasattr(config.strategy, "max_positions") else 5
        v1_slots = max(0, max_positions - len(v1_positions))
        v2_slots = max(0, max_positions - len(v2_positions))

        # Build structured performance stats (Phase 4)
        v1_perf_stats = None
        v2_perf_stats = None
        if supabase:
            v1_perf_stats = build_performance_stats(supabase, market_config.v1_strategy_mode)
            v2_perf_stats = build_performance_stats(supabase, market_config.v2_strategy_mode)

        total_candidates = len(v1_candidates) + len(v2_candidates)

        # Fetch weekly research for prompt injection
        weekly_research_text = None
        if supabase:
            weekly_research_text = _format_weekly_research(supabase)

        # Run V1 portfolio judgment
        v1_final_picks = []
        if v1_candidates and v1_slots > 0:
            v1_result = run_portfolio_judgment(
                judgment_service=judgment_service,
                supabase=supabase,
                candidates=v1_candidates,
                strategy_mode=market_config.v1_strategy_mode,
                market_regime=market_regime_str,
                batch_date=today,
                current_positions=v1_positions,
                available_slots=v1_slots,
                available_cash=100000,  # Paper trading nominal
                finnhub=finnhub,
                yfinance=yfinance,
                performance_stats=v1_perf_stats,
                weekly_research=weekly_research_text,
            )
            # Safety valve: only accept AI recommendations that passed threshold
            v1_final_picks = [
                r.symbol for r in v1_result.recommended_buys
                if r.symbol in v1_passed_symbols
            ][:max_picks]
            logger.info(f"V1 portfolio judgment: {v1_final_picks} (reasoning: {v1_result.portfolio_reasoning[:100]})")
        else:
            logger.info(f"V1 skipped: {len(v1_candidates)} candidates, {v1_slots} slots")

        # Run V2 portfolio judgment
        v2_final_picks = []
        v2_max_picks = config.strategy.v2_max_picks if max_picks > 0 else 0
        if v2_candidates and v2_slots > 0:
            v2_result = run_portfolio_judgment(
                judgment_service=judgment_service,
                supabase=supabase,
                candidates=v2_candidates,
                strategy_mode=market_config.v2_strategy_mode,
                market_regime=market_regime_str,
                batch_date=today,
                current_positions=v2_positions,
                available_slots=v2_slots,
                available_cash=100000,
                finnhub=finnhub,
                yfinance=yfinance,
                performance_stats=v2_perf_stats,
                weekly_research=weekly_research_text,
            )
            v2_final_picks = [
                r.symbol for r in v2_result.recommended_buys
                if r.symbol in v2_passed_symbols
            ][:v2_max_picks]
            logger.info(f"V2 portfolio judgment: {v2_final_picks} (reasoning: {v2_result.portfolio_reasoning[:100]})")
        else:
            logger.info(f"V2 skipped: {len(v2_candidates)} candidates, {v2_slots} slots")

        logger.info(f"V1 picks after LLM judgment: {v1_final_picks}")
        logger.info(f"V2 picks after LLM judgment: {v2_final_picks}")

        stats.total_candidates = total_candidates
        stats.successful_judgments = total_candidates  # Portfolio judgment is all-or-nothing
        judgment_ctx.successful_items = stats.successful_judgments
        judgment_ctx.total_items = stats.total_candidates
        BatchLogger.finish(judgment_ctx)

    except Exception as e:
        # No fallback: propagate error after logging
        logger.error(f"LLM judgment failed: {e}")
        BatchLogger.finish(judgment_ctx, error=str(e))
        raise

    return v1_final_picks, v2_final_picks, stats


def _get_portfolio_holdings(portfolio, strategy_mode: str) -> list[PortfolioHolding]:
    """Get current open positions as PortfolioHolding list."""
    if portfolio is None:
        return []

    try:
        from datetime import datetime, timezone
        positions = portfolio.get_open_positions(strategy_mode=strategy_mode)
        holdings = []
        today = datetime.now(timezone.utc)
        for pos in positions:
            entry_date_str = pos.entry_date if isinstance(pos.entry_date, str) else pos.entry_date.strftime("%Y-%m-%d")
            try:
                entry_dt = datetime.strptime(entry_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                hold_days = (today - entry_dt).days
            except (ValueError, TypeError):
                hold_days = 0
            holdings.append(PortfolioHolding(
                symbol=pos.symbol,
                strategy_mode=pos.strategy_mode,
                entry_date=entry_date_str,
                pnl_pct=pos.pnl_pct if hasattr(pos, "pnl_pct") else 0.0,
                hold_days=hold_days,
            ))
        return holdings
    except Exception as e:
        logger.warning(f"Failed to get portfolio holdings for {strategy_mode}: {e}")
        return []


def open_positions_and_snapshot(
    portfolio,
    dual_result,
    v1_stocks_data: list,
    v1_final_picks: list[str],
    v2_final_picks: list[str],
    market_config: MarketConfig,
    max_picks: int,
    benchmark_daily_pct: float | None,
) -> None:
    """Open paper trading positions and update portfolio snapshots.

    Shared between US and JP markets.
    """
    if max_picks <= 0:
        logger.info("Skipping position opening - market in crisis mode")
        return

    # Build price and score dicts
    prices = {d.symbol: d.open_price for d in v1_stocks_data if d.open_price > 0}
    v1_score_dict = {s.symbol: s.composite_score for s in dual_result.v1_scores}
    v2_score_dict = {s.symbol: s.composite_score for s in dual_result.v2_scores}

    # Open V1 positions
    if v1_final_picks:
        v1_opened = portfolio.open_positions_for_picks(
            picks=v1_final_picks,
            strategy_mode=market_config.v1_strategy_mode,
            scores=v1_score_dict,
            prices=prices,
        )
        logger.info(f"V1 opened {len(v1_opened)} positions")

    # Open V2 positions
    if v2_final_picks:
        v2_opened = portfolio.open_positions_for_picks(
            picks=v2_final_picks,
            strategy_mode=market_config.v2_strategy_mode,
            scores=v2_score_dict,
            prices=prices,
        )
        logger.info(f"V2 opened {len(v2_opened)} positions")

    # Update portfolio snapshots
    for strategy in [market_config.v1_strategy_mode, market_config.v2_strategy_mode]:
        try:
            portfolio.update_portfolio_snapshot(
                strategy_mode=strategy,
                sp500_daily_pct=benchmark_daily_pct,
            )
        except Exception as e:
            logger.error(f"Failed to update snapshot for {strategy}: {e}")


def _format_weekly_research(supabase) -> str | None:
    """Fetch and format latest weekly research for judgment context."""
    try:
        research = supabase.get_latest_weekly_research()
        if not research:
            return None

        findings = research.get("content", "")
        if not findings:
            return None

        system_data = research.get("metadata") or {}
        batch_date = research.get("research_date", "?")

        lines = [f"[Weekly Research {batch_date}]"]
        # Truncate findings to keep prompt manageable
        lines.append(findings[:800])

        watch = system_data.get("stocks_to_watch", [])
        avoid = system_data.get("stocks_to_avoid", [])
        if watch:
            lines.append(f"Watch: {', '.join(watch[:10])}")
        if avoid:
            lines.append(f"Avoid: {', '.join(avoid[:10])}")

        logger.info(f"Injecting weekly research ({batch_date}) into judgment prompt")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Failed to format weekly research: {e}")
        return None
