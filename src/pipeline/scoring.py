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
    run_judgment_for_candidates,
    select_final_picks,
)
from src.scoring.composite_v2 import get_threshold_passed_symbols
from src.pipeline.market_config import MarketConfig

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
) -> tuple[list[str], list[str], JudgmentStats]:
    """Run LLM judgment on threshold-passed candidates and select final picks.

    This is the Layer 2 of the 4-layer architecture, shared between US and JP.

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

    judgment_ctx = None
    try:
        judgment_ctx = BatchLogger.start(
            BatchType.LLM_JUDGMENT,
            model=config.llm.analysis_model,
        )
        judgment_service = JudgmentService()

        # Fetch past lessons for context injection
        past_lessons_text = None
        if supabase:
            past_lessons_text = _format_past_lessons(supabase, market_config)

        v1_min_score = v1_threshold if v1_threshold is not None else config.strategy.v1_min_score
        v2_min_score = v2_threshold if v2_threshold is not None else config.strategy.v2_min_score

        # Filter candidates by threshold
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

        # Judgment kwargs (finnhub for US, yfinance for JP)
        judgment_kwargs = {}
        if finnhub is not None:
            judgment_kwargs["finnhub"] = finnhub
        else:
            judgment_kwargs["finnhub"] = None
        if yfinance is not None:
            judgment_kwargs["yfinance"] = yfinance

        # Run V1 judgments
        v1_judgment_result = run_judgment_for_candidates(
            judgment_service=judgment_service,
            supabase=supabase,
            candidates=v1_candidates,
            strategy_mode=market_config.v1_strategy_mode,
            market_regime=market_regime_str,
            batch_date=today,
            top_n=None,
            past_lessons=past_lessons_text,
            **judgment_kwargs,
        )

        v1_final_picks = select_final_picks(
            scores=dual_result.v1_scores,
            judgments=v1_judgment_result.successful,
            max_picks=max_picks,
            min_rule_score=v1_min_score,
            min_confidence=0.6,
        )

        if v1_judgment_result.failed:
            logger.warning(
                f"V1 judgment failures ({v1_judgment_result.failure_count}): "
                f"{[(sym, err[:50]) for sym, err in v1_judgment_result.failed]}"
            )

        # Run V2 judgments
        v2_judgment_result = run_judgment_for_candidates(
            judgment_service=judgment_service,
            supabase=supabase,
            candidates=v2_candidates,
            strategy_mode=market_config.v2_strategy_mode,
            market_regime=market_regime_str,
            batch_date=today,
            top_n=None,
            past_lessons=past_lessons_text,
            **judgment_kwargs,
        )

        v2_max_picks = config.strategy.v2_max_picks if max_picks > 0 else 0
        v2_final_picks = select_final_picks(
            scores=dual_result.v2_scores,
            judgments=v2_judgment_result.successful,
            max_picks=v2_max_picks,
            min_rule_score=v2_min_score,
            min_confidence=0.5,
        )

        if v2_judgment_result.failed:
            logger.warning(
                f"V2 judgment failures ({v2_judgment_result.failure_count}): "
                f"{[(sym, err[:50]) for sym, err in v2_judgment_result.failed]}"
            )

        logger.info(f"V1 picks after LLM judgment: {v1_final_picks}")
        logger.info(f"V2 picks after LLM judgment: {v2_final_picks}")

        # Track judgment results
        stats.total_candidates = len(v1_candidates) + len(v2_candidates)
        stats.successful_judgments = v1_judgment_result.success_count + v2_judgment_result.success_count
        stats.failed_judgments = v1_judgment_result.failure_count + v2_judgment_result.failure_count

        judgment_ctx.successful_items = stats.successful_judgments
        judgment_ctx.total_items = stats.total_candidates
        judgment_ctx.failed_items = stats.failed_judgments
        BatchLogger.finish(judgment_ctx)

    except Exception as e:
        logger.error(f"LLM judgment failed, using rule-based picks: {e}")
        if judgment_ctx is not None:
            BatchLogger.finish(judgment_ctx, error=str(e))
        v1_final_picks = dual_result.v1_picks
        v2_final_picks = dual_result.v2_picks

    return v1_final_picks, v2_final_picks, stats


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


def _format_past_lessons(supabase, market_config: MarketConfig) -> str | None:
    """Fetch and format recent AI lessons for prompt injection."""
    try:
        lessons = supabase.get_recent_ai_lessons(
            market_type=market_config.market_type,
            limit=3,
        )
        if not lessons:
            return None

        lines = []
        for lesson in lessons:
            date = lesson.get("lesson_date", "?")
            miss_analysis = lesson.get("miss_analysis", "")
            if miss_analysis:
                lines.append(f"[{date}] 見逃し分析: {miss_analysis}")
            else:
                text = lesson.get("lesson_text", "")
                if text:
                    # Truncate long lessons
                    lines.append(f"[{date}] {text[:300]}")

        if not lines:
            return None

        logger.info(f"Injecting {len(lines)} past lessons into judgment prompt")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Failed to format past lessons: {e}")
        return None
