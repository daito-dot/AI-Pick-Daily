"""Meta-monitor orchestration service.

Entry point called as Step 7 of daily_review.
"""

import logging

from src.config import config
from src.llm import get_llm_client_for_model
from .detector import (
    compute_rolling_metrics,
    detect_degradation,
    check_cooldown,
    count_monthly_interventions,
)
from .diagnostician import diagnose
from .actuator import execute_actions, evaluate_past_interventions

logger = logging.getLogger(__name__)

MAX_MONTHLY_INTERVENTIONS = 6


def run_meta_monitor(supabase, strategy_mode: str) -> None:
    """Run the full meta-monitor cycle for a strategy.

    Called as Step 7 of daily_review after existing feedback loops.
    Flow: Evaluate past → Compute metrics → Detect → Cooldown check →
          Monthly limit → Diagnose → Act
    """
    logger.info(f"Meta-monitor starting for {strategy_mode}")

    # 1. Evaluate past interventions (7+ days old)
    try:
        evaluate_past_interventions(supabase, strategy_mode)
    except Exception as e:
        logger.error(f"Past intervention evaluation failed: {e}")

    # 2. Compute rolling metrics
    try:
        metrics = compute_rolling_metrics(supabase, strategy_mode)
    except Exception as e:
        logger.error(f"Rolling metrics computation failed: {e}")
        return

    logger.info(
        f"Metrics for {strategy_mode}: "
        f"7d_wr={metrics.win_rate_7d}, 30d_wr={metrics.win_rate_30d}, "
        f"7d_ret={metrics.avg_return_7d}, missed={metrics.missed_rate_7d}"
    )

    # 3. Detect degradation
    signals = detect_degradation(metrics, supabase=supabase)
    if not signals:
        logger.info(f"No degradation detected for {strategy_mode}")
        return

    logger.warning(
        f"Degradation detected for {strategy_mode}: "
        f"{len(signals)} signal(s) - "
        + ", ".join(f"{s.trigger_type}({s.severity})" for s in signals)
    )

    # 4. Cooldown check
    if check_cooldown(supabase, strategy_mode):
        logger.info(f"Cooldown active for {strategy_mode}, skipping intervention")
        return

    # 5. Monthly limit check
    monthly_count = count_monthly_interventions(supabase, strategy_mode)
    if monthly_count >= MAX_MONTHLY_INTERVENTIONS:
        logger.info(
            f"Monthly limit reached for {strategy_mode}: "
            f"{monthly_count}/{MAX_MONTHLY_INTERVENTIONS}"
        )
        return

    # 6. LLM diagnosis
    try:
        llm_client = get_llm_client_for_model(config.llm.scoring_model)
        diagnosis = diagnose(supabase, llm_client, strategy_mode, signals, metrics)
    except Exception as e:
        logger.error(f"Diagnosis failed for {strategy_mode}: {e}")
        return

    if not diagnosis.recommended_actions:
        logger.info(f"No actions recommended for {strategy_mode}")
        return

    logger.info(
        f"Diagnosis for {strategy_mode}: "
        f"{len(diagnosis.root_causes)} causes, "
        f"{len(diagnosis.recommended_actions)} actions recommended"
    )

    # 7. Execute actions
    try:
        result = execute_actions(supabase, diagnosis, strategy_mode, metrics)
        if result.intervention_id:
            logger.info(
                f"Meta intervention #{result.intervention_id} applied for {strategy_mode}: "
                f"{len(result.actions_taken)} action(s)"
            )
        else:
            logger.info(f"No actions were applied for {strategy_mode}")
    except Exception as e:
        logger.error(f"Action execution failed for {strategy_mode}: {e}")
