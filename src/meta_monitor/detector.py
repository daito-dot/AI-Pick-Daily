"""Degradation detection: compute rolling metrics and detect performance drops."""

import logging
from datetime import datetime, timedelta, timezone

from .models import RollingMetrics, DegradationSignal
from .parameters import get_parameter

logger = logging.getLogger(__name__)

# Fallback detection thresholds (used when DB unavailable)
WIN_RATE_DROP_RATIO = 0.7
RETURN_DECLINE_THRESHOLD = -1.0
MISSED_SPIKE_THRESHOLD = 0.30
CONFIDENCE_DRIFT_THRESHOLD = 0.05
MIN_JUDGMENTS_FOR_DETECTION = 5


def compute_rolling_metrics(supabase, strategy_mode: str) -> RollingMetrics:
    """Compute 7d and 30d rolling performance metrics from judgment data.

    Queries judgment_outcomes JOIN judgment_records for win rates
    and average returns. Caches result to performance_rolling_metrics.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    metrics_7d = _compute_window_metrics(supabase, strategy_mode, days=7)
    metrics_30d = _compute_window_metrics(supabase, strategy_mode, days=30)
    missed_rate_7d = _compute_missed_rate(supabase, strategy_mode, days=7)
    confidence_7d = _compute_avg_confidence(supabase, strategy_mode, days=7)
    confidence_30d = _compute_avg_confidence(supabase, strategy_mode, days=30)

    metrics = RollingMetrics(
        strategy_mode=strategy_mode,
        metric_date=today,
        win_rate_7d=metrics_7d["win_rate"],
        win_rate_30d=metrics_30d["win_rate"],
        avg_return_7d=metrics_7d["avg_return"],
        avg_return_30d=metrics_30d["avg_return"],
        missed_rate_7d=missed_rate_7d,
        total_judgments_7d=metrics_7d["total"],
        total_judgments_30d=metrics_30d["total"],
        avg_confidence_7d=confidence_7d,
        avg_confidence_30d=confidence_30d,
    )

    # Cache to DB
    _save_metrics(supabase, metrics)

    return metrics


def _compute_window_metrics(supabase, strategy_mode: str, days: int) -> dict:
    """Compute win rate and avg return for a time window."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        rows = (
            supabase._client.table("judgment_outcomes")
            .select(
                "actual_return_5d, outcome_aligned, "
                "judgment_records!inner(symbol, strategy_mode, decision, batch_date)"
            )
            .gte("outcome_date", cutoff)
            .execute()
            .data
            or []
        )

        # Filter by strategy
        rows = [
            r
            for r in rows
            if r.get("judgment_records", {}).get("strategy_mode") == strategy_mode
        ]

        if not rows:
            return {"win_rate": None, "avg_return": None, "total": 0}

        # Only count buy decisions for win rate
        buys = [r for r in rows if r["judgment_records"]["decision"] == "buy"]
        returns = [
            r["actual_return_5d"]
            for r in buys
            if r.get("actual_return_5d") is not None
        ]

        if not returns:
            return {"win_rate": None, "avg_return": None, "total": len(rows)}

        wins = [r for r in returns if r >= 0]
        win_rate = len(wins) / len(returns) * 100 if returns else None
        avg_return = sum(returns) / len(returns) if returns else None

        return {
            "win_rate": round(win_rate, 1) if win_rate is not None else None,
            "avg_return": round(avg_return, 2) if avg_return is not None else None,
            "total": len(rows),
        }

    except Exception as e:
        logger.warning(f"Failed to compute {days}d metrics for {strategy_mode}: {e}")
        return {"win_rate": None, "avg_return": None, "total": 0}


def _compute_missed_rate(supabase, strategy_mode: str, days: int) -> float | None:
    """Compute missed opportunity rate: % of avoid decisions where stock rose >3%."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        rows = (
            supabase._client.table("judgment_outcomes")
            .select(
                "actual_return_5d, "
                "judgment_records!inner(strategy_mode, decision, batch_date)"
            )
            .gte("outcome_date", cutoff)
            .execute()
            .data
            or []
        )

        avoids = [
            r
            for r in rows
            if r.get("judgment_records", {}).get("strategy_mode") == strategy_mode
            and r["judgment_records"]["decision"] == "avoid"
            and r.get("actual_return_5d") is not None
        ]

        if not avoids:
            return None

        missed = [r for r in avoids if r["actual_return_5d"] > 3.0]
        return round(len(missed) / len(avoids) * 100, 1)

    except Exception as e:
        logger.warning(f"Failed to compute missed rate for {strategy_mode}: {e}")
        return None


def _compute_avg_confidence(supabase, strategy_mode: str, days: int) -> float | None:
    """Compute average AI confidence score for a time window."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        rows = (
            supabase._client.table("judgment_records")
            .select("confidence")
            .eq("strategy_mode", strategy_mode)
            .gte("batch_date", cutoff)
            .not_.is_("confidence", "null")
            .execute()
            .data
            or []
        )

        if not rows:
            return None

        values = [float(r["confidence"]) for r in rows if r.get("confidence") is not None]
        if not values:
            return None

        return round(sum(values) / len(values), 3)

    except Exception as e:
        logger.warning(f"Failed to compute avg confidence for {strategy_mode}: {e}")
        return None


def _save_metrics(supabase, metrics: RollingMetrics) -> None:
    """Cache rolling metrics to DB with upsert."""
    try:
        supabase._client.table("performance_rolling_metrics").upsert(
            {
                "strategy_mode": metrics.strategy_mode,
                "metric_date": metrics.metric_date,
                "win_rate_7d": metrics.win_rate_7d,
                "win_rate_30d": metrics.win_rate_30d,
                "avg_return_7d": metrics.avg_return_7d,
                "avg_return_30d": metrics.avg_return_30d,
                "missed_rate_7d": metrics.missed_rate_7d,
                "total_judgments_7d": metrics.total_judgments_7d,
                "total_judgments_30d": metrics.total_judgments_30d,
                "avg_confidence_7d": metrics.avg_confidence_7d,
                "avg_confidence_30d": metrics.avg_confidence_30d,
            },
            on_conflict="strategy_mode,metric_date",
        ).execute()
    except Exception as e:
        logger.warning(f"Failed to save rolling metrics: {e}")


def detect_degradation(
    metrics: RollingMetrics, supabase=None
) -> list[DegradationSignal]:
    """Detect performance degradation from rolling metrics.

    Returns list of signals; empty list means no degradation.
    If supabase is provided, reads thresholds from DB; otherwise uses fallback constants.
    """
    signals: list[DegradationSignal] = []

    # Load thresholds from DB (with fallback to module constants)
    if supabase:
        sm = metrics.strategy_mode
        win_rate_drop_ratio = get_parameter(supabase, sm, "win_rate_drop_ratio")
        return_decline_threshold = get_parameter(supabase, sm, "return_decline_threshold")
        missed_spike_threshold = get_parameter(supabase, sm, "missed_spike_threshold")
        confidence_drift_threshold = get_parameter(supabase, sm, "confidence_drift_threshold")
    else:
        win_rate_drop_ratio = WIN_RATE_DROP_RATIO
        return_decline_threshold = RETURN_DECLINE_THRESHOLD
        missed_spike_threshold = MISSED_SPIKE_THRESHOLD
        confidence_drift_threshold = CONFIDENCE_DRIFT_THRESHOLD

    # Skip if insufficient data
    if metrics.total_judgments_7d < MIN_JUDGMENTS_FOR_DETECTION:
        logger.info(
            f"Insufficient data for {metrics.strategy_mode}: "
            f"{metrics.total_judgments_7d} judgments in 7d (need {MIN_JUDGMENTS_FOR_DETECTION})"
        )
        return signals

    # 1. Win rate drop: 7d significantly below 30d baseline
    if (
        metrics.win_rate_7d is not None
        and metrics.win_rate_30d is not None
        and metrics.win_rate_30d > 0
    ):
        ratio = metrics.win_rate_7d / metrics.win_rate_30d
        if ratio < win_rate_drop_ratio:
            signals.append(
                DegradationSignal(
                    trigger_type="win_rate_drop",
                    severity="warning",
                    current_value=metrics.win_rate_7d,
                    baseline_value=metrics.win_rate_30d,
                    details=(
                        f"7d win rate ({metrics.win_rate_7d:.1f}%) is "
                        f"{(1 - ratio) * 100:.0f}% below 30d baseline ({metrics.win_rate_30d:.1f}%)"
                    ),
                )
            )

    # 2. Return decline: 7d average return is negative
    if metrics.avg_return_7d is not None and metrics.avg_return_7d < return_decline_threshold:
        signals.append(
            DegradationSignal(
                trigger_type="return_decline",
                severity="warning",
                current_value=metrics.avg_return_7d,
                baseline_value=return_decline_threshold,
                details=(
                    f"7d avg return ({metrics.avg_return_7d:.2f}%) "
                    f"below threshold ({return_decline_threshold}%)"
                ),
            )
        )

    # 3. Missed spike: too many profitable stocks being avoided
    if metrics.missed_rate_7d is not None and metrics.missed_rate_7d > missed_spike_threshold * 100:
        signals.append(
            DegradationSignal(
                trigger_type="missed_spike",
                severity="warning",
                current_value=metrics.missed_rate_7d,
                baseline_value=missed_spike_threshold * 100,
                details=(
                    f"7d missed rate ({metrics.missed_rate_7d:.1f}%) "
                    f"exceeds threshold ({missed_spike_threshold * 100:.0f}%)"
                ),
            )
        )

    # 4. Confidence drift: significant divergence between 7d and 30d avg confidence
    if (
        metrics.avg_confidence_7d is not None
        and metrics.avg_confidence_30d is not None
    ):
        drift = abs(metrics.avg_confidence_7d - metrics.avg_confidence_30d)
        if drift > confidence_drift_threshold:
            direction = "上昇" if metrics.avg_confidence_7d > metrics.avg_confidence_30d else "低下"
            signals.append(
                DegradationSignal(
                    trigger_type="confidence_drift",
                    severity="warning",
                    current_value=metrics.avg_confidence_7d,
                    baseline_value=metrics.avg_confidence_30d,
                    details=(
                        f"Confidence drift detected: 7d avg ({metrics.avg_confidence_7d:.3f}) vs "
                        f"30d avg ({metrics.avg_confidence_30d:.3f}), "
                        f"差分 {drift:.3f} ({direction})"
                    ),
                )
            )

    # Upgrade to critical if multiple signals
    if len(signals) >= 2:
        for s in signals:
            s.severity = "critical"

    return signals


def check_cooldown(supabase, strategy_mode: str) -> bool:
    """Check if strategy is in cooldown period. Returns True if in cooldown."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        rows = (
            supabase._client.table("meta_interventions")
            .select("cooldown_until")
            .eq("strategy_mode", strategy_mode)
            .gt("cooldown_until", now)
            .order("intervention_date", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        return len(rows) > 0
    except Exception as e:
        logger.warning(f"Failed to check cooldown for {strategy_mode}: {e}")
        return True  # Conservative: assume cooldown active on error


def count_monthly_interventions(supabase, strategy_mode: str) -> int:
    """Count interventions in the current month."""
    try:
        month_start = datetime.now(timezone.utc).replace(day=1).strftime("%Y-%m-%d")
        rows = (
            supabase._client.table("meta_interventions")
            .select("id", count="exact")
            .eq("strategy_mode", strategy_mode)
            .gte("intervention_date", month_start)
            .execute()
        )
        return rows.count or 0
    except Exception as e:
        logger.warning(f"Failed to count monthly interventions: {e}")
        return 999  # Conservative: assume limit reached on error
