"""Centralized strategy parameter management.

Reads tunable parameters from strategy_parameters table,
falls back to hardcoded defaults if DB is unavailable.
All changes are logged to parameter_change_log.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Fallback defaults (used when DB is unavailable)
DEFAULTS: dict[str, float] = {
    "take_profit_pct": 8.0,
    "stop_loss_pct": -7.0,
    "max_hold_days": 10,
    "absolute_max_hold_days": 15,
    "max_positions": 10,
    "mdd_warning_pct": -10.0,
    "mdd_stop_new_pct": -15.0,
    "win_rate_drop_ratio": 0.7,
    "return_decline_threshold": -1.0,
    "missed_spike_threshold": 0.30,
    "cooldown_days": 3,
    "prompt_expiry_days": 14,
    "max_threshold_change": 10,
    "max_weight_change": 0.1,
    "confidence_drift_threshold": 0.05,
}


def get_parameter(supabase, strategy_mode: str, param_name: str) -> float:
    """Get a single parameter value. DB-first with hardcoded fallback."""
    try:
        row = (
            supabase._client.table("strategy_parameters")
            .select("current_value")
            .eq("strategy_mode", strategy_mode)
            .eq("param_name", param_name)
            .single()
            .execute()
            .data
        )
        if row and row.get("current_value") is not None:
            return float(row["current_value"])
    except Exception as e:
        logger.debug(f"DB read failed for {strategy_mode}/{param_name}: {e}")

    return DEFAULTS.get(param_name, 0.0)


def get_parameters(supabase, strategy_mode: str) -> dict[str, float]:
    """Get all parameters for a strategy. Returns dict of param_name -> value."""
    result = dict(DEFAULTS)  # Start with defaults
    try:
        rows = (
            supabase._client.table("strategy_parameters")
            .select("param_name, current_value")
            .eq("strategy_mode", strategy_mode)
            .execute()
            .data
            or []
        )
        for row in rows:
            name = row.get("param_name")
            val = row.get("current_value")
            if name and val is not None:
                result[name] = float(val)
    except Exception as e:
        logger.warning(f"Failed to load parameters for {strategy_mode}: {e}")

    return result


def get_parameter_with_bounds(
    supabase, strategy_mode: str, param_name: str
) -> dict:
    """Get parameter with its min/max/step bounds. Used by actuator."""
    try:
        row = (
            supabase._client.table("strategy_parameters")
            .select("current_value, min_value, max_value, step")
            .eq("strategy_mode", strategy_mode)
            .eq("param_name", param_name)
            .single()
            .execute()
            .data
        )
        if row:
            return {
                "current_value": float(row["current_value"]),
                "min_value": float(row["min_value"]),
                "max_value": float(row["max_value"]),
                "step": float(row["step"]),
            }
    except Exception as e:
        logger.debug(f"DB bounds read failed for {strategy_mode}/{param_name}: {e}")

    return {
        "current_value": DEFAULTS.get(param_name, 0.0),
        "min_value": float("-inf"),
        "max_value": float("inf"),
        "step": 1.0,
    }


def get_all_parameters_with_bounds(
    supabase, strategy_mode: str,
) -> list[dict]:
    """Get all parameters with bounds for diagnosis prompt context."""
    try:
        rows = (
            supabase._client.table("strategy_parameters")
            .select("param_name, current_value, min_value, max_value, step, description")
            .eq("strategy_mode", strategy_mode)
            .execute()
            .data
            or []
        )
        return [
            {
                "param_name": r["param_name"],
                "current_value": float(r["current_value"]),
                "min_value": float(r["min_value"]),
                "max_value": float(r["max_value"]),
                "step": float(r["step"]),
                "description": r.get("description", ""),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"Failed to load parameter bounds for {strategy_mode}: {e}")
        return []


def set_parameter(
    supabase,
    strategy_mode: str,
    param_name: str,
    new_value: float,
    changed_by: str,
    reason: str,
    intervention_id: int | None = None,
) -> bool:
    """Update a parameter with bounds checking and change logging.

    Returns True if successfully updated, False otherwise.
    """
    bounds = get_parameter_with_bounds(supabase, strategy_mode, param_name)
    old_value = bounds["current_value"]

    # Clamp to step increments
    step = bounds["step"]
    if step > 0:
        change = new_value - old_value
        if abs(change) > step:
            # Clamp change to step size
            clamped_change = step if change > 0 else -step
            new_value = old_value + clamped_change
            logger.info(
                f"Change clamped by step limit: {change} -> {clamped_change} "
                f"(step={step}) for {param_name}"
            )

    # Clamp to min/max bounds
    new_value = max(bounds["min_value"], min(bounds["max_value"], new_value))

    if new_value == old_value:
        logger.info(f"No change for {strategy_mode}/{param_name}: value stays at {old_value}")
        return False

    try:
        # Update the parameter
        supabase._client.table("strategy_parameters").update(
            {
                "current_value": new_value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("strategy_mode", strategy_mode).eq("param_name", param_name).execute()

        # Log the change
        log_record = {
            "strategy_mode": strategy_mode,
            "param_name": param_name,
            "old_value": old_value,
            "new_value": new_value,
            "changed_by": changed_by,
            "reason": reason,
        }
        if intervention_id is not None:
            log_record["intervention_id"] = intervention_id

        supabase._client.table("parameter_change_log").insert(log_record).execute()

        logger.info(
            f"Parameter updated: {strategy_mode}/{param_name} "
            f"{old_value} -> {new_value} (by {changed_by})"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to update parameter {strategy_mode}/{param_name}: {e}")
        return False
