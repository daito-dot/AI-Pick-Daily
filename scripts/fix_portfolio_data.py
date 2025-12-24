#!/usr/bin/env python3
"""
Portfolio Data Fix Script

This script fixes corrupted portfolio data by recalculating from first principles:
- Cash = INITIAL_CAPITAL - (current positions cost) + (realized PnL from trades)
- Total = Cash + Positions Value

Usage:
    python scripts/fix_portfolio_data.py [--market us|jp|all] [--dry-run]
"""

import argparse
import sys
from datetime import datetime

sys.path.insert(0, ".")

from src.data.supabase_client import SupabaseClient

INITIAL_CAPITAL = 100000.0

STRATEGY_MODES = {
    "us": ["conservative", "aggressive"],
    "jp": ["jp_conservative", "jp_aggressive"],
}


def get_strategy_modes(market: str) -> list[str]:
    if market == "all":
        return STRATEGY_MODES["us"] + STRATEGY_MODES["jp"]
    return STRATEGY_MODES.get(market, [])


def get_open_positions(supabase: SupabaseClient, strategy_mode: str) -> list[dict]:
    """Get all open positions for a strategy."""
    result = supabase._client.table("virtual_portfolio").select("*").eq(
        "strategy_mode", strategy_mode
    ).is_("closed_at", "null").execute()
    return result.data or []


def get_realized_pnl(supabase: SupabaseClient, strategy_mode: str) -> float:
    """Get total realized PnL from closed trades."""
    result = supabase._client.table("trade_history").select("pnl").eq(
        "strategy_mode", strategy_mode
    ).execute()

    if not result.data:
        return 0.0

    return sum(float(t.get("pnl", 0) or 0) for t in result.data)


def get_invested_cost(positions: list[dict]) -> float:
    """Get total cost of current positions."""
    return sum(float(p.get("position_value", 0) or 0) for p in positions)


def get_current_snapshot(supabase: SupabaseClient, strategy_mode: str) -> dict:
    """Get the latest portfolio snapshot."""
    result = supabase._client.table("portfolio_daily_snapshot").select("*").eq(
        "strategy_mode", strategy_mode
    ).order("snapshot_date", desc=True).limit(1).execute()
    return result.data[0] if result.data else {}


def calculate_correct_values(
    positions: list[dict],
    realized_pnl: float,
) -> dict:
    """Calculate correct portfolio values from first principles."""

    # Cost of open positions
    invested_cost = get_invested_cost(positions)

    # Correct cash = Initial - Invested + Realized PnL
    correct_cash = INITIAL_CAPITAL - invested_cost + realized_pnl

    # Positions value (at current/entry price)
    positions_value = invested_cost  # For simplicity, use entry value

    # Total value
    total_value = correct_cash + positions_value

    # Cumulative PnL
    cumulative_pnl = total_value - INITIAL_CAPITAL
    cumulative_pnl_pct = (cumulative_pnl / INITIAL_CAPITAL) * 100

    return {
        "cash_balance": round(correct_cash, 2),
        "positions_value": round(positions_value, 2),
        "total_value": round(total_value, 2),
        "open_positions": len(positions),
        "cumulative_pnl": round(cumulative_pnl, 2),
        "cumulative_pnl_pct": round(cumulative_pnl_pct, 4),
    }


def fix_snapshot(
    supabase: SupabaseClient,
    strategy_mode: str,
    correct_values: dict,
    dry_run: bool = False,
) -> dict:
    """Update the portfolio snapshot with correct values."""
    today = datetime.now().strftime("%Y-%m-%d")
    market_type = "jp" if strategy_mode.startswith("jp_") else "us"

    record = {
        "snapshot_date": today,
        "strategy_mode": strategy_mode,
        "market_type": market_type,
        "total_value": correct_values["total_value"],
        "cash_balance": correct_values["cash_balance"],
        "positions_value": correct_values["positions_value"],
        "open_positions": correct_values["open_positions"],
        "cumulative_pnl": correct_values["cumulative_pnl"],
        "cumulative_pnl_pct": correct_values["cumulative_pnl_pct"],
        "daily_pnl": 0,
        "daily_pnl_pct": 0,
        "sp500_cumulative_pct": 0,
        "alpha": correct_values["cumulative_pnl_pct"],
    }

    if dry_run:
        return record

    result = supabase._client.table("portfolio_daily_snapshot").upsert(
        record,
        on_conflict="snapshot_date,strategy_mode",
    ).execute()

    return result.data[0] if result.data else record


def main():
    parser = argparse.ArgumentParser(description="Fix portfolio data")
    parser.add_argument(
        "--market",
        choices=["us", "jp", "all"],
        default="all",
        help="Which market to fix (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without actually changing",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("Portfolio Data Fix Script")
    print("=" * 70)
    print(f"Market: {args.market}")
    print(f"Dry run: {args.dry_run}")
    print()

    supabase = SupabaseClient()
    strategy_modes = get_strategy_modes(args.market)

    for mode in strategy_modes:
        print(f"--- {mode} ---")

        # Get current data
        positions = get_open_positions(supabase, mode)
        realized_pnl = get_realized_pnl(supabase, mode)
        current_snapshot = get_current_snapshot(supabase, mode)

        # Calculate correct values
        correct = calculate_correct_values(positions, realized_pnl)

        # Show comparison
        print(f"  Open positions: {len(positions)}")
        print(f"  Realized PnL (from trades): ${realized_pnl:,.2f}")
        print()

        current_total = current_snapshot.get("total_value", 0)
        current_cash = current_snapshot.get("cash_balance", 0)
        current_pnl = current_snapshot.get("cumulative_pnl_pct", 0)

        print("  Current (corrupted):")
        print(f"    Total:    ${current_total:>12,.2f}")
        print(f"    Cash:     ${current_cash:>12,.2f}")
        print(f"    PnL:      {current_pnl:>12.2f}%")
        print()

        print("  Correct (calculated):")
        print(f"    Total:    ${correct['total_value']:>12,.2f}")
        print(f"    Cash:     ${correct['cash_balance']:>12,.2f}")
        print(f"    Positions:${correct['positions_value']:>12,.2f}")
        print(f"    PnL:      {correct['cumulative_pnl_pct']:>12.2f}%")
        print()

        # Show difference
        diff_total = correct["total_value"] - current_total
        diff_pnl = correct["cumulative_pnl_pct"] - current_pnl

        if abs(diff_total) > 0.01 or abs(diff_pnl) > 0.01:
            print(f"  Difference:")
            print(f"    Total:    ${diff_total:>+12,.2f}")
            print(f"    PnL:      {diff_pnl:>+12.2f}%")
            print()

            if not args.dry_run:
                fix_snapshot(supabase, mode, correct, dry_run=False)
                print("  ✓ Fixed!")
            else:
                print("  [DRY RUN] Would fix")
        else:
            print("  ✓ Already correct")

        print()

    print("=" * 70)
    if args.dry_run:
        print("Dry run complete. No changes made.")
    else:
        print("Fix complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
