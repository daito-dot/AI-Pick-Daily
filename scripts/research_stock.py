#!/usr/bin/env python3
"""
Stock Research Script

Fetches current system judgment and scores for a given stock symbol.
Used by the /research Claude Code command.
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from supabase import create_client


def get_supabase_client():
    """Get Supabase client from environment variables."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY")

    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")

    return create_client(url, key)


def get_stock_research_data(symbol: str) -> dict:
    """
    Fetch research data for a stock symbol.

    Args:
        symbol: Stock ticker symbol (e.g., "AAPL", "7203.T")

    Returns:
        Dictionary containing:
        - latest_judgment: Most recent LLM judgment
        - latest_scores: Most recent rule-based scores (V1 and V2)
        - daily_pick_status: Whether included in today's picks
        - historical_performance: Past pick performance if available
    """
    client = get_supabase_client()
    symbol = symbol.upper()

    result = {
        "symbol": symbol,
        "query_time": datetime.now().isoformat(),
        "latest_judgment": None,
        "latest_scores": [],
        "daily_pick_status": None,
        "historical_performance": None,
    }

    # 1. Get latest LLM judgment
    try:
        judgment_result = client.table("llm_judgments").select("*").eq(
            "symbol", symbol
        ).order("created_at", desc=True).limit(1).execute()

        if judgment_result.data:
            j = judgment_result.data[0]
            result["latest_judgment"] = {
                "decision": j.get("decision"),
                "confidence": j.get("confidence"),
                "score": j.get("score"),
                "reasoning": j.get("reasoning"),
                "key_factors": j.get("key_factors"),
                "identified_risks": j.get("identified_risks"),
                "strategy_mode": j.get("strategy_mode"),
                "model_version": j.get("model_version"),
                "batch_date": j.get("batch_date"),
                "created_at": j.get("created_at"),
            }
    except Exception as e:
        result["judgment_error"] = str(e)

    # 2. Get latest rule-based scores (both V1 and V2)
    try:
        scores_result = client.table("stock_scores").select("*").eq(
            "symbol", symbol
        ).order("batch_date", desc=True).limit(2).execute()

        if scores_result.data:
            for s in scores_result.data:
                result["latest_scores"].append({
                    "strategy_mode": s.get("strategy_mode"),
                    "composite_score": s.get("composite_score"),
                    "percentile_rank": s.get("percentile_rank"),
                    "trend_score": s.get("trend_score"),
                    "momentum_score": s.get("momentum_score"),
                    "value_score": s.get("value_score"),
                    "sentiment_score": s.get("sentiment_score"),
                    "price_at_time": s.get("price_at_time"),
                    "batch_date": s.get("batch_date"),
                    "reasoning": s.get("reasoning"),
                    # V2 specific
                    "breakout_score": s.get("breakout_score"),
                    "catalyst_score": s.get("catalyst_score"),
                    "risk_adjusted_score": s.get("risk_adjusted_score"),
                    "earnings_date": s.get("earnings_date"),
                })
    except Exception as e:
        result["scores_error"] = str(e)

    # 3. Check if in today's daily picks
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        picks_result = client.table("daily_picks").select("*").eq(
            "batch_date", today
        ).execute()

        if picks_result.data:
            for pick in picks_result.data:
                symbols = pick.get("symbols", [])
                if symbol in symbols:
                    result["daily_pick_status"] = {
                        "included": True,
                        "strategy_mode": pick.get("strategy_mode"),
                        "market_regime": pick.get("market_regime"),
                        "status": pick.get("status"),
                    }
                    break
            else:
                result["daily_pick_status"] = {"included": False}
        else:
            result["daily_pick_status"] = {"included": False, "no_picks_today": True}
    except Exception as e:
        result["picks_error"] = str(e)

    # 4. Get historical performance (past 30 days)
    try:
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        perf_result = client.table("pick_performance").select("*").eq(
            "symbol", symbol
        ).gte("pick_date", thirty_days_ago).order("pick_date", desc=True).execute()

        if perf_result.data:
            result["historical_performance"] = [{
                "pick_date": p.get("pick_date"),
                "return_pct_5d": p.get("return_pct_5d"),
                "status_5d": p.get("status_5d"),
                "entry_price": p.get("entry_price"),
                "exit_price_5d": p.get("exit_price_5d"),
            } for p in perf_result.data]
    except Exception as e:
        result["performance_error"] = str(e)

    return result


def format_output(data: dict) -> str:
    """Format the research data for display."""
    lines = []
    symbol = data["symbol"]

    lines.append("=" * 60)
    lines.append(f"Stock Research Data: {symbol}")
    lines.append(f"Query Time: {data['query_time']}")
    lines.append("=" * 60)

    # Latest Judgment
    lines.append("\n## Latest LLM Judgment")
    if data.get("latest_judgment"):
        j = data["latest_judgment"]
        lines.append(f"  Decision: {j.get('decision', 'N/A').upper()}")
        conf = j.get('confidence')
        lines.append(f"  Confidence: {conf * 100:.0f}%" if conf else "  Confidence: N/A")
        lines.append(f"  Score: {j.get('score', 'N/A')}")
        lines.append(f"  Strategy: {j.get('strategy_mode', 'N/A')}")
        lines.append(f"  Model: {j.get('model_version', 'N/A')}")
        lines.append(f"  Batch Date: {j.get('batch_date', 'N/A')}")

        # Key Factors
        kf = j.get('key_factors')
        if kf:
            lines.append("\n  Key Factors:")
            if isinstance(kf, list):
                for f in kf[:5]:
                    if isinstance(f, dict):
                        impact = f.get('impact', 'neutral')
                        icon = '+' if impact == 'positive' else '-' if impact == 'negative' else '='
                        lines.append(f"    {icon} {f.get('description', 'N/A')}")
                    else:
                        lines.append(f"    - {f}")

        # Risks
        risks = j.get('identified_risks')
        if risks:
            lines.append("\n  Identified Risks:")
            if isinstance(risks, list):
                for r in risks[:5]:
                    lines.append(f"    ! {r}")

        # Reasoning
        reasoning = j.get('reasoning')
        if reasoning and isinstance(reasoning, dict):
            if reasoning.get('decision_point'):
                lines.append(f"\n  Decision Point: {reasoning['decision_point']}")
    else:
        lines.append("  No judgment data found")
        if data.get("judgment_error"):
            lines.append(f"  Error: {data['judgment_error']}")

    # Latest Scores
    lines.append("\n## Latest Rule-Based Scores")
    if data.get("latest_scores"):
        for s in data["latest_scores"]:
            strategy = s.get('strategy_mode', 'unknown')
            lines.append(f"\n  [{strategy.upper()}] (Batch: {s.get('batch_date', 'N/A')})")
            lines.append(f"    Composite Score: {s.get('composite_score', 'N/A')} pts")
            lines.append(f"    Percentile Rank: {s.get('percentile_rank', 'N/A')}%")
            lines.append(f"    Price at Time: ${s.get('price_at_time', 'N/A')}")
            lines.append(f"    Trend: {s.get('trend_score', 'N/A')} | Momentum: {s.get('momentum_score', 'N/A')} | Value: {s.get('value_score', 'N/A')} | Sentiment: {s.get('sentiment_score', 'N/A')}")
            if s.get('breakout_score') is not None:
                lines.append(f"    [V2] Breakout: {s.get('breakout_score')} | Catalyst: {s.get('catalyst_score')} | Risk-Adj: {s.get('risk_adjusted_score')}")
            if s.get('earnings_date'):
                lines.append(f"    Next Earnings: {s.get('earnings_date')}")
    else:
        lines.append("  No score data found")
        if data.get("scores_error"):
            lines.append(f"  Error: {data['scores_error']}")

    # Daily Pick Status
    lines.append("\n## Today's Pick Status")
    if data.get("daily_pick_status"):
        ps = data["daily_pick_status"]
        if ps.get("included"):
            lines.append(f"  INCLUDED in today's picks")
            lines.append(f"  Strategy: {ps.get('strategy_mode', 'N/A')}")
            lines.append(f"  Market Regime: {ps.get('market_regime', 'N/A')}")
            lines.append(f"  Status: {ps.get('status', 'N/A')}")
        elif ps.get("no_picks_today"):
            lines.append("  No picks generated today yet")
        else:
            lines.append("  NOT included in today's picks")
    else:
        lines.append("  Status unknown")
        if data.get("picks_error"):
            lines.append(f"  Error: {data['picks_error']}")

    # Historical Performance
    lines.append("\n## Recent Performance (Past 30 Days)")
    if data.get("historical_performance"):
        for p in data["historical_performance"][:5]:
            ret = p.get('return_pct_5d')
            status = p.get('status_5d', 'unknown')
            ret_str = f"{ret:+.2f}%" if ret is not None else "N/A"
            icon = "W" if status == 'win' else "L" if status == 'loss' else "?"
            lines.append(f"  [{icon}] {p.get('pick_date', 'N/A')}: {ret_str}")
    else:
        lines.append("  No recent performance data")
        if data.get("performance_error"):
            lines.append(f"  Error: {data['performance_error']}")

    lines.append("\n" + "=" * 60)

    return "\n".join(lines)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: research_stock.py <SYMBOL>")
        print("Example: research_stock.py AAPL")
        print("         research_stock.py 7203.T")
        sys.exit(1)

    symbol = sys.argv[1]

    try:
        data = get_stock_research_data(symbol)

        # Output both formatted text and JSON for flexibility
        print(format_output(data))
        print("\n--- Raw JSON ---")
        print(json.dumps(data, indent=2, default=str))

    except ValueError as e:
        print(f"Configuration Error: {e}")
        print("Make sure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
