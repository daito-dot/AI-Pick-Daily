"""
Structured Logging Configuration

Provides JSON-formatted logging with correlation IDs (batch_id) and
consistent log levels across the application.

Features:
- JSON format for production (LOG_FORMAT=json)
- Text format for development (LOG_FORMAT=text, default)
- Correlation ID (batch_id) support
- Symbol tracking per log entry
- ISO 8601 timestamps

Usage:
    from src.logging_config import setup_logging, get_logger

    # At application startup
    setup_logging(batch_id="20241224_090000")

    # Get logger with batch_id context
    logger = get_logger(__name__)
    logger.info("Processing started", extra={"symbol": "AAPL"})
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Thread-local storage for batch_id
import threading

_context = threading.local()


def set_batch_id(batch_id: str) -> None:
    """Set the current batch_id for correlation."""
    _context.batch_id = batch_id


def get_batch_id() -> str | None:
    """Get the current batch_id."""
    return getattr(_context, "batch_id", None)


def clear_batch_id() -> None:
    """Clear the current batch_id."""
    if hasattr(_context, "batch_id"):
        delattr(_context, "batch_id")


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Outputs log records as JSON objects with the following fields:
    - timestamp: ISO 8601 format
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - message: Log message
    - logger: Logger name
    - batch_id: Correlation ID (if set)
    - symbol: Stock symbol (if provided in extra)
    - Additional fields from extra dict
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        # Build the base log entry
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Add batch_id from context if available
        batch_id = get_batch_id()
        if batch_id:
            log_entry["batch_id"] = batch_id

        # Add symbol if provided in extra
        if hasattr(record, "symbol") and record.symbol:
            log_entry["symbol"] = record.symbol

        # Add any extra fields (excluding standard LogRecord attributes)
        standard_attrs = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "pathname", "process", "processName", "relativeCreated",
            "stack_info", "exc_info", "exc_text", "thread", "threadName",
            "message", "symbol",  # Also exclude our custom ones
        }

        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                # Ensure value is JSON serializable
                try:
                    json.dumps(value)
                    log_entry[key] = value
                except (TypeError, ValueError):
                    log_entry[key] = str(value)

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """
    Enhanced text formatter with batch_id support.

    Format: timestamp - logger - level - [batch_id] message
    """

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as text with batch_id prefix."""
        # Add batch_id to message if available
        batch_id = get_batch_id()
        if batch_id:
            # Store original message
            original_msg = record.msg
            record.msg = f"[{batch_id}] {original_msg}"

            # Add symbol if provided
            if hasattr(record, "symbol") and record.symbol:
                record.msg = f"[{batch_id}][{record.symbol}] {original_msg}"

        result = super().format(record)

        # Restore original message to avoid side effects
        if batch_id:
            record.msg = original_msg if "original_msg" in dir() else record.msg

        return result


def setup_logging(
    batch_id: str | None = None,
    log_level: int | str | None = None,
    log_dir: str | Path = "logs",
) -> logging.Logger:
    """
    Setup structured logging for the application.

    Args:
        batch_id: Correlation ID for the batch (optional, can be set later)
        log_level: Logging level (default: from DEBUG env var or INFO)
        log_dir: Directory for log files

    Returns:
        Root logger instance

    Environment Variables:
        LOG_FORMAT: "json" for JSON output, "text" for traditional format (default: text)
        DEBUG: "true" for DEBUG level (default: false)
    """
    # Set batch_id if provided
    if batch_id:
        set_batch_id(batch_id)

    # Determine log format from environment
    log_format = os.getenv("LOG_FORMAT", "text").lower()
    use_json = log_format == "json"

    # Determine log level
    if log_level is None:
        debug_mode = os.getenv("DEBUG", "false").lower() == "true"
        log_level = logging.DEBUG if debug_mode else logging.INFO
    elif isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Generate log filename with date
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_filename = log_path / f"scoring_{today}.log"

    # Create formatters
    if use_json:
        formatter = StructuredFormatter()
    else:
        formatter = TextFormatter()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # File handler
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Stream handler (console)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(log_level)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    # Log setup completion
    root_logger.info(
        "Logging initialized",
        extra={
            "format": "json" if use_json else "text",
            "level": logging.getLevelName(log_level),
            "log_file": str(log_filename),
        }
    )

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    This is a convenience wrapper around logging.getLogger() that ensures
    the logger inherits the structured logging configuration.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter that automatically includes batch_id and symbol.

    Usage:
        logger = LoggerAdapter(logging.getLogger(__name__), symbol="AAPL")
        logger.info("Processing stock")  # Will include symbol in log
    """

    def __init__(
        self,
        logger: logging.Logger,
        symbol: str | None = None,
        extra: dict | None = None,
    ):
        """
        Initialize the adapter.

        Args:
            logger: Base logger instance
            symbol: Stock symbol to include in all logs
            extra: Additional fields to include in all logs
        """
        base_extra = extra or {}
        if symbol:
            base_extra["symbol"] = symbol
        super().__init__(logger, base_extra)

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        """Process the log message and kwargs."""
        # Merge extra from adapter with extra from log call
        extra = kwargs.get("extra", {})
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs


def create_symbol_logger(base_logger: logging.Logger, symbol: str) -> LoggerAdapter:
    """
    Create a logger adapter for a specific symbol.

    This is useful when processing multiple symbols and you want
    each log entry to include the symbol being processed.

    Args:
        base_logger: Base logger instance
        symbol: Stock symbol

    Returns:
        LoggerAdapter configured with the symbol
    """
    return LoggerAdapter(base_logger, symbol=symbol)
