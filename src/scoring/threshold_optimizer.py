"""
Threshold Optimizer Module

Implements Walk-Forward Optimization + UCB-style exploration
to automatically adjust scoring thresholds based on performance.

This is the core of the closed feedback loop:
1. Analyze missed opportunities and picked performance
2. Calculate optimal threshold adjustment
3. Update scoring_config in database
4. Record change in threshold_history for audit
"""
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


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
        f"",
        f"Reason: {analysis.reason}",
        f"{'='*50}",
    ]
    return "\n".join(lines)
