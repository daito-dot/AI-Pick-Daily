"""Data models for meta-monitor."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RollingMetrics:
    """Rolling performance metrics for a strategy."""

    strategy_mode: str
    metric_date: str
    win_rate_7d: float | None
    win_rate_30d: float | None
    avg_return_7d: float | None
    avg_return_30d: float | None
    missed_rate_7d: float | None
    total_judgments_7d: int
    total_judgments_30d: int
    avg_confidence_7d: float | None = None
    avg_confidence_30d: float | None = None

    def to_dict(self) -> dict:
        return {
            "strategy_mode": self.strategy_mode,
            "metric_date": self.metric_date,
            "win_rate_7d": self.win_rate_7d,
            "win_rate_30d": self.win_rate_30d,
            "avg_return_7d": self.avg_return_7d,
            "avg_return_30d": self.avg_return_30d,
            "missed_rate_7d": self.missed_rate_7d,
            "total_judgments_7d": self.total_judgments_7d,
            "total_judgments_30d": self.total_judgments_30d,
            "avg_confidence_7d": self.avg_confidence_7d,
            "avg_confidence_30d": self.avg_confidence_30d,
        }


@dataclass
class DegradationSignal:
    """A detected performance degradation signal."""

    trigger_type: str  # 'win_rate_drop' | 'missed_spike' | 'return_decline' | 'confidence_drift'
    severity: str  # 'warning' | 'critical'
    current_value: float
    baseline_value: float
    details: str


@dataclass
class Diagnosis:
    """LLM-generated root cause diagnosis."""

    root_causes: list[str]
    recommended_actions: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    raw_response: str = ""


@dataclass
class InterventionResult:
    """Result of executing a meta-intervention."""

    intervention_id: int
    actions_taken: list[dict]
    pre_metrics: dict
