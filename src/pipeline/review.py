"""Shared review pipeline functions for US and JP markets.

Extracts duplicated threshold adjustment logic from
daily_review.py and daily_review_jp.py.
"""
import logging
from datetime import datetime, timezone

from src.scoring.threshold_optimizer import (
    calculate_optimal_threshold,
    should_apply_adjustment,
    format_adjustment_log,
    check_overfitting_protection,
)

logger = logging.getLogger(__name__)


def populate_judgment_outcomes(
    supabase,
    results: dict,
    return_field: str = "5d",
) -> int:
    """Record outcomes for judgment_records based on calculated returns.

    Links the return data from calculate_all_returns back to the
    corresponding judgment_records, closing the feedback loop for
    the reflection service.

    Args:
        supabase: Supabase client
        results: Return calculation results from calculate_all_returns
        return_field: "1d" or "5d"

    Returns:
        Number of judgment outcomes saved
    """
    if results.get("error"):
        return 0

    check_date = results.get("date")
    if not check_date:
        return 0

    # Build lookup: (symbol, strategy) -> return_pct
    return_lookup: dict[tuple[str, str], float] = {}
    for r in results.get("picked_returns", []) + results.get("not_picked_returns", []):
        return_lookup[(r["symbol"], r["strategy"])] = r["return_pct"]

    if not return_lookup:
        return 0

    # Get judgment records for check_date
    try:
        judgments = supabase.get_judgment_records(batch_date=check_date)
    except Exception as e:
        logger.warning(f"Failed to fetch judgment records for {check_date}: {e}")
        return 0

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    saved = 0

    for j in judgments:
        symbol = j.get("symbol")
        strategy = j.get("strategy_mode")
        judgment_id = j.get("id")
        decision = j.get("decision", "hold")

        return_pct = return_lookup.get((symbol, strategy))
        if return_pct is None or not judgment_id:
            continue

        # Determine outcome alignment
        if decision == "buy":
            outcome_aligned = return_pct >= 0
        elif decision == "avoid":
            outcome_aligned = return_pct < 0
        else:  # hold
            outcome_aligned = abs(return_pct) < 3.0

        kwargs: dict = {
            "judgment_id": judgment_id,
            "outcome_date": today,
            "outcome_aligned": outcome_aligned,
        }
        if return_field == "1d":
            kwargs["actual_return_1d"] = return_pct
        else:
            kwargs["actual_return_5d"] = return_pct

        try:
            supabase.save_judgment_outcome(**kwargs)
            saved += 1
        except Exception as e:
            logger.warning(f"Failed to save judgment outcome for {symbol}: {e}")

    logger.info(f"Saved {saved} judgment outcomes ({return_field}) for {check_date}")
    return saved


def adjust_thresholds_for_strategies(
    supabase,
    results: dict,
    strategies: list[str],
    create_default_config: bool = False,
) -> None:
    """Analyze performance and adjust thresholds for given strategies.

    This is the core feedback loop, shared between US and JP:
    1. Get current thresholds from scoring_config
    2. Check overfitting protection rules
    3. Calculate optimal threshold adjustment
    4. Update scoring_config if warranted
    5. Record in threshold_history for audit

    Args:
        supabase: Supabase client
        results: Return calculation results with picked_returns, not_picked_returns, missed_opportunities
        strategies: List of strategy modes to process (e.g., ["conservative", "aggressive"])
        create_default_config: If True, create default config when missing (JP behavior)
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

    for strategy in strategies:
        try:
            config = supabase.get_scoring_config(strategy)
            if not config:
                if create_default_config:
                    logger.info(f"Creating default scoring_config for {strategy}")
                    default_threshold = 60 if "conservative" in strategy else 75
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
                else:
                    logger.warning(f"No scoring_config found for {strategy}, skipping")
                    continue

            current_threshold = float(config.get("threshold", 60 if "conservative" in strategy else 75))
            min_threshold = float(config.get("min_threshold", 40))
            max_threshold = float(config.get("max_threshold", 90))
            last_adjustment_date = config.get("last_adjustment_date")

            # Filter by strategy
            strategy_picked = [p for p in picked if p.get("strategy") == strategy]
            strategy_not_picked = [p for p in not_picked if p.get("strategy") == strategy]
            strategy_missed = [m for m in missed if m.get("strategy") == strategy]

            data_points = len(strategy_picked) + len(strategy_not_picked)

            # Overfitting protection check
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

            analysis.overfitting_check = overfitting_check
            logger.info(format_adjustment_log(analysis))

            if not overfitting_check.can_adjust:
                logger.info(
                    f"THRESHOLD ADJUSTMENT BLOCKED ({strategy}): {overfitting_check.reason}"
                )
                continue

            if should_apply_adjustment(analysis):
                logger.info(
                    f"APPLYING THRESHOLD CHANGE: {strategy} "
                    f"{current_threshold} -> {analysis.recommended_threshold}"
                )

                supabase.update_threshold(
                    strategy_mode=strategy,
                    new_threshold=analysis.recommended_threshold,
                    reason=analysis.reason,
                )

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
