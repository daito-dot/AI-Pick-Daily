"""Shared review pipeline functions for US and JP markets.

Extracts duplicated threshold adjustment logic from
daily_review.py and daily_review_jp.py.
"""
import logging
from datetime import datetime, timedelta, timezone

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
        else:  # "skip", legacy "avoid", legacy "hold"
            outcome_aligned = return_pct < 0

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


def get_unprocessed_outcome_dates(
    supabase,
    return_field: str = "5d",
    lookback_days: int = 14,
    min_age_days: int = 5,
) -> list[str]:
    """Find batch_dates that have judgment_records but missing outcomes.

    Searches for judgment records old enough to have measurable returns
    but lacking the specified outcome field. Used to backfill missed
    review runs.

    Args:
        supabase: Supabase client
        return_field: "1d" or "5d"
        lookback_days: How far back to search
        min_age_days: Minimum age before expecting outcomes

    Returns:
        Sorted list of batch_date strings needing outcome processing
    """
    try:
        today = datetime.now(timezone.utc).date()
        cutoff_recent = (today - timedelta(days=min_age_days)).isoformat()
        cutoff_old = (today - timedelta(days=lookback_days)).isoformat()

        result = supabase._client.table("judgment_records").select(
            "id, batch_date, judgment_outcomes(actual_return_1d, actual_return_5d)"
        ).gte(
            "batch_date", cutoff_old
        ).lte(
            "batch_date", cutoff_recent
        ).execute()

        rows = result.data or []
        return_col = f"actual_return_{return_field}"

        missing_dates = set()
        for row in rows:
            outcomes = row.get("judgment_outcomes", [])
            if not outcomes or not any(
                o.get(return_col) is not None for o in outcomes
            ):
                missing_dates.add(row["batch_date"])

        result_dates = sorted(missing_dates)
        if result_dates:
            logger.info(
                f"Found {len(result_dates)} unprocessed outcome dates "
                f"({return_field}): {result_dates}"
            )
        return result_dates

    except Exception as e:
        logger.warning(f"Failed to query unprocessed outcome dates: {e}")
        return []


def check_batch_gap(supabase, market_type: str = "us") -> int | None:
    """Check for gaps in batch execution and log warnings.

    Args:
        supabase: Supabase client
        market_type: "us" or "jp" (used in log messages only)

    Returns:
        Number of days since last successful batch, or None if no history
    """
    try:
        result = supabase._client.table("batch_execution_logs").select(
            "started_at, status"
        ).eq(
            "batch_type", "evening_review"
        ).in_(
            "status", ["success", "partial_success"]
        ).order(
            "started_at", desc=True
        ).limit(1).execute()

        if not result.data:
            return None

        last_run = datetime.fromisoformat(
            result.data[0]["started_at"].replace("Z", "+00:00")
        ).date()
        today = datetime.now(timezone.utc).date()
        gap_days = (today - last_run).days

        if gap_days > 1:
            logger.warning(
                f"BATCH GAP DETECTED ({market_type}): {gap_days} days since "
                f"last successful run on {last_run}"
            )

        return gap_days

    except Exception as e:
        logger.warning(f"Failed to check batch gap: {e}")
        return None


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


def build_performance_stats(supabase, strategy_mode: str, days: int = 30) -> dict:
    """Aggregate judgment performance into structured data for prompt injection.

    Focuses on buy accuracy only (avoid/hold tracking removed — LLM now does
    risk assessment, not buy/avoid decisions).

    Returns dict with buy win rate and average return.
    Returns empty dict if insufficient data.
    """
    try:
        cutoff = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")
        rows = supabase._client.table("judgment_outcomes").select(
            "actual_return_5d, outcome_aligned, "
            "judgment_records!inner(symbol, strategy_mode, decision, batch_date)"
        ).gte("outcome_date", cutoff).execute().data or []

        rows = [r for r in rows if r.get("judgment_records", {}).get("strategy_mode") == strategy_mode]

        if len(rows) < 5:
            return {}

        buys = [r for r in rows if r["judgment_records"]["decision"] == "buy"]

        stats: dict = {}

        if buys:
            buy_returns = [r["actual_return_5d"] for r in buys if r.get("actual_return_5d") is not None]
            buy_wins = [r for r in buy_returns if r >= 0]
            stats["buy_count"] = len(buy_returns)
            stats["buy_win_count"] = len(buy_wins)
            stats["buy_win_rate"] = round(len(buy_wins) / len(buy_returns) * 100, 1) if buy_returns else 0
            stats["buy_avg_return"] = round(sum(buy_returns) / len(buy_returns), 2) if buy_returns else 0

        logger.info(f"Built performance stats for {strategy_mode}: {len(rows)} outcomes, {len(buys)} buys")
        return stats

    except Exception as e:
        logger.warning(f"Failed to build performance stats for {strategy_mode}: {e}")
        return {}


def build_recent_mistakes(supabase, strategy_mode: str, days: int = 3) -> list[dict]:
    """Fetch recent buy recommendations that dropped next day.

    Returns the worst recent mistakes for injection into the risk assessment
    prompt, enabling immediate learning from failures.

    Args:
        supabase: Supabase client
        strategy_mode: Strategy to filter by
        days: How many days back to look

    Returns:
        List of mistake dicts with symbol, batch_date, return_1d, confidence
    """
    try:
        cutoff = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")
        rows = supabase._client.table("judgment_outcomes").select(
            "actual_return_1d, "
            "judgment_records!inner(symbol, strategy_mode, decision, batch_date, confidence, reasoning)"
        ).gte("outcome_date", cutoff).not_.is_("actual_return_1d", "null").execute().data or []

        rows = [
            r for r in rows
            if r.get("judgment_records", {}).get("strategy_mode") == strategy_mode
            and r["judgment_records"]["decision"] == "buy"
            and r.get("actual_return_1d") is not None
            and r["actual_return_1d"] < -2.0
        ]

        rows.sort(key=lambda r: r["actual_return_1d"])

        mistakes = []
        for r in rows[:3]:
            jr = r["judgment_records"]
            reasoning = jr.get("reasoning") or {}
            summary = ""
            if isinstance(reasoning, dict):
                steps = reasoning.get("steps", [])
                summary = steps[0][:100] if steps else ""
            mistakes.append({
                "symbol": jr["symbol"],
                "batch_date": jr["batch_date"],
                "return_1d": round(r["actual_return_1d"], 2),
                "confidence": jr.get("confidence", 0),
                "reasoning_summary": summary,
            })

        if mistakes:
            logger.info(f"Found {len(mistakes)} recent mistakes for {strategy_mode}")
        return mistakes

    except Exception as e:
        logger.warning(f"Failed to build recent mistakes for {strategy_mode}: {e}")
        return []


# === Factor Weight Constants ===
WEIGHT_MIN = 0.05
WEIGHT_MAX = 0.60
WEIGHT_MAX_DELTA = 0.05  # Max change per adjustment cycle

V1_FACTOR_KEYS = ["trend", "momentum", "value", "sentiment"]
V2_FACTOR_KEYS = ["momentum_12_1", "breakout", "catalyst", "risk_adjusted"]


def adjust_factor_weights(
    supabase,
    strategy_mode: str,
    days: int = 30,
) -> None:
    """Adjust rule-based scoring factor weights based on outcome correlations.

    For each factor, measure correlation between high factor score and positive
    returns. Increase weight of predictive factors, decrease non-predictive ones.
    No LLM involved — pure statistical adjustment.

    Uses same overfitting protection as threshold adjustment.
    """
    is_v2 = "aggressive" in strategy_mode
    factor_keys = V2_FACTOR_KEYS if is_v2 else V1_FACTOR_KEYS

    try:
        # Get trade count for overfitting check
        trade_count_result = supabase._client.table("trade_history").select(
            "id", count="exact"
        ).execute()
        total_trades = trade_count_result.count or 0

        if total_trades < 8:
            logger.info(f"Factor weight adjustment skipped ({strategy_mode}): only {total_trades} trades")
            return

        # Get stock_scores with returns for the last N days
        cutoff = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")
        scores_data = supabase._client.table("stock_scores").select(
            "symbol, strategy_mode, composite_score, trend_score, momentum_score, "
            "value_score, sentiment_score, momentum_12_1_score, breakout_score, "
            "catalyst_score, risk_adjusted_score, return_5d"
        ).eq("strategy_mode", strategy_mode
        ).gte("batch_date", cutoff
        ).not_.is_("return_5d", "null"
        ).execute().data or []

        if len(scores_data) < 20:
            logger.info(f"Factor weight adjustment skipped ({strategy_mode}): only {len(scores_data)} data points")
            return

        # Calculate correlation: for each factor, compare avg return when factor is above/below median
        factor_effectiveness: dict[str, float] = {}
        for factor_key in factor_keys:
            score_col = f"{factor_key}_score"
            values = [(row.get(score_col, 50), row.get("return_5d", 0)) for row in scores_data if row.get(score_col) is not None]
            if len(values) < 10:
                continue

            scores_arr = [v[0] for v in values]
            median_score = sorted(scores_arr)[len(scores_arr) // 2]

            above = [v[1] for v in values if v[0] >= median_score]
            below = [v[1] for v in values if v[0] < median_score]

            if above and below:
                avg_above = sum(above) / len(above)
                avg_below = sum(below) / len(below)
                # Effectiveness = how much return difference the factor creates
                factor_effectiveness[factor_key] = avg_above - avg_below
            else:
                factor_effectiveness[factor_key] = 0.0

        if not factor_effectiveness:
            logger.info(f"No factor effectiveness data for {strategy_mode}")
            return

        # Get current weights from DB or use defaults
        config = supabase.get_scoring_config(strategy_mode)
        current_weights: dict[str, float] = {}
        if config and config.get("factor_weights"):
            current_weights = config["factor_weights"]
        else:
            if is_v2:
                current_weights = {"momentum_12_1": 0.40, "breakout": 0.25, "catalyst": 0.20, "risk_adjusted": 0.15}
            else:
                current_weights = {"trend": 0.35, "momentum": 0.35, "value": 0.20, "sentiment": 0.10}

        # Adjust weights based on effectiveness
        total_effectiveness = sum(max(v, 0.01) for v in factor_effectiveness.values())
        if total_effectiveness <= 0:
            logger.info(f"All factors equally ineffective for {strategy_mode}, no adjustment")
            return

        new_weights: dict[str, float] = {}
        for key in factor_keys:
            eff = max(factor_effectiveness.get(key, 0), 0.01)
            target = eff / total_effectiveness  # Proportional to effectiveness
            current = current_weights.get(key, 1.0 / len(factor_keys))

            # Limit change per cycle
            delta = max(-WEIGHT_MAX_DELTA, min(WEIGHT_MAX_DELTA, target - current))
            new_weight = max(WEIGHT_MIN, min(WEIGHT_MAX, current + delta))
            new_weights[key] = new_weight

        # Normalize to sum=1.0
        weight_sum = sum(new_weights.values())
        new_weights = {k: round(v / weight_sum, 4) for k, v in new_weights.items()}

        # Check if any meaningful change
        max_change = max(abs(new_weights.get(k, 0) - current_weights.get(k, 0)) for k in factor_keys)
        if max_change < 0.005:
            logger.info(f"Factor weights unchanged for {strategy_mode} (max delta: {max_change:.4f})")
            return

        # Save to DB
        supabase._client.table("scoring_config").update({
            "factor_weights": new_weights,
        }).eq("strategy_mode", strategy_mode).execute()

        logger.info(
            f"FACTOR WEIGHTS UPDATED ({strategy_mode}): "
            f"{current_weights} -> {new_weights} "
            f"(effectiveness: {factor_effectiveness})"
        )

    except Exception as e:
        logger.error(f"Failed to adjust factor weights for {strategy_mode}: {e}")
