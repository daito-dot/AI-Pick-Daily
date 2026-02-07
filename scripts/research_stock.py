#!/usr/bin/env python3
"""
Stock Research Script

Fetches current system judgment and scores for stocks.
Supports multiple modes:
- Individual symbol: research_stock.py AAPL
- All picks: research_stock.py all
- Market status: research_stock.py market
- Japan only: research_stock.py jp
- US only: research_stock.py us

Additional commands:
- Save research: research_stock.py AAPL --save
- Record override: research_stock.py override <research_id> <decision> [reason]
- List recent: research_stock.py history [symbol]

Used by the /research Claude Code command.
"""
import argparse
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


# ============================================================
# Mode: Individual Stock
# ============================================================

def get_stock_research_data(symbol: str) -> dict:
    """
    Fetch research data for a stock symbol.

    Args:
        symbol: Stock ticker symbol (e.g., "AAPL", "7203.T")

    Returns:
        Dictionary containing judgment, scores, pick status, and performance.
    """
    client = get_supabase_client()
    symbol = symbol.upper()

    result = {
        "mode": "symbol",
        "symbol": symbol,
        "query_time": datetime.now().isoformat(),
        "latest_judgment": None,
        "latest_scores": [],
        "daily_pick_status": None,
        "historical_performance": None,
    }

    # 1. Get latest LLM judgment
    try:
        judgment_result = client.table("judgment_records").select("*").eq(
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
        perf_result = client.table("performance_log").select("*").eq(
            "symbol", symbol
        ).gte("pick_date", thirty_days_ago).order("pick_date", desc=True).execute()

        if perf_result.data:
            result["historical_performance"] = [{
                "pick_date": p.get("pick_date"),
                "return_pct_5d": p.get("return_pct_5d"),
                "status_5d": p.get("status_5d"),
                "entry_price": p.get("entry_price"),
                "exit_price_5d": p.get("price_5d"),
            } for p in perf_result.data]
    except Exception as e:
        result["performance_error"] = str(e)

    return result


# ============================================================
# Mode: All Picks Summary
# ============================================================

def get_all_picks_summary(market_filter: str | None = None) -> dict:
    """
    Fetch summary of all today's picks.

    Args:
        market_filter: Optional filter - 'jp' for Japan, 'us' for US, None for all

    Returns:
        Dictionary containing picks summary and judgment distribution.
    """
    client = get_supabase_client()
    today = datetime.now().strftime("%Y-%m-%d")

    result = {
        "mode": "all" if not market_filter else market_filter,
        "date": today,
        "query_time": datetime.now().isoformat(),
        "picks_by_strategy": {},
        "judgment_distribution": {"buy": 0, "hold": 0, "avoid": 0},
        "high_confidence_picks": [],
        "total_picks": 0,
        "total_judgments": 0,
    }

    # 1. Get today's picks
    try:
        picks_result = client.table("daily_picks").select("*").eq(
            "batch_date", today
        ).execute()

        if picks_result.data:
            for pick in picks_result.data:
                strategy = pick.get("strategy_mode", "unknown")
                symbols = pick.get("symbols", [])

                # Filter by market if specified
                if market_filter == "jp":
                    symbols = [s for s in symbols if s.endswith(".T") or s.isdigit()]
                    if "jp" not in strategy:
                        continue
                elif market_filter == "us":
                    symbols = [s for s in symbols if not s.endswith(".T") and not s.isdigit()]
                    if "jp" in strategy:
                        continue

                result["picks_by_strategy"][strategy] = {
                    "symbols": symbols,
                    "count": len(symbols),
                    "market_regime": pick.get("market_regime"),
                    "status": pick.get("status"),
                }
                result["total_picks"] += len(symbols)
    except Exception as e:
        result["picks_error"] = str(e)

    # 2. Get today's judgments
    try:
        judgments_result = client.table("judgment_records").select("*").eq(
            "batch_date", today
        ).execute()

        if judgments_result.data:
            for j in judgments_result.data:
                symbol = j.get("symbol", "")

                # Filter by market if specified
                if market_filter == "jp":
                    if not (symbol.endswith(".T") or symbol.replace(".", "").isdigit()):
                        continue
                elif market_filter == "us":
                    if symbol.endswith(".T") or symbol.replace(".", "").isdigit():
                        continue

                decision = j.get("decision", "hold").lower()
                if decision in result["judgment_distribution"]:
                    result["judgment_distribution"][decision] += 1
                result["total_judgments"] += 1

                # Track high confidence picks
                confidence = j.get("confidence", 0)
                if confidence >= 0.75 and decision == "buy":
                    result["high_confidence_picks"].append({
                        "symbol": symbol,
                        "confidence": confidence,
                        "score": j.get("score"),
                        "strategy_mode": j.get("strategy_mode"),
                    })

            # Sort high confidence picks by confidence
            result["high_confidence_picks"].sort(
                key=lambda x: x["confidence"], reverse=True
            )
    except Exception as e:
        result["judgments_error"] = str(e)

    return result


# ============================================================
# Mode: Market Status
# ============================================================

def get_market_status() -> dict:
    """
    Fetch current market regime and status.

    Returns:
        Dictionary containing market regime history and current status.
    """
    client = get_supabase_client()
    today = datetime.now().strftime("%Y-%m-%d")
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    result = {
        "mode": "market",
        "date": today,
        "query_time": datetime.now().isoformat(),
        "current_regime": None,
        "regime_history": [],
        "batch_status": [],
    }

    # 1. Get market regime history
    try:
        regime_result = client.table("market_regime_history").select("*").gte(
            "check_date", seven_days_ago
        ).order("check_date", desc=True).execute()

        if regime_result.data:
            result["current_regime"] = {
                "regime": regime_result.data[0].get("market_regime"),
                "vix_level": regime_result.data[0].get("vix_level"),
                "sp500_sma20_deviation": regime_result.data[0].get("sp500_sma20_deviation_pct"),
                "volatility_flag": regime_result.data[0].get("volatility_cluster_flag"),
                "check_date": regime_result.data[0].get("check_date"),
                "notes": regime_result.data[0].get("notes"),
            }

            result["regime_history"] = [{
                "date": r.get("check_date"),
                "regime": r.get("market_regime"),
                "vix": r.get("vix_level"),
            } for r in regime_result.data[:7]]
    except Exception as e:
        result["regime_error"] = str(e)

    # 2. Get recent batch execution status
    try:
        batch_result = client.table("batch_execution_logs").select("*").gte(
            "started_at", seven_days_ago
        ).order("started_at", desc=True).limit(10).execute()

        if batch_result.data:
            result["batch_status"] = [{
                "batch_type": b.get("batch_type"),
                "model_used": b.get("model_used"),
                "status": b.get("status"),
                "started_at": b.get("started_at"),
                "total_items": b.get("total_items"),
            } for b in batch_result.data]
    except Exception as e:
        result["batch_error"] = str(e)

    return result


# ============================================================
# Output Formatters
# ============================================================

def format_symbol_output(data: dict) -> str:
    """Format individual stock research output."""
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

        risks = j.get('identified_risks')
        if risks:
            lines.append("\n  Identified Risks:")
            if isinstance(risks, list):
                for r in risks[:5]:
                    lines.append(f"    ! {r}")

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
            price = s.get('price_at_time')
            if price:
                lines.append(f"    Price at Time: ${price:.2f}")
            lines.append(f"    Trend: {s.get('trend_score', 'N/A')} | Momentum: {s.get('momentum_score', 'N/A')} | Value: {s.get('value_score', 'N/A')} | Sentiment: {s.get('sentiment_score', 'N/A')}")
            if s.get('breakout_score') is not None:
                lines.append(f"    [V2] Breakout: {s.get('breakout_score')} | Catalyst: {s.get('catalyst_score')} | Risk-Adj: {s.get('risk_adjusted_score')}")
            if s.get('earnings_date'):
                lines.append(f"    Next Earnings: {s.get('earnings_date')}")
    else:
        lines.append("  No score data found")

    # Daily Pick Status
    lines.append("\n## Today's Pick Status")
    if data.get("daily_pick_status"):
        ps = data["daily_pick_status"]
        if ps.get("included"):
            lines.append("  INCLUDED in today's picks")
            lines.append(f"  Strategy: {ps.get('strategy_mode', 'N/A')}")
            lines.append(f"  Market Regime: {ps.get('market_regime', 'N/A')}")
        elif ps.get("no_picks_today"):
            lines.append("  No picks generated today yet")
        else:
            lines.append("  NOT included in today's picks")

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

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


def format_all_output(data: dict) -> str:
    """Format all picks summary output."""
    lines = []
    mode = data["mode"]
    mode_label = {"all": "全体", "jp": "日本株", "us": "米国株"}.get(mode, mode)

    lines.append("=" * 60)
    lines.append(f"Picks Summary: {mode_label} [{data['date']}]")
    lines.append(f"Query Time: {data['query_time']}")
    lines.append("=" * 60)

    # Picks by Strategy
    lines.append("\n## Picks by Strategy")
    if data.get("picks_by_strategy"):
        for strategy, info in data["picks_by_strategy"].items():
            symbols = info.get("symbols", [])
            regime = info.get("market_regime", "N/A")
            lines.append(f"\n  [{strategy.upper()}] ({info.get('count', 0)} picks)")
            lines.append(f"    Regime: {regime}")
            lines.append(f"    Symbols: {', '.join(symbols[:10])}")
            if len(symbols) > 10:
                lines.append(f"    ... and {len(symbols) - 10} more")
    else:
        lines.append("  No picks found for today")

    # Judgment Distribution
    lines.append("\n## Judgment Distribution")
    dist = data.get("judgment_distribution", {})
    total = data.get("total_judgments", 0)
    if total > 0:
        for decision, count in dist.items():
            pct = (count / total) * 100
            lines.append(f"  {decision.upper()}: {count} ({pct:.0f}%)")
    else:
        lines.append("  No judgments found")

    # High Confidence Picks
    lines.append("\n## High Confidence Picks (>= 75%)")
    if data.get("high_confidence_picks"):
        for p in data["high_confidence_picks"][:5]:
            conf = p.get("confidence", 0) * 100
            lines.append(f"  {p.get('symbol')}: {conf:.0f}% (Score: {p.get('score', 'N/A')})")
    else:
        lines.append("  No high confidence picks")

    # Summary
    lines.append("\n## Summary")
    lines.append(f"  Total Picks: {data.get('total_picks', 0)}")
    lines.append(f"  Total Judgments: {data.get('total_judgments', 0)}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


def format_market_output(data: dict) -> str:
    """Format market status output."""
    lines = []

    lines.append("=" * 60)
    lines.append(f"Market Status [{data['date']}]")
    lines.append(f"Query Time: {data['query_time']}")
    lines.append("=" * 60)

    # Current Regime
    lines.append("\n## Current Market Regime")
    if data.get("current_regime"):
        r = data["current_regime"]
        lines.append(f"  Regime: {r.get('regime', 'N/A')}")
        lines.append(f"  VIX Level: {r.get('vix_level', 'N/A')}")
        dev = r.get('sp500_sma20_deviation')
        if dev is not None:
            lines.append(f"  S&P500 SMA20 Deviation: {dev:+.2f}%")
        lines.append(f"  Volatility Flag: {'ON' if r.get('volatility_flag') else 'OFF'}")
        if r.get('notes'):
            lines.append(f"  Notes: {r.get('notes')}")
    else:
        lines.append("  No regime data found")
        if data.get("regime_error"):
            lines.append(f"  Error: {data['regime_error']}")

    # Regime History
    lines.append("\n## Regime History (7 Days)")
    if data.get("regime_history"):
        for r in data["regime_history"]:
            vix = r.get('vix')
            vix_str = f"VIX: {vix:.1f}" if vix else "VIX: N/A"
            lines.append(f"  {r.get('date', 'N/A')}: {r.get('regime', 'N/A')} ({vix_str})")
    else:
        lines.append("  No history available")

    # Batch Status
    lines.append("\n## Recent Batch Executions")
    if data.get("batch_status"):
        for b in data["batch_status"][:5]:
            status_icon = "O" if b.get('status') == 'success' else "X"
            lines.append(f"  [{status_icon}] {b.get('batch_type', 'N/A')} ({b.get('model_used', 'N/A')})")
            lines.append(f"      Started: {b.get('started_at', 'N/A')}")
            total = b.get('total_items')
            if total is not None:
                lines.append(f"      Items: {total}")
    else:
        lines.append("  No batch logs found")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


# ============================================================
# Save & Override Functions
# ============================================================

def save_research_log(
    research_type: str,
    data: dict,
    symbol: str | None = None,
    external_findings: str | None = None,
    news_sentiment: str | None = None,
    sentiment_alignment: str | None = None,
    user_conclusion: str | None = None,
) -> str:
    """
    Save research results to database.

    Returns:
        Research log ID for later override updates.
    """
    client = get_supabase_client()
    today = datetime.now().strftime("%Y-%m-%d")

    # Extract system judgment info if available
    system_judgment = None
    system_confidence = None
    if data.get("latest_judgment"):
        j = data["latest_judgment"]
        system_judgment = j.get("decision", "").upper()
        system_confidence = j.get("confidence")

    record = {
        "research_type": research_type,
        "symbol": symbol,
        "system_data": json.dumps(data, default=str),
        "external_findings": external_findings,
        "news_sentiment": news_sentiment,
        "system_judgment": system_judgment,
        "system_confidence": system_confidence,
        "sentiment_alignment": sentiment_alignment,
        "user_conclusion": user_conclusion,
        "batch_date": today,
    }

    result = client.table("research_logs").insert(record).execute()

    if result.data:
        return result.data[0]["id"]
    raise Exception("Failed to save research log")


def update_research_override(
    research_id: str,
    override_decision: str,
    override_reason: str | None = None,
    external_findings: str | None = None,
    news_sentiment: str | None = None,
    sentiment_alignment: str | None = None,
    user_conclusion: str | None = None,
) -> dict:
    """
    Update a research log with override decision.

    Args:
        research_id: UUID of the research log
        override_decision: buy, hold, avoid, or no_change
        override_reason: Why the decision was overridden
    """
    client = get_supabase_client()

    update_data = {
        "override_decision": override_decision.lower(),
    }
    if override_reason:
        update_data["override_reason"] = override_reason
    if external_findings:
        update_data["external_findings"] = external_findings
    if news_sentiment:
        update_data["news_sentiment"] = news_sentiment
    if sentiment_alignment:
        update_data["sentiment_alignment"] = sentiment_alignment
    if user_conclusion:
        update_data["user_conclusion"] = user_conclusion

    result = client.table("research_logs").update(update_data).eq(
        "id", research_id
    ).execute()

    if result.data:
        return result.data[0]
    raise Exception(f"Failed to update research log {research_id}")


def get_research_history(symbol: str | None = None, limit: int = 10) -> list[dict]:
    """Get recent research history."""
    client = get_supabase_client()

    query = client.table("research_logs").select("*").order(
        "researched_at", desc=True
    ).limit(limit)

    if symbol:
        query = query.eq("symbol", symbol.upper())

    result = query.execute()
    return result.data or []


def format_history_output(records: list[dict]) -> str:
    """Format research history output."""
    lines = []
    lines.append("=" * 60)
    lines.append("Research History")
    lines.append("=" * 60)

    if not records:
        lines.append("\n  No research history found")
    else:
        for r in records:
            lines.append("")
            research_type = r.get("research_type", "unknown")
            symbol = r.get("symbol", "-")
            researched_at = r.get("researched_at", "")[:16]  # Trim to minute

            if research_type == "symbol":
                lines.append(f"  [{symbol}] {researched_at}")
            else:
                lines.append(f"  [{research_type.upper()}] {researched_at}")

            # System judgment at time
            sys_j = r.get("system_judgment")
            sys_c = r.get("system_confidence")
            if sys_j:
                conf_str = f" ({sys_c*100:.0f}%)" if sys_c else ""
                lines.append(f"    System: {sys_j}{conf_str}")

            # Override if any
            override = r.get("override_decision")
            if override and override != "no_change":
                lines.append(f"    Override: {override.upper()}")
                reason = r.get("override_reason")
                if reason:
                    lines.append(f"    Reason: {reason[:50]}...")

            # Sentiment
            sentiment = r.get("news_sentiment")
            alignment = r.get("sentiment_alignment")
            if sentiment or alignment:
                lines.append(f"    News: {sentiment or '-'} | Alignment: {alignment or '-'}")

            # ID for reference
            lines.append(f"    ID: {r.get('id', '-')[:8]}...")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


# ============================================================
# Main
# ============================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Stock Research Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  research_stock.py AAPL              # Research individual stock
  research_stock.py AAPL --save       # Research and save to DB
  research_stock.py all               # All picks summary
  research_stock.py market            # Market status
  research_stock.py jp                # Japan stocks only
  research_stock.py us                # US stocks only
  research_stock.py history           # Show research history
  research_stock.py history AAPL      # Show history for AAPL
  research_stock.py override <id> buy "News was positive"
        """
    )

    parser.add_argument("mode", help="Research mode: SYMBOL, all, market, jp, us, history, override")
    parser.add_argument("args", nargs="*", help="Additional arguments")
    parser.add_argument("--save", action="store_true", help="Save research to database")
    parser.add_argument("--json", action="store_true", help="Output raw JSON only")

    args = parser.parse_args()
    mode = args.mode.lower()

    try:
        # History mode
        if mode == "history":
            symbol = args.args[0].upper() if args.args else None
            records = get_research_history(symbol)
            print(format_history_output(records))
            if args.json:
                print("\n--- Raw JSON ---")
                print(json.dumps(records, indent=2, default=str))
            return

        # Override mode
        if mode == "override":
            if len(args.args) < 2:
                print("Usage: research_stock.py override <research_id> <decision> [reason]")
                print("  decision: buy, hold, avoid, no_change")
                sys.exit(1)

            research_id = args.args[0]
            decision = args.args[1]
            reason = " ".join(args.args[2:]) if len(args.args) > 2 else None

            result = update_research_override(research_id, decision, reason)
            print(f"Updated research {research_id[:8]}...")
            print(f"  Override: {decision.upper()}")
            if reason:
                print(f"  Reason: {reason}")
            return

        # Standard research modes
        if mode == "all":
            data = get_all_picks_summary()
            research_type = "all"
            symbol = None
            if not args.json:
                print(format_all_output(data))

        elif mode == "market":
            data = get_market_status()
            research_type = "market"
            symbol = None
            if not args.json:
                print(format_market_output(data))

        elif mode == "jp":
            data = get_all_picks_summary(market_filter="jp")
            research_type = "jp"
            symbol = None
            if not args.json:
                print(format_all_output(data))

        elif mode == "us":
            data = get_all_picks_summary(market_filter="us")
            research_type = "us"
            symbol = None
            if not args.json:
                print(format_all_output(data))

        else:
            # Individual symbol
            symbol = mode.upper()
            data = get_stock_research_data(symbol)
            research_type = "symbol"
            if not args.json:
                print(format_symbol_output(data))

        # Save if requested
        if args.save:
            research_id = save_research_log(
                research_type=research_type,
                data=data,
                symbol=symbol,
            )
            print(f"\n[Saved] Research ID: {research_id}")
            print("Use this ID to record your decision after external research:")
            print(f"  python scripts/research_stock.py override {research_id[:8]} buy 'reason'")

        # JSON output
        if args.json or not args.save:
            print("\n--- Raw JSON ---")
            print(json.dumps(data, indent=2, default=str))

    except ValueError as e:
        print(f"Configuration Error: {e}")
        print("Make sure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
