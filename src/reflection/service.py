"""
Reflection Service - Implements systematic reflection on past judgments.

Based on Reflexion framework:
1. Collect past judgments with outcomes
2. Analyze patterns using LLM
3. Generate improvement suggestions
4. Store for future reference
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from src.llm import get_llm_client, LLMClient
from src.config import config
from src.data.supabase_client import SupabaseClient
from .models import (
    ReflectionResult,
    PatternAnalysis,
    FactorReliability,
    ImprovementSuggestion,
    JudgmentWithOutcome,
)
from .prompts import REFLECTION_SYSTEM_PROMPT, build_reflection_prompt, PROMPT_VERSION


logger = logging.getLogger(__name__)


class ReflectionService:
    """
    Service for analyzing past judgments and generating insights.

    Uses LLM to identify patterns and suggest improvements.
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        supabase_client: SupabaseClient | None = None,
    ):
        """
        Initialize the reflection service.

        Args:
            llm_client: Optional LLM client
            supabase_client: Optional Supabase client for data access
        """
        self.llm_client = llm_client or get_llm_client()
        self.supabase = supabase_client or SupabaseClient()
        self.model_name = config.llm.reflection_model

    def run_weekly_reflection(
        self,
        strategy_mode: str,
    ) -> ReflectionResult:
        """
        Run weekly reflection analysis.

        Args:
            strategy_mode: 'conservative' or 'aggressive'

        Returns:
            ReflectionResult with analysis
        """
        # Get past 7 days of judgments with outcomes
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        return self._run_reflection(
            strategy_mode=strategy_mode,
            reflection_type="weekly",
            start_date=start_date,
            end_date=end_date,
        )

    def run_monthly_reflection(
        self,
        strategy_mode: str,
    ) -> ReflectionResult:
        """
        Run monthly reflection analysis.

        Args:
            strategy_mode: 'conservative' or 'aggressive'

        Returns:
            ReflectionResult with analysis
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        return self._run_reflection(
            strategy_mode=strategy_mode,
            reflection_type="monthly",
            start_date=start_date,
            end_date=end_date,
        )

    def run_post_trade_reflection(
        self,
        symbol: str,
        entry_date: str,
        exit_date: str,
        strategy_mode: str,
    ) -> dict[str, Any]:
        """
        Run reflection on a specific closed trade.

        Args:
            symbol: Stock symbol
            entry_date: Trade entry date
            exit_date: Trade exit date
            strategy_mode: Strategy mode

        Returns:
            Post-trade analysis dict
        """
        # Get the judgment record
        judgments = self.supabase.get_judgment_records(
            batch_date=entry_date,
            symbol=symbol,
            strategy_mode=strategy_mode,
        )

        if not judgments:
            logger.warning(f"No judgment found for {symbol} on {entry_date}")
            return {"error": "No judgment record found"}

        judgment = judgments[0]

        # Get the trade outcome
        # (This would come from trade_history table)
        # For now, calculate from stock returns

        # TODO: Implement post-trade reflection
        return {"status": "not_implemented"}

    def _run_reflection(
        self,
        strategy_mode: str,
        reflection_type: str,
        start_date: datetime,
        end_date: datetime,
    ) -> ReflectionResult:
        """
        Run reflection analysis for a time period.

        Args:
            strategy_mode: Strategy to analyze
            reflection_type: Type of reflection
            start_date: Start of analysis period
            end_date: End of analysis period

        Returns:
            ReflectionResult
        """
        logger.info(
            f"Running {reflection_type} reflection for {strategy_mode} "
            f"({start_date.date()} to {end_date.date()})"
        )

        # Collect judgments with outcomes
        judgments = self._collect_judgments_with_outcomes(
            strategy_mode=strategy_mode,
            start_date=start_date,
            end_date=end_date,
        )

        if not judgments:
            logger.warning("No judgments found for reflection")
            return self._create_empty_result(
                strategy_mode, reflection_type, start_date, end_date
            )

        # Calculate performance summary
        summary = self._calculate_performance_summary(judgments)

        # Build prompt
        judgments_dicts = [self._judgment_to_dict(j) for j in judgments]
        prompt = build_reflection_prompt(
            strategy_mode=strategy_mode,
            reflection_type=reflection_type,
            period_start=start_date.strftime("%Y-%m-%d"),
            period_end=end_date.strftime("%Y-%m-%d"),
            judgments_with_outcomes=judgments_dicts,
            performance_summary=summary,
        )

        full_prompt = f"{REFLECTION_SYSTEM_PROMPT}\n\n{prompt}"

        # Generate reflection using LLM
        try:
            response = self.llm_client.generate(
                prompt=full_prompt,
                model=self.model_name,
            )

            # Parse response
            result = self._parse_reflection_response(
                response=response.content,
                strategy_mode=strategy_mode,
                reflection_type=reflection_type,
                start_date=start_date,
                end_date=end_date,
                summary=summary,
            )

            # Store raw response
            result.raw_llm_response = response.content

            # Save to database
            self._save_reflection(result)

            logger.info(
                f"Reflection complete: {result.accuracy_rate:.0%} accuracy, "
                f"{len(result.suggestions)} suggestions"
            )

            return result

        except Exception as e:
            logger.error(f"Reflection analysis failed: {e}")
            return self._create_error_result(
                strategy_mode, reflection_type, start_date, end_date, str(e)
            )

    def _collect_judgments_with_outcomes(
        self,
        strategy_mode: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[JudgmentWithOutcome]:
        """Collect judgments with their outcomes from database."""
        # Get recent judgments with outcomes
        raw_judgments = self.supabase.get_recent_judgments_for_reflection(
            strategy_mode=strategy_mode,
            days=(end_date - start_date).days,
        )

        judgments = []
        for j in raw_judgments:
            # Extract outcome data
            outcomes = j.get("judgment_outcomes", [])
            outcome = outcomes[0] if outcomes else {}

            judgment = JudgmentWithOutcome(
                symbol=j.get("symbol", ""),
                batch_date=j.get("batch_date", ""),
                strategy_mode=j.get("strategy_mode", ""),
                decision=j.get("decision", ""),
                confidence=j.get("confidence", 0),
                score=j.get("score", 0),
                reasoning_steps=j.get("reasoning", {}).get("steps", []),
                key_factors=j.get("key_factors", []),
                market_regime=j.get("market_regime", ""),
                actual_return_1d=outcome.get("actual_return_1d"),
                actual_return_5d=outcome.get("actual_return_5d"),
                outcome_aligned=outcome.get("outcome_aligned"),
            )
            judgments.append(judgment)

        return judgments

    def _calculate_performance_summary(
        self,
        judgments: list[JudgmentWithOutcome],
    ) -> dict[str, Any]:
        """Calculate performance summary statistics."""
        total = len(judgments)
        if total == 0:
            return {"total": 0, "accuracy": 0}

        # Count correct/incorrect
        correct = sum(1 for j in judgments if j.was_correct is True)
        incorrect = sum(1 for j in judgments if j.was_correct is False)
        unknown = total - correct - incorrect

        # By decision type
        buy_judgments = [j for j in judgments if j.decision == "buy"]
        avoid_judgments = [j for j in judgments if j.decision == "avoid"]

        buy_correct = sum(1 for j in buy_judgments if j.was_correct is True)
        avoid_correct = sum(1 for j in avoid_judgments if j.was_correct is True)

        # Confidence analysis
        avg_confidence = sum(j.confidence for j in judgments) / total

        # Calibration (high confidence should correlate with correctness)
        high_conf = [j for j in judgments if j.confidence >= 0.7]
        high_conf_correct = sum(1 for j in high_conf if j.was_correct is True)
        calibration = "good" if len(high_conf) > 0 and high_conf_correct / len(high_conf) >= 0.7 else "needs_work"

        return {
            "total": total,
            "correct": correct,
            "incorrect": incorrect,
            "unknown": unknown,
            "accuracy": correct / (correct + incorrect) if (correct + incorrect) > 0 else 0,
            "buy_count": len(buy_judgments),
            "buy_accuracy": buy_correct / len(buy_judgments) if buy_judgments else 0,
            "avoid_count": len(avoid_judgments),
            "avoid_accuracy": avoid_correct / len(avoid_judgments) if avoid_judgments else 0,
            "avg_confidence": avg_confidence,
            "calibration": calibration,
        }

    def _judgment_to_dict(self, j: JudgmentWithOutcome) -> dict:
        """Convert JudgmentWithOutcome to dict for prompt."""
        return {
            "symbol": j.symbol,
            "batch_date": j.batch_date,
            "decision": j.decision,
            "confidence": j.confidence,
            "score": j.score,
            "reasoning_steps": j.reasoning_steps,
            "key_factors": j.key_factors,
            "market_regime": j.market_regime,
            "actual_return_5d": j.actual_return_5d,
            "was_correct": j.was_correct,
        }

    def _parse_reflection_response(
        self,
        response: str,
        strategy_mode: str,
        reflection_type: str,
        start_date: datetime,
        end_date: datetime,
        summary: dict,
    ) -> ReflectionResult:
        """Parse LLM response into ReflectionResult."""
        # Clean response
        cleaned = response.strip()
        if "```json" in cleaned:
            start = cleaned.find("```json") + 7
            end = cleaned.find("```", start)
            cleaned = cleaned[start:end].strip()
        elif "```" in cleaned:
            start = cleaned.find("```") + 3
            end = cleaned.find("```", start)
            cleaned = cleaned[start:end].strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse reflection response: {e}")
            raise ValueError(f"Invalid JSON response: {e}")

        # Parse factor reliability
        factor_reliability = []
        for fr in data.get("factor_reliability", []):
            factor_reliability.append(FactorReliability(
                factor_type=fr.get("factor_type", "unknown"),
                total_uses=fr.get("total_uses", 0),
                correct_predictions=fr.get("correct_predictions", 0),
                incorrect_predictions=fr.get("incorrect_predictions", 0),
                accuracy_rate=fr.get("accuracy_rate", 0),
                avg_confidence_when_used=fr.get("avg_confidence_when_used", 0),
                avg_return_when_correct=None,
                avg_return_when_incorrect=None,
                reliability_grade=fr.get("reliability_grade", "C"),
                recommendation=fr.get("recommendation", ""),
            ))

        # Parse success patterns
        success_patterns = []
        for sp in data.get("success_patterns", []):
            success_patterns.append(PatternAnalysis(
                pattern_type="success",
                description=sp.get("description", ""),
                frequency=sp.get("frequency", 0),
                confidence=sp.get("confidence", 0),
                examples=sp.get("examples", []),
                insight=sp.get("insight", ""),
                suggested_action=sp.get("suggested_action", ""),
            ))

        # Parse failure patterns
        failure_patterns = []
        for fp in data.get("failure_patterns", []):
            failure_patterns.append(PatternAnalysis(
                pattern_type="failure",
                description=fp.get("description", ""),
                frequency=fp.get("frequency", 0),
                confidence=fp.get("confidence", 0),
                examples=fp.get("examples", []),
                insight=fp.get("insight", ""),
                suggested_action=fp.get("suggested_action", ""),
            ))

        # Parse improvement suggestions
        suggestions = []
        for s in data.get("improvement_suggestions", []):
            suggestions.append(ImprovementSuggestion(
                category=s.get("category", "model"),
                priority=s.get("priority", "medium"),
                suggestion=s.get("suggestion", ""),
                rationale=s.get("rationale", ""),
                expected_impact=s.get("expected_impact", ""),
                implementation_difficulty=s.get("implementation_difficulty", "medium"),
            ))

        return ReflectionResult(
            reflection_date=datetime.now(),
            strategy_mode=strategy_mode,
            reflection_type=reflection_type,
            period_start=start_date,
            period_end=end_date,
            total_judgments=summary.get("total", 0),
            buy_recommendations=summary.get("buy_count", 0),
            avoid_recommendations=summary.get("avoid_count", 0),
            hold_recommendations=0,
            correct_judgments=summary.get("correct", 0),
            incorrect_judgments=summary.get("incorrect", 0),
            accuracy_rate=summary.get("accuracy", 0),
            buy_accuracy=summary.get("buy_accuracy"),
            avoid_accuracy=summary.get("avoid_accuracy"),
            factor_reliability=factor_reliability,
            success_patterns=success_patterns,
            failure_patterns=failure_patterns,
            suggestions=suggestions,
            regime_performance=data.get("regime_performance", {}),
            model_version=self.model_name,
        )

    def _save_reflection(self, result: ReflectionResult) -> None:
        """Save reflection result to database."""
        try:
            patterns = {
                "successful_patterns": [
                    {"description": p.description, "insight": p.insight}
                    for p in result.success_patterns
                ],
                "failure_patterns": [
                    {"description": p.description, "insight": p.insight}
                    for p in result.failure_patterns
                ],
                "factor_reliability": {
                    f.factor_type: f.accuracy_rate
                    for f in result.factor_reliability
                },
                "regime_performance": result.regime_performance,
            }

            suggestions = [
                {
                    "category": s.category,
                    "priority": s.priority,
                    "suggestion": s.suggestion,
                    "rationale": s.rationale,
                }
                for s in result.suggestions
            ]

            self.supabase.save_reflection_record(
                reflection_date=result.reflection_date.strftime("%Y-%m-%d"),
                strategy_mode=result.strategy_mode,
                reflection_type=result.reflection_type,
                period_start=result.period_start.strftime("%Y-%m-%d"),
                period_end=result.period_end.strftime("%Y-%m-%d"),
                total_judgments=result.total_judgments,
                correct_judgments=result.correct_judgments,
                accuracy_rate=result.accuracy_rate,
                patterns_identified=patterns,
                improvement_suggestions=suggestions,
                model_version=result.model_version,
                raw_llm_response=result.raw_llm_response,
            )

        except Exception as e:
            logger.error(f"Failed to save reflection: {e}")

    def _create_empty_result(
        self,
        strategy_mode: str,
        reflection_type: str,
        start_date: datetime,
        end_date: datetime,
    ) -> ReflectionResult:
        """Create empty result when no data available."""
        return ReflectionResult(
            reflection_date=datetime.now(),
            strategy_mode=strategy_mode,
            reflection_type=reflection_type,
            period_start=start_date,
            period_end=end_date,
            total_judgments=0,
            buy_recommendations=0,
            avoid_recommendations=0,
            hold_recommendations=0,
            correct_judgments=0,
            incorrect_judgments=0,
            accuracy_rate=0,
            model_version=self.model_name,
        )

    def _create_error_result(
        self,
        strategy_mode: str,
        reflection_type: str,
        start_date: datetime,
        end_date: datetime,
        error_message: str,
    ) -> ReflectionResult:
        """Create result with error information."""
        result = self._create_empty_result(
            strategy_mode, reflection_type, start_date, end_date
        )
        result.suggestions = [
            ImprovementSuggestion(
                category="model",
                priority="high",
                suggestion="Fix reflection analysis error",
                rationale=f"Error occurred: {error_message}",
                expected_impact="Enable reflection analysis",
                implementation_difficulty="medium",
            )
        ]
        return result
