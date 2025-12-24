#!/usr/bin/env python3
"""
Portfolio Reset Script

This script resets the portfolio data to a clean state.
It clears virtual_portfolio and portfolio_daily_snapshot tables,
then optionally recalculates based on trade_history.

Usage:
    python scripts/reset_portfolio.py [--market us|jp|all] [--dry-run]

Options:
    --market: Which market to reset (us, jp, or all). Default: all
    --dry-run: Show what would be deleted without actually deleting
"""

import argparse
import sys
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, ".")

from src.data.supabase_client import SupabaseClient

INITIAL_CAPITAL = 100000.0

STRATEGY_MODES = {
    "us": ["conservative", "aggressive"],
    "jp": ["jp_conservative", "jp_aggressive"],
}


def get_strategy_modes(market: str) -> list[str]:
    """Get strategy modes for the specified market."""
    if market == "all":
        return STRATEGY_MODES["us"] + STRATEGY_MODES["jp"]
    return STRATEGY_MODES.get(market, [])


def count_records(supabase: SupabaseClient, table: str, strategy_modes: list[str]) -> int:
    """Count records in a table for the given strategy modes."""
    result = supabase._client.table(table).select("id", count="exact").in_(
        "strategy_mode", strategy_modes
    ).execute()
    return result.count or 0


def delete_records(supabase: SupabaseClient, table: str, strategy_modes: list[str]) -> int:
    """Delete records from a table for the given strategy modes."""
    result = supabase._client.table(table).delete().in_(
        "strategy_mode", strategy_modes
    ).execute()
    return len(result.data) if result.data else 0


def get_realized_pnl(supabase: SupabaseClient, strategy_mode: str) -> float:
    """Get total realized PnL from trade_history."""
    result = supabase._client.table("trade_history").select("pnl").eq(
        "strategy_mode", strategy_mode
    ).execute()

    if not result.data:
        return 0.0

    return sum(float(t.get("pnl", 0) or 0) for t in result.data)


def create_initial_snapshot(
    supabase: SupabaseClient,
    strategy_mode: str,
    realized_pnl: float
) -> dict:
    """Create an initial portfolio snapshot."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Calculate values based on realized PnL
    total_value = INITIAL_CAPITAL + realized_pnl
    cumulative_pnl_pct = (realized_pnl / INITIAL_CAPITAL) * 100

    # Determine market type
    market_type = "jp" if strategy_mode.startswith("jp_") else "us"

    record = {
        "snapshot_date": today,
        "strategy_mode": strategy_mode,
        "market_type": market_type,
        "total_value": round(total_value, 2),
        "cash_balance": round(total_value, 2),  # All cash, no positions
        "positions_value": 0,
        "open_positions": 0,
        "daily_pnl": 0,
        "daily_pnl_pct": 0,
        "cumulative_pnl": round(realized_pnl, 2),
        "cumulative_pnl_pct": round(cumulative_pnl_pct, 4),
        "sp500_cumulative_pct": 0,
        "alpha": round(cumulative_pnl_pct, 4),
    }

    result = supabase._client.table("portfolio_daily_snapshot").upsert(
        record,
        on_conflict="snapshot_date,strategy_mode",
    ).execute()

    return result.data[0] if result.data else {}


def main():
    parser = argparse.ArgumentParser(description="Reset portfolio data")
    parser.add_argument(
        "--market",
        choices=["us", "jp", "all"],
        default="all",
        help="Which market to reset (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Portfolio Reset Script")
    print("=" * 60)
    print(f"Market: {args.market}")
    print(f"Dry run: {args.dry_run}")
    print()

    supabase = SupabaseClient()
    strategy_modes = get_strategy_modes(args.market)

    if not strategy_modes:
        print(f"Error: Invalid market '{args.market}'")
        sys.exit(1)

    print(f"Strategy modes to reset: {strategy_modes}")
    print()

    # Count records to be deleted
    print("Counting records...")
    vp_count = count_records(supabase, "virtual_portfolio", strategy_modes)
    snapshot_count = count_records(supabase, "portfolio_daily_snapshot", strategy_modes)

    print(f"  virtual_portfolio: {vp_count} records")
    print(f"  portfolio_daily_snapshot: {snapshot_count} records")
    print()

    if args.dry_run:
        print("[DRY RUN] Would delete the above records.")
        print()

        # Show realized PnL for each strategy
        print("Realized PnL from trade_history:")
        for mode in strategy_modes:
            pnl = get_realized_pnl(supabase, mode)
            new_total = INITIAL_CAPITAL + pnl
            print(f"  {mode}: ${pnl:,.2f} -> New total: ${new_total:,.2f}")

        print()
        print("[DRY RUN] No changes made.")
        return

    # Confirm
    print("WARNING: This will delete all portfolio data and recreate initial snapshots.")
    confirm = input("Are you sure? (yes/no): ")
    if confirm.lower() != "yes":
        print("Aborted.")
        return

    print()
    print("Deleting records...")

    # Delete virtual_portfolio
    if vp_count > 0:
        deleted = delete_records(supabase, "virtual_portfolio", strategy_modes)
        print(f"  Deleted {deleted} records from virtual_portfolio")

    # Delete portfolio_daily_snapshot
    if snapshot_count > 0:
        deleted = delete_records(supabase, "portfolio_daily_snapshot", strategy_modes)
        print(f"  Deleted {deleted} records from portfolio_daily_snapshot")

    print()
    print("Creating initial snapshots...")

    for mode in strategy_modes:
        # Get realized PnL from trade history
        realized_pnl = get_realized_pnl(supabase, mode)

        # Create initial snapshot
        snapshot = create_initial_snapshot(supabase, mode, realized_pnl)

        total = snapshot.get("total_value", INITIAL_CAPITAL)
        pnl_pct = snapshot.get("cumulative_pnl_pct", 0)

        print(f"  {mode}: Total=${total:,.2f}, Realized PnL={pnl_pct:+.2f}%")

    print()
    print("=" * 60)
    print("Portfolio reset complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
