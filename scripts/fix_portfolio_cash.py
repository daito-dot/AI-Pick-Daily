#!/usr/bin/env python3
"""
Fix corrupted portfolio cash balance.

Since all positions are closed, the correct cash should be:
Cash = Initial Capital + Sum of all realized PnL

This script recalculates and updates the portfolio_daily_snapshot.
"""
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.supabase_client import SupabaseClient

INITIAL_CAPITAL = 100000.0


def fix_portfolio_cash():
    supabase = SupabaseClient()
    today = datetime.now().strftime("%Y-%m-%d")

    for strategy in ["conservative", "aggressive", "jp_conservative", "jp_aggressive"]:
        print(f"\n=== Fixing {strategy} ===")

        # 1. Get all trade history
        result = supabase._client.table("trade_history").select(
            "pnl, exit_price, shares"
        ).eq("strategy_mode", strategy).execute()

        trades = result.data or []
        total_pnl = sum(float(t.get("pnl", 0)) for t in trades)
        total_proceeds = sum(
            float(t.get("exit_price", 0)) * float(t.get("shares", 0))
            for t in trades
        )

        currency = "¥" if "jp_" in strategy else "$"
        print(f"  Total trades: {len(trades)}")
        print(f"  Total PnL: {currency}{total_pnl:,.0f}")
        print(f"  Total proceeds: {currency}{total_proceeds:,.0f}")

        # 2. Check open positions
        positions = supabase.get_open_positions(strategy)
        positions_value = sum(float(p.get("position_value", 0)) for p in positions)
        print(f"  Open positions: {len(positions)}")
        print(f"  Positions value: {currency}{positions_value:,.0f}")

        # 3. Calculate correct values
        # If no open positions: Cash = Initial + Total PnL
        # If positions: Cash = Initial - invested + closed proceeds
        if len(positions) == 0:
            correct_cash = INITIAL_CAPITAL + total_pnl
            correct_total = correct_cash
        else:
            invested = sum(float(p.get("position_value", 0)) for p in positions)
            correct_cash = INITIAL_CAPITAL - invested + total_proceeds
            correct_total = correct_cash + positions_value

        print(f"  Correct cash: {currency}{correct_cash:,.0f}")
        print(f"  Correct total: {currency}{correct_total:,.0f}")

        # 4. Get current snapshot
        current = supabase.get_latest_portfolio_snapshot(strategy)
        if current:
            print(f"  Current cash: {currency}{current.get('cash_balance', 0):,.0f}")
            print(f"  Current total: {currency}{current.get('total_value', 0):,.0f}")

        # 5. Update snapshot
        cumulative_pnl = correct_total - INITIAL_CAPITAL
        cumulative_pnl_pct = (cumulative_pnl / INITIAL_CAPITAL) * 100

        # Preserve existing S&P500 cumulative (tracked by daily_review.py)
        sp500_cumulative_pct = float(current.get("sp500_cumulative_pct", 0)) if current else 0.0
        alpha = cumulative_pnl_pct - sp500_cumulative_pct

        print(f"  Cumulative PnL: {cumulative_pnl_pct:.2f}%")
        print(f"  Alpha (vs S&P500): {alpha:.2f}%")

        result = supabase._client.table("portfolio_daily_snapshot").upsert({
            "snapshot_date": today,
            "strategy_mode": strategy,
            "total_value": correct_total,
            "cash_balance": correct_cash,
            "positions_value": positions_value,
            "cumulative_pnl": cumulative_pnl,
            "cumulative_pnl_pct": round(cumulative_pnl_pct, 4),
            "sp500_cumulative_pct": sp500_cumulative_pct,
            "alpha": round(alpha, 4),
            "open_positions": len(positions),
        }, on_conflict="snapshot_date,strategy_mode").execute()

        print(f"  ✓ Updated snapshot")

    print("\n=== Fix complete ===")


if __name__ == "__main__":
    fix_portfolio_cash()
