"""Market-specific configuration for pipeline operations."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MarketConfig:
    """Configuration that differs between US and JP markets."""
    v1_strategy_mode: str
    v2_strategy_mode: str
    market_type: str
    benchmark_symbol: str
    use_finnhub: bool


US_MARKET = MarketConfig(
    v1_strategy_mode="conservative",
    v2_strategy_mode="aggressive",
    market_type="us",
    benchmark_symbol="SPY",
    use_finnhub=True,
)

JP_MARKET = MarketConfig(
    v1_strategy_mode="jp_conservative",
    v2_strategy_mode="jp_aggressive",
    market_type="jp",
    benchmark_symbol="^N225",
    use_finnhub=False,
)
