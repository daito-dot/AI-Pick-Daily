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
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config
from src.data.finnhub_client import FinnhubClient
from src.data.yfinance_client import get_yfinance_client, YFinanceClient
from src.data.supabase_client import SupabaseClient
from src.judgment import JudgmentService
from src.pipeline.market_config import US_MARKET
from src.pipeline.review import adjust_thresholds_for_strategies, adjust_factor_weights, populate_judgment_outcomes
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


def get_current_price(
    finnhub: FinnhubClient,
    yf_client: YFinanceClient,
    symbol: str,
) -> float | None:
    """
    Get current price for a symbol with fallback.

    Args:
        finnhub: Finnhub client
        yf_client: yfinance client
        symbol: Stock symbol

    Returns:
        Current price or None if unavailable
    """
    # Try Finnhub first
    try:
        quote = finnhub.get_quote(symbol)
        if quote.current_price and quote.current_price > 0:
            return quote.current_price
    except Exception as e:
        logger.debug(f"{symbol}: Finnhub quote failed: {e}")

    # Fallback to yfinance
    try:
        yf_quote = yf_client.get_quote(symbol)
        if yf_quote and yf_quote.current_price > 0:
            return yf_quote.current_price
    except Exception as e:
        logger.debug(f"{symbol}: yfinance quote failed: {e}")

    return None


def calculate_all_returns(
    finnhub: FinnhubClient,
    yf_client: YFinanceClient,
    supabase: SupabaseClient,
    days_ago: int = 5,
    return_field: str = "5d",
) -> dict:
    """
    Calculate returns for ALL scored stocks from N days ago.

    Args:
        finnhub: Finnhub client
        yf_client: yfinance client
        supabase: Supabase client
        days_ago: Number of days to look back
        return_field: Which return field to update ("1d" or "5d")

    Returns:
        Dict with results summary
    """
    check_date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    logger.info(f"Calculating {return_field} returns for ALL stocks from {check_date}")

    # Get ALL scores from that date
    all_scores = supabase.get_scores_for_review(check_date)
    if not all_scores:
        logger.info(f"No scores found for {check_date}")
        return {"error": "No scores found", "date": check_date}

    logger.info(f"Found {len(all_scores)} stock scores to review")

    # Get the picks for that date to mark was_picked
    picks_data = {}
    for strategy in ["conservative", "aggressive"]:
        picks_result = supabase._client.table("daily_picks").select("symbols").eq(
            "batch_date", check_date
        ).eq(
            "strategy_mode", strategy
        ).execute()
        if picks_result.data:
            picks_data[strategy] = set(picks_result.data[0].get("symbols", []))
        else:
            picks_data[strategy] = set()

    logger.info(f"Picks - Conservative: {picks_data['conservative']}, Aggressive: {picks_data['aggressive']}")

    # Calculate returns for each stock
    updates = []
    results = {
        "date": check_date,
        "days_ago": days_ago,
        "total_stocks": len(all_scores),
        "successful": 0,
        "failed": 0,
        "picked_returns": [],
        "not_picked_returns": [],
        "missed_opportunities": [],
    }

    for score in all_scores:
        symbol = score["symbol"]
        strategy = score["strategy_mode"]
        original_price = score.get("price_at_time", 0)
        composite_score = score.get("composite_score", 0)

        if original_price <= 0:
            logger.warning(f"{symbol}: No original price, skipping")
            results["failed"] += 1
            continue

        # Get current price
        current_price = get_current_price(finnhub, yf_client, symbol)
        if not current_price:
            logger.warning(f"{symbol}: Could not get current price")
            results["failed"] += 1
            continue

        # Calculate return
        return_pct = ((current_price - original_price) / original_price) * 100
        was_picked = symbol in picks_data.get(strategy, set())

        # Build update dict based on return_field
        update_entry = {
            "batch_date": check_date,
            "symbol": symbol,
            "strategy_mode": strategy,
            "was_picked": was_picked,
        }
        if return_field == "1d":
            update_entry["return_1d"] = return_pct
            update_entry["price_1d"] = current_price
        else:
            update_entry["return_5d"] = return_pct
            update_entry["price_5d"] = current_price
        updates.append(update_entry)

        result_entry = {
            "symbol": symbol,
            "strategy": strategy,
            "score": composite_score,
            "return_pct": round(return_pct, 2),
            "original_price": original_price,
            "current_price": current_price,
        }

        if was_picked:
            results["picked_returns"].append(result_entry)
            logger.info(f"[PICKED] {symbol} ({strategy}): {original_price:.2f} -> {current_price:.2f} ({return_pct:+.1f}%)")
        else:
            results["not_picked_returns"].append(result_entry)
            # Check if this is a missed opportunity (not picked but good return)
            if return_pct >= 3.0:  # 3%+ return is considered significant
                results["missed_opportunities"].append(result_entry)
                logger.warning(f"[MISSED] {symbol} ({strategy}): Score={composite_score}, Return={return_pct:+.1f}%")
            else:
                logger.debug(f"[NOT PICKED] {symbol} ({strategy}): {return_pct:+.1f}%")

        results["successful"] += 1
        time.sleep(0.2)  # Rate limiting

    # Bulk update to database
    if updates:
        updated = supabase.bulk_update_returns(updates)
        logger.info(f"Updated {updated} stock scores with return data")

    return results


def main():
    """Main review pipeline."""
    logger.info("=" * 60)
    logger.info("Starting daily review batch (ALL STOCKS)")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    logger.info("=" * 60)

    # Start batch logging
    batch_ctx = BatchLogger.start(BatchType.EVENING_REVIEW)

    # Initialize clients
    try:
        finnhub = FinnhubClient()
        yf_client = get_yfinance_client()
        supabase = SupabaseClient()
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        BatchLogger.finish(batch_ctx, error=str(e))
        sys.exit(1)

    # Initialize results in case of unexpected exceptions
    results_5d = {"error": "Not executed"}
    results_1d = {"error": "Not executed"}

    # 1. Calculate returns for ALL stocks (5-day review)
    logger.info("Step 1: Calculating 5-day returns for ALL scored stocks...")
    results_5d = calculate_all_returns(finnhub, yf_client, supabase, days_ago=5, return_field="5d")

    if results_5d.get("error"):
        logger.warning(f"No data for 5-day review: {results_5d}")
    else:
        picked = results_5d.get("picked_returns", [])
        not_picked = results_5d.get("not_picked_returns", [])
        missed = results_5d.get("missed_opportunities", [])

        logger.info("5-day results summary:")
        logger.info(f"  - Total reviewed: {results_5d['successful']}")
        logger.info(f"  - Picked stocks: {len(picked)}")
        logger.info(f"  - Not picked: {len(not_picked)}")
        logger.info(f"  - MISSED OPPORTUNITIES: {len(missed)}")

        if missed:
            logger.warning("=" * 40)
            logger.warning("MISSED OPPORTUNITIES DETECTED!")
            for m in missed[:5]:
                logger.warning(f"  {m['symbol']}: Score={m['score']}, +{m['return_pct']:.1f}%")
            logger.warning("=" * 40)

    # 1b. Record judgment outcomes for 5-day returns
    populate_judgment_outcomes(supabase, results_5d, return_field="5d")

    # 2. Also do 1-day review (for faster feedback)
    logger.info("Step 2: Calculating 1-day returns for ALL scored stocks...")
    results_1d = calculate_all_returns(finnhub, yf_client, supabase, days_ago=1, return_field="1d")

    # 2b. Record judgment outcomes for 1-day returns
    populate_judgment_outcomes(supabase, results_1d, return_field="1d")

    # 3. PAPER TRADING: Evaluate exit signals and close positions
    logger.info("Step 3: Evaluating exit signals for open positions...")
    portfolio = PortfolioManager(
        supabase=supabase,
        finnhub=finnhub,
        yfinance=yf_client,
        market_config=US_MARKET,
    )

    # Get current market regime
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    current_regime = supabase.get_market_regime(today)
    market_regime_str = current_regime.get("market_regime") if current_regime else None

    # Get current thresholds
    v1_config = supabase.get_scoring_config("conservative")
    v2_config = supabase.get_scoring_config("aggressive")
    thresholds = {
        "conservative": float(v1_config.get("threshold", 60)) if v1_config else 60,
        "aggressive": float(v2_config.get("threshold", 75)) if v2_config else 75,
    }

    # Get scores for exit evaluation using BATCH LINKING (not date-based)
    # Each strategy_mode is linked to its unreviewed Post-Market batch
    scores_by_strategy: dict[str, dict[str, int]] = {}
    reviewed_batches: list[str] = []  # Track batch IDs to mark as reviewed

    for strategy in ["conservative", "aggressive"]:
        unreviewed_batch = supabase.get_unreviewed_batch(strategy)
        if unreviewed_batch:
            batch_date = unreviewed_batch["batch_date"]
            batch_id = unreviewed_batch["id"]
            logger.info(
                f"Found unreviewed batch for {strategy}: {batch_date} "
                f"(picks: {unreviewed_batch['pick_count']})"
            )
            # Get scores from the linked batch
            scores_by_strategy[strategy] = supabase.get_scores_for_batch(batch_date, strategy)
            reviewed_batches.append(batch_id)
        else:
            logger.info(f"No unreviewed batch for {strategy}")
            scores_by_strategy[strategy] = {}

    # Get all open positions
    all_positions = portfolio.get_open_positions()
    logger.info(f"Found {len(all_positions)} open positions")

    # Initialize exit_signals in case of exceptions
    exit_signals = []

    if all_positions:
        # Step 3a: Identify soft exit candidates and consult AI
        exit_judgments: dict[str, object] = {}
        if config.llm.enable_judgment:
            try:
                judgment_service = JudgmentService()
                all_soft_candidates = []
                for strategy in ["conservative", "aggressive"]:
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
                # No fallback — proceed without AI (all soft exits fire)

        # Step 3b: Evaluate exit signals with AI judgments
        for strategy in ["conservative", "aggressive"]:
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

            # Close positions
            trades = portfolio.close_positions(
                exit_signals=exit_signals,
                market_regime_at_exit=market_regime_str,
            )
            logger.info(f"Closed {len(trades)} positions")

        else:
            logger.info("No exit signals triggered")
    else:
        logger.info("No open positions to evaluate")

    # Mark batches as reviewed (regardless of whether positions were closed)
    for batch_id in reviewed_batches:
        supabase.mark_batch_reviewed(batch_id)
        logger.info(f"Marked batch {batch_id} as reviewed")

    # Get S&P500 daily return for benchmark (always track regardless of positions)
    sp500_daily_pct = yf_client.get_sp500_daily_return()
    if sp500_daily_pct is not None:
        logger.info(f"S&P500 daily return: {sp500_daily_pct:+.2f}%")
    else:
        logger.warning("Could not get S&P500 daily return")

    # Update portfolio snapshots (always update for S&P500 tracking)
    logger.info("Updating portfolio snapshots...")
    for strategy in ["conservative", "aggressive"]:
        closed_today = len([s for s in exit_signals if s.position.strategy_mode == strategy]) if exit_signals else 0
        try:
            portfolio.update_portfolio_snapshot(
                strategy_mode=strategy,
                closed_today=closed_today,
                sp500_daily_pct=sp500_daily_pct,
            )
        except Exception as e:
            logger.error(f"Failed to update snapshot for {strategy}: {e}")

    # 4. FEEDBACK LOOP: Adjust thresholds based on performance (only if we have data)
    if not results_5d.get("error"):
        logger.info("Step 4: Analyzing and adjusting thresholds (FEEDBACK LOOP)...")
        adjust_thresholds_for_strategies(supabase, results_5d, ["conservative", "aggressive"])
    else:
        logger.info("Step 4: Skipping threshold adjustment (no 5-day data)")

    # 5. FEEDBACK LOOP: Adjust factor weights based on outcome correlations
    logger.info("Step 5: Adjusting factor weights (FEEDBACK LOOP)...")
    for strategy in ["conservative", "aggressive"]:
        adjust_factor_weights(supabase, strategy)

    # 6. Get and log performance summary
    logger.info("Step 6: Getting overall performance summary...")
    for strategy in ["conservative", "aggressive"]:
        summary = supabase.get_performance_summary(days=30, strategy_mode=strategy)
        logger.info(f"\n{strategy.upper()} Summary (30 days):")
        logger.info(f"  Picked: {summary.get('picked_count', 0)} stocks, avg return: {summary.get('picked_avg_return', 0):.2f}%")
        logger.info(f"  Not Picked: {summary.get('not_picked_count', 0)} stocks, avg return: {summary.get('not_picked_avg_return', 0):.2f}%")
        logger.info(f"  Missed Opportunities (>3%): {summary.get('missed_opportunities', 0)}")

    # 7. META-MONITOR: Detect degradation and auto-correct
    logger.info("Step 7: Running meta-monitor (autonomous improvement)...")
    from src.meta_monitor import run_meta_monitor
    for strategy in ["conservative", "aggressive"]:
        try:
            run_meta_monitor(supabase, strategy)
        except Exception as e:
            logger.error(f"Meta-monitor failed for {strategy}: {e}")

    logger.info("=" * 60)
    logger.info("Daily review batch completed")
    logger.info("=" * 60)

    # Finish batch logging
    # Use 5d results if available, otherwise fall back to 1d results
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
