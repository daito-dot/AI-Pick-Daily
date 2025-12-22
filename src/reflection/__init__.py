"""
Reflection Module - Layer 3 of 4-layer architecture.

This module implements systematic reflection on past judgments:
- Outcome comparison (predicted vs actual)
- Pattern identification (what worked, what didn't)
- Factor reliability analysis
- Improvement suggestions

Based on research insights:
- Reflexion framework: memory + reflection = improvement
- FinCoT: Explicit reasoning traces enable better learning
- Self-refinement: LLMs can identify their own mistakes
"""
from .service import ReflectionService
from .models import (
    ReflectionResult,
    PatternAnalysis,
    FactorReliability,
    ImprovementSuggestion,
)

__all__ = [
    "ReflectionService",
    "ReflectionResult",
    "PatternAnalysis",
    "FactorReliability",
    "ImprovementSuggestion",
]
