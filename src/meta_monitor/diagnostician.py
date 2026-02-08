"""LLM-based root cause diagnosis for performance degradation."""

import json
import logging
from datetime import datetime, timedelta, timezone

from src.llm import LLMClient
from .models import DegradationSignal, Diagnosis, RollingMetrics
from .parameters import get_all_parameters_with_bounds
from .prompts import META_DIAGNOSIS_SYSTEM_PROMPT, build_diagnosis_prompt

logger = logging.getLogger(__name__)


def diagnose(
    supabase,
    llm_client: LLMClient,
    strategy_mode: str,
    signals: list[DegradationSignal],
    metrics: RollingMetrics,
) -> Diagnosis:
    """Run LLM diagnosis to identify root causes and recommend actions.

    Collects context from reflection_records (previously write-only),
    recent judgments, and current config, then asks LLM for analysis.
    """
    # Collect context data
    recent_reflections = _get_recent_reflections(supabase, strategy_mode)
    recent_judgments = _get_recent_judgments_with_outcomes(supabase, strategy_mode, days=7)
    current_config = _get_current_config(supabase, strategy_mode)
    active_overrides = _get_active_overrides(supabase, strategy_mode)
    strategy_parameters = get_all_parameters_with_bounds(supabase, strategy_mode)

    # Build prompt
    signals_dicts = [
        {
            "trigger_type": s.trigger_type,
            "severity": s.severity,
            "current_value": s.current_value,
            "baseline_value": s.baseline_value,
            "details": s.details,
        }
        for s in signals
    ]

    prompt = build_diagnosis_prompt(
        strategy_mode=strategy_mode,
        signals=signals_dicts,
        metrics=metrics.to_dict(),
        recent_reflections=recent_reflections,
        recent_judgments=recent_judgments,
        current_config=current_config,
        active_overrides=active_overrides,
        strategy_parameters=strategy_parameters,
    )

    full_prompt = f"{META_DIAGNOSIS_SYSTEM_PROMPT}\n\n{prompt}"

    # Call LLM
    try:
        response = llm_client.generate(
            prompt=full_prompt,
            temperature=0.3,
            max_tokens=2048,
            json_mode=True,
        )

        result = _parse_diagnosis_response(response.content)
        logger.info(
            f"Diagnosis for {strategy_mode}: {len(result.root_causes)} causes, "
            f"{len(result.recommended_actions)} actions, confidence={result.confidence:.2f}"
        )
        return result

    except Exception as e:
        logger.error(f"Diagnosis failed for {strategy_mode}: {e}")
        return Diagnosis(
            root_causes=[f"Diagnosis error: {str(e)}"],
            recommended_actions=[],
            confidence=0.0,
            raw_response="",
        )


def _parse_diagnosis_response(content: str) -> Diagnosis:
    """Parse LLM JSON response into Diagnosis model."""
    try:
        # Strip markdown code fences if present
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        data = json.loads(text)

        return Diagnosis(
            root_causes=data.get("root_causes", []),
            recommended_actions=data.get("recommended_actions", []),
            confidence=float(data.get("confidence", 0.5)),
            raw_response=content,
        )
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"Failed to parse diagnosis response: {e}")
        return Diagnosis(
            root_causes=["Parse error: could not interpret LLM response"],
            recommended_actions=[],
            confidence=0.0,
            raw_response=content,
        )


def _get_recent_reflections(supabase, strategy_mode: str, limit: int = 3) -> list[dict]:
    """Fetch recent reflection_records — consuming the previously write-only data."""
    try:
        rows = (
            supabase._client.table("reflection_records")
            .select("*")
            .eq("strategy_mode", strategy_mode)
            .order("reflection_date", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
        return rows
    except Exception as e:
        logger.warning(f"Failed to fetch reflections for {strategy_mode}: {e}")
        return []


def _get_recent_judgments_with_outcomes(
    supabase, strategy_mode: str, days: int = 7
) -> list[dict]:
    """Fetch recent judgments with their outcomes for diagnosis context."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        rows = (
            supabase._client.table("judgment_outcomes")
            .select(
                "actual_return_5d, outcome_aligned, outcome_date, "
                "judgment_records!inner(symbol, strategy_mode, decision, confidence, "
                "composite_score, batch_date)"
            )
            .gte("outcome_date", cutoff)
            .execute()
            .data
            or []
        )

        # Filter and flatten
        result = []
        for r in rows:
            jr = r.get("judgment_records", {})
            if jr.get("strategy_mode") != strategy_mode:
                continue
            result.append(
                {
                    "symbol": jr.get("symbol"),
                    "decision": jr.get("decision"),
                    "confidence": jr.get("confidence"),
                    "score": jr.get("composite_score"),
                    "actual_return": r.get("actual_return_5d"),
                    "outcome_aligned": r.get("outcome_aligned"),
                    "date": jr.get("batch_date"),
                }
            )
        return result

    except Exception as e:
        logger.warning(f"Failed to fetch recent judgments: {e}")
        return []


def _get_current_config(supabase, strategy_mode: str) -> dict:
    """Get current scoring config for the strategy."""
    try:
        config = supabase.get_scoring_config(strategy_mode)
        return config or {}
    except Exception as e:
        logger.warning(f"Failed to get config for {strategy_mode}: {e}")
        return {}


def _get_active_overrides(supabase, strategy_mode: str) -> list[dict]:
    """Get currently active prompt overrides."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        rows = (
            supabase._client.table("prompt_overrides")
            .select("*")
            .eq("strategy_mode", strategy_mode)
            .eq("active", True)
            .gt("expires_at", now)
            .execute()
            .data
            or []
        )
        return rows
    except Exception as e:
        logger.warning(f"Failed to get overrides for {strategy_mode}: {e}")
        return []
