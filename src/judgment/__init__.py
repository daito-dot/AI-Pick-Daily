"""
Judgment module for LLM-based investment decision making.

This module implements Layer 2 of the 4-layer architecture:
- Layer 1: Information collection and structuring
- Layer 2: Judgment with explicit reasoning (this module)
- Layer 3: Reflection and feedback
- Layer 4: Deep research and strategy

Key components:
- JudgmentOutput: Structured output with reasoning trace
- JudgmentService: LLM-based judgment with CoT prompting
- Database integration for judgment records
"""
from .models import (
    JudgmentOutput,
    ReasoningTrace,
    KeyFactor,
    JudgmentDecision,
)
from .service import JudgmentService
from .integration import (
    run_judgment_for_candidates,
    filter_picks_by_judgment,
    save_judgment_to_db,
    select_final_picks,
    JudgmentResult,
)

__all__ = [
    "JudgmentOutput",
    "ReasoningTrace",
    "KeyFactor",
    "JudgmentDecision",
    "JudgmentService",
    "JudgmentResult",
    "run_judgment_for_candidates",
    "filter_picks_by_judgment",
    "save_judgment_to_db",
    "select_final_picks",
]
