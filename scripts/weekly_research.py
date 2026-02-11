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
from src.data.yfinance_client import get_yfinance_client
from src.data.supabase_client import SupabaseClient
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

    # Build market context from live data
    market_context = _build_market_context()

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

    # Save research insights to database for judgment prompt injection
    _save_research_to_db(report)

    logger.info("\n" + "=" * 50)
    logger.info("Weekly research completed successfully")
    logger.info("=" * 50)

    # Finish batch logging
    batch_ctx.total_items = 1  # 1 research report
    batch_ctx.successful_items = 1
    batch_ctx.failed_items = 0
    BatchLogger.finish(batch_ctx)


def _save_research_to_db(report) -> None:
    """Save weekly research insights to research_logs for judgment injection."""
    try:
        supabase = SupabaseClient()
        today = datetime.utcnow().strftime("%Y-%m-%d")

        # Build a concise summary for judgment prompt consumption
        summary_parts = []
        if report.executive_summary:
            summary_parts.append(report.executive_summary[:500])

        for insight in (report.actionable_insights or [])[:5]:
            summary_parts.append(f"- {insight}")

        if report.macro_outlook:
            mo = report.macro_outlook
            summary_parts.append(
                f"Macro: {mo.market_outlook} outlook, risk={mo.risk_level}"
            )
            if mo.overweight_sectors:
                summary_parts.append(f"Overweight: {', '.join(mo.overweight_sectors)}")
            if mo.underweight_sectors:
                summary_parts.append(f"Underweight: {', '.join(mo.underweight_sectors)}")

        content = "\n".join(summary_parts)

        # Collect all mentioned symbols
        symbols = list(set(
            (report.stocks_to_watch or []) + (report.stocks_to_avoid or [])
        ))

        # Sector outlook metadata
        sector_data = {}
        for sa in (report.sector_analyses or []):
            sector_data[sa.sector] = {
                "outlook": sa.outlook,
                "confidence": sa.confidence,
                "top_opportunities": sa.top_opportunities[:3] if sa.top_opportunities else [],
            }

        # TODO: JP market weekly research not yet implemented
        supabase._client.table("research_logs").insert({
            "research_type": "market",
            "market_type": "us",
            "content": content,
            "metadata": {
                "sectors": sector_data,
                "stocks_to_watch": report.stocks_to_watch or [],
                "stocks_to_avoid": report.stocks_to_avoid or [],
            },
            "symbols_mentioned": symbols[:20],
            "research_date": today,
            "model_version": config.llm.deep_research_model,
        }).execute()

        logger.info(f"Saved weekly research to research_logs ({len(content)} chars, {len(symbols)} symbols)")
    except Exception as e:
        logger.warning(f"Failed to save research to DB: {e}")


def _build_market_context() -> dict:
    """Build market context from live data sources."""
    context = {"regime": "normal", "vix": 15.0, "sp500_trend": "up"}

    try:
        yf_client = get_yfinance_client()
        vix = yf_client.get_vix()
        if vix is not None:
            context["vix"] = vix
            logger.info(f"VIX: {vix:.1f}")

        sp500_return = yf_client.get_sp500_daily_return()
        if sp500_return is not None:
            context["sp500_trend"] = "up" if sp500_return >= 0 else "down"
    except Exception as e:
        logger.warning(f"Failed to get yfinance data, using defaults: {e}")

    try:
        supabase = SupabaseClient()
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        regime = supabase.get_market_regime(today)
        if regime and regime.get("market_regime"):
            context["regime"] = regime["market_regime"]
            logger.info(f"Market regime: {context['regime']}")
    except Exception as e:
        logger.warning(f"Failed to get market regime, using default: {e}")

    logger.info(f"Market context: {context}")
    return context


if __name__ == "__main__":
    main()
