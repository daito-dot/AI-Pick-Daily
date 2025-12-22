"""
Deep Research Module - Layer 4 of 4-layer architecture.

This module implements deep research capabilities using advanced LLM:
- Weekly sector/market analysis
- Thematic investigation (e.g., AI stocks, interest rate sensitivity)
- Comprehensive company deep dives
- Macro trend analysis

Uses: Gemini Deep Research model (or Gemini Pro for complex analysis)

Timing: Weekly or on-demand (not daily due to cost)
"""
from .service import DeepResearchService
from .models import (
    ResearchReport,
    SectorAnalysis,
    ThematicInsight,
    MacroOutlook,
)

__all__ = [
    "DeepResearchService",
    "ResearchReport",
    "SectorAnalysis",
    "ThematicInsight",
    "MacroOutlook",
]
