"""
Reflection Models - Data structures for reflection analysis.

Based on Reflexion framework principles:
- Memory: Store past experiences (judgments + outcomes)
- Reflection: Analyze patterns and generate insights
- Self-refinement: Generate concrete improvements
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


ReflectionType = Literal["weekly", "monthly", "post_trade"]


@dataclass
class FactorReliability:
    """
    Analysis of how reliable a factor type has been.

    Tracks which factors led to correct predictions
    and which led to errors.
    """
    factor_type: str  # fundamental, technical, sentiment, macro, catalyst
    total_uses: int
    correct_predictions: int
    incorrect_predictions: int
    accuracy_rate: float  # 0-1

    # Impact analysis
    avg_confidence_when_used: float
    avg_return_when_correct: float | None
    avg_return_when_incorrect: float | None

    # Recommendations
    reliability_grade: Literal["A", "B", "C", "D", "F"]
    recommendation: str  # e.g., "Increase weight" or "Verify with other signals"


@dataclass
class PatternAnalysis:
    """
    Identified patterns from past judgments.

    Distinguishes between successful and failure patterns.
    """
    pattern_type: Literal["success", "failure"]
    description: str
    frequency: int  # How often this pattern occurred
    confidence: float  # How confident we are in this pattern
    examples: list[str]  # Specific examples (symbols, dates)

    # Actionable insight
    insight: str
    suggested_action: str


@dataclass
class ImprovementSuggestion:
    """
    Concrete suggestion for improving future judgments.

    Prioritized and actionable.
    """
    category: Literal["data", "model", "strategy", "timing", "risk"]
    priority: Literal["high", "medium", "low"]
    suggestion: str
    rationale: str
    expected_impact: str
    implementation_difficulty: Literal["easy", "medium", "hard"]


@dataclass
class ReflectionResult:
    """
    Complete result of a reflection analysis.

    This is the primary output of Layer 3.
    """
    # Metadata
    reflection_date: datetime
    strategy_mode: str
    reflection_type: ReflectionType
    period_start: datetime
    period_end: datetime

    # Performance summary
    total_judgments: int
    buy_recommendations: int
    avoid_recommendations: int
    hold_recommendations: int

    # Accuracy metrics
    correct_judgments: int
    incorrect_judgments: int
    accuracy_rate: float

    # Breakdown by decision type
    buy_accuracy: float | None = None
    avoid_accuracy: float | None = None

    # Factor analysis
    factor_reliability: list[FactorReliability] = field(default_factory=list)

    # Pattern analysis
    success_patterns: list[PatternAnalysis] = field(default_factory=list)
    failure_patterns: list[PatternAnalysis] = field(default_factory=list)

    # Improvement suggestions
    suggestions: list[ImprovementSuggestion] = field(default_factory=list)

    # Regime-specific insights
    regime_performance: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Model metadata
    model_version: str = ""
    raw_llm_response: str | None = None

    def get_top_suggestions(self, n: int = 3) -> list[ImprovementSuggestion]:
        """Get top N suggestions by priority."""
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_suggestions = sorted(
            self.suggestions,
            key=lambda x: priority_order.get(x.priority, 3)
        )
        return sorted_suggestions[:n]

    def get_reliable_factors(self, min_accuracy: float = 0.6) -> list[FactorReliability]:
        """Get factors with accuracy above threshold."""
        return [f for f in self.factor_reliability if f.accuracy_rate >= min_accuracy]

    def get_unreliable_factors(self, max_accuracy: float = 0.5) -> list[FactorReliability]:
        """Get factors with accuracy below threshold."""
        return [f for f in self.factor_reliability if f.accuracy_rate <= max_accuracy]


@dataclass
class JudgmentWithOutcome:
    """
    A judgment paired with its outcome for reflection analysis.
    """
    # Judgment data
    symbol: str
    batch_date: str
    strategy_mode: str
    decision: str
    confidence: float
    score: int
    reasoning_steps: list[str]
    key_factors: list[dict]
    market_regime: str

    # Outcome data
    actual_return_1d: float | None = None
    actual_return_5d: float | None = None
    outcome_aligned: bool | None = None

    # Calculated
    was_correct: bool | None = None

    def __post_init__(self):
        """Determine if judgment was correct based on outcome."""
        if self.actual_return_5d is not None:
            if self.decision == "buy":
                # Buy was correct if return is positive
                self.was_correct = self.actual_return_5d > 0
            elif self.decision == "avoid":
                # Avoid was correct if return is negative or flat
                self.was_correct = self.actual_return_5d <= 0
            else:  # hold
                # Hold is harder to evaluate, consider correct if small movement
                self.was_correct = abs(self.actual_return_5d) < 3.0
