#!/usr/bin/env python3
"""
Daily Review Script

Evening batch job that:
1. Calculates returns for ALL scored stocks (not just picks)
2. Identifies missed opportunities
3. Generates AI reflection using Gemini
4. Saves lessons to database

This enables learning from what we DIDN'T recommend, not just what we did.
"""
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config
from src.data.finnhub_client import FinnhubClient
from src.data.yfinance_client import get_yfinance_client, YFinanceClient
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


def get_current_price(
    finnhub: FinnhubClient,
    yf_client: YFinanceClient,
    symbol: str,
) -> float | None:
    """
    Get current price for a symbol with fallback.

    Args:
        finnhub: Finnhub client
        yf_client: yfinance client
        symbol: Stock symbol

    Returns:
        Current price or None if unavailable
    """
    # Try Finnhub first
    try:
        quote = finnhub.get_quote(symbol)
        if quote.current_price and quote.current_price > 0:
            return quote.current_price
    except Exception as e:
        logger.debug(f"{symbol}: Finnhub quote failed: {e}")

    # Fallback to yfinance
    try:
        yf_quote = yf_client.get_quote(symbol)
        if yf_quote and yf_quote.current_price > 0:
            return yf_quote.current_price
    except Exception as e:
        logger.debug(f"{symbol}: yfinance quote failed: {e}")

    return None


def calculate_all_returns(
    finnhub: FinnhubClient,
    yf_client: YFinanceClient,
    supabase: SupabaseClient,
    days_ago: int = 5,
) -> dict:
    """
    Calculate returns for ALL scored stocks from N days ago.

    Args:
        finnhub: Finnhub client
        yf_client: yfinance client
        supabase: Supabase client
        days_ago: Number of days to look back

    Returns:
        Dict with results summary
    """
    check_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    logger.info(f"Calculating returns for ALL stocks from {check_date}")

    # Get ALL scores from that date
    all_scores = supabase.get_scores_for_review(check_date)
    if not all_scores:
        logger.info(f"No scores found for {check_date}")
        return {"error": "No scores found", "date": check_date}

    logger.info(f"Found {len(all_scores)} stock scores to review")

    # Get the picks for that date to mark was_picked
    picks_data = {}
    for strategy in ["conservative", "aggressive"]:
        picks_result = supabase._client.table("daily_picks").select("symbols").eq(
            "batch_date", check_date
        ).eq(
            "strategy_mode", strategy
        ).execute()
        if picks_result.data:
            picks_data[strategy] = set(picks_result.data[0].get("symbols", []))
        else:
            picks_data[strategy] = set()

    logger.info(f"Picks - Conservative: {picks_data['conservative']}, Aggressive: {picks_data['aggressive']}")

    # Calculate returns for each stock
    updates = []
    results = {
        "date": check_date,
        "days_ago": days_ago,
        "total_stocks": len(all_scores),
        "successful": 0,
        "failed": 0,
        "picked_returns": [],
        "not_picked_returns": [],
        "missed_opportunities": [],
    }

    for score in all_scores:
        symbol = score["symbol"]
        strategy = score["strategy_mode"]
        original_price = score.get("price_at_time", 0)
        composite_score = score.get("composite_score", 0)

        if original_price <= 0:
            logger.warning(f"{symbol}: No original price, skipping")
            results["failed"] += 1
            continue

        # Get current price
        current_price = get_current_price(finnhub, yf_client, symbol)
        if not current_price:
            logger.warning(f"{symbol}: Could not get current price")
            results["failed"] += 1
            continue

        # Calculate return
        return_pct = ((current_price - original_price) / original_price) * 100
        was_picked = symbol in picks_data.get(strategy, set())

        updates.append({
            "batch_date": check_date,
            "symbol": symbol,
            "strategy_mode": strategy,
            "return_5d": return_pct,
            "price_5d": current_price,
            "was_picked": was_picked,
        })

        result_entry = {
            "symbol": symbol,
            "strategy": strategy,
            "score": composite_score,
            "return_pct": round(return_pct, 2),
            "original_price": original_price,
            "current_price": current_price,
        }

        if was_picked:
            results["picked_returns"].append(result_entry)
            logger.info(f"[PICKED] {symbol} ({strategy}): {original_price:.2f} -> {current_price:.2f} ({return_pct:+.1f}%)")
        else:
            results["not_picked_returns"].append(result_entry)
            # Check if this is a missed opportunity (not picked but good return)
            if return_pct >= 3.0:  # 3%+ return is considered significant
                results["missed_opportunities"].append(result_entry)
                logger.warning(f"[MISSED] {symbol} ({strategy}): Score={composite_score}, Return={return_pct:+.1f}%")
            else:
                logger.debug(f"[NOT PICKED] {symbol} ({strategy}): {return_pct:+.1f}%")

        results["successful"] += 1
        time.sleep(0.2)  # Rate limiting

    # Bulk update to database
    if updates:
        updated = supabase.bulk_update_returns(updates)
        logger.info(f"Updated {updated} stock scores with return data")

    return results


def generate_reflection(llm_client, results: dict) -> str:
    """
    Generate AI reflection on today's performance.
    Includes analysis of missed opportunities.
    """
    if results.get("error"):
        return f"No data to review: {results.get('error')}"

    picked = results.get("picked_returns", [])
    not_picked = results.get("not_picked_returns", [])
    missed = results.get("missed_opportunities", [])

    # Calculate stats
    def avg_return(lst):
        if not lst:
            return 0
        return sum(r["return_pct"] for r in lst) / len(lst)

    picked_avg = avg_return(picked)
    not_picked_avg = avg_return(not_picked)
    missed_avg = avg_return(missed)

    wins = len([r for r in picked if r["return_pct"] >= 1])
    losses = len([r for r in picked if r["return_pct"] <= -1])

    context = f"""
## Performance Review ({results['days_ago']}-day, {results['date']})

### Picked Stocks Performance
- Total picked: {len(picked)}
- Wins (≥1%): {wins}
- Losses (≤-1%): {losses}
- Average return: {picked_avg:+.2f}%

### Not Picked Stocks Performance
- Total not picked: {len(not_picked)}
- Average return: {not_picked_avg:+.2f}%

### CRITICAL: Missed Opportunities (≥3% return, NOT picked)
- Count: {len(missed)}
- Average missed return: {missed_avg:+.2f}%
"""

    if missed:
        context += "\nMissed opportunity details:\n"
        for m in sorted(missed, key=lambda x: x["return_pct"], reverse=True)[:5]:
            context += f"- {m['symbol']} ({m['strategy']}): Score={m['score']}, Return={m['return_pct']:+.1f}%\n"

    if picked:
        context += "\nPicked stocks details:\n"
        for p in sorted(picked, key=lambda x: x["return_pct"], reverse=True)[:5]:
            context += f"- {p['symbol']} ({p['strategy']}): Score={p['score']}, Return={p['return_pct']:+.1f}%\n"

    prompt = f"""
You are an AI stock recommendation system reviewing your past performance.

{context}

Based on these results, provide analysis:

1. **Pick Quality**: Were picked stocks better than not-picked? Compare average returns.

2. **Missed Opportunities Analysis**:
   - Why did we miss these stocks? (Score too low? Threshold too high?)
   - What scores did the missed opportunities have vs our threshold?
   - Should we adjust our thresholds?

3. **Threshold Recommendation**:
   - Current V1 threshold: 60, Current V2 threshold: 75
   - Based on missed opportunities, suggest threshold adjustments (be specific with numbers)

4. **One Key Learning**: What's the single most important takeaway?

Be brutally honest. "Recommending nothing" is NOT a success if we missed good opportunities.
Be specific with numbers and actionable recommendations.
"""

    try:
        response = llm_client.generate_with_thinking(prompt)
        return response.content
    except Exception as e:
        logger.error(f"Failed to generate reflection: {e}")
        return f"Failed to generate reflection: {e}"


def save_ai_lesson(
    supabase: SupabaseClient,
    reflection: str,
    missed: list,
    date: str,
):
    """Save AI lesson to database."""
    try:
        missed_symbols = [m["symbol"] for m in missed[:5]]
        miss_analysis = "\n".join([
            f"{m['symbol']}: Score={m['score']}, Return={m['return_pct']:+.1f}%"
            for m in missed[:5]
        ])

        supabase._client.table("ai_lessons").upsert({
            "lesson_date": date,
            "lesson_text": reflection,
            "biggest_miss_symbols": missed_symbols,
            "miss_analysis": miss_analysis,
        }, on_conflict="lesson_date").execute()

        logger.info(f"Saved AI lesson for {date}")
    except Exception as e:
        logger.error(f"Failed to save AI lesson: {e}")


def main():
    """Main review pipeline."""
    logger.info("=" * 60)
    logger.info("Starting daily review batch (ALL STOCKS)")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    logger.info("=" * 60)

    # Initialize clients
    try:
        finnhub = FinnhubClient()
        yf_client = get_yfinance_client()
        supabase = SupabaseClient()
        llm = get_llm_client()
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        sys.exit(1)

    # 1. Calculate returns for ALL stocks (5-day review)
    logger.info("Step 1: Calculating 5-day returns for ALL scored stocks...")
    results_5d = calculate_all_returns(finnhub, yf_client, supabase, days_ago=5)

    if results_5d.get("error"):
        logger.warning(f"No data for 5-day review: {results_5d}")
    else:
        picked = results_5d.get("picked_returns", [])
        not_picked = results_5d.get("not_picked_returns", [])
        missed = results_5d.get("missed_opportunities", [])

        logger.info("5-day results summary:")
        logger.info(f"  - Total reviewed: {results_5d['successful']}")
        logger.info(f"  - Picked stocks: {len(picked)}")
        logger.info(f"  - Not picked: {len(not_picked)}")
        logger.info(f"  - MISSED OPPORTUNITIES: {len(missed)}")

        if missed:
            logger.warning("=" * 40)
            logger.warning("MISSED OPPORTUNITIES DETECTED!")
            for m in missed[:5]:
                logger.warning(f"  {m['symbol']}: Score={m['score']}, +{m['return_pct']:.1f}%")
            logger.warning("=" * 40)

    # 2. Also do 1-day review (for faster feedback)
    logger.info("Step 2: Calculating 1-day returns for ALL scored stocks...")
    results_1d = calculate_all_returns(finnhub, yf_client, supabase, days_ago=1)

    # 3. Generate AI reflection (focus on 5-day results)
    if not results_5d.get("error"):
        logger.info("Step 3: Generating AI reflection...")
        reflection = generate_reflection(llm, results_5d)
        logger.info(f"Reflection:\n{reflection}")

        # 4. Save lesson
        logger.info("Step 4: Saving AI lesson...")
        today = datetime.now().strftime("%Y-%m-%d")
        save_ai_lesson(
            supabase,
            reflection,
            results_5d.get("missed_opportunities", []),
            today,
        )

    # 5. Get and log performance summary
    logger.info("Step 5: Getting overall performance summary...")
    for strategy in ["conservative", "aggressive"]:
        summary = supabase.get_performance_summary(days=30, strategy_mode=strategy)
        logger.info(f"\n{strategy.upper()} Summary (30 days):")
        logger.info(f"  Picked: {summary.get('picked_count', 0)} stocks, avg return: {summary.get('picked_avg_return', 0):.2f}%")
        logger.info(f"  Not Picked: {summary.get('not_picked_count', 0)} stocks, avg return: {summary.get('not_picked_avg_return', 0):.2f}%")
        logger.info(f"  Missed Opportunities (>3%): {summary.get('missed_opportunities', 0)}")

    logger.info("=" * 60)
    logger.info("Daily review batch completed")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
