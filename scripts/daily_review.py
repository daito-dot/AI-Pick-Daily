#!/usr/bin/env python3
"""
Daily Review Script

Evening batch job that:
1. Calculates returns for ALL scored stocks (not just picks)
2. Identifies missed opportunities
3. Records judgment outcomes for feedback
4. **FEEDBACK LOOP**: Adjusts scoring thresholds based on performance
5. **FEEDBACK LOOP**: Adjusts factor weights based on outcome correlations

This enables learning from what we DIDN'T recommend, not just what we did.
The threshold and factor weight adjustments create closed feedback loops where
the system automatically adapts its behavior based on past performance.
"""
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config
from src.data.finnhub_client import FinnhubClient
from src.data.yfinance_client import get_yfinance_client
from src.data.supabase_client import SupabaseClient
from src.judgment import JudgmentService
from src.pipeline.market_config import US_MARKET
from src.pipeline.review import (
    adjust_thresholds_for_strategies,
    adjust_factor_weights,
    populate_judgment_outcomes,
    get_unprocessed_outcome_dates,
    check_batch_gap,
    get_current_price,
    calculate_all_returns,
    log_return_summary,
)
from src.portfolio import PortfolioManager
from src.batch_logger import BatchLogger, BatchType

# Setup logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG if config.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / f"review_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def main():
    """Main review pipeline."""
    logger.info("=" * 60)
    logger.info("Starting daily review batch (ALL STOCKS)")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    logger.info("=" * 60)

    market_config = US_MARKET
    strategies = market_config.strategies

    # Start batch logging
    batch_ctx = BatchLogger.start(BatchType.EVENING_REVIEW)
    batch_ctx.metadata["market"] = market_config.market_type

    # Initialize clients
    try:
        finnhub = FinnhubClient()
        yf_client = get_yfinance_client()
        supabase = SupabaseClient()
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        BatchLogger.finish(batch_ctx, error=str(e))
        sys.exit(1)

    # Build price fetcher using shared function
    def price_fetcher(symbol: str) -> float | None:
        return get_current_price(symbol, market_config, finnhub=finnhub, yf_client=yf_client)

    # Initialize results in case of unexpected exceptions
    results_5d = {"error": "Not executed"}
    results_1d = {"error": "Not executed"}

    # Step 0: Check for batch gaps and backfill missed outcomes
    check_batch_gap(supabase, market_type=market_config.market_type)

    try:
        today_date = datetime.now(timezone.utc).date()
        MAX_BACKFILL_DATES = 2

        unprocessed_5d = get_unprocessed_outcome_dates(supabase, return_field="5d", strategy_modes=strategies)
        for missed_date in unprocessed_5d[:MAX_BACKFILL_DATES]:
            days_ago = (today_date - datetime.strptime(missed_date, "%Y-%m-%d").date()).days
            logger.info(f"Backfilling 5d outcomes for {missed_date} (days_ago={days_ago})")
            backfill_results = calculate_all_returns(price_fetcher, supabase, market_config, days_ago=days_ago, return_field="5d")
            populate_judgment_outcomes(supabase, backfill_results, return_field="5d")

        unprocessed_1d = get_unprocessed_outcome_dates(supabase, return_field="1d", min_age_days=1, strategy_modes=strategies)
        for missed_date in unprocessed_1d[:MAX_BACKFILL_DATES]:
            days_ago = (today_date - datetime.strptime(missed_date, "%Y-%m-%d").date()).days
            logger.info(f"Backfilling 1d outcomes for {missed_date} (days_ago={days_ago})")
            backfill_results = calculate_all_returns(price_fetcher, supabase, market_config, days_ago=days_ago, return_field="1d")
            populate_judgment_outcomes(supabase, backfill_results, return_field="1d")
    except Exception as e:
        logger.error(f"Outcome backfill failed (non-fatal): {e}")

    # 1. Calculate returns for ALL stocks (5-day review)
    logger.info("Step 1: Calculating 5-day returns for ALL scored stocks...")
    results_5d = calculate_all_returns(price_fetcher, supabase, market_config, days_ago=5, return_field="5d")
    log_return_summary(results_5d, "5-day")

    # 1b. Record judgment outcomes for 5-day returns
    populate_judgment_outcomes(supabase, results_5d, return_field="5d")

    # 2. Also do 1-day review (for faster feedback)
    logger.info("Step 2: Calculating 1-day returns for ALL scored stocks...")
    results_1d = calculate_all_returns(price_fetcher, supabase, market_config, days_ago=1, return_field="1d")

    # 2b. Record judgment outcomes for 1-day returns
    populate_judgment_outcomes(supabase, results_1d, return_field="1d")

    # 3. PAPER TRADING: Evaluate exit signals and close positions
    logger.info("Step 3: Evaluating exit signals for open positions...")
    portfolio = PortfolioManager(
        supabase=supabase,
        finnhub=finnhub,
        yfinance=yf_client,
        market_config=market_config,
    )

    # Get current market regime
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    current_regime = supabase.get_market_regime(today)
    market_regime_str = current_regime.get("market_regime") if current_regime else None

    # Get current thresholds
    v1_config = supabase.get_scoring_config(market_config.v1_strategy_mode)
    v2_config = supabase.get_scoring_config(market_config.v2_strategy_mode)
    thresholds = {
        market_config.v1_strategy_mode: float(v1_config.get("threshold", market_config.default_v1_threshold)) if v1_config else market_config.default_v1_threshold,
        market_config.v2_strategy_mode: float(v2_config.get("threshold", market_config.default_v2_threshold)) if v2_config else market_config.default_v2_threshold,
    }

    # Get scores for exit evaluation using BATCH LINKING (not date-based)
    scores_by_strategy: dict[str, dict[str, int]] = {}
    reviewed_batches: list[str] = []

    for strategy in strategies:
        unreviewed_batch = supabase.get_unreviewed_batch(strategy)
        if unreviewed_batch:
            batch_date = unreviewed_batch["batch_date"]
            batch_id = unreviewed_batch["id"]
            logger.info(
                f"Found unreviewed batch for {strategy}: {batch_date} "
                f"(picks: {unreviewed_batch['pick_count']})"
            )
            scores_by_strategy[strategy] = supabase.get_scores_for_batch(batch_date, strategy)
            reviewed_batches.append(batch_id)
        else:
            logger.info(f"No unreviewed batch for {strategy}")
            scores_by_strategy[strategy] = {}

    # Get all open positions
    all_positions = portfolio.get_open_positions()
    logger.info(f"Found {len(all_positions)} open positions")

    exit_signals = []

    if all_positions:
        # Step 3a: Identify soft exit candidates and consult AI
        exit_judgments: dict[str, object] = {}
        if config.llm.enable_judgment:
            try:
                judgment_service = JudgmentService()
                all_soft_candidates = []
                for strategy in strategies:
                    strategy_positions = [p for p in all_positions if p.strategy_mode == strategy]
                    current_scores = scores_by_strategy.get(strategy, {})
                    soft_candidates = portfolio.get_soft_exit_candidates(
                        positions=strategy_positions,
                        current_scores=current_scores if current_scores else None,
                        thresholds=thresholds,
                        market_regime=market_regime_str,
                    )
                    all_soft_candidates.extend(soft_candidates)

                if all_soft_candidates:
                    logger.info(f"Consulting AI for {len(all_soft_candidates)} soft exit candidates")
                    ai_results = judgment_service.judge_exits(
                        positions_for_review=all_soft_candidates,
                        market_regime=market_regime_str or "normal",
                    )
                    exit_judgments = {r.symbol: r for r in ai_results}
                    logger.info(f"AI exit judgments: {[(r.symbol, r.decision) for r in ai_results]}")
            except Exception as e:
                logger.error(f"AI exit judgment failed: {e}")

        # Step 3b: Evaluate exit signals with AI judgments
        for strategy in strategies:
            strategy_positions = [p for p in all_positions if p.strategy_mode == strategy]
            if not strategy_positions:
                continue

            current_scores = scores_by_strategy.get(strategy, {})
            strategy_exit_signals = portfolio.evaluate_exit_signals(
                positions=strategy_positions,
                current_scores=current_scores if current_scores else None,
                thresholds=thresholds,
                market_regime=market_regime_str,
                exit_judgments=exit_judgments,
            )
            exit_signals.extend(strategy_exit_signals)

        if exit_signals:
            logger.info(f"Exit signals triggered: {len(exit_signals)}")
            for signal in exit_signals:
                logger.info(
                    f"  {signal.position.symbol} ({signal.position.strategy_mode}): "
                    f"{signal.reason} @ {signal.pnl_pct:+.1f}%"
                )
            trades = portfolio.close_positions(
                exit_signals=exit_signals,
                market_regime_at_exit=market_regime_str,
            )
            logger.info(f"Closed {len(trades)} positions")
        else:
            logger.info("No exit signals triggered")
    else:
        logger.info("No open positions to evaluate")

    # Mark batches as reviewed
    for batch_id in reviewed_batches:
        supabase.mark_batch_reviewed(batch_id)
        logger.info(f"Marked batch {batch_id} as reviewed")

    # Get benchmark daily return (always track regardless of positions)
    sp500_daily_pct = yf_client.get_sp500_daily_return()
    if sp500_daily_pct is not None:
        logger.info(f"S&P500 daily return: {sp500_daily_pct:+.2f}%")
    else:
        logger.warning("Could not get S&P500 daily return")

    # Update portfolio snapshots
    logger.info("Updating portfolio snapshots...")
    for strategy in strategies:
        closed_today = len([s for s in exit_signals if s.position.strategy_mode == strategy]) if exit_signals else 0
        try:
            portfolio.update_portfolio_snapshot(
                strategy_mode=strategy,
                closed_today=closed_today,
                benchmark_daily_pct=sp500_daily_pct,
            )
        except Exception as e:
            logger.error(f"Failed to update snapshot for {strategy}: {e}")

    # 4. FEEDBACK LOOP: Adjust thresholds based on performance
    if not results_5d.get("error"):
        logger.info("Step 4: Analyzing and adjusting thresholds (FEEDBACK LOOP)...")
        adjust_thresholds_for_strategies(supabase, results_5d, strategies)
    else:
        logger.info("Step 4: Skipping threshold adjustment (no 5-day data)")

    # 5. FEEDBACK LOOP: Adjust factor weights based on outcome correlations
    logger.info("Step 5: Adjusting factor weights (FEEDBACK LOOP)...")
    for strategy in strategies:
        adjust_factor_weights(supabase, strategy)

    # 6. Get and log performance summary
    logger.info("Step 6: Getting overall performance summary...")
    for strategy in strategies:
        summary = supabase.get_performance_summary(days=30, strategy_mode=strategy)
        logger.info(f"\n{strategy.upper()} Summary (30 days):")
        logger.info(f"  Picked: {summary.get('picked_count', 0)} stocks, avg return: {summary.get('picked_avg_return', 0):.2f}%")
        logger.info(f"  Not Picked: {summary.get('not_picked_count', 0)} stocks, avg return: {summary.get('not_picked_avg_return', 0):.2f}%")
        logger.info(f"  Missed Opportunities (>3%): {summary.get('missed_opportunities', 0)}")

    # 7. META-MONITOR: Detect degradation and auto-correct
    logger.info("Step 7: Running meta-monitor (autonomous improvement)...")
    from src.meta_monitor import run_meta_monitor
    for strategy in strategies:
        try:
            run_meta_monitor(supabase, strategy)
        except Exception as e:
            logger.error(f"Meta-monitor failed for {strategy}: {e}")

    logger.info("=" * 60)
    logger.info("Daily review batch completed")
    logger.info("=" * 60)

    # Finish batch logging
    if not results_5d.get("error"):
        batch_ctx.total_items = results_5d.get("total_stocks", 0)
        batch_ctx.successful_items = results_5d.get("successful", 0)
        batch_ctx.failed_items = results_5d.get("failed", 0)
    elif not results_1d.get("error"):
        batch_ctx.total_items = results_1d.get("total_stocks", 0)
        batch_ctx.successful_items = results_1d.get("successful", 0)
        batch_ctx.failed_items = results_1d.get("failed", 0)
    BatchLogger.finish(batch_ctx)


if __name__ == "__main__":
    main()
