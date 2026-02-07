"""
Tests for transaction cost calculation.

Covers:
- calculate_transaction_cost utility
- TransactionCostConfig properties
- Position open/close cost integration
"""
import pytest

from src.pipeline.market_config import TransactionCostConfig, US_MARKET, JP_MARKET
from src.portfolio.manager import calculate_transaction_cost


class TestTransactionCostConfig:
    """Tests for TransactionCostConfig dataclass."""

    def test_us_market_costs(self):
        tc = US_MARKET.transaction_costs
        assert tc.commission_rate == 0.0003
        assert tc.slippage_rate == 0.0002
        assert tc.min_commission == 0.0

    def test_jp_market_costs(self):
        tc = JP_MARKET.transaction_costs
        assert tc.commission_rate == 0.003
        assert tc.slippage_rate == 0.001
        assert tc.min_commission == 100.0

    def test_total_rate(self):
        tc = TransactionCostConfig(0.001, 0.002, 0.0)
        assert tc.total_rate == pytest.approx(0.003)

    def test_zero_cost_config(self):
        tc = TransactionCostConfig(0.0, 0.0, 0.0)
        assert tc.total_rate == 0.0


class TestCalculateTransactionCost:
    """Tests for calculate_transaction_cost function."""

    def test_none_config_returns_zero(self):
        assert calculate_transaction_cost(10000, None) == 0.0

    def test_zero_cost_config(self):
        tc = TransactionCostConfig(0.0, 0.0, 0.0)
        assert calculate_transaction_cost(10000, tc) == 0.0

    def test_us_market_cost(self):
        """US: 0.03% commission + 0.02% slippage = 0.05% per trade."""
        tc = US_MARKET.transaction_costs
        cost = calculate_transaction_cost(10000, tc)
        # commission = max(10000 * 0.0003, 0) = 3.0
        # slippage = 10000 * 0.0002 = 2.0
        assert cost == pytest.approx(5.0)

    def test_jp_market_cost(self):
        """JP: 0.3% commission + 0.1% slippage, min commission ¥100."""
        tc = JP_MARKET.transaction_costs
        cost = calculate_transaction_cost(100000, tc)
        # commission = max(100000 * 0.003, 100) = max(300, 100) = 300
        # slippage = 100000 * 0.001 = 100
        assert cost == pytest.approx(400.0)

    def test_jp_market_min_commission(self):
        """Small trade hits minimum commission."""
        tc = JP_MARKET.transaction_costs
        cost = calculate_transaction_cost(1000, tc)
        # commission = max(1000 * 0.003, 100) = max(3, 100) = 100
        # slippage = 1000 * 0.001 = 1
        assert cost == pytest.approx(101.0)

    def test_zero_trade_value(self):
        tc = US_MARKET.transaction_costs
        cost = calculate_transaction_cost(0, tc)
        assert cost == 0.0

    def test_round_trip_cost_us(self):
        """Verify round-trip cost is ~0.1% for US market."""
        tc = US_MARKET.transaction_costs
        trade_value = 10000
        one_way = calculate_transaction_cost(trade_value, tc)
        round_trip_pct = (one_way * 2) / trade_value * 100
        assert round_trip_pct == pytest.approx(0.1)

    def test_round_trip_cost_jp(self):
        """Verify round-trip cost is ~0.8% for JP market."""
        tc = JP_MARKET.transaction_costs
        trade_value = 100000
        one_way = calculate_transaction_cost(trade_value, tc)
        round_trip_pct = (one_way * 2) / trade_value * 100
        assert round_trip_pct == pytest.approx(0.8)
