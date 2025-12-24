"""
Alert notification system for batch processing.

Checks metrics against thresholds and sends alerts when issues are detected.
"""

import logging
from enum import Enum

from .metrics import BatchMetrics

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# Threshold constants
JUDGMENT_FAILURE_RATE_THRESHOLD = 0.2  # 20%
BATCH_DURATION_THRESHOLD_SECONDS = 1800  # 30 minutes
MIN_PICKS_WARNING_THRESHOLD = 1  # Warn if fewer than this many picks


def check_and_alert(metrics: BatchMetrics) -> list[str]:
    """
    Check metrics and return alert messages if thresholds exceeded.

    Args:
        metrics: BatchMetrics instance to check.

    Returns:
        List of alert messages for any threshold violations.
    """
    alerts = []

    # Check judgment failure rate
    if metrics.judgment_failure_rate > JUDGMENT_FAILURE_RATE_THRESHOLD:
        alerts.append(
            f"LLM judgment failure rate > {JUDGMENT_FAILURE_RATE_THRESHOLD * 100:.0f}% "
            f"(actual: {metrics.judgment_failure_rate * 100:.1f}%)"
        )

    # Check batch duration
    if metrics.duration_seconds > BATCH_DURATION_THRESHOLD_SECONDS:
        alerts.append(
            f"Batch duration > {BATCH_DURATION_THRESHOLD_SECONDS // 60} minutes "
            f"(actual: {metrics.duration_seconds / 60:.1f} minutes)"
        )

    # Check for zero picks (might indicate a problem)
    total_picks = metrics.v1_picks_count + metrics.v2_picks_count
    if total_picks == 0 and metrics.total_symbols > 0:
        alerts.append(
            f"No picks generated from {metrics.total_symbols} symbols"
        )

    # Check for very few picks (warning level)
    if 0 < total_picks < MIN_PICKS_WARNING_THRESHOLD:
        alerts.append(
            f"Very few picks generated: V1={metrics.v1_picks_count}, V2={metrics.v2_picks_count}"
        )

    return alerts


def send_alert(message: str, level: AlertLevel) -> None:
    """
    Send alert notification.

    Currently logs the alert. Can be extended to send to Slack, email, etc.

    Args:
        message: Alert message text.
        level: Severity level of the alert.
    """
    log_prefix = f"[ALERT:{level.value.upper()}]"

    if level == AlertLevel.CRITICAL:
        logger.critical(f"{log_prefix} {message}")
    elif level == AlertLevel.WARNING:
        logger.warning(f"{log_prefix} {message}")
    else:
        logger.info(f"{log_prefix} {message}")

    # Future extension point: send to external services
    # e.g., Slack webhook, email, PagerDuty, etc.
    # if config.alerts.slack_webhook_url:
    #     _send_slack_alert(message, level)


def process_alerts(metrics: BatchMetrics) -> None:
    """
    Check metrics and send any necessary alerts.

    Convenience function that combines check_and_alert with send_alert.

    Args:
        metrics: BatchMetrics instance to check and alert on.
    """
    alerts = check_and_alert(metrics)

    for alert_message in alerts:
        # Determine severity based on content
        if "failure rate" in alert_message.lower() or "no picks" in alert_message.lower():
            level = AlertLevel.WARNING
        elif "duration" in alert_message.lower():
            level = AlertLevel.WARNING
        else:
            level = AlertLevel.INFO

        send_alert(alert_message, level)
