"""
Data models for judgment recording.

These structures capture the full reasoning process of investment decisions,
enabling later reflection and learning from both successes and failures.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Any
import json


# Type aliases
JudgmentDecision = Literal["buy", "hold", "avoid"]
AllocationHint = Literal["high", "normal", "low"]
FactorType = Literal["fundamental", "technical", "sentiment", "macro", "catalyst"]
FactorImpact = Literal["positive", "negative", "neutral"]


@dataclass
class KeyFactor:
    """
    A key factor that influenced the investment judgment.

    Each factor is traceable back to its source, enabling
    post-hoc evaluation of information validity.
    """
    factor_type: FactorType
    description: str
    source: str  # e.g., "finnhub_news", "yfinance_price", "earnings_call"
    impact: FactorImpact
    weight: float  # How much this factor influenced the decision (0.0-1.0)
    verifiable: bool  # Can this be verified after the fact?
    raw_data: dict[str, Any] | None = None  # Original data for audit

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "factor_type": self.factor_type,
            "description": self.description,
            "source": self.source,
            "impact": self.impact,
            "weight": self.weight,
            "verifiable": self.verifiable,
            "raw_data": self.raw_data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KeyFactor":
        """Create from dictionary."""
        return cls(
            factor_type=data["factor_type"],
            description=data["description"],
            source=data["source"],
            impact=data["impact"],
            weight=data["weight"],
            verifiable=data.get("verifiable", True),
            raw_data=data.get("raw_data"),
        )


@dataclass
class ReasoningTrace:
    """
    Captures the step-by-step reasoning process.

    This is the core of Chain-of-Thought (CoT) prompting output,
    making the decision process transparent and auditable.
    """
    # Step-by-step thinking process
    steps: list[str]

    # Top factors that drove the decision
    top_factors: list[str]

    # The key moment where the decision was made
    decision_point: str

    # Acknowledged uncertainties
    uncertainties: list[str]

    # Confidence level with explanation
    confidence_explanation: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "steps": self.steps,
            "top_factors": self.top_factors,
            "decision_point": self.decision_point,
            "uncertainties": self.uncertainties,
            "confidence_explanation": self.confidence_explanation,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReasoningTrace":
        """Create from dictionary."""
        return cls(
            steps=data["steps"],
            top_factors=data["top_factors"],
            decision_point=data["decision_point"],
            uncertainties=data.get("uncertainties", []),
            confidence_explanation=data.get("confidence_explanation", ""),
        )


@dataclass
class JudgmentOutput:
    """
    Complete output from the judgment process.

    This is the primary output of Layer 2, containing:
    - The decision itself
    - Full reasoning trace (CoT)
    - Key factors with sources
    - Metadata for tracking
    """
    # Identification
    symbol: str
    strategy_mode: str  # "conservative" or "aggressive"

    # Decision
    decision: JudgmentDecision
    confidence: float  # 0.0-1.0
    score: int  # 0-100, compatible with existing scoring

    # Reasoning (the core of CoT)
    reasoning: ReasoningTrace

    # Factors that influenced the decision
    key_factors: list[KeyFactor]

    # Risk awareness
    identified_risks: list[str]

    # Context
    market_regime: str  # "normal", "adjustment", "crisis"
    input_summary: str  # Summary of input data

    # Metadata
    judged_at: datetime = field(default_factory=datetime.now)
    model_version: str = ""
    prompt_version: str = "v1"

    # Raw LLM output for debugging
    raw_llm_response: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            "symbol": self.symbol,
            "strategy_mode": self.strategy_mode,
            "decision": self.decision,
            "confidence": self.confidence,
            "score": self.score,
            "reasoning_trace": self.reasoning.to_dict(),
            "key_factors": [f.to_dict() for f in self.key_factors],
            "identified_risks": self.identified_risks,
            "market_regime": self.market_regime,
            "input_summary": self.input_summary,
            "judged_at": self.judged_at.isoformat(),
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
            "raw_llm_response": self.raw_llm_response,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JudgmentOutput":
        """Create from dictionary (e.g., from database)."""
        return cls(
            symbol=data["symbol"],
            strategy_mode=data["strategy_mode"],
            decision=data["decision"],
            confidence=data["confidence"],
            score=data["score"],
            reasoning=ReasoningTrace.from_dict(data["reasoning_trace"]),
            key_factors=[KeyFactor.from_dict(f) for f in data["key_factors"]],
            identified_risks=data.get("identified_risks", []),
            market_regime=data.get("market_regime", "normal"),
            input_summary=data.get("input_summary", ""),
            judged_at=datetime.fromisoformat(data["judged_at"]) if isinstance(data["judged_at"], str) else data["judged_at"],
            model_version=data.get("model_version", ""),
            prompt_version=data.get("prompt_version", "v1"),
            raw_llm_response=data.get("raw_llm_response"),
        )

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "JudgmentOutput":
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))

    @property
    def is_actionable(self) -> bool:
        """Whether this judgment suggests taking action (buy)."""
        return self.decision == "buy" and self.confidence >= 0.6

    @property
    def primary_factor(self) -> KeyFactor | None:
        """The factor with the highest weight."""
        if not self.key_factors:
            return None
        return max(self.key_factors, key=lambda f: f.weight)

    def get_factors_by_type(self, factor_type: FactorType) -> list[KeyFactor]:
        """Get all factors of a specific type."""
        return [f for f in self.key_factors if f.factor_type == factor_type]

    def summary(self) -> str:
        """Generate a human-readable summary of the judgment."""
        factors_summary = ", ".join(self.reasoning.top_factors[:3])
        risks_summary = "; ".join(self.identified_risks[:2]) if self.identified_risks else "None identified"

        return (
            f"{self.symbol} [{self.strategy_mode}]: {self.decision.upper()} "
            f"(score={self.score}, confidence={self.confidence:.0%})\n"
            f"  Key factors: {factors_summary}\n"
            f"  Risks: {risks_summary}\n"
            f"  Decision point: {self.reasoning.decision_point}"
        )


# === Portfolio-Level Judgment Models ===


@dataclass
class PortfolioCandidateSummary:
    """Summary of a single candidate for portfolio-level judgment."""
    symbol: str
    composite_score: int
    percentile_rank: int
    price: float
    change_pct: float
    rsi: float | None
    volume_ratio: float | None
    key_signal: str  # "BREAKOUT", "EARNINGS_BEAT", "OVERSOLD", etc.
    top_news_headline: str | None
    news_sentiment: str | None
    sector: str | None


@dataclass
class PortfolioHolding:
    """Current holding info for portfolio context."""
    symbol: str
    strategy_mode: str
    entry_date: str
    pnl_pct: float
    hold_days: int


@dataclass
class StockAllocation:
    """LLM's recommendation for a single stock within portfolio context."""
    symbol: str
    action: str  # "buy" or "skip"
    conviction: float  # 0.0-1.0
    allocation_hint: AllocationHint
    reasoning: str


@dataclass
class PortfolioJudgmentOutput:
    """Complete output from portfolio-level judgment."""
    recommended_buys: list[StockAllocation]
    skipped: list[StockAllocation]
    portfolio_reasoning: str
    risk_assessment: str
    raw_llm_response: str | None = None
    prompt_version: str = "v2_portfolio"


# === Exit Judgment Models ===

ExitDecision = Literal["close", "hold"]


@dataclass
class ExitJudgmentOutput:
    """AI judgment on whether to close or hold a position."""
    symbol: str
    decision: ExitDecision
    confidence: float  # 0.0-1.0
    reasoning: str
    hold_duration_hint: int | None  # Additional days to hold if "hold"
    risks_of_holding: list[str]
    risks_of_closing: list[str]
    raw_llm_response: str | None = None


# === Risk Assessment Models (Ensemble Architecture) ===


@dataclass
class RiskAssessment:
    """LLM risk assessment for a single stock candidate."""
    symbol: str
    risk_score: int  # 1 (very low risk) - 5 (very high risk)
    negative_catalysts: list[str]
    news_interpretation: str
    portfolio_concern: str | None = None


@dataclass
class PortfolioRiskOutput:
    """Complete risk assessment output from LLM."""
    assessments: list[RiskAssessment]
    market_level_risks: str
    sector_concentration_warning: str | None = None
    raw_llm_response: str | None = None


@dataclass
class EnsembleResult:
    """Aggregated ensemble result for a single stock after multi-model voting."""
    symbol: str
    composite_score: int           # Rule-based score
    avg_risk_score: float          # Mean risk across all models
    risk_scores: dict[str, int]    # model_id -> risk_score
    consensus_ratio: float         # Fraction of models with risk <= 3
    final_decision: str            # "buy" or "skip"
    decision_reason: str           # Human-readable decision explanation
