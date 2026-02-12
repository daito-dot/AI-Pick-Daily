"""
Batch Execution Logger

Provides utilities for tracking batch job execution status in the database.
"""
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generator
from uuid import uuid4

from supabase import create_client, Client
from src.config import config


logger = logging.getLogger(__name__)


def _get_supabase_client() -> Client:
    """Get a Supabase client instance."""
    url = config.supabase.url
    key = config.supabase.service_role_key or config.supabase.anon_key

    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")

    return create_client(url, key)


class BatchType(str, Enum):
    """Types of batch jobs."""
    MORNING_SCORING = "morning_scoring"
    EVENING_REVIEW = "evening_review"
    WEEKLY_RESEARCH = "weekly_research"
    LLM_JUDGMENT = "llm_judgment"
    REFLECTION = "reflection"


class ExecutionStatus(str, Enum):
    """Execution status values."""
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


@dataclass
class BatchExecutionContext:
    """Context for tracking batch execution."""
    id: str
    batch_date: str
    batch_type: BatchType
    start_time: float = field(default_factory=time.time)
    total_items: int = 0
    successful_items: int = 0
    failed_items: int = 0
    errors: list[dict] = field(default_factory=list)
    model_used: str | None = None
    analysis_model: str | None = None
    reflection_model: str | None = None
    metadata: dict = field(default_factory=dict)

    def record_success(self, item_id: str | None = None) -> None:
        """Record a successful item processing."""
        self.successful_items += 1
        self.total_items += 1

    def record_failure(
        self,
        item_id: str | None = None,
        error: str | None = None,
        details: dict | None = None,
    ) -> None:
        """Record a failed item processing."""
        self.failed_items += 1
        self.total_items += 1
        if error:
            self.errors.append({
                "item_id": item_id,
                "error": error,
                "details": details,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    def set_total(self, total: int) -> None:
        """Set the total expected items."""
        self.total_items = total

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_items == 0:
            return 0.0
        return self.successful_items / self.total_items

    @property
    def duration_seconds(self) -> int:
        """Get duration in seconds."""
        return int(time.time() - self.start_time)


class BatchLogger:
    """
    Logger for batch job execution status.

    Usage (context manager):
        with BatchLogger.track("morning_scoring") as ctx:
            for item in items:
                try:
                    process(item)
                    ctx.record_success(item.id)
                except Exception as e:
                    ctx.record_failure(item.id, str(e))

    Usage (manual):
        ctx = BatchLogger.start("morning_scoring")
        try:
            # ... do work ...
            ctx.record_success()
            BatchLogger.finish(ctx)
        except Exception as e:
            BatchLogger.finish(ctx, error=str(e))
    """

    @staticmethod
    def start(
        batch_type: BatchType | str,
        batch_date: str | None = None,
        model: str | None = None,
    ) -> BatchExecutionContext:
        """
        Start tracking a batch execution (non-context manager version).

        Args:
            batch_type: Type of batch job
            batch_date: Date for the batch (defaults to today)
            model: Model being used (optional)

        Returns:
            BatchExecutionContext for tracking progress
        """
        if isinstance(batch_type, str):
            batch_type = BatchType(batch_type)

        batch_date = batch_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        execution_id = str(uuid4())

        ctx = BatchExecutionContext(
            id=execution_id,
            batch_date=batch_date,
            batch_type=batch_type,
            model_used=model,
        )

        # Record start
        try:
            BatchLogger._insert_log(ctx, ExecutionStatus.RUNNING)
        except Exception as e:
            logger.warning(f"Failed to insert batch log start: {e}")

        return ctx

    @staticmethod
    def finish(
        ctx: BatchExecutionContext,
        error: str | None = None,
    ) -> None:
        """
        Finish tracking a batch execution.

        Args:
            ctx: The execution context
            error: Error message if failed
        """
        if error:
            ctx.errors.append({
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            BatchLogger._update_log(ctx, ExecutionStatus.FAILED, error)
        else:
            # Determine final status
            if ctx.failed_items == 0 and ctx.successful_items > 0:
                status = ExecutionStatus.SUCCESS
            elif ctx.successful_items > 0 and ctx.failed_items > 0:
                status = ExecutionStatus.PARTIAL_SUCCESS
            elif ctx.successful_items == 0 and ctx.failed_items > 0:
                status = ExecutionStatus.FAILED
            else:
                # No items processed - mark as partial to distinguish from real success
                status = ExecutionStatus.PARTIAL_SUCCESS

            BatchLogger._update_log(ctx, status)

    @staticmethod
    @contextmanager
    def track(
        batch_type: BatchType | str,
        batch_date: str | None = None,
        model: str | None = None,
    ) -> Generator[BatchExecutionContext, None, None]:
        """
        Context manager for tracking batch execution.

        Args:
            batch_type: Type of batch job
            batch_date: Date for the batch (defaults to today)
            model: Model being used (optional)

        Yields:
            BatchExecutionContext for tracking progress
        """
        if isinstance(batch_type, str):
            batch_type = BatchType(batch_type)

        batch_date = batch_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        execution_id = str(uuid4())

        ctx = BatchExecutionContext(
            id=execution_id,
            batch_date=batch_date,
            batch_type=batch_type,
            model_used=model,
        )

        # Record start
        try:
            BatchLogger._insert_log(ctx, ExecutionStatus.RUNNING)
        except Exception as e:
            logger.warning(f"Failed to insert batch log start: {e}")

        try:
            yield ctx

            # Determine final status
            if ctx.failed_items == 0 and ctx.successful_items > 0:
                status = ExecutionStatus.SUCCESS
            elif ctx.successful_items > 0 and ctx.failed_items > 0:
                status = ExecutionStatus.PARTIAL_SUCCESS
            elif ctx.successful_items == 0 and ctx.failed_items > 0:
                status = ExecutionStatus.FAILED
            else:
                # No items processed - mark as partial to distinguish from real success
                status = ExecutionStatus.PARTIAL_SUCCESS

            # Update with final status
            BatchLogger._update_log(ctx, status)

        except Exception as e:
            # Record failure
            ctx.errors.append({
                "error": str(e),
                "type": type(e).__name__,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            BatchLogger._update_log(ctx, ExecutionStatus.FAILED, str(e))
            raise

    @staticmethod
    def _insert_log(ctx: BatchExecutionContext, status: ExecutionStatus) -> None:
        """Insert initial log record, cleaning up stale running records first."""
        try:
            supabase = _get_supabase_client()

            # Clean up any stale 'running' records for this batch_date and batch_type
            # This handles cases where a previous run crashed without updating status
            supabase.table("batch_execution_logs").update({
                "status": ExecutionStatus.FAILED.value,
                "error_message": "Replaced by new run (previous run did not complete)",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq(
                "batch_date", ctx.batch_date
            ).eq(
                "batch_type", ctx.batch_type.value
            ).eq(
                "status", ExecutionStatus.RUNNING.value
            ).execute()

            # Now insert the new record
            record = {
                "id": ctx.id,
                "batch_date": ctx.batch_date,
                "batch_type": ctx.batch_type.value,
                "status": status.value,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "model_used": ctx.model_used,
                "metadata": ctx.metadata,
            }
            if ctx.analysis_model:
                record["analysis_model"] = ctx.analysis_model
            if ctx.reflection_model:
                record["reflection_model"] = ctx.reflection_model
            supabase.table("batch_execution_logs").insert(record).execute()
        except Exception as e:
            logger.error(f"Failed to insert batch log: {e}")

    @staticmethod
    def _update_log(
        ctx: BatchExecutionContext,
        status: ExecutionStatus,
        error_message: str | None = None,
    ) -> None:
        """Update log record with final status."""
        try:
            supabase = _get_supabase_client()

            update_data = {
                "status": status.value,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": ctx.duration_seconds,
                "total_items": ctx.total_items,
                "successful_items": ctx.successful_items,
                "failed_items": ctx.failed_items,
                "model_used": ctx.model_used,
                "metadata": ctx.metadata,
            }
            if ctx.analysis_model:
                update_data["analysis_model"] = ctx.analysis_model
            if ctx.reflection_model:
                update_data["reflection_model"] = ctx.reflection_model

            if error_message:
                update_data["error_message"] = error_message

            if ctx.errors:
                update_data["error_details"] = {"errors": ctx.errors[:10]}  # Limit to 10 errors

            supabase.table("batch_execution_logs").update(update_data).eq(
                "id", ctx.id
            ).execute()

        except Exception as e:
            logger.error(f"Failed to update batch log: {e}")

    @staticmethod
    def get_today_status() -> list[dict]:
        """Get today's batch execution status."""
        try:
            supabase = _get_supabase_client()
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            result = supabase.rpc(
                "get_latest_batch_status",
                {"target_date": today}
            ).execute()

            return result.data or []
        except Exception as e:
            logger.error(f"Failed to get batch status: {e}")
            return []

    @staticmethod
    def get_recent_failures(days: int = 7) -> list[dict]:
        """Get recent failed batch executions."""
        try:
            supabase = _get_supabase_client()

            result = supabase.table("batch_execution_logs").select(
                "id, batch_date, batch_type, status, error_message, "
                "total_items, failed_items, started_at"
            ).in_(
                "status", ["failed", "partial_success"]
            ).order(
                "started_at", desc=True
            ).limit(20).execute()

            return result.data or []
        except Exception as e:
            logger.error(f"Failed to get recent failures: {e}")
            return []
