#!/usr/bin/env python3
"""
Daily Review Script for Japanese Stocks

Evening batch job that:
1. Calculates returns for ALL scored Japanese stocks (not just picks)
2. Identifies missed opportunities
3. Generates AI reflection using Gemini
4. Saves lessons to database
5. **FEEDBACK LOOP**: Adjusts scoring thresholds based on performance

This enables learning from what we DIDN'T recommend, not just what we did.
The threshold adjustment creates a closed feedback loop where the system
automatically adapts its behavior based on past performance.
"""
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config
from src.data.yfinance_client import get_yfinance_client, YFinanceClient
from src.data.supabase_client import SupabaseClient
from src.llm import get_llm_client
from src.scoring.threshold_optimizer import (
    calculate_optimal_threshold,
    should_apply_adjustment,
    format_adjustment_log,
    check_overfitting_protection,
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
        logging.FileHandler(log_dir / f"review_jp_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# Japanese strategy modes
JP_STRATEGIES = ["jp_conservative", "jp_aggressive"]


def get_current_price_jp(
    yf_client: YFinanceClient,
    symbol: str,
) -> float | None:
    """
    Get current price for a Japanese stock symbol.

    Args:
        yf_client: yfinance client
        symbol: Stock symbol (e.g., 7203.T)

    Returns:
        Current price or None if unavailable
    """
    try:
        yf_quote = yf_client.get_quote(symbol)
        if yf_quote and yf_quote.current_price > 0:
            return yf_quote.current_price
    except Exception as e:
        logger.debug(f"{symbol}: yfinance quote failed: {e}")

    return None


def calculate_all_returns_jp(
    yf_client: YFinanceClient,
    supabase: SupabaseClient,
    days_ago: int = 5,
    return_field: str = "5d",
) -> dict:
    """
    Calculate returns for ALL scored Japanese stocks from N days ago.

    Args:
        yf_client: yfinance client
        supabase: Supabase client
        days_ago: Number of days to look back
        return_field: Which return field to update ("1d" or "5d")

    Returns:
        Dict with results summary
    """
    check_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    logger.info(f"Calculating {return_field} returns for ALL JP stocks from {check_date}")

    # Get ALL JP scores from that date (using strategy_mode filter)
    all_scores = []
    for strategy in JP_STRATEGIES:
        try:
            result = supabase._client.table("stock_scores").select("*").eq(
                "batch_date", check_date
            ).eq(
                "strategy_mode", strategy
            ).execute()
            if result.data:
                all_scores.extend(result.data)
        except Exception as e:
            logger.error(f"Failed to fetch scores for {strategy}: {e}")

    if not all_scores:
        logger.info(f"No JP scores found for {check_date}")
        return {"error": "No scores found", "date": check_date}

    logger.info(f"Found {len(all_scores)} JP stock scores to review")

    # Get the picks for that date to mark was_picked
    picks_data = {}
    for strategy in JP_STRATEGIES:
        picks_result = supabase._client.table("daily_picks").select("symbols").eq(
            "batch_date", check_date
        ).eq(
            "strategy_mode", strategy
        ).execute()
        if picks_result.data:
            picks_data[strategy] = set(picks_result.data[0].get("symbols", []))
        else:
            picks_data[strategy] = set()

    logger.info(f"Picks - JP Conservative: {picks_data.get('jp_conservative', set())}, "
                f"JP Aggressive: {picks_data.get('jp_aggressive', set())}")

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
        current_price = get_current_price_jp(yf_client, symbol)
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
            logger.info(f"[PICKED] {symbol} ({strategy}): ¥{original_price:,.0f} -> ¥{current_price:,.0f} ({return_pct:+.1f}%)")
        else:
            results["not_picked_returns"].append(result_entry)
            # Check if this is a missed opportunity (not picked but good return)
            if return_pct >= 3.0:  # 3%+ return is considered significant
                results["missed_opportunities"].append(result_entry)
                logger.warning(f"[MISSED] {symbol} ({strategy}): Score={composite_score}, Return={return_pct:+.1f}%")
            else:
                logger.debug(f"[NOT PICKED] {symbol} ({strategy}): {return_pct:+.1f}%")

        results["successful"] += 1
        time.sleep(0.3)  # Rate limiting (slightly longer for yfinance)

    # Bulk update to database
    if updates:
        updated = supabase.bulk_update_returns(updates)
        logger.info(f"Updated {updated} JP stock scores with return data")

    return results


def generate_reflection_jp(llm_client, results: dict) -> str:
    """
    Generate AI reflection on today's Japanese stock performance.
    Includes analysis of missed opportunities.
    """
    if results.get("error"):
        return f"No data to review: {results.get('error')}"

    picked = results.get("picked_returns", [])
    not_picked = results.get("not_picked_returns", [])
    missed = results.get("missed_opportunities", [])

    # Calculate stats
    def avg_return(lst):
        if not lst:
            return 0
        return sum(r["return_pct"] for r in lst) / len(lst)

    picked_avg = avg_return(picked)
    not_picked_avg = avg_return(not_picked)
    missed_avg = avg_return(missed)

    wins = len([r for r in picked if r["return_pct"] >= 1])
    losses = len([r for r in picked if r["return_pct"] <= -1])

    context = f"""
## 日本株パフォーマンスレビュー ({results['days_ago']}日後, {results['date']})

### 推奨銘柄のパフォーマンス
- 推奨銘柄数: {len(picked)}
- 勝ち (≥1%): {wins}
- 負け (≤-1%): {losses}
- 平均リターン: {picked_avg:+.2f}%

### 非推奨銘柄のパフォーマンス
- 非推奨銘柄数: {len(not_picked)}
- 平均リターン: {not_picked_avg:+.2f}%

### 重要: 見逃した機会 (≥3%リターン、非推奨)
- 件数: {len(missed)}
- 見逃した平均リターン: {missed_avg:+.2f}%
"""

    if missed:
        context += "\n見逃した機会の詳細:\n"
        for m in sorted(missed, key=lambda x: x["return_pct"], reverse=True)[:5]:
            context += f"- {m['symbol']} ({m['strategy']}): スコア={m['score']}, リターン={m['return_pct']:+.1f}%\n"

    if picked:
        context += "\n推奨銘柄の詳細:\n"
        for p in sorted(picked, key=lambda x: x["return_pct"], reverse=True)[:5]:
            context += f"- {p['symbol']} ({p['strategy']}): スコア={p['score']}, リターン={p['return_pct']:+.1f}%\n"

    prompt = f"""
あなたはAI株式推奨システムで、過去のパフォーマンスをレビューしています。
対象市場: 日本株（東証）

{context}

これらの結果に基づいて分析を行ってください:

1. **推奨品質**: 推奨銘柄は非推奨銘柄より良かったか？平均リターンを比較。

2. **見逃した機会の分析**:
   - なぜこれらの銘柄を見逃したのか？（スコアが低すぎた？閾値が高すぎた？）
   - 見逃した機会のスコアと閾値の比較
   - 閾値を調整すべきか？

3. **閾値の推奨**:
   - 現在のV1閾値: 60, 現在のV2閾値: 75
   - 見逃した機会に基づき、閾値調整を具体的な数値で提案

4. **重要な学び**: 最も重要な教訓は何か？

正直に分析してください。良い機会を見逃した場合、「何も推奨しない」は成功ではありません。
具体的な数値と実行可能な推奨事項を含めてください。
"""

    try:
        response = llm_client.generate_with_thinking(prompt)
        return response.content
    except Exception as e:
        logger.error(f"Failed to generate reflection: {e}")
        return f"Failed to generate reflection: {e}"


def save_ai_lesson_jp(
    supabase: SupabaseClient,
    reflection: str,
    missed: list,
    date: str,
):
    """Save AI lesson for Japanese stocks to database."""
    try:
        missed_symbols = [m["symbol"] for m in missed[:5]]
        miss_analysis = "\n".join([
            f"{m['symbol']}: スコア={m['score']}, リターン={m['return_pct']:+.1f}%"
            for m in missed[:5]
        ])

        # Use a different lesson_date format to distinguish from US lessons
        lesson_date = f"{date}_jp"

        supabase._client.table("ai_lessons").upsert({
            "lesson_date": lesson_date,
            "lesson_text": reflection,
            "biggest_miss_symbols": missed_symbols,
            "miss_analysis": miss_analysis,
        }, on_conflict="lesson_date").execute()

        logger.info(f"Saved JP AI lesson for {lesson_date}")
    except Exception as e:
        logger.error(f"Failed to save JP AI lesson: {e}")


def adjust_thresholds_jp(supabase: SupabaseClient, results: dict):
    """
    FEEDBACK LOOP: Analyze performance and adjust thresholds for Japanese stocks.

    This is the core of the closed feedback loop:
    1. Get current thresholds from scoring_config
    2. Check overfitting protection rules
    3. Analyze missed opportunities and picked performance
    4. Calculate optimal threshold adjustment
    5. Update scoring_config if adjustment is warranted
    6. Record change in threshold_history for audit
    """
    if results.get("error"):
        logger.info("No data for threshold adjustment")
        return

    picked = results.get("picked_returns", [])
    not_picked = results.get("not_picked_returns", [])
    missed = results.get("missed_opportunities", [])

    # Get threshold history for overfitting check
    try:
        threshold_history = supabase._client.table("threshold_history").select("*").order(
            "adjustment_date", desc=True
        ).limit(30).execute().data or []
    except Exception as e:
        logger.warning(f"Failed to fetch threshold history: {e}")
        threshold_history = []

    # Get trade count for overfitting check
    try:
        trade_count_result = supabase._client.table("trade_history").select(
            "id", count="exact"
        ).execute()
        total_trades = trade_count_result.count or 0
    except Exception as e:
        logger.warning(f"Failed to fetch trade count: {e}")
        total_trades = 0

    # Process each Japanese strategy separately
    for strategy in JP_STRATEGIES:
        try:
            # Get current config (or create default)
            config = supabase.get_scoring_config(strategy)
            if not config:
                # Create default config for JP strategy
                logger.info(f"Creating default scoring_config for {strategy}")
                default_threshold = 60 if strategy == "jp_conservative" else 75
                supabase._client.table("scoring_config").insert({
                    "strategy_mode": strategy,
                    "threshold": default_threshold,
                    "min_threshold": 40,
                    "max_threshold": 90,
                    "adjustment_step": 2.0,
                }).execute()
                config = {
                    "threshold": default_threshold,
                    "min_threshold": 40,
                    "max_threshold": 90,
                }

            current_threshold = float(config.get("threshold", 60 if "conservative" in strategy else 75))
            min_threshold = float(config.get("min_threshold", 40))
            max_threshold = float(config.get("max_threshold", 90))
            last_adjustment_date = config.get("last_adjustment_date")

            # Filter by strategy
            strategy_picked = [p for p in picked if p.get("strategy") == strategy]
            strategy_not_picked = [p for p in not_picked if p.get("strategy") == strategy]
            strategy_missed = [m for m in missed if m.get("strategy") == strategy]

            # Count data points (stocks with return data)
            data_points = len(strategy_picked) + len(strategy_not_picked)

            # OVERFITTING PROTECTION CHECK
            overfitting_check = check_overfitting_protection(
                strategy_mode=strategy,
                total_trades=total_trades,
                data_points=data_points,
                last_adjustment_date=last_adjustment_date,
                threshold_history=threshold_history,
            )

            # Calculate optimal threshold
            analysis = calculate_optimal_threshold(
                current_threshold=current_threshold,
                missed_opportunities=strategy_missed,
                picked_performance=strategy_picked,
                not_picked_performance=strategy_not_picked,
                strategy_mode=strategy,
                min_threshold=min_threshold,
                max_threshold=max_threshold,
            )

            # Attach overfitting check result to analysis
            analysis.overfitting_check = overfitting_check

            # Log the analysis
            logger.info(format_adjustment_log(analysis))

            # Check overfitting protection FIRST
            if not overfitting_check.can_adjust:
                logger.info(
                    f"THRESHOLD ADJUSTMENT BLOCKED ({strategy}): {overfitting_check.reason}"
                )
                continue

            # Determine if we should apply the adjustment
            if should_apply_adjustment(analysis):
                # Update the threshold
                logger.info(
                    f"APPLYING THRESHOLD CHANGE: {strategy} "
                    f"{current_threshold} -> {analysis.recommended_threshold}"
                )

                supabase.update_threshold(
                    strategy_mode=strategy,
                    new_threshold=analysis.recommended_threshold,
                    reason=analysis.reason,
                )

                # Record in history
                supabase.save_threshold_history(
                    strategy_mode=strategy,
                    old_threshold=current_threshold,
                    new_threshold=analysis.recommended_threshold,
                    reason=analysis.reason,
                    missed_opportunities_count=analysis.missed_count,
                    missed_avg_return=analysis.missed_avg_return,
                    missed_avg_score=analysis.missed_avg_score,
                    picked_count=analysis.picked_count,
                    picked_avg_return=analysis.picked_avg_return,
                    not_picked_count=analysis.not_picked_count,
                    not_picked_avg_return=analysis.not_picked_avg_return,
                    wfe_score=analysis.wfe_score,
                )

                logger.info(f"Threshold change recorded for {strategy}")
            else:
                logger.info(f"No threshold change needed for {strategy}")

        except Exception as e:
            logger.error(f"Failed to adjust threshold for {strategy}: {e}")


def main():
    """Main review pipeline for Japanese stocks."""
    logger.info("=" * 60)
    logger.info("Starting daily review batch for JAPANESE STOCKS")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    logger.info("=" * 60)

    # Start batch logging
    batch_ctx = BatchLogger.start(BatchType.EVENING_REVIEW)

    # Initialize clients
    try:
        yf_client = get_yfinance_client()
        supabase = SupabaseClient()
        llm = get_llm_client()
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        BatchLogger.finish(batch_ctx, error=str(e))
        sys.exit(1)

    # Initialize results in case of unexpected exceptions
    results_5d = {"error": "Not executed"}
    results_1d = {"error": "Not executed"}

    # 1. Calculate returns for ALL Japanese stocks (5-day review)
    logger.info("Step 1: Calculating 5-day returns for ALL scored JP stocks...")
    results_5d = calculate_all_returns_jp(yf_client, supabase, days_ago=5, return_field="5d")

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

    # 2. Also do 1-day review (for faster feedback)
    logger.info("Step 2: Calculating 1-day returns for ALL scored JP stocks...")
    results_1d = calculate_all_returns_jp(yf_client, supabase, days_ago=1, return_field="1d")

    # 3. PAPER TRADING: Evaluate exit signals and close positions
    logger.info("Step 3: Evaluating exit signals for open JP positions...")
    portfolio = PortfolioManager(
        supabase=supabase,
        finnhub=None,  # Not used for JP stocks
        yfinance=yf_client,
    )

    # Get current market regime
    today = datetime.now().strftime("%Y-%m-%d")
    current_regime = supabase.get_market_regime(today)
    market_regime_str = current_regime.get("market_regime") if current_regime else None

    # Get current thresholds for JP strategies
    jp_v1_config = supabase.get_scoring_config("jp_conservative")
    jp_v2_config = supabase.get_scoring_config("jp_aggressive")
    thresholds = {
        "jp_conservative": float(jp_v1_config.get("threshold", 60)) if jp_v1_config else 60,
        "jp_aggressive": float(jp_v2_config.get("threshold", 75)) if jp_v2_config else 75,
    }

    # Get current scores for score-drop exit check (JP only)
    today_scores = []
    for strategy in JP_STRATEGIES:
        try:
            result = supabase._client.table("stock_scores").select("*").eq(
                "batch_date", today
            ).eq(
                "strategy_mode", strategy
            ).execute()
            if result.data:
                today_scores.extend(result.data)
        except Exception as e:
            logger.error(f"Failed to fetch today's scores for {strategy}: {e}")

    current_scores = {s["symbol"]: s.get("composite_score", 0) for s in today_scores}

    # Get all open JP positions
    all_positions = []
    for strategy in JP_STRATEGIES:
        positions = portfolio.get_open_positions(strategy_mode=strategy)
        all_positions.extend(positions)

    logger.info(f"Found {len(all_positions)} open JP positions")

    # Initialize exit_signals in case of exceptions
    exit_signals = []

    if all_positions:
        # Evaluate exit signals
        exit_signals = portfolio.evaluate_exit_signals(
            positions=all_positions,
            current_scores=current_scores if current_scores else None,
            thresholds=thresholds,
            market_regime=market_regime_str,
        )

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
        logger.info("No open JP positions to evaluate")

    # Get Nikkei 225 daily return for benchmark (always track regardless of positions)
    nikkei_daily_pct = yf_client.get_nikkei_daily_return()
    if nikkei_daily_pct is not None:
        logger.info(f"Nikkei 225 daily return: {nikkei_daily_pct:+.2f}%")
    else:
        logger.warning("Could not get Nikkei 225 daily return")

    # Update portfolio snapshots for JP strategies (always update for Nikkei tracking)
    logger.info("Updating JP portfolio snapshots...")
    for strategy in JP_STRATEGIES:
        closed_today = len([s for s in exit_signals if s.position.strategy_mode == strategy]) if exit_signals else 0
        try:
            portfolio.update_portfolio_snapshot(
                strategy_mode=strategy,
                closed_today=closed_today,
                sp500_daily_pct=nikkei_daily_pct,  # Use Nikkei for JP strategies
            )
        except Exception as e:
            logger.error(f"Failed to update snapshot for {strategy}: {e}")

    # 4. Generate AI reflection (focus on 5-day results)
    logger.info("Step 4: Generating AI reflection for JP stocks...")
    if not results_5d.get("error"):
        reflection = generate_reflection_jp(llm, results_5d)
        logger.info(f"Reflection:\n{reflection}")
        missed_opportunities = results_5d.get("missed_opportunities", [])
    else:
        # Fallback: save a placeholder lesson when no 5-day data available
        logger.warning(f"No 5-day data available for JP: {results_5d.get('error')}")
        reflection = f"5日前のデータがまだ蓄積されていないため、本日のパフォーマンス分析はスキップされました。データ蓄積後に詳細な分析が開始されます。（{results_5d.get('error', 'Unknown error')}）"
        missed_opportunities = []

    # 5. Save lesson (always save, even if just a placeholder)
    logger.info("Step 5: Saving JP AI lesson...")
    save_ai_lesson_jp(
        supabase,
        reflection,
        missed_opportunities,
        today,
    )

    # 6. FEEDBACK LOOP: Adjust thresholds based on performance (only if we have data)
    if not results_5d.get("error"):
        logger.info("Step 6: Analyzing and adjusting JP thresholds (FEEDBACK LOOP)...")
        adjust_thresholds_jp(supabase, results_5d)
    else:
        logger.info("Step 6: Skipping JP threshold adjustment (no 5-day data)")

    # 7. Get and log performance summary
    logger.info("Step 7: Getting overall JP performance summary...")
    for strategy in JP_STRATEGIES:
        summary = supabase.get_performance_summary(days=30, strategy_mode=strategy)
        logger.info(f"\n{strategy.upper()} Summary (30 days):")
        logger.info(f"  Picked: {summary.get('picked_count', 0)} stocks, avg return: {summary.get('picked_avg_return', 0):.2f}%")
        logger.info(f"  Not Picked: {summary.get('not_picked_count', 0)} stocks, avg return: {summary.get('not_picked_avg_return', 0):.2f}%")
        logger.info(f"  Missed Opportunities (>3%): {summary.get('missed_opportunities', 0)}")

    logger.info("=" * 60)
    logger.info("Daily review batch for JAPANESE STOCKS completed")
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
