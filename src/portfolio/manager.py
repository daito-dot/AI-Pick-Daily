"""
Portfolio Manager

Manages virtual portfolio for paper trading simulation:
1. Opens positions based on daily picks
2. Evaluates exit signals (stop loss, take profit, score drop, max hold)
3. Closes positions and records trade history
4. Updates daily portfolio snapshots
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from src.data.supabase_client import SupabaseClient
from src.data.finnhub_client import FinnhubClient
from src.data.yfinance_client import YFinanceClient

logger = logging.getLogger(__name__)

# Configuration
INITIAL_CAPITAL = 100000.0  # ¥100,000
MAX_POSITIONS = 10
STOP_LOSS_PCT = -7.0
TAKE_PROFIT_PCT = 15.0
MAX_HOLD_DAYS = 10

ExitReason = Literal["score_drop", "stop_loss", "take_profit", "max_hold", "regime_change"]


@dataclass
class Position:
    """Open position in the portfolio."""
    id: str
    strategy_mode: str
    symbol: str
    entry_date: str
    entry_price: float
    shares: float
    position_value: float
    entry_score: int | None
    current_price: float | None = None
    current_pnl_pct: float | None = None
    hold_days: int = 0


@dataclass
class ExitSignal:
    """Exit signal for a position."""
    position: Position
    reason: ExitReason
    current_price: float
    pnl_pct: float


class PortfolioManager:
    """
    Manages virtual portfolio for paper trading simulation.

    Key responsibilities:
    - Track open positions
    - Calculate position sizes
    - Evaluate exit signals
    - Record trades and snapshots
    """

    def __init__(
        self,
        supabase: SupabaseClient,
        finnhub: FinnhubClient | None = None,
        yfinance: YFinanceClient | None = None,
    ):
        self.supabase = supabase
        self.finnhub = finnhub
        self.yfinance = yfinance

    def get_open_positions(self, strategy_mode: str | None = None) -> list[Position]:
        """Get all open positions."""
        positions_data = self.supabase.get_open_positions(strategy_mode)
        positions = []

        for p in positions_data:
            entry_date = p["entry_date"]
            if isinstance(entry_date, str):
                entry_dt = datetime.strptime(entry_date, "%Y-%m-%d")
            else:
                entry_dt = entry_date

            hold_days = (datetime.now().date() - entry_dt.date()).days

            positions.append(Position(
                id=p["id"],
                strategy_mode=p["strategy_mode"],
                symbol=p["symbol"],
                entry_date=entry_date if isinstance(entry_date, str) else entry_date.strftime("%Y-%m-%d"),
                entry_price=float(p["entry_price"]),
                shares=float(p["shares"]),
                position_value=float(p["position_value"]),
                entry_score=p.get("entry_score"),
                hold_days=hold_days,
            ))

        return positions

    def get_available_cash(self, strategy_mode: str) -> float:
        """Get available cash for new positions."""
        snapshot = self.supabase.get_latest_portfolio_snapshot(strategy_mode)
        if not snapshot:
            return INITIAL_CAPITAL
        return float(snapshot.get("cash_balance", INITIAL_CAPITAL))

    def calculate_position_size(
        self,
        available_cash: float,
        num_picks: int,
        current_positions: int,
    ) -> float:
        """
        Calculate position size for new picks.

        Uses equal-weight allocation:
        - Divide available cash equally among new picks
        - Respect max positions limit
        """
        if num_picks == 0:
            return 0.0

        # Calculate slots available
        slots_available = MAX_POSITIONS - current_positions
        if slots_available <= 0:
            return 0.0

        # Only open positions up to available slots
        actual_picks = min(num_picks, slots_available)

        # Equal weight allocation
        position_size = available_cash / actual_picks
        return position_size

    def open_positions_for_picks(
        self,
        picks: list[str],
        strategy_mode: str,
        scores: dict[str, int],
        prices: dict[str, float],
    ) -> list[dict[str, Any]]:
        """
        Open new positions for today's picks.

        Args:
            picks: List of symbols to buy
            strategy_mode: 'conservative' or 'aggressive'
            scores: Dict of symbol -> composite_score
            prices: Dict of symbol -> current price

        Returns:
            List of opened position records
        """
        if not picks:
            logger.info(f"No picks for {strategy_mode}, skipping position opening")
            return []

        # Get current state
        current_positions = self.get_open_positions(strategy_mode)
        current_symbols = {p.symbol for p in current_positions}
        available_cash = self.get_available_cash(strategy_mode)

        # Filter out symbols we already hold
        new_picks = [p for p in picks if p not in current_symbols]
        if not new_picks:
            logger.info(f"All picks already in portfolio for {strategy_mode}")
            return []

        # Calculate position size
        position_size = self.calculate_position_size(
            available_cash,
            len(new_picks),
            len(current_positions),
        )

        if position_size <= 0:
            logger.warning(f"No cash or slots available for {strategy_mode}")
            return []

        today = datetime.now().strftime("%Y-%m-%d")
        opened = []

        for symbol in new_picks:
            price = prices.get(symbol, 0)
            if price <= 0:
                logger.warning(f"No price for {symbol}, skipping")
                continue

            shares = position_size / price
            score = scores.get(symbol)

            try:
                result = self.supabase.open_position(
                    strategy_mode=strategy_mode,
                    symbol=symbol,
                    entry_date=today,
                    entry_price=price,
                    shares=shares,
                    position_value=position_size,
                    entry_score=score,
                )
                opened.append(result)
                logger.info(
                    f"Opened position: {symbol} @ {price:.2f} x {shares:.4f} shares "
                    f"= ¥{position_size:.0f} ({strategy_mode})"
                )
            except Exception as e:
                logger.error(f"Failed to open position for {symbol}: {e}")

        return opened

    def get_current_price(self, symbol: str) -> float | None:
        """Get current price for a symbol with fallback."""
        # Try Finnhub first
        if self.finnhub:
            try:
                quote = self.finnhub.get_quote(symbol)
                if quote.current_price and quote.current_price > 0:
                    return quote.current_price
            except Exception as e:
                logger.debug(f"{symbol}: Finnhub quote failed: {e}")

        # Fallback to yfinance
        if self.yfinance:
            try:
                yf_quote = self.yfinance.get_quote(symbol)
                if yf_quote and yf_quote.current_price > 0:
                    return yf_quote.current_price
            except Exception as e:
                logger.debug(f"{symbol}: yfinance quote failed: {e}")

        return None

    def evaluate_exit_signals(
        self,
        positions: list[Position],
        current_scores: dict[str, int] | None = None,
        thresholds: dict[str, float] | None = None,
        market_regime: str | None = None,
    ) -> list[ExitSignal]:
        """
        Evaluate exit signals for all positions.

        Exit reasons (in priority order):
        1. Stop Loss (-7%)
        2. Take Profit (+15%)
        3. Regime Change (crisis mode)
        4. Score Drop (below threshold)
        5. Max Hold (10 days)

        Args:
            positions: List of open positions
            current_scores: Dict of symbol -> current score (for re-scoring check)
            thresholds: Dict of strategy_mode -> threshold
            market_regime: Current market regime ('normal', 'caution', 'crisis')

        Returns:
            List of exit signals
        """
        exit_signals = []
        thresholds = thresholds or {"conservative": 60, "aggressive": 75}

        for position in positions:
            # Get current price
            current_price = self.get_current_price(position.symbol)
            if not current_price:
                logger.warning(f"Cannot get price for {position.symbol}, skipping exit check")
                continue

            # Calculate current P&L
            pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100
            position.current_price = current_price
            position.current_pnl_pct = pnl_pct

            # Check exit conditions in priority order

            # 1. Stop Loss
            if pnl_pct <= STOP_LOSS_PCT:
                exit_signals.append(ExitSignal(
                    position=position,
                    reason="stop_loss",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                logger.warning(
                    f"STOP LOSS triggered: {position.symbol} @ {pnl_pct:.1f}%"
                )
                continue

            # 2. Take Profit
            if pnl_pct >= TAKE_PROFIT_PCT:
                exit_signals.append(ExitSignal(
                    position=position,
                    reason="take_profit",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                logger.info(
                    f"TAKE PROFIT triggered: {position.symbol} @ {pnl_pct:.1f}%"
                )
                continue

            # 3. Regime Change
            if market_regime == "crisis":
                exit_signals.append(ExitSignal(
                    position=position,
                    reason="regime_change",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                logger.warning(
                    f"REGIME CHANGE exit: {position.symbol} (crisis mode)"
                )
                continue

            # 4. Score Drop
            if current_scores:
                current_score = current_scores.get(position.symbol)
                threshold = thresholds.get(position.strategy_mode, 60)
                if current_score is not None and current_score < threshold:
                    exit_signals.append(ExitSignal(
                        position=position,
                        reason="score_drop",
                        current_price=current_price,
                        pnl_pct=pnl_pct,
                    ))
                    logger.info(
                        f"SCORE DROP exit: {position.symbol} (score={current_score} < {threshold})"
                    )
                    continue

            # 5. Max Hold
            if position.hold_days >= MAX_HOLD_DAYS:
                exit_signals.append(ExitSignal(
                    position=position,
                    reason="max_hold",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                logger.info(
                    f"MAX HOLD exit: {position.symbol} (held {position.hold_days} days)"
                )
                continue

        return exit_signals

    def close_positions(
        self,
        exit_signals: list[ExitSignal],
        market_regime_at_exit: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Close positions based on exit signals.

        Args:
            exit_signals: List of exit signals
            market_regime_at_exit: Current market regime

        Returns:
            List of trade history records
        """
        today = datetime.now().strftime("%Y-%m-%d")
        trades = []

        for signal in exit_signals:
            position = signal.position

            # Calculate P&L
            pnl = (signal.current_price - position.entry_price) * position.shares

            try:
                # Close position in virtual_portfolio
                self.supabase.close_position(
                    position_id=position.id,
                    exit_date=today,
                    exit_price=signal.current_price,
                    exit_reason=signal.reason,
                    realized_pnl=pnl,
                    realized_pnl_pct=signal.pnl_pct,
                )

                # Save to trade history
                trade = self.supabase.save_trade_history(
                    strategy_mode=position.strategy_mode,
                    symbol=position.symbol,
                    entry_date=position.entry_date,
                    entry_price=position.entry_price,
                    entry_score=position.entry_score,
                    exit_date=today,
                    exit_price=signal.current_price,
                    shares=position.shares,
                    hold_days=position.hold_days,
                    pnl=pnl,
                    pnl_pct=signal.pnl_pct,
                    exit_reason=signal.reason,
                    market_regime_at_exit=market_regime_at_exit,
                )
                trades.append(trade)

                logger.info(
                    f"Closed position: {position.symbol} @ {signal.current_price:.2f} "
                    f"({signal.reason}) P&L: ¥{pnl:.0f} ({signal.pnl_pct:+.1f}%)"
                )

            except Exception as e:
                logger.error(f"Failed to close position {position.symbol}: {e}")

        return trades

    def update_portfolio_snapshot(
        self,
        strategy_mode: str,
        closed_today: int = 0,
        sp500_daily_pct: float | None = None,
    ) -> dict[str, Any]:
        """
        Update daily portfolio snapshot.

        Args:
            strategy_mode: 'conservative' or 'aggressive'
            closed_today: Number of positions closed today
            sp500_daily_pct: S&P 500 daily return for benchmark

        Returns:
            Saved snapshot record
        """
        today = datetime.now().strftime("%Y-%m-%d")

        # Get open positions
        positions = self.get_open_positions(strategy_mode)

        # Calculate positions value
        positions_value = 0.0
        for pos in positions:
            current_price = self.get_current_price(pos.symbol)
            if current_price:
                positions_value += current_price * pos.shares
            else:
                positions_value += pos.position_value  # Use entry value as fallback

        # Get previous snapshot for cumulative calculations
        prev_snapshot = self.supabase.get_latest_portfolio_snapshot(strategy_mode)

        if prev_snapshot and prev_snapshot.get("snapshot_date") != today:
            prev_total = float(prev_snapshot.get("total_value", INITIAL_CAPITAL))
            prev_cumulative_pnl = float(prev_snapshot.get("cumulative_pnl", 0))
            prev_sp500_cumulative = float(prev_snapshot.get("sp500_cumulative_pct", 0))
            cash_balance = float(prev_snapshot.get("cash_balance", INITIAL_CAPITAL))
        else:
            prev_total = INITIAL_CAPITAL
            prev_cumulative_pnl = 0
            prev_sp500_cumulative = 0
            cash_balance = INITIAL_CAPITAL - positions_value

        # Calculate total value
        total_value = cash_balance + positions_value

        # Calculate daily P&L
        daily_pnl = total_value - prev_total
        daily_pnl_pct = (daily_pnl / prev_total) * 100 if prev_total > 0 else 0

        # Calculate cumulative P&L
        cumulative_pnl = total_value - INITIAL_CAPITAL
        cumulative_pnl_pct = (cumulative_pnl / INITIAL_CAPITAL) * 100

        # Calculate S&P 500 cumulative and alpha
        sp500_cumulative_pct = prev_sp500_cumulative + (sp500_daily_pct or 0)
        alpha = cumulative_pnl_pct - sp500_cumulative_pct

        # Save snapshot
        snapshot = self.supabase.save_portfolio_snapshot(
            snapshot_date=today,
            strategy_mode=strategy_mode,
            total_value=total_value,
            cash_balance=cash_balance,
            positions_value=positions_value,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            cumulative_pnl=cumulative_pnl,
            cumulative_pnl_pct=cumulative_pnl_pct,
            sp500_daily_pct=sp500_daily_pct,
            sp500_cumulative_pct=sp500_cumulative_pct,
            alpha=alpha,
            open_positions=len(positions),
            closed_today=closed_today,
        )

        logger.info(
            f"Portfolio snapshot ({strategy_mode}): "
            f"Total=¥{total_value:.0f}, Cash=¥{cash_balance:.0f}, "
            f"Positions=¥{positions_value:.0f}, Daily={daily_pnl_pct:+.2f}%, "
            f"Cumulative={cumulative_pnl_pct:+.2f}%, Alpha={alpha:+.2f}%"
        )

        return snapshot
