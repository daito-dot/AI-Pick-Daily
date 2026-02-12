"""Shared scoring pipeline functions for US and JP markets.

Extracts duplicated logic from daily_scoring.py and daily_scoring_jp.py
into reusable functions parameterized by MarketConfig.
"""
import logging
from dataclasses import dataclass

from src.config import config
from src.batch_logger import BatchLogger, BatchType
from src.data.supabase_client import StockScore, DailyPick
from src.judgment import (
    JudgmentService,
    PortfolioHolding,
    run_portfolio_judgment,
)
from src.judgment.integration import run_risk_assessment, save_risk_assessment_records
from src.judgment.models import PortfolioRiskOutput, EnsembleResult
from src.scoring.composite_v2 import get_threshold_passed_symbols
from src.scoring.market_regime import REGIME_DECISION_PARAMS, MarketRegime
from src.pipeline.market_config import MarketConfig
from src.pipeline.review import build_performance_stats, build_recent_mistakes

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
        v1_threshold = int(float(v1_config.get("threshold", config.strategy.v1_min_score))) if v1_config else None
        v2_threshold = int(float(v2_config.get("threshold", config.strategy.v2_min_score))) if v2_config else None
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
    """Run risk assessment + ensemble aggregation on threshold-passed candidates.

    New architecture (v3):
    1. Primary LLM assesses risk (1-5) for each candidate
    2. Shadow LLMs also assess risk (optional)
    3. Ensemble aggregation: avg_risk + consensus → deterministic buy/skip
    4. Regime parameters control thresholds (max_risk, min_consensus, max_picks)

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

        # Build structured performance stats
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

        # Fetch recent mistakes for feedback injection (Step 4)
        v1_recent_mistakes = None
        v2_recent_mistakes = None
        if supabase:
            v1_recent_mistakes = build_recent_mistakes(supabase, market_config.v1_strategy_mode)
            v2_recent_mistakes = build_recent_mistakes(supabase, market_config.v2_strategy_mode)

        # Get regime decision params (Step 1)
        regime_enum = _parse_regime(market_regime_str)
        regime_params = REGIME_DECISION_PARAMS.get(
            regime_enum, REGIME_DECISION_PARAMS[MarketRegime.NORMAL]
        )
        regime_max_picks = regime_params["max_picks"]

        # Run V1 risk assessment + ensemble
        v1_final_picks = []
        if v1_candidates:
            v1_final_picks = _run_strategy_ensemble(
                judgment_service=judgment_service,
                supabase=supabase,
                candidates=v1_candidates,
                positions=v1_positions,
                strategy_mode=market_config.v1_strategy_mode,
                market_regime_str=market_regime_str,
                regime_params=regime_params,
                today=today,
                max_picks=min(max_picks, regime_max_picks),
                finnhub=finnhub,
                yfinance=yfinance,
                perf_stats=v1_perf_stats,
                weekly_research=weekly_research_text,
                recent_mistakes=v1_recent_mistakes,
                market_config=market_config,
            )
        else:
            logger.info(f"V1 skipped: no candidates passed threshold")

        # Run V2 risk assessment + ensemble
        v2_final_picks = []
        v2_max_picks = config.strategy.v2_max_picks if max_picks > 0 else 0
        if v2_candidates:
            v2_final_picks = _run_strategy_ensemble(
                judgment_service=judgment_service,
                supabase=supabase,
                candidates=v2_candidates,
                positions=v2_positions,
                strategy_mode=market_config.v2_strategy_mode,
                market_regime_str=market_regime_str,
                regime_params=regime_params,
                today=today,
                max_picks=min(v2_max_picks, regime_max_picks),
                finnhub=finnhub,
                yfinance=yfinance,
                perf_stats=v2_perf_stats,
                weekly_research=weekly_research_text,
                recent_mistakes=v2_recent_mistakes,
                market_config=market_config,
            )
        else:
            logger.info(f"V2 skipped: no candidates passed threshold")

        logger.info(f"V1 picks after ensemble: {v1_final_picks}")
        logger.info(f"V2 picks after ensemble: {v2_final_picks}")

        stats.total_candidates = total_candidates
        stats.successful_judgments = total_candidates
        judgment_ctx.successful_items = stats.successful_judgments
        judgment_ctx.total_items = stats.total_candidates
        BatchLogger.finish(judgment_ctx)

    except Exception as e:
        logger.error(f"LLM judgment failed: {e}")
        BatchLogger.finish(judgment_ctx, error=str(e))
        raise

    return v1_final_picks, v2_final_picks, stats


def _parse_regime(regime_str: str) -> MarketRegime:
    """Parse regime string to MarketRegime enum."""
    regime_str_lower = regime_str.lower()
    if "crisis" in regime_str_lower:
        return MarketRegime.CRISIS
    elif "adjustment" in regime_str_lower or "correction" in regime_str_lower:
        return MarketRegime.ADJUSTMENT
    return MarketRegime.NORMAL


def _run_strategy_ensemble(
    judgment_service: JudgmentService,
    supabase,
    candidates: list[tuple],
    positions: list,
    strategy_mode: str,
    market_regime_str: str,
    regime_params: dict,
    today: str,
    max_picks: int,
    finnhub=None,
    yfinance=None,
    perf_stats=None,
    weekly_research=None,
    recent_mistakes=None,
    market_config: MarketConfig | None = None,
) -> list[str]:
    """Run risk assessment + shadow ensemble for a single strategy.

    Returns:
        List of selected symbols (buy decisions)
    """
    # 1. Primary risk assessment
    primary_risk, summaries, news_by_symbol = run_risk_assessment(
        judgment_service=judgment_service,
        supabase=supabase,
        candidates=candidates,
        strategy_mode=strategy_mode,
        market_regime=market_regime_str,
        batch_date=today,
        current_positions=positions,
        finnhub=finnhub,
        yfinance=yfinance,
        recent_mistakes=recent_mistakes,
        weekly_research=weekly_research,
        performance_stats=perf_stats,
    )

    # 2. Shadow risk assessments (optional)
    shadow_risks: dict[str, PortfolioRiskOutput] = {}
    try:
        shadow_risks = _run_shadow_risk_assessments(
            candidates=candidates,
            positions=positions,
            strategy_mode=strategy_mode,
            market_regime_str=market_regime_str,
            today=today,
            finnhub=finnhub,
            yfinance=yfinance,
            supabase=supabase,
            perf_stats=perf_stats,
            weekly_research=weekly_research,
            recent_mistakes=recent_mistakes,
        )
    except Exception as e:
        logger.warning(f"Shadow risk assessments failed (non-critical): {e}")

    # 3. Ensemble aggregation
    ensemble_results = _aggregate_ensemble(
        primary_risk=primary_risk,
        shadow_risks=shadow_risks,
        candidates=candidates,
        regime_params=regime_params,
    )

    # 4. Save records (primary + all shadow models)
    if supabase:
        save_risk_assessment_records(
            supabase=supabase,
            ensemble_results=ensemble_results,
            risk_output=primary_risk,
            strategy_mode=strategy_mode,
            market_regime=market_regime_str,
            batch_date=today,
            model_version=judgment_service.model_name,
            is_primary=True,
        )
        for shadow_model_id, shadow_risk_output in shadow_risks.items():
            save_risk_assessment_records(
                supabase=supabase,
                ensemble_results=ensemble_results,
                risk_output=shadow_risk_output,
                strategy_mode=strategy_mode,
                market_regime=market_regime_str,
                batch_date=today,
                model_version=shadow_model_id,
                is_primary=False,
            )

    # 5. Extract buy picks
    picks = [
        er.symbol for er in ensemble_results
        if er.final_decision == "buy"
    ][:max_picks]

    logger.info(
        f"[{strategy_mode}] Ensemble: {len(picks)} buys from "
        f"{len(ensemble_results)} candidates "
        f"(regime={market_regime_str}, models={1 + len(shadow_risks)})"
    )

    return picks


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
                benchmark_daily_pct=benchmark_daily_pct,
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


def _aggregate_ensemble(
    primary_risk: PortfolioRiskOutput,
    shadow_risks: dict[str, PortfolioRiskOutput],
    candidates: list[tuple],
    regime_params: dict,
) -> list[EnsembleResult]:
    """Aggregate risk scores from primary + shadow models into ensemble decisions.

    Decision logic (deterministic):
    1. avg_risk = mean(all models' risk_scores for this symbol)
    2. consensus = (models with risk_score <= 3) / total_models
    3. buy if: avg_risk <= max_risk AND consensus >= min_consensus AND score >= min_score
    4. Sort by composite_score, limit to max_picks

    Args:
        primary_risk: Primary model's risk output
        shadow_risks: Dict of model_id -> PortfolioRiskOutput
        candidates: Original (stock_data, score) tuples
        regime_params: REGIME_DECISION_PARAMS for current regime

    Returns:
        List of EnsembleResult sorted by composite_score (descending)
    """
    max_risk = regime_params["max_risk"]
    min_consensus = regime_params["min_consensus"]
    min_score = regime_params["min_score"]
    max_picks = regime_params["max_picks"]

    # Build per-symbol risk score map: {symbol: {model_id: risk_score}}
    all_risk_scores: dict[str, dict[str, int]] = {}

    # Primary model
    primary_model_id = "primary"
    for assessment in primary_risk.assessments:
        all_risk_scores.setdefault(assessment.symbol, {})[primary_model_id] = assessment.risk_score

    # Shadow models
    for model_id, risk_output in shadow_risks.items():
        for assessment in risk_output.assessments:
            all_risk_scores.setdefault(assessment.symbol, {})[model_id] = assessment.risk_score

    # Build score lookup
    score_map = {}
    for stock_data, score in candidates:
        sym = stock_data.symbol if hasattr(stock_data, "symbol") else stock_data.get("symbol", "")
        score_map[sym] = score.composite_score if hasattr(score, "composite_score") else 0

    results = []
    for symbol, risk_scores in all_risk_scores.items():
        composite_score = score_map.get(symbol, 0)
        n_models = len(risk_scores)
        avg_risk = sum(risk_scores.values()) / n_models
        consensus = sum(1 for r in risk_scores.values() if r <= 3) / n_models

        # Deterministic decision
        reasons = []
        if composite_score < min_score:
            reasons.append(f"score {composite_score} < {min_score}")
        if avg_risk > max_risk:
            reasons.append(f"risk {avg_risk:.1f} > {max_risk}")
        if consensus < min_consensus:
            reasons.append(f"consensus {consensus:.0%} < {min_consensus:.0%}")

        if reasons:
            decision = "skip"
            reason = "Skip: " + ", ".join(reasons)
        else:
            decision = "buy"
            reason = f"Buy: score={composite_score}, risk={avg_risk:.1f}, consensus={consensus:.0%}"

        results.append(EnsembleResult(
            symbol=symbol,
            composite_score=composite_score,
            avg_risk_score=avg_risk,
            risk_scores=risk_scores,
            consensus_ratio=consensus,
            final_decision=decision,
            decision_reason=reason,
        ))

    # Sort by composite_score descending, take top max_picks buys
    results.sort(key=lambda r: r.composite_score, reverse=True)

    # Apply max_picks: only keep top N buys, rest become skip
    buy_count = 0
    for r in results:
        if r.final_decision == "buy":
            buy_count += 1
            if buy_count > max_picks:
                r.final_decision = "skip"
                r.decision_reason += f" (exceeded max_picks={max_picks})"

    return results


def _run_shadow_risk_assessments(
    candidates: list[tuple],
    positions: list,
    strategy_mode: str,
    market_regime_str: str,
    today: str,
    finnhub=None,
    yfinance=None,
    supabase=None,
    perf_stats=None,
    weekly_research=None,
    recent_mistakes=None,
) -> dict[str, PortfolioRiskOutput]:
    """Run shadow model risk assessments and return results for ensemble.

    Unlike the old _run_shadow_judgments() which returned None and saved directly,
    this returns results so they can participate in ensemble aggregation.

    Returns:
        Dict of model_id -> PortfolioRiskOutput
    """
    if not config.llm.enable_shadow_judgment:
        return {}

    shadow_models = config.llm.shadow_models
    if not shadow_models:
        logger.info("Shadow judgment enabled but no shadow models configured")
        return {}

    if not config.llm.openrouter_api_key:
        logger.warning("Shadow judgment enabled but OPENROUTER_API_KEY not set")
        return {}

    from src.llm.openai_client import OpenAIClient

    logger.info(f"Starting shadow risk assessments with {len(shadow_models)} models")

    results: dict[str, PortfolioRiskOutput] = {}

    for model_id in shadow_models:
        try:
            logger.info(f"Shadow risk assessment: {model_id}")

            shadow_client = OpenAIClient(
                base_url=config.llm.openrouter_base_url,
                api_key=config.llm.openrouter_api_key,
                default_model=model_id,
            )
            shadow_service = JudgmentService(
                llm_client=shadow_client,
                model_name=model_id,
            )

            risk_output, _, _ = run_risk_assessment(
                judgment_service=shadow_service,
                supabase=supabase,
                candidates=candidates,
                strategy_mode=strategy_mode,
                market_regime=market_regime_str,
                batch_date=today,
                current_positions=positions,
                finnhub=finnhub,
                yfinance=yfinance,
                recent_mistakes=recent_mistakes,
                weekly_research=weekly_research,
                performance_stats=perf_stats,
            )

            results[model_id] = risk_output
            logger.info(
                f"Shadow {model_id}: "
                + ", ".join(f"{a.symbol}=R{a.risk_score}" for a in risk_output.assessments)
            )

        except Exception as e:
            logger.warning(f"Shadow {model_id} failed: {e}")
            continue

    logger.info(f"Shadow risk assessments complete: {len(results)}/{len(shadow_models)} succeeded")
    return results


def save_scoring_results(
    supabase,
    batch_date: str,
    market_regime_str: str,
    dual_result,
    v1_stocks_data: list,
    v1_final_picks: list[str],
    v2_final_picks: list[str],
    market_config: MarketConfig,
) -> list[str]:
    """Save V1/V2 stock scores and daily picks to the database.

    Shared between US and JP markets. Uses StockScore/DailyPick dataclasses
    so all saves go through the SupabaseClient data layer consistently.

    Args:
        supabase: SupabaseClient instance
        batch_date: Batch date string (YYYY-MM-DD)
        market_regime_str: Current market regime string
        dual_result: DualScoringResult with v1_scores and v2_scores
        v1_stocks_data: V1 stock data (for price lookup)
        v1_final_picks: Final V1 pick symbols (after LLM judgment)
        v2_final_picks: Final V2 pick symbols (after LLM judgment)
        market_config: Market configuration

    Returns:
        List of error messages (empty if all succeeded)
    """
    save_errors: list[str] = []
    market_type = market_config.market_type if market_config.market_type != "us" else None

    def get_price(symbol: str) -> float:
        return next(
            (d.open_price for d in v1_stocks_data if d.symbol == symbol),
            0.0,
        )

    # Save V1 stock scores
    try:
        v1_stock_scores = [
            StockScore(
                batch_date=batch_date,
                symbol=s.symbol,
                strategy_mode=market_config.v1_strategy_mode,
                trend_score=s.trend_score,
                momentum_score=s.momentum_score,
                value_score=s.value_score,
                sentiment_score=s.sentiment_score,
                composite_score=s.composite_score,
                percentile_rank=s.percentile_rank,
                reasoning=s.reasoning,
                price_at_time=get_price(s.symbol),
                market_regime_at_time=market_regime_str,
                momentum_12_1_score=s.momentum_12_1_score,
                breakout_score=s.breakout_score,
                catalyst_score=s.catalyst_score,
                risk_adjusted_score=s.risk_adjusted_score,
                cutoff_timestamp=dual_result.cutoff_timestamp.isoformat(),
                market_type=market_type,
            )
            for s in dual_result.v1_scores
        ]
        supabase.save_stock_scores(v1_stock_scores)
        logger.info(f"Saved {len(v1_stock_scores)} V1 ({market_config.v1_strategy_mode}) stock scores")
    except Exception as e:
        error_msg = f"Failed to save V1 stock scores: {e}"
        logger.error(error_msg)
        save_errors.append(error_msg)

    # Save V2 stock scores
    try:
        v2_stock_scores = [
            StockScore(
                batch_date=batch_date,
                symbol=s.symbol,
                strategy_mode=market_config.v2_strategy_mode,
                trend_score=s.trend_score,
                momentum_score=s.momentum_score,
                value_score=s.value_score,
                sentiment_score=s.sentiment_score,
                composite_score=s.composite_score,
                percentile_rank=s.percentile_rank,
                reasoning=s.reasoning,
                price_at_time=get_price(s.symbol),
                market_regime_at_time=market_regime_str,
                momentum_12_1_score=s.momentum_12_1_score,
                breakout_score=s.breakout_score,
                catalyst_score=s.catalyst_score,
                risk_adjusted_score=s.risk_adjusted_score,
                cutoff_timestamp=dual_result.cutoff_timestamp.isoformat(),
                market_type=market_type,
            )
            for s in dual_result.v2_scores
        ]
        supabase.save_stock_scores(v2_stock_scores)
        logger.info(f"Saved {len(v2_stock_scores)} V2 ({market_config.v2_strategy_mode}) stock scores")
    except Exception as e:
        error_msg = f"Failed to save V2 stock scores: {e}"
        logger.error(error_msg)
        save_errors.append(error_msg)

    # Save daily picks
    try:
        v1_pick = DailyPick(
            batch_date=batch_date,
            symbols=v1_final_picks,
            pick_count=len(v1_final_picks),
            market_regime=market_regime_str,
            strategy_mode=market_config.v1_strategy_mode,
            status="published",
            market_type=market_type,
        )
        v2_pick = DailyPick(
            batch_date=batch_date,
            symbols=v2_final_picks,
            pick_count=len(v2_final_picks),
            market_regime=market_regime_str,
            strategy_mode=market_config.v2_strategy_mode,
            status="published",
            market_type=market_type,
        )

        saved_picks, pick_errors = supabase.save_daily_picks_batch(
            [v1_pick, v2_pick],
            delete_existing=True,
        )

        if pick_errors:
            for err in pick_errors:
                logger.error(err)
                save_errors.append(err)
        else:
            logger.info(f"Saved daily picks: V1={len(v1_final_picks)}, V2={len(v2_final_picks)}")

    except Exception as e:
        error_msg = f"Failed to save daily picks: {e}"
        logger.error(error_msg)
        save_errors.append(error_msg)

    if save_errors:
        logger.error(f"Save operation completed with {len(save_errors)} error(s)")
    else:
        logger.info(f"Final Picks: V1={v1_final_picks}, V2={v2_final_picks}")

    return save_errors
