#!/usr/bin/env python3
"""
Daily Review Script

Evening batch job that:
1. Evaluates past recommendations
2. Calculates win/loss rates
3. Generates AI reflection using Gemini 3 Flash
4. Updates agent weights (Phase 2)
5. Saves lessons to database
"""
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config
from src.data.finnhub_client import FinnhubClient
from src.data.supabase_client import SupabaseClient
from src.llm import get_llm_client

# Setup logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG if config.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / f"review_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def calculate_returns(
    finnhub: FinnhubClient,
    supabase: SupabaseClient,
    days_ago: int = 5,
) -> list[dict]:
    """
    Calculate returns for picks made N days ago.

    Args:
        finnhub: Finnhub client
        supabase: Supabase client
        days_ago: Number of days to look back

    Returns:
        List of performance records
    """
    check_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    logger.info(f"Checking returns for picks from {check_date}")

    picks = supabase.get_daily_picks(check_date)
    if not picks or not picks.get("symbols"):
        logger.info(f"No picks found for {check_date}")
        return []

    symbols = picks["symbols"]
    results = []

    for symbol in symbols:
        try:
            # Get current price
            quote = finnhub.get_quote(symbol)
            current_price = quote.current_price

            # Get original price from stock_scores
            scores = supabase.get_stock_scores(check_date)
            original_score = next(
                (s for s in scores if s["symbol"] == symbol),
                None,
            )

            if not original_score:
                continue

            original_price = original_score.get("price_at_time", 0)
            if original_price <= 0:
                continue

            # Calculate return
            return_pct = ((current_price - original_price) / original_price) * 100

            # Determine status
            if return_pct >= 1:
                status = "win"
            elif return_pct <= -1:
                status = "loss"
            else:
                status = "flat"

            results.append({
                "symbol": symbol,
                "pick_date": check_date,
                "original_price": original_price,
                "current_price": current_price,
                "return_pct": round(return_pct, 2),
                "status": status,
                "composite_score": original_score.get("composite_score", 0),
            })

            logger.info(f"{symbol}: {original_price:.2f} -> {current_price:.2f} ({return_pct:+.1f}%) = {status}")

        except Exception as e:
            logger.error(f"Error calculating return for {symbol}: {e}")

    return results


def generate_reflection(llm_client, results: list[dict]) -> str:
    """
    Generate AI reflection on today's performance.

    Uses Gemini 3 Flash with thinking mode for analysis.
    """
    if not results:
        return "No picks to review today."

    # Prepare context
    wins = [r for r in results if r["status"] == "win"]
    losses = [r for r in results if r["status"] == "loss"]

    context = f"""
## Performance Summary (5-day review)

**Total Picks:** {len(results)}
**Wins:** {len(wins)} ({len(wins)/len(results)*100:.0f}%)
**Losses:** {len(losses)} ({len(losses)/len(results)*100:.0f}%)

### Details:
"""

    for r in results:
        context += f"- {r['symbol']}: {r['return_pct']:+.1f}% ({r['status']})\n"

    # Generate reflection with thinking
    prompt = f"""
You are an AI stock recommendation system reviewing your past performance.

{context}

Based on these results, provide a brief analysis:
1. What worked well?
2. What didn't work?
3. What pattern do you notice?
4. One specific improvement for tomorrow.

Be concise (3-5 sentences). Focus on actionable insights.
Do not make excuses. Be honest about failures.
"""

    try:
        response = llm_client.generate_with_thinking(prompt)
        return response.content
    except Exception as e:
        logger.error(f"Failed to generate reflection: {e}")
        return f"Failed to generate reflection: {e}"


def main():
    """Main review pipeline."""
    logger.info("=" * 50)
    logger.info("Starting daily review batch")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    logger.info("=" * 50)

    # Initialize clients
    try:
        finnhub = FinnhubClient()
        supabase = SupabaseClient()
        llm = get_llm_client()
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        sys.exit(1)

    # 1. Calculate returns for 5-day-old picks
    logger.info("Step 1: Calculating 5-day returns...")
    results_5d = calculate_returns(finnhub, supabase, days_ago=5)

    if results_5d:
        wins = len([r for r in results_5d if r["status"] == "win"])
        losses = len([r for r in results_5d if r["status"] == "loss"])
        logger.info(f"5-day results: {wins} wins, {losses} losses")

        # Save performance logs
        for result in results_5d:
            supabase.save_performance_log({
                "pick_date": result["pick_date"],
                "symbol": result["symbol"],
                "recommendation_open_price": result["original_price"],
                "check_date_5d": datetime.now().strftime("%Y-%m-%d"),
                "price_5d": result["current_price"],
                "return_pct_5d": result["return_pct"],
                "status_5d": result["status"],
            })

    # 2. Generate AI reflection
    logger.info("Step 2: Generating AI reflection...")
    reflection = generate_reflection(llm, results_5d)
    logger.info(f"Reflection:\n{reflection}")

    # 3. Save lesson
    if results_5d:
        today = datetime.now().strftime("%Y-%m-%d")
        biggest_misses = [
            r["symbol"] for r in sorted(results_5d, key=lambda x: x["return_pct"])[:3]
            if r["status"] == "loss"
        ]

        # Would save to ai_lessons table
        logger.info(f"Biggest misses: {biggest_misses}")

    logger.info("=" * 50)
    logger.info("Daily review batch completed")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
