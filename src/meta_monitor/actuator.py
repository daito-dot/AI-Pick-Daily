"""Execute meta-monitor actions and evaluate past interventions."""

import json
import logging
from datetime import datetime, timedelta, timezone

from .models import Diagnosis, InterventionResult, RollingMetrics

logger = logging.getLogger(__name__)

# Safety limits
MAX_THRESHOLD_CHANGE = 10
MAX_WEIGHT_CHANGE = 0.1
MAX_PROMPT_LENGTH = 500
PROMPT_EXPIRY_DAYS = 14
COOLDOWN_DAYS = 3
ROLLBACK_THRESHOLD = -2.0  # effectiveness_score below this triggers rollback


def execute_actions(
    supabase,
    diagnosis: Diagnosis,
    strategy_mode: str,
    metrics: RollingMetrics,
) -> InterventionResult:
    """Execute recommended actions from diagnosis with safety limits.

    Records intervention in meta_interventions table and sets cooldown.
    """
    actions_taken = []
    pre_metrics = metrics.to_dict()

    for action in diagnosis.recommended_actions:
        action_type = action.get("type")

        try:
            if action_type == "prompt_override":
                result = _apply_prompt_override(supabase, strategy_mode, action)
                if result:
                    actions_taken.append(result)

            elif action_type == "threshold_adjust":
                result = _apply_threshold_adjust(supabase, strategy_mode, action)
                if result:
                    actions_taken.append(result)

            elif action_type == "weight_adjust":
                result = _apply_weight_adjust(supabase, strategy_mode, action)
                if result:
                    actions_taken.append(result)

            else:
                logger.warning(f"Unknown action type: {action_type}")

        except Exception as e:
            logger.error(f"Failed to execute action {action_type}: {e}")

    if not actions_taken:
        logger.info(f"No actions executed for {strategy_mode}")
        return InterventionResult(
            intervention_id=0,
            actions_taken=[],
            pre_metrics=pre_metrics,
        )

    # Record intervention
    cooldown_until = (
        datetime.now(timezone.utc) + timedelta(days=COOLDOWN_DAYS)
    ).isoformat()

    try:
        row = (
            supabase._client.table("meta_interventions")
            .insert(
                {
                    "strategy_mode": strategy_mode,
                    "trigger_type": ",".join(
                        set(a.get("trigger_type", "unknown") for a in actions_taken)
                    ),
                    "diagnosis": {
                        "root_causes": diagnosis.root_causes,
                        "confidence": diagnosis.confidence,
                    },
                    "actions_taken": actions_taken,
                    "pre_metrics": pre_metrics,
                    "cooldown_until": cooldown_until,
                }
            )
            .execute()
        )
        intervention_id = row.data[0]["id"] if row.data else 0

        # Link prompt overrides to this intervention
        for action in actions_taken:
            if action.get("type") == "prompt_override" and action.get("override_id"):
                try:
                    supabase._client.table("prompt_overrides").update(
                        {"intervention_id": intervention_id}
                    ).eq("id", action["override_id"]).execute()
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Failed to record intervention: {e}")
        intervention_id = 0

    return InterventionResult(
        intervention_id=intervention_id,
        actions_taken=actions_taken,
        pre_metrics=pre_metrics,
    )


def _apply_prompt_override(supabase, strategy_mode: str, action: dict) -> dict | None:
    """Apply a prompt override with safety limits."""
    text = action.get("override_text", "")
    if not text:
        return None

    # Enforce length limit
    if len(text) > MAX_PROMPT_LENGTH:
        text = text[:MAX_PROMPT_LENGTH]
        logger.warning(f"Prompt override truncated to {MAX_PROMPT_LENGTH} chars")

    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=PROMPT_EXPIRY_DAYS)
    ).isoformat()

    try:
        row = (
            supabase._client.table("prompt_overrides")
            .insert(
                {
                    "strategy_mode": strategy_mode,
                    "override_text": text,
                    "reason": action.get("rationale", "Meta-monitor auto-adjustment"),
                    "active": True,
                    "expires_at": expires_at,
                }
            )
            .execute()
        )
        override_id = row.data[0]["id"] if row.data else None
        logger.info(f"Prompt override applied for {strategy_mode}: {text[:80]}...")
        return {
            "type": "prompt_override",
            "override_id": override_id,
            "text": text,
            "expires_at": expires_at,
            "trigger_type": "prompt_override",
        }
    except Exception as e:
        logger.error(f"Failed to save prompt override: {e}")
        return None


def _apply_threshold_adjust(supabase, strategy_mode: str, action: dict) -> dict | None:
    """Apply threshold adjustment with safety limits."""
    change = action.get("change", 0)
    if not change:
        return None

    # Enforce max change
    change = max(-MAX_THRESHOLD_CHANGE, min(MAX_THRESHOLD_CHANGE, change))

    config = supabase.get_scoring_config(strategy_mode)
    if not config:
        logger.warning(f"No config found for {strategy_mode}")
        return None

    old_threshold = float(config.get("threshold", 60))
    min_threshold = float(config.get("min_threshold", 40))
    max_threshold = float(config.get("max_threshold", 90))

    new_threshold = max(min_threshold, min(max_threshold, old_threshold + change))

    if new_threshold == old_threshold:
        return None

    supabase.update_threshold(
        strategy_mode=strategy_mode,
        new_threshold=new_threshold,
        reason=f"Meta-monitor: {action.get('rationale', 'auto-adjustment')}",
    )

    logger.info(
        f"Threshold adjusted for {strategy_mode}: {old_threshold} -> {new_threshold}"
    )
    return {
        "type": "threshold_adjust",
        "old_value": old_threshold,
        "new_value": new_threshold,
        "change": new_threshold - old_threshold,
        "trigger_type": "threshold_adjust",
    }


def _apply_weight_adjust(supabase, strategy_mode: str, action: dict) -> dict | None:
    """Apply factor weight adjustment with safety limits."""
    factor = action.get("factor", "")
    change = action.get("change", 0)
    if not factor or not change:
        return None

    # Enforce max change
    change = max(-MAX_WEIGHT_CHANGE, min(MAX_WEIGHT_CHANGE, change))

    config = supabase.get_scoring_config(strategy_mode)
    if not config:
        return None

    weights = config.get("factor_weights", {})
    if not weights or factor not in weights:
        logger.warning(f"Factor '{factor}' not found in weights for {strategy_mode}")
        return None

    old_weight = float(weights[factor])
    new_weight = max(0.05, min(0.60, old_weight + change))

    if abs(new_weight - old_weight) < 0.001:
        return None

    # Normalize weights to sum to 1.0
    weights[factor] = round(new_weight, 3)
    total = sum(weights.values())
    weights = {k: round(v / total, 3) for k, v in weights.items()}

    try:
        supabase._client.table("scoring_config").update(
            {"factor_weights": json.dumps(weights)}
        ).eq("strategy_mode", strategy_mode).execute()

        logger.info(
            f"Weight adjusted for {strategy_mode}/{factor}: {old_weight:.3f} -> {weights[factor]:.3f}"
        )
        return {
            "type": "weight_adjust",
            "factor": factor,
            "old_value": old_weight,
            "new_value": weights[factor],
            "all_weights": weights,
            "trigger_type": "weight_adjust",
        }
    except Exception as e:
        logger.error(f"Failed to update weights: {e}")
        return None


def evaluate_past_interventions(supabase, strategy_mode: str) -> None:
    """Evaluate interventions that are 7+ days old and auto-rollback if harmful.

    Runs before detection to clean up bad interventions.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    try:
        # Find unevaluated interventions older than 7 days
        rows = (
            supabase._client.table("meta_interventions")
            .select("*")
            .eq("strategy_mode", strategy_mode)
            .is_("post_metrics", "null")
            .eq("rolled_back", False)
            .lt("intervention_date", cutoff)
            .execute()
            .data
            or []
        )

        if not rows:
            return

        for intervention in rows:
            _evaluate_single_intervention(supabase, intervention, strategy_mode)

    except Exception as e:
        logger.error(f"Failed to evaluate past interventions: {e}")


def _evaluate_single_intervention(
    supabase, intervention: dict, strategy_mode: str
) -> None:
    """Evaluate a single past intervention and rollback if needed."""
    intervention_id = intervention["id"]
    pre_metrics = intervention.get("pre_metrics", {})

    # Compute current metrics for comparison
    from .detector import _compute_window_metrics

    current = _compute_window_metrics(supabase, strategy_mode, days=7)

    pre_win_rate = pre_metrics.get("win_rate_7d")
    post_win_rate = current.get("win_rate")
    pre_return = pre_metrics.get("avg_return_7d")
    post_return = current.get("avg_return")

    # Calculate effectiveness score (-10 to +10 scale)
    score = 0.0
    comparisons = 0

    if pre_win_rate is not None and post_win_rate is not None:
        score += (post_win_rate - pre_win_rate) / 10  # 10% change = 1 point
        comparisons += 1

    if pre_return is not None and post_return is not None:
        score += (post_return - pre_return)  # 1% return change = 1 point
        comparisons += 1

    if comparisons > 0:
        score = round(score / comparisons, 2)

    post_metrics = current

    # Update intervention record
    try:
        supabase._client.table("meta_interventions").update(
            {
                "post_metrics": post_metrics,
                "effectiveness_score": score,
            }
        ).eq("id", intervention_id).execute()

        logger.info(
            f"Intervention #{intervention_id} evaluated: score={score:.2f}"
        )

        # Auto-rollback if harmful
        if score < ROLLBACK_THRESHOLD:
            _rollback_intervention(supabase, intervention)

    except Exception as e:
        logger.error(f"Failed to update intervention #{intervention_id}: {e}")


def _rollback_intervention(supabase, intervention: dict) -> None:
    """Rollback a harmful intervention."""
    intervention_id = intervention["id"]
    strategy_mode = intervention["strategy_mode"]
    actions = intervention.get("actions_taken", [])
    pre_metrics = intervention.get("pre_metrics", {})

    logger.warning(f"Rolling back intervention #{intervention_id} for {strategy_mode}")

    for action in actions:
        action_type = action.get("type")

        try:
            if action_type == "prompt_override":
                override_id = action.get("override_id")
                if override_id:
                    supabase._client.table("prompt_overrides").update(
                        {"active": False}
                    ).eq("id", override_id).execute()
                    logger.info(f"Deactivated prompt override #{override_id}")

            elif action_type == "threshold_adjust":
                old_value = action.get("old_value")
                if old_value is not None:
                    supabase.update_threshold(
                        strategy_mode=strategy_mode,
                        new_threshold=old_value,
                        reason=f"Meta-monitor rollback of intervention #{intervention_id}",
                    )
                    logger.info(f"Restored threshold to {old_value}")

            elif action_type == "weight_adjust":
                # Restore all weights from pre_metrics if available
                # Individual weight rollback is complex due to normalization
                logger.info(
                    f"Weight rollback noted for {action.get('factor')} "
                    f"(manual review recommended)"
                )

        except Exception as e:
            logger.error(f"Rollback failed for action {action_type}: {e}")

    # Mark as rolled back
    try:
        supabase._client.table("meta_interventions").update(
            {
                "rolled_back": True,
                "rollback_date": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", intervention_id).execute()
    except Exception as e:
        logger.error(f"Failed to mark intervention as rolled back: {e}")
