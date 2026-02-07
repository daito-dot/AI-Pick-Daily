"""Market-specific configuration for pipeline operations."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TransactionCostConfig:
    """Transaction cost configuration per market."""
    commission_rate: float  # Per-trade commission rate (0.0003 = 0.03%)
    slippage_rate: float    # Estimated slippage rate
    min_commission: float   # Minimum commission per trade (local currency)

    @property
    def total_rate(self) -> float:
        """Total one-way cost rate (commission + slippage)."""
        return self.commission_rate + self.slippage_rate


@dataclass(frozen=True)
class MarketConfig:
    """Configuration that differs between US and JP markets."""
    v1_strategy_mode: str
    v2_strategy_mode: str
    market_type: str
    benchmark_symbol: str
    use_finnhub: bool
    transaction_costs: TransactionCostConfig = TransactionCostConfig(0.0, 0.0, 0.0)


US_MARKET = MarketConfig(
    v1_strategy_mode="conservative",
    v2_strategy_mode="aggressive",
    market_type="us",
    benchmark_symbol="SPY",
    use_finnhub=True,
    transaction_costs=TransactionCostConfig(
        commission_rate=0.0003,
        slippage_rate=0.0002,
        min_commission=0.0,
    ),
)

JP_MARKET = MarketConfig(
    v1_strategy_mode="jp_conservative",
    v2_strategy_mode="jp_aggressive",
    market_type="jp",
    benchmark_symbol="^N225",
    use_finnhub=False,
    transaction_costs=TransactionCostConfig(
        commission_rate=0.003,
        slippage_rate=0.001,
        min_commission=100.0,
    ),
)
