#!/usr/bin/env python3
"""
Weekly Reflection Script

Runs weekly reflection analysis for both strategies:
1. Collects past week's judgments with outcomes
2. Analyzes patterns (success and failure)
3. Generates improvement suggestions
4. Saves results to database

Recommended to run every Sunday evening.
"""
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config
from src.reflection import ReflectionService
from src.batch_logger import BatchLogger, BatchType
from src.logging_config import setup_logging, get_logger

# Setup logging (uses shared config — consistent format across all scripts)
setup_logging()
logger = get_logger(__name__)


def main():
    """Run weekly reflection for both strategies."""
    logger.info("=" * 50)
    logger.info("Starting weekly reflection analysis")
    logger.info(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    logger.info("=" * 50)

    # Start batch logging
    batch_ctx = BatchLogger.start(BatchType.REFLECTION)

    # Check if reflection is enabled
    if not config.llm.enable_reflection:
        logger.info("Reflection is disabled in config, exiting")
        BatchLogger.finish(batch_ctx)
        return

    try:
        reflection_service = ReflectionService()
    except Exception as e:
        logger.error(f"Failed to initialize reflection service: {e}")
        BatchLogger.finish(batch_ctx, error=str(e))
        sys.exit(1)

    # Run for both strategies
    successful_strategies = 0
    failed_strategies = 0

    for strategy in ["conservative", "aggressive", "jp_conservative", "jp_aggressive"]:
        logger.info(f"\n{'='*30}")
        logger.info(f"Reflecting on {strategy} strategy...")
        logger.info(f"{'='*30}")

        try:
            result = reflection_service.run_weekly_reflection(strategy)

            # Log summary
            logger.info(f"\nResults for {strategy}:")
            logger.info(f"  Total judgments: {result.total_judgments}")
            logger.info(f"  Accuracy: {result.accuracy_rate:.0%}")
            logger.info(f"  Buy accuracy: {result.buy_accuracy:.0%}" if result.buy_accuracy else "")
            logger.info(f"  Avoid accuracy: {result.avoid_accuracy:.0%}" if result.avoid_accuracy else "")

            # Log patterns
            if result.success_patterns:
                logger.info(f"\n  Success patterns found: {len(result.success_patterns)}")
                for p in result.success_patterns[:3]:
                    logger.info(f"    - {p.description}")

            if result.failure_patterns:
                logger.info(f"\n  Failure patterns found: {len(result.failure_patterns)}")
                for p in result.failure_patterns[:3]:
                    logger.info(f"    - {p.description}")

            # Log top suggestions
            top_suggestions = result.get_top_suggestions(3)
            if top_suggestions:
                logger.info(f"\n  Top improvement suggestions:")
                for s in top_suggestions:
                    logger.info(f"    [{s.priority.upper()}] {s.suggestion}")

            # Log factor reliability
            reliable = result.get_reliable_factors()
            unreliable = result.get_unreliable_factors()
            if reliable:
                logger.info(f"\n  Reliable factors: {', '.join(f.factor_type for f in reliable)}")
            if unreliable:
                logger.info(f"  Unreliable factors: {', '.join(f.factor_type for f in unreliable)}")

            successful_strategies += 1

        except Exception as e:
            logger.error(f"Reflection failed for {strategy}: {e}")
            failed_strategies += 1
            continue

    logger.info("\n" + "=" * 50)
    logger.info("Weekly reflection completed")
    logger.info("=" * 50)

    # Finish batch logging
    batch_ctx.total_items = 4  # 4 strategies (US + JP)
    batch_ctx.successful_items = successful_strategies
    batch_ctx.failed_items = failed_strategies
    BatchLogger.finish(batch_ctx)


if __name__ == "__main__":
    main()
