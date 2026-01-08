#!/usr/bin/env python3
"""
Weekly Research Script

Runs comprehensive weekly research:
1. Sector analysis
2. Thematic insights
3. Macro outlook
4. Generates actionable recommendations

Recommended to run every weekend (Saturday/Sunday).
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config
from src.research import DeepResearchService
from src.batch_logger import BatchLogger, BatchType

# Setup logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG if config.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / f"research_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def main():
    """Run weekly research analysis."""
    logger.info("=" * 50)
    logger.info("Starting weekly deep research")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    logger.info("=" * 50)

    # Start batch logging
    batch_ctx = BatchLogger.start(BatchType.WEEKLY_RESEARCH)

    try:
        research_service = DeepResearchService()
    except Exception as e:
        logger.error(f"Failed to initialize research service: {e}")
        BatchLogger.finish(batch_ctx, error=str(e))
        sys.exit(1)

    # Build market context (would normally come from data sources)
    market_context = {
        "regime": "normal",
        "vix": 15.0,  # Placeholder
        "sp500_trend": "up",
    }

    logger.info("Running weekly research...")

    try:
        report = research_service.run_weekly_research(
            market_context=market_context,
            focus_sectors=["Technology", "Healthcare", "Financials", "Industrials", "Energy"],
            focus_themes=["AI Infrastructure", "Interest Rate Sensitivity", "Reshoring/Supply Chain"],
        )

        # Log results
        logger.info(f"\nResearch Report: {report.report_id}")
        logger.info(f"Duration: {report.research_duration_seconds:.1f} seconds")
        logger.info(f"\nExecutive Summary:\n{report.executive_summary}")

        # Sector analyses
        logger.info(f"\n{'='*30}")
        logger.info("Sector Analyses")
        logger.info(f"{'='*30}")
        for sa in report.sector_analyses:
            logger.info(f"\n{sa.sector}: {sa.outlook.upper()} ({sa.confidence:.0%})")
            if sa.tailwinds:
                logger.info(f"  Tailwinds: {', '.join(sa.tailwinds[:2])}")
            if sa.headwinds:
                logger.info(f"  Headwinds: {', '.join(sa.headwinds[:2])}")
            if sa.top_opportunities:
                logger.info(f"  Top picks: {', '.join(sa.top_opportunities)}")

        # Thematic insights
        logger.info(f"\n{'='*30}")
        logger.info("Thematic Insights")
        logger.info(f"{'='*30}")
        for ti in report.thematic_insights:
            logger.info(f"\n{ti.theme}: {ti.relevance.upper()} relevance ({ti.stage})")
            if ti.beneficiaries:
                logger.info(f"  Beneficiaries: {', '.join(ti.beneficiaries)}")

        # Macro outlook
        if report.macro_outlook:
            mo = report.macro_outlook
            logger.info(f"\n{'='*30}")
            logger.info("Macro Outlook")
            logger.info(f"{'='*30}")
            logger.info(f"Outlook: {mo.market_outlook.upper()}")
            logger.info(f"Risk Level: {mo.risk_level}")
            if mo.overweight_sectors:
                logger.info(f"Overweight: {', '.join(mo.overweight_sectors)}")
            if mo.underweight_sectors:
                logger.info(f"Underweight: {', '.join(mo.underweight_sectors)}")

        # Actionable insights
        logger.info(f"\n{'='*30}")
        logger.info("Actionable Insights")
        logger.info(f"{'='*30}")
        for insight in report.actionable_insights:
            logger.info(f"  • {insight}")

        # Stocks to watch
        if report.stocks_to_watch:
            logger.info(f"\nStocks to Watch: {', '.join(report.stocks_to_watch[:10])}")
        if report.stocks_to_avoid:
            logger.info(f"Stocks to Avoid: {', '.join(report.stocks_to_avoid[:10])}")

    except Exception as e:
        logger.error(f"Research failed: {e}")
        import traceback
        traceback.print_exc()
        BatchLogger.finish(batch_ctx, error=str(e))
        sys.exit(1)

    logger.info("\n" + "=" * 50)
    logger.info("Weekly research completed successfully")
    logger.info("=" * 50)

    # Finish batch logging
    batch_ctx.total_items = 1  # 1 research report
    batch_ctx.successful_items = 1
    batch_ctx.failed_items = 0
    BatchLogger.finish(batch_ctx)


if __name__ == "__main__":
    main()
