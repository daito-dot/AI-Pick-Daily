"""
Threshold Optimizer Module

Implements Walk-Forward Optimization + UCB-style exploration
to automatically adjust scoring thresholds based on performance.

This is the core of the closed feedback loop:
1. Analyze missed opportunities and picked performance
2. Calculate optimal threshold adjustment
3. Update scoring_config in database
4. Record change in threshold_history for audit

BACKTEST OVERFITTING PROTECTION:
- Minimum trade count before adjustments are allowed
- Cooldown period between adjustments
- Maximum adjustments per month
- All trial counts are logged for transparency

Reference: "The Probability of Backtest Overfitting" (Bailey et al., 2014)
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# === OVERFITTING PROTECTION CONSTANTS ===
# Minimum number of completed trades before allowing threshold adjustments
# Relaxed from 20 to allow early-stage learning while still preventing noise
MIN_TRADES_FOR_ADJUSTMENT = 8

# Minimum days between threshold adjustments (cooldown)
# Prevents rapid oscillation and allows time for evaluation
ADJUSTMENT_COOLDOWN_DAYS = 5

# Maximum adjustments per month to limit "strategy shopping"
MAX_ADJUSTMENTS_PER_MONTH = 4

# Minimum data points (scored stocks with returns) for analysis
# Relaxed from 50 to allow feedback loop to start earlier
MIN_DATA_POINTS = 20


@dataclass
class OverfittingCheck:
    """Result of backtest overfitting protection checks."""
    can_adjust: bool
    reason: str
    total_trades: int
    days_since_last_adjustment: int | None
    adjustments_this_month: int
    data_points: int


@dataclass
class ThresholdAnalysis:
    """Result of threshold analysis."""
    strategy_mode: str
    current_threshold: float
    recommended_threshold: float
    adjustment: float
    reason: str
    # Evidence
    missed_count: int
    missed_avg_return: float
    missed_avg_score: float
    picked_count: int
    picked_avg_return: float
    not_picked_count: int
    not_picked_avg_return: float
    # Validation
    wfe_score: float  # Walk-Forward Efficiency
    # Overfitting protection
    overfitting_check: OverfittingCheck | None = None


def calculate_optimal_threshold(
    current_threshold: float,
    missed_opportunities: list[dict[str, Any]],
    picked_performance: list[dict[str, Any]],
    not_picked_performance: list[dict[str, Any]],
    strategy_mode: str,
    min_threshold: float = 40.0,
    max_threshold: float = 90.0,
) -> ThresholdAnalysis:
    """
    Calculate optimal threshold adjustment using Walk-Forward + UCB concepts.

    Args:
        current_threshold: Current scoring threshold
        missed_opportunities: Stocks not picked but had good returns (>=3%)
        picked_performance: Picked stocks with their returns
        not_picked_performance: All non-picked stocks with their returns
        strategy_mode: 'conservative' or 'aggressive'
        min_threshold: Minimum allowed threshold
        max_threshold: Maximum allowed threshold

    Returns:
        ThresholdAnalysis with recommended adjustment
    """
    # 1. Calculate statistics
    missed_count = len(missed_opportunities)
    picked_count = len(picked_performance)
    not_picked_count = len(not_picked_performance)

    def avg(lst: list, key: str) -> float:
        vals = [item.get(key, 0) or 0 for item in lst]
        return sum(vals) / len(vals) if vals else 0.0

    def avg_score(lst: list) -> float:
        # Handle different key names
        scores = []
        for item in lst:
            score = item.get("score") or item.get("composite_score") or 0
            scores.append(score)
        return sum(scores) / len(scores) if scores else 0.0

    missed_avg_return = avg(missed_opportunities, "return_pct")
    missed_avg_score = avg_score(missed_opportunities)
    picked_avg_return = avg(picked_performance, "return_pct")
    not_picked_avg_return = avg(not_picked_performance, "return_pct")

    # 2. Determine adjustment
    adjustment = 0.0
    reason_parts = []

    # Case 1: Many missed opportunities with scores close to threshold
    if missed_count >= 3 and missed_avg_score > 0:
        gap = current_threshold - missed_avg_score
        if gap <= 10:  # Missed stocks scored within 10 points of threshold
            # Lower threshold to capture these opportunities
            adjustment = -3.0
            reason_parts.append(
                f"見逃し{missed_count}件（平均スコア{missed_avg_score:.0f}、"
                f"閾値との差{gap:.0f}点、平均リターン+{missed_avg_return:.1f}%）"
            )
        elif gap <= 15:
            adjustment = -2.0
            reason_parts.append(
                f"見逃し{missed_count}件（平均スコア{missed_avg_score:.0f}、"
                f"閾値より{gap:.0f}点低い）"
            )

    # Case 2: Picked stocks performing poorly
    if picked_count >= 5 and picked_avg_return < -1.0:
        # Raise threshold to be more selective
        adjustment_for_poor = 2.0
        adjustment = max(adjustment, adjustment_for_poor) if adjustment >= 0 else adjustment + adjustment_for_poor
        reason_parts.append(
            f"推奨銘柄低調（{picked_count}件、平均リターン{picked_avg_return:.1f}%）→厳選強化"
        )

    # Case 3: Picked stocks doing well, few missed opportunities
    if picked_count >= 5 and picked_avg_return >= 2.0 and missed_count <= 1:
        # Current threshold is working well
        if adjustment == 0:
            reason_parts.append(
                f"好調維持（推奨{picked_count}件、平均+{picked_avg_return:.1f}%、見逃し{missed_count}件）"
            )

    # Case 4: Not picking is better than picking (serious problem)
    if picked_count >= 3 and not_picked_count >= 3:
        if not_picked_avg_return > picked_avg_return + 1.0:
            # Non-picked stocks significantly outperforming
            adjustment = -4.0  # Aggressive threshold lowering
            reason_parts.append(
                f"非推奨銘柄が優位（推奨{picked_avg_return:.1f}% vs 非推奨{not_picked_avg_return:.1f}%）"
            )

    # 3. Apply constraints
    # Limit adjustment to ±5 points per cycle
    adjustment = max(-5.0, min(5.0, adjustment))

    # Calculate new threshold
    new_threshold = current_threshold + adjustment

    # Apply range limits based on strategy
    if strategy_mode == "conservative":
        min_t, max_t = 40, 80
    else:  # aggressive
        min_t, max_t = 50, 90

    min_t = max(min_t, min_threshold)
    max_t = min(max_t, max_threshold)

    new_threshold = max(min_t, min(max_t, new_threshold))
    actual_adjustment = new_threshold - current_threshold

    # Build reason string
    if not reason_parts:
        reason = "変更なし（データ不足または現状維持）"
    else:
        reason = "; ".join(reason_parts)

    # 4. Calculate Walk-Forward Efficiency (WFE)
    # WFE = expected_return_after / expected_return_before
    # Simplified: if we expect better capture of missed opportunities, WFE > 1
    if actual_adjustment < 0 and missed_count > 0:
        # Lowering threshold should capture more opportunities
        # Estimate: we'd capture ~60% of missed opportunities
        potential_gain = missed_avg_return * missed_count * 0.6
        # Risk: we might also pick more losers
        potential_loss = abs(actual_adjustment) * 0.1 * 5  # rough estimate
        wfe_score = (potential_gain / (potential_loss + 0.1)) * 50  # normalize to ~50-100 range
    elif actual_adjustment > 0:
        # Raising threshold should reduce losses
        if picked_avg_return < 0:
            wfe_score = 70.0  # Good to be more selective when losing
        else:
            wfe_score = 50.0  # Neutral
    else:
        wfe_score = 60.0  # No change, neutral

    wfe_score = max(0, min(100, wfe_score))

    return ThresholdAnalysis(
        strategy_mode=strategy_mode,
        current_threshold=current_threshold,
        recommended_threshold=new_threshold,
        adjustment=actual_adjustment,
        reason=reason,
        missed_count=missed_count,
        missed_avg_return=missed_avg_return,
        missed_avg_score=missed_avg_score,
        picked_count=picked_count,
        picked_avg_return=picked_avg_return,
        not_picked_count=not_picked_count,
        not_picked_avg_return=not_picked_avg_return,
        wfe_score=wfe_score,
    )


def should_apply_adjustment(analysis: ThresholdAnalysis) -> bool:
    """
    Determine if the threshold adjustment should be applied.

    Uses WFE (Walk-Forward Efficiency) as the key criterion.
    WFE > 50 means the change is expected to improve performance.
    """
    # Don't apply if no change
    if analysis.adjustment == 0:
        return False

    # Apply if WFE is above threshold
    if analysis.wfe_score >= 50:
        return True

    # Additional safety check: don't apply if very low confidence
    if analysis.wfe_score < 30:
        logger.warning(
            f"Threshold adjustment rejected (WFE={analysis.wfe_score:.1f} < 30): "
            f"{analysis.strategy_mode} {analysis.current_threshold} -> {analysis.recommended_threshold}"
        )
        return False

    # Borderline case (30-50): apply only if there are clear missed opportunities
    if analysis.missed_count >= 5 and analysis.adjustment < 0:
        return True

    return False


def format_adjustment_log(analysis: ThresholdAnalysis) -> str:
    """Format threshold analysis for logging."""
    lines = [
        f"\n{'='*50}",
        f"THRESHOLD ANALYSIS: {analysis.strategy_mode.upper()}",
        f"{'='*50}",
        f"Current Threshold: {analysis.current_threshold}",
        f"Recommended: {analysis.recommended_threshold} ({analysis.adjustment:+.0f})",
        f"WFE Score: {analysis.wfe_score:.1f}%",
        f"",
        f"Evidence:",
        f"  - Missed Opportunities: {analysis.missed_count}",
        f"    Avg Score: {analysis.missed_avg_score:.1f}, Avg Return: +{analysis.missed_avg_return:.1f}%",
        f"  - Picked Stocks: {analysis.picked_count}",
        f"    Avg Return: {analysis.picked_avg_return:+.1f}%",
        f"  - Not Picked: {analysis.not_picked_count}",
        f"    Avg Return: {analysis.not_picked_avg_return:+.1f}%",
    ]

    # Add overfitting protection status
    if analysis.overfitting_check:
        check = analysis.overfitting_check
        lines.extend([
            f"",
            f"Overfitting Protection:",
            f"  - Total Trades: {check.total_trades} (min: {MIN_TRADES_FOR_ADJUSTMENT})",
            f"  - Data Points: {check.data_points} (min: {MIN_DATA_POINTS})",
            f"  - Days Since Last Adjustment: {check.days_since_last_adjustment or 'N/A'} (cooldown: {ADJUSTMENT_COOLDOWN_DAYS})",
            f"  - Adjustments This Month: {check.adjustments_this_month} (max: {MAX_ADJUSTMENTS_PER_MONTH})",
            f"  - Can Adjust: {'YES' if check.can_adjust else 'NO'} ({check.reason})",
        ])

    lines.extend([
        f"",
        f"Reason: {analysis.reason}",
        f"{'='*50}",
    ])
    return "\n".join(lines)


def check_overfitting_protection(
    strategy_mode: str,
    total_trades: int,
    data_points: int,
    last_adjustment_date: str | None,
    threshold_history: list[dict[str, Any]],
) -> OverfittingCheck:
    """
    Check if threshold adjustment is allowed based on overfitting protection rules.

    This implements safeguards from "The Probability of Backtest Overfitting":
    - Require minimum sample size before adjustments
    - Cooldown period between adjustments
    - Limit total adjustments to prevent "strategy shopping"

    Args:
        strategy_mode: 'conservative' or 'aggressive'
        total_trades: Number of completed trades
        data_points: Number of scored stocks with return data
        last_adjustment_date: Date of last threshold change (YYYY-MM-DD)
        threshold_history: Recent threshold changes

    Returns:
        OverfittingCheck with can_adjust flag and reason
    """
    today = datetime.now().date()

    # Calculate days since last adjustment
    days_since_last = None
    if last_adjustment_date:
        try:
            last_date = datetime.strptime(last_adjustment_date, "%Y-%m-%d").date()
            days_since_last = (today - last_date).days
        except (ValueError, TypeError):
            pass

    # Count adjustments this month
    month_start = today.replace(day=1)
    adjustments_this_month = sum(
        1 for h in threshold_history
        if h.get("strategy_mode") == strategy_mode
        and h.get("adjustment_date")
        and datetime.strptime(h["adjustment_date"], "%Y-%m-%d").date() >= month_start
    )

    # Check rules in order of priority
    reasons = []

    # Rule 1: Minimum trades
    if total_trades < MIN_TRADES_FOR_ADJUSTMENT:
        reasons.append(
            f"トレード数不足（{total_trades}/{MIN_TRADES_FOR_ADJUSTMENT}）"
        )

    # Rule 2: Minimum data points
    if data_points < MIN_DATA_POINTS:
        reasons.append(
            f"データ不足（{data_points}/{MIN_DATA_POINTS}）"
        )

    # Rule 3: Cooldown period
    if days_since_last is not None and days_since_last < ADJUSTMENT_COOLDOWN_DAYS:
        reasons.append(
            f"クールダウン中（{days_since_last}/{ADJUSTMENT_COOLDOWN_DAYS}日）"
        )

    # Rule 4: Monthly limit
    if adjustments_this_month >= MAX_ADJUSTMENTS_PER_MONTH:
        reasons.append(
            f"月間上限到達（{adjustments_this_month}/{MAX_ADJUSTMENTS_PER_MONTH}回）"
        )

    can_adjust = len(reasons) == 0
    reason = "調整可能" if can_adjust else "; ".join(reasons)

    return OverfittingCheck(
        can_adjust=can_adjust,
        reason=reason,
        total_trades=total_trades,
        days_since_last_adjustment=days_since_last,
        adjustments_this_month=adjustments_this_month,
        data_points=data_points,
    )
