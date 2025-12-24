"""
Metrics collection for batch processing.

Collects and logs structured metrics for monitoring and observability.
"""

import logging
import json
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class BatchMetrics:
    """Metrics for a batch processing run."""

    batch_id: str
    start_time: datetime
    end_time: datetime | None
    total_symbols: int
    successful_judgments: int
    failed_judgments: int
    v1_picks_count: int
    v2_picks_count: int

    @property
    def duration_seconds(self) -> float:
        """Calculate batch duration in seconds."""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()

    @property
    def judgment_failure_rate(self) -> float:
        """Calculate the judgment failure rate."""
        total_judgments = self.successful_judgments + self.failed_judgments
        if total_judgments == 0:
            return 0.0
        return self.failed_judgments / total_judgments

    def to_dict(self) -> dict:
        """Convert to dictionary for logging."""
        return {
            "batch_id": self.batch_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_symbols": self.total_symbols,
            "successful_judgments": self.successful_judgments,
            "failed_judgments": self.failed_judgments,
            "v1_picks_count": self.v1_picks_count,
            "v2_picks_count": self.v2_picks_count,
            "duration_seconds": self.duration_seconds,
            "judgment_failure_rate": self.judgment_failure_rate,
        }


def record_batch_metrics(metrics: BatchMetrics) -> None:
    """
    Log metrics in structured format for monitoring.

    Outputs JSON-formatted metrics for easy parsing by log aggregators.

    Args:
        metrics: BatchMetrics instance containing batch execution data.
    """
    metrics_dict = metrics.to_dict()

    # Log structured metrics
    logger.info(
        f"BATCH_METRICS: {json.dumps(metrics_dict, ensure_ascii=False)}"
    )

    # Also log human-readable summary
    logger.info(
        f"Batch {metrics.batch_id} completed in {metrics.duration_seconds:.1f}s: "
        f"{metrics.successful_judgments}/{metrics.successful_judgments + metrics.failed_judgments} judgments succeeded, "
        f"V1={metrics.v1_picks_count} V2={metrics.v2_picks_count} picks"
    )
