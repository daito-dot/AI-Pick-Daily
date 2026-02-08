"""
Portfolio Manager

Manages virtual portfolio for paper trading simulation:
1. Opens positions based on daily picks
2. Evaluates exit signals (stop loss, take profit, score drop, max hold)
3. Closes positions and records trade history
4. Updates daily portfolio snapshots
"""
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from src.data.supabase_client import SupabaseClient
from src.data.finnhub_client import FinnhubClient
from src.data.yfinance_client import YFinanceClient
from src.pipeline.market_config import MarketConfig, TransactionCostConfig

logger = logging.getLogger(__name__)

# Configuration
INITIAL_CAPITAL = 100000.0  # ¥100,000
MAX_POSITIONS = 10
STOP_LOSS_PCT = -7.0
TAKE_PROFIT_PCT = 8.0  # Lowered from 15% — 15% unreachable in 10-day hold
MAX_HOLD_DAYS = 10
ABSOLUTE_MAX_HOLD_DAYS = 15  # Hard limit even if AI says hold
RISK_FREE_RATE = 0.02  # Annual risk-free rate for Sharpe calculation

# Drawdown Management Thresholds
# See: docs/paper_trading_strategy.md Section 2.4
MDD_WARNING_THRESHOLD = -10.0  # Reduce position size by 50%
MDD_STOP_NEW_THRESHOLD = -15.0  # Stop opening new positions
MDD_CRITICAL_THRESHOLD = -50.0  # Consider closing all positions (was -20, relaxed to allow recovery)

ExitReason = Literal["score_drop", "stop_loss", "take_profit", "max_hold", "regime_change"]


def calculate_transaction_cost(
    trade_value: float,
    cost_config: TransactionCostConfig | None,
) -> float:
    """Calculate total transaction cost for a single trade.

    Returns commission + slippage, respecting min_commission.
    """
    if cost_config is None:
        return 0.0
    commission = max(
        trade_value * cost_config.commission_rate,
        cost_config.min_commission,
    )
    slippage = trade_value * cost_config.slippage_rate
    return commission + slippage


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


@dataclass
class DrawdownStatus:
    """Current drawdown status for position sizing decisions."""
    current_mdd: float  # Current max drawdown (negative percentage)
    can_open_positions: bool  # Whether new positions are allowed
    position_size_multiplier: float  # 1.0 = normal, 0.5 = reduced, 0 = none
    status: Literal["normal", "warning", "stopped", "critical"]
    message: str


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
        market_config: MarketConfig | None = None,
    ):
        self.supabase = supabase
        self.finnhub = finnhub
        self.yfinance = yfinance
        self.market_config = market_config
        self._txn_costs = market_config.transaction_costs if market_config else None
        self._params_cache: dict[str, dict[str, float]] = {}

    def _get_params(self, strategy_mode: str) -> dict[str, float]:
        """Load strategy parameters from DB with caching and fallback."""
        if strategy_mode not in self._params_cache:
            try:
                from src.meta_monitor.parameters import get_parameters
                self._params_cache[strategy_mode] = get_parameters(
                    self.supabase, strategy_mode
                )
            except Exception:
                self._params_cache[strategy_mode] = {
                    "take_profit_pct": TAKE_PROFIT_PCT,
                    "stop_loss_pct": STOP_LOSS_PCT,
                    "max_hold_days": MAX_HOLD_DAYS,
                    "absolute_max_hold_days": ABSOLUTE_MAX_HOLD_DAYS,
                    "max_positions": MAX_POSITIONS,
                    "mdd_warning_pct": MDD_WARNING_THRESHOLD,
                    "mdd_stop_new_pct": MDD_STOP_NEW_THRESHOLD,
                }
        return self._params_cache[strategy_mode]

    def get_drawdown_status(self, strategy_mode: str) -> DrawdownStatus:
        """
        Get current drawdown status to determine position sizing.

        Thresholds:
        - MDD > -10%: Normal (multiplier = 1.0)
        - -10% >= MDD > -15%: Warning (multiplier = 0.5)
        - -15% >= MDD > -20%: Stopped (multiplier = 0)
        - MDD <= -20%: Critical (multiplier = 0, consider closing all)

        Returns:
            DrawdownStatus with current MDD and position sizing guidance
        """
        snapshot = self.supabase.get_latest_portfolio_snapshot(strategy_mode)

        if not snapshot:
            # No history yet, assume normal
            return DrawdownStatus(
                current_mdd=0.0,
                can_open_positions=True,
                position_size_multiplier=1.0,
                status="normal",
                message="No portfolio history, starting fresh",
            )

        current_mdd = float(snapshot.get("max_drawdown", 0) or 0)

        # Determine status based on MDD thresholds (DB-backed)
        params = self._get_params(strategy_mode)
        mdd_warning = params.get("mdd_warning_pct", MDD_WARNING_THRESHOLD)
        mdd_stop = params.get("mdd_stop_new_pct", MDD_STOP_NEW_THRESHOLD)

        if current_mdd > mdd_warning:
            return DrawdownStatus(
                current_mdd=current_mdd,
                can_open_positions=True,
                position_size_multiplier=1.0,
                status="normal",
                message=f"MDD {current_mdd:.1f}% within normal range",
            )
        elif current_mdd > mdd_stop:
            return DrawdownStatus(
                current_mdd=current_mdd,
                can_open_positions=True,
                position_size_multiplier=0.5,
                status="warning",
                message=f"MDD {current_mdd:.1f}% - reducing position size by 50%",
            )
        elif current_mdd > MDD_CRITICAL_THRESHOLD:
            return DrawdownStatus(
                current_mdd=current_mdd,
                can_open_positions=False,
                position_size_multiplier=0.0,
                status="stopped",
                message=f"MDD {current_mdd:.1f}% - new positions blocked",
            )
        else:
            return DrawdownStatus(
                current_mdd=current_mdd,
                can_open_positions=False,
                position_size_multiplier=0.0,
                status="critical",
                message=f"MDD {current_mdd:.1f}% CRITICAL - consider closing all positions",
            )

    def calculate_sharpe_ratio(
        self,
        daily_returns: list[float],
        risk_free_rate: float = RISK_FREE_RATE,
    ) -> float | None:
        """
        Calculate annualized Sharpe ratio from daily returns.

        Args:
            daily_returns: List of daily return percentages
            risk_free_rate: Annual risk-free rate (default 2%)

        Returns:
            Sharpe ratio or None if insufficient data
        """
        if len(daily_returns) < 5:
            return None

        # Convert to decimals
        returns = [r / 100 for r in daily_returns]

        # Calculate mean daily return
        mean_return = sum(returns) / len(returns)

        # Calculate standard deviation
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        std_dev = math.sqrt(variance) if variance > 0 else 0

        if std_dev == 0:
            return None

        # Daily risk-free rate
        daily_rf = risk_free_rate / 252

        # Annualized Sharpe ratio
        sharpe = ((mean_return - daily_rf) / std_dev) * math.sqrt(252)
        return round(sharpe, 4)

    def calculate_max_drawdown(
        self,
        equity_values: list[float],
    ) -> float:
        """
        Calculate maximum drawdown from equity curve.

        Args:
            equity_values: List of portfolio total values over time

        Returns:
            Maximum drawdown as negative percentage
        """
        if len(equity_values) < 2:
            return 0.0

        peak = equity_values[0]
        max_dd = 0.0

        for value in equity_values:
            if value > peak:
                peak = value
            drawdown = ((value - peak) / peak) * 100 if peak > 0 else 0
            if drawdown < max_dd:
                max_dd = drawdown

        return round(max_dd, 4)

    def calculate_win_rate(self, strategy_mode: str) -> float | None:
        """
        Calculate win rate from closed trades.

        Args:
            strategy_mode: 'conservative' or 'aggressive'

        Returns:
            Win rate percentage or None if no trades
        """
        # Get trade history
        result = self.supabase._client.table("trade_history").select(
            "pnl_pct"
        ).eq(
            "strategy_mode", strategy_mode
        ).execute()

        trades = result.data or []
        if not trades:
            return None

        wins = sum(1 for t in trades if t.get("pnl_pct", 0) > 0)
        return round((wins / len(trades)) * 100, 2)

    def _get_closed_trades_value(self, strategy_mode: str, date: str) -> float:
        """
        Get total exit value of trades closed on a specific date.

        This is used to add back cash when positions are closed.
        """
        try:
            result = self.supabase._client.table("trade_history").select(
                "exit_price, shares, symbol"
            ).eq(
                "strategy_mode", strategy_mode
            ).eq(
                "exit_date", date
            ).execute()

            trades = result.data or []
            total = 0.0
            for t in trades:
                exit_price = float(t.get("exit_price", 0) or 0)
                shares = float(t.get("shares", 0) or 0)
                trade_value = exit_price * shares
                total += trade_value
                logger.debug(
                    f"Closed trade {t.get('symbol')}: "
                    f"{exit_price:.2f} × {shares:.4f} = {trade_value:.2f}"
                )

            logger.info(
                f"Total closed trades value for {strategy_mode} on {date}: "
                f"{len(trades)} trades = ¥{total:.0f}"
            )
            return total
        except Exception as e:
            logger.error(f"Failed to get closed trades value: {e}")
            return 0.0

    def _get_invested_cost(self, strategy_mode: str) -> float:
        """
        Get total invested cost (entry value) of all open positions.

        This is the amount of cash spent on positions.
        """
        positions = self.get_open_positions(strategy_mode)
        return sum(p.position_value for p in positions)

    def _get_total_realized_pnl(self, strategy_mode: str) -> float:
        """
        Get total realized PnL from all closed trades.

        Used to recalculate cash when all positions are closed.
        """
        try:
            result = self.supabase._client.table("trade_history").select(
                "pnl"
            ).eq(
                "strategy_mode", strategy_mode
            ).execute()

            trades = result.data or []
            total_pnl = sum(float(t.get("pnl", 0) or 0) for t in trades)
            logger.info(
                f"Total realized PnL for {strategy_mode}: "
                f"{len(trades)} trades = ¥{total_pnl:,.0f}"
            )
            return total_pnl
        except Exception as e:
            logger.error(f"Failed to get total realized PnL: {e}")
            return 0.0

    def _get_positions_opened_on(self, strategy_mode: str, date: str) -> float:
        """
        Get total entry value of positions opened on a specific date.
        """
        try:
            result = self.supabase._client.table("virtual_portfolio").select(
                "position_value, symbol"
            ).eq(
                "strategy_mode", strategy_mode
            ).eq(
                "entry_date", date
            ).execute()

            positions = result.data or []
            total = sum(float(p.get("position_value", 0) or 0) for p in positions)
            logger.info(
                f"Positions opened for {strategy_mode} on {date}: "
                f"{len(positions)} positions = ¥{total:.0f}"
            )
            return total
        except Exception as e:
            logger.error(f"Failed to get positions opened on {date}: {e}")
            return 0.0

    def _get_positions_opened_after(
        self,
        strategy_mode: str,
        timestamp: str | None,
    ) -> float:
        """
        Get total entry value of positions opened after a timestamp.

        Used for same-day updates to track new positions since last snapshot.
        """
        if not timestamp:
            return 0.0

        try:
            result = self.supabase._client.table("virtual_portfolio").select(
                "position_value, symbol"
            ).eq(
                "strategy_mode", strategy_mode
            ).gt(
                "created_at", timestamp
            ).execute()

            positions = result.data or []
            total = sum(float(p.get("position_value", 0) or 0) for p in positions)
            if positions:
                logger.info(
                    f"New positions for {strategy_mode} after {timestamp}: "
                    f"{len(positions)} positions = ¥{total:.0f}"
                )
            return total
        except Exception as e:
            logger.error(f"Failed to get positions opened after {timestamp}: {e}")
            return 0.0

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

        # Calculate slots available (use first strategy's params as approximation)
        slots_available = int(self._get_params("conservative").get(
            "max_positions", MAX_POSITIONS
        )) - current_positions
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

        Includes drawdown management:
        - MDD > -10%: Normal position size
        - -10% >= MDD > -15%: Position size reduced by 50%
        - MDD <= -15%: No new positions allowed

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

        # Check drawdown status before opening positions
        dd_status = self.get_drawdown_status(strategy_mode)
        logger.info(f"Drawdown status ({strategy_mode}): {dd_status.status} - {dd_status.message}")

        if not dd_status.can_open_positions:
            logger.warning(
                f"Position opening blocked for {strategy_mode}: {dd_status.message}"
            )
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

        # Filter out symbols that were closed TODAY (prevent same-day re-entry)
        # This prevents the timing issue where Review closes a position before Scoring
        # picks the same stock again with potentially stale data
        today = datetime.now().strftime("%Y-%m-%d")
        closed_today = set(self.supabase.get_symbols_closed_on_date(strategy_mode, today))
        if closed_today:
            before_count = len(new_picks)
            new_picks = [p for p in new_picks if p not in closed_today]
            excluded = closed_today & set(picks)
            if excluded:
                logger.info(
                    f"Excluded {len(excluded)} symbols closed today from re-entry: {excluded}"
                )
        if not new_picks:
            logger.info(f"All picks were either held or closed today for {strategy_mode}")
            return []

        # Calculate position size
        position_size = self.calculate_position_size(
            available_cash,
            len(new_picks),
            len(current_positions),
        )

        # Apply drawdown multiplier
        if dd_status.position_size_multiplier < 1.0:
            original_size = position_size
            position_size *= dd_status.position_size_multiplier
            logger.info(
                f"Position size reduced: ¥{original_size:.0f} -> ¥{position_size:.0f} "
                f"(multiplier: {dd_status.position_size_multiplier})"
            )

        if position_size <= 0:
            logger.warning(f"No cash or slots available for {strategy_mode}")
            return []

        opened = []

        for symbol in new_picks:
            price = prices.get(symbol, 0)
            if price <= 0:
                logger.warning(f"No price for {symbol}, skipping")
                continue

            # Deduct entry transaction cost from investable amount
            entry_cost = calculate_transaction_cost(position_size, self._txn_costs)
            effective_position = position_size - entry_cost
            shares = effective_position / price
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
                cost_msg = f" (txn cost: ¥{entry_cost:.0f})" if entry_cost > 0 else ""
                logger.info(
                    f"Opened position: {symbol} @ {price:.2f} x {shares:.4f} shares "
                    f"= ¥{position_size:.0f}{cost_msg} ({strategy_mode})"
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
        exit_judgments: dict[str, Any] | None = None,
    ) -> list[ExitSignal]:
        """
        Evaluate exit signals for all positions.

        Hard exits (no AI consultation):
        1. Stop Loss (-7%)
        2. Regime Change (crisis mode)
        3. Absolute Max Hold (15 days)

        Soft exits (AI can override to hold):
        4. Take Profit (+15%)
        5. Score Drop (below threshold)
        6. Max Hold (10 days)

        Args:
            positions: List of open positions
            current_scores: Dict of symbol -> current score
            thresholds: Dict of strategy_mode -> threshold
            market_regime: Current market regime
            exit_judgments: Dict of symbol -> ExitJudgmentOutput from AI

        Returns:
            List of exit signals
        """
        exit_signals = []
        thresholds = thresholds or {"conservative": 60, "aggressive": 75}
        exit_judgments = exit_judgments or {}

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

            # Load strategy-specific parameters from DB
            p = self._get_params(position.strategy_mode)
            stop_loss = p.get("stop_loss_pct", STOP_LOSS_PCT)
            take_profit = p.get("take_profit_pct", TAKE_PROFIT_PCT)
            max_hold = int(p.get("max_hold_days", MAX_HOLD_DAYS))
            abs_max_hold = int(p.get("absolute_max_hold_days", ABSOLUTE_MAX_HOLD_DAYS))

            # === HARD EXITS (no AI override) ===

            # 1. Stop Loss
            if pnl_pct <= stop_loss:
                exit_signals.append(ExitSignal(
                    position=position,
                    reason="stop_loss",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                logger.warning(f"STOP LOSS triggered: {position.symbol} @ {pnl_pct:.1f}%")
                continue

            # 2. Regime Change
            if market_regime == "crisis":
                exit_signals.append(ExitSignal(
                    position=position,
                    reason="regime_change",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                logger.warning(f"REGIME CHANGE exit: {position.symbol} (crisis mode)")
                continue

            # 3. Absolute Max Hold (hard limit, even if AI says hold)
            if position.hold_days >= abs_max_hold:
                exit_signals.append(ExitSignal(
                    position=position,
                    reason="absolute_max_hold",
                    current_price=current_price,
                    pnl_pct=pnl_pct,
                ))
                logger.warning(f"ABSOLUTE MAX HOLD exit: {position.symbol} (held {position.hold_days} days)")
                continue

            # === SOFT EXITS (AI can override) ===

            soft_trigger = None

            # 4. Take Profit (priority: highest among soft exits)
            if pnl_pct >= take_profit:
                soft_trigger = "take_profit"

            # 5. Score Drop (only if take_profit didn't fire)
            if soft_trigger is None and current_scores:
                current_score = current_scores.get(position.symbol)
                threshold = thresholds.get(position.strategy_mode, 60)
                if current_score is not None and current_score < threshold:
                    soft_trigger = "score_drop"

            # 6. Max Hold (independent check — was skipped when current_scores existed)
            if soft_trigger is None and position.hold_days >= max_hold:
                soft_trigger = "max_hold"

            if soft_trigger is None:
                continue

            # Check AI judgment for override
            ai_judgment = exit_judgments.get(position.symbol)
            if ai_judgment and ai_judgment.decision == "hold":
                logger.info(
                    f"AI OVERRIDE: {position.symbol} soft exit '{soft_trigger}' → HOLD "
                    f"(confidence={ai_judgment.confidence:.0%}, reason: {ai_judgment.reasoning[:80]})"
                )
                continue

            # No AI override → proceed with exit
            exit_signals.append(ExitSignal(
                position=position,
                reason=soft_trigger,
                current_price=current_price,
                pnl_pct=pnl_pct,
            ))
            if ai_judgment:
                logger.info(
                    f"AI CONFIRMED exit: {position.symbol} '{soft_trigger}' @ {pnl_pct:.1f}% "
                    f"(confidence={ai_judgment.confidence:.0%})"
                )
            else:
                logger.info(f"SOFT EXIT (no AI): {position.symbol} '{soft_trigger}' @ {pnl_pct:.1f}%")

        return exit_signals

    def get_soft_exit_candidates(
        self,
        positions: list[Position],
        current_scores: dict[str, int] | None = None,
        thresholds: dict[str, float] | None = None,
        market_regime: str | None = None,
    ) -> list[dict]:
        """Identify positions with soft exit triggers for AI consultation.

        Returns list of dicts with position info suitable for AI exit judgment.
        """
        candidates = []
        thresholds = thresholds or {"conservative": 60, "aggressive": 75}

        for position in positions:
            current_price = self.get_current_price(position.symbol)
            if not current_price:
                continue

            pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100

            # Load strategy-specific parameters
            p = self._get_params(position.strategy_mode)

            # Skip hard exits
            if pnl_pct <= p.get("stop_loss_pct", STOP_LOSS_PCT):
                continue
            if market_regime == "crisis":
                continue
            if position.hold_days >= int(p.get("absolute_max_hold_days", ABSOLUTE_MAX_HOLD_DAYS)):
                continue

            # Check soft triggers
            trigger = None
            if pnl_pct >= p.get("take_profit_pct", TAKE_PROFIT_PCT):
                trigger = "take_profit"
            elif current_scores:
                current_score = current_scores.get(position.symbol)
                threshold = thresholds.get(position.strategy_mode, 60)
                if current_score is not None and current_score < threshold:
                    trigger = "score_drop"
            elif position.hold_days >= int(p.get("max_hold_days", MAX_HOLD_DAYS)):
                trigger = "max_hold"

            if trigger:
                candidates.append({
                    "symbol": position.symbol,
                    "pnl_pct": pnl_pct,
                    "hold_days": position.hold_days,
                    "trigger_reason": trigger,
                    "top_news": None,  # Caller can enrich with news
                })

        return candidates

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

            # Calculate P&L with exit transaction cost
            gross_pnl = (signal.current_price - position.entry_price) * position.shares
            exit_value = signal.current_price * position.shares
            exit_cost = calculate_transaction_cost(exit_value, self._txn_costs)
            pnl = gross_pnl - exit_cost
            pnl_pct = (pnl / position.position_value) * 100 if position.position_value else signal.pnl_pct

            try:
                # Close position in virtual_portfolio
                self.supabase.close_position(
                    position_id=position.id,
                    exit_date=today,
                    exit_price=signal.current_price,
                    exit_reason=signal.reason,
                    realized_pnl=pnl,
                    realized_pnl_pct=pnl_pct,
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
                    pnl_pct=pnl_pct,
                    exit_reason=signal.reason,
                    market_regime_at_exit=market_regime_at_exit,
                )
                trades.append(trade)

                cost_msg = f" txn cost: ¥{exit_cost:.0f}" if exit_cost > 0 else ""
                logger.info(
                    f"Closed position: {position.symbol} @ {signal.current_price:.2f} "
                    f"({signal.reason}) P&L: ¥{pnl:.0f} ({pnl_pct:+.1f}%){cost_msg}"
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

        # Calculate positions value (net of potential exit costs)
        positions_value = 0.0
        for pos in positions:
            current_price = self.get_current_price(pos.symbol)
            if current_price:
                gross_value = current_price * pos.shares
                exit_cost = calculate_transaction_cost(gross_value, self._txn_costs)
                positions_value += gross_value - exit_cost
            else:
                positions_value += pos.position_value  # Use entry value as fallback

        # Get previous snapshot for cumulative calculations
        prev_snapshot = self.supabase.get_latest_portfolio_snapshot(strategy_mode)

        if prev_snapshot:
            prev_total = float(prev_snapshot.get("total_value", INITIAL_CAPITAL))
            prev_cumulative_pnl = float(prev_snapshot.get("cumulative_pnl", 0))
            prev_sp500_cumulative = float(prev_snapshot.get("sp500_cumulative_pct", 0))

            # Calculate cash balance properly:
            # Cash changes when:
            # - Positions are opened: cash decreases by position entry value
            # - Positions are closed: cash increases by position exit value
            #
            # Formula: Cash = Previous Cash - New Opens + Closes
            prev_cash = float(prev_snapshot.get("cash_balance", INITIAL_CAPITAL))

            if prev_snapshot.get("snapshot_date") == today:
                # Same day update: add back closed trades (may have been processed)
                closed_trades_today = self._get_closed_trades_value(strategy_mode, today)
                # Get positions opened after last snapshot (new positions)
                new_positions_cost = self._get_positions_opened_after(
                    strategy_mode,
                    prev_snapshot.get("created_at"),
                )
                cash_balance = prev_cash - new_positions_cost + closed_trades_today
            else:
                # New day: previous cash - new positions opened today + closed today
                new_positions_cost = self._get_positions_opened_on(strategy_mode, today)
                closed_trades_today = self._get_closed_trades_value(strategy_mode, today)
                cash_balance = prev_cash - new_positions_cost + closed_trades_today
        else:
            prev_total = INITIAL_CAPITAL
            prev_cumulative_pnl = 0
            prev_sp500_cumulative = 0
            # First snapshot: calculate cash as what's left after positions
            cash_balance = INITIAL_CAPITAL - self._get_invested_cost(strategy_mode)

        # CRITICAL FIX: When all positions are closed, recalculate cash from first principles
        # This prevents cash balance corruption from accumulating errors
        if len(positions) == 0:
            # Cash = Initial Capital + Total Realized PnL
            total_realized_pnl = self._get_total_realized_pnl(strategy_mode)
            cash_balance = INITIAL_CAPITAL + total_realized_pnl
            logger.info(
                f"[{strategy_mode}] No open positions - recalculated cash from realized PnL: "
                f"¥{INITIAL_CAPITAL:,.0f} + ¥{total_realized_pnl:,.0f} = ¥{cash_balance:,.0f}"
            )

        # Calculate total value
        total_value = cash_balance + positions_value

        # Calculate daily P&L
        daily_pnl = total_value - prev_total
        daily_pnl_pct = (daily_pnl / prev_total) * 100 if prev_total > 0 else 0

        # Calculate cumulative P&L
        cumulative_pnl = total_value - INITIAL_CAPITAL
        cumulative_pnl_pct = (cumulative_pnl / INITIAL_CAPITAL) * 100

        # Calculate S&P 500 cumulative (compound) and alpha
        # Use multiplicative compounding to match portfolio's natural compounding
        if sp500_daily_pct is not None:
            prev_factor = 1.0 + (prev_sp500_cumulative / 100.0)
            daily_factor = 1.0 + (sp500_daily_pct / 100.0)
            sp500_cumulative_pct = (prev_factor * daily_factor - 1.0) * 100.0
        else:
            sp500_cumulative_pct = prev_sp500_cumulative
        alpha = cumulative_pnl_pct - sp500_cumulative_pct

        # Calculate risk metrics from historical data
        max_drawdown = None
        sharpe_ratio = None
        win_rate = None

        try:
            # Get historical snapshots for risk calculations (30-day rolling)
            historical_snapshots = self.supabase._client.table(
                "portfolio_daily_snapshot"
            ).select(
                "total_value, daily_pnl_pct"
            ).eq(
                "strategy_mode", strategy_mode
            ).order(
                "snapshot_date", desc=True
            ).limit(30).execute()

            historical = historical_snapshots.data or []

            if historical:
                # Extract equity values and daily returns
                equity_values = [s.get("total_value", INITIAL_CAPITAL) for s in reversed(historical)]
                equity_values.append(total_value)  # Add current value

                daily_returns = [
                    s.get("daily_pnl_pct", 0) for s in reversed(historical)
                    if s.get("daily_pnl_pct") is not None
                ]
                if daily_pnl_pct:
                    daily_returns.append(daily_pnl_pct)

                # Calculate max drawdown
                max_drawdown = self.calculate_max_drawdown(equity_values)

                # Calculate Sharpe ratio (need at least 5 data points)
                if len(daily_returns) >= 5:
                    sharpe_ratio = self.calculate_sharpe_ratio(daily_returns)

            # Calculate win rate from trade history
            win_rate = self.calculate_win_rate(strategy_mode)

        except Exception as e:
            logger.warning(f"Failed to calculate risk metrics: {e}")

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
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            win_rate=win_rate,
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

        # Log risk metrics if available
        risk_info = []
        if max_drawdown is not None:
            risk_info.append(f"MDD={max_drawdown:.2f}%")
        if sharpe_ratio is not None:
            risk_info.append(f"Sharpe={sharpe_ratio:.2f}")
        if win_rate is not None:
            risk_info.append(f"WinRate={win_rate:.1f}%")
        if risk_info:
            logger.info(f"Risk metrics ({strategy_mode}): {', '.join(risk_info)}")

        return snapshot
