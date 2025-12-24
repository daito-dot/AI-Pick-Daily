"""
Tests for V2 Aggressive Scoring Agents.

Tests cover:
- CatalystAgent: Earnings surprise handling
- Momentum12_1Agent: 12-month momentum calculation
- BreakoutAgent: Breakout detection conditions
- RiskAdjustedAgent: VIX-based risk adjustment
"""
import pytest

from src.scoring.agents_v2 import (
    CatalystAgent,
    Momentum12_1Agent,
    BreakoutAgent,
    RiskAdjustedAgent,
    calculate_momentum_12_1,
    detect_breakout,
)
from src.scoring.agents import AgentScore


class TestCatalystAgent:
    """Tests for CatalystAgent."""

    def test_neutral_score_when_no_data(self):
        """CatalystAgent should return neutral score (35) when no catalyst data is provided."""
        from tests.conftest import MockV2StockData

        data = MockV2StockData(
            symbol="TEST",
            prices=[100.0] * 60,
            volumes=[1_000_000.0] * 60,
            earnings_surprise_pct=None,
            analyst_revision_score=None,
            gap_pct=None,
        )

        agent = CatalystAgent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        assert result.name == "catalyst"
        # Neutral defaults: earnings=15 + revision=10 + gap=10 = 35
        assert result.score == 35
        assert result.reasoning == "No catalyst detected"

    def test_positive_earnings_surprise(self):
        """CatalystAgent should score high for positive earnings surprise."""
        from tests.conftest import MockV2StockData

        data = MockV2StockData(
            symbol="TEST",
            prices=[100.0] * 60,
            volumes=[1_000_000.0] * 60,
            earnings_surprise_pct=25.0,  # Strong beat
            analyst_revision_score=None,
            gap_pct=None,
        )

        agent = CatalystAgent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        assert result.name == "catalyst"
        # Strong earnings (40) + neutral revision (10) + neutral gap (10) = 60
        assert result.score == 60
        assert result.components["earnings_surprise"] == 40
        assert "Strong earnings beat" in result.reasoning

    def test_negative_earnings_surprise(self):
        """CatalystAgent should score low for negative earnings surprise."""
        from tests.conftest import MockV2StockData

        data = MockV2StockData(
            symbol="TEST",
            prices=[100.0] * 60,
            volumes=[1_000_000.0] * 60,
            earnings_surprise_pct=-15.0,  # Significant miss
            analyst_revision_score=None,
            gap_pct=None,
        )

        agent = CatalystAgent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        assert result.name == "catalyst"
        # Earnings miss (5) + neutral revision (10) + neutral gap (10) = 25
        assert result.score == 25
        assert result.components["earnings_surprise"] == 5
        assert "Earnings miss" in result.reasoning

    def test_with_all_positive_catalysts(self, mock_v2_stock_data):
        """CatalystAgent should score high with all positive catalysts."""
        # Modify fixture data for strong catalysts
        mock_v2_stock_data.earnings_surprise_pct = 25.0
        mock_v2_stock_data.analyst_revision_score = 12.0
        mock_v2_stock_data.gap_pct = 12.0

        agent = CatalystAgent()
        result = agent.score(mock_v2_stock_data)

        assert isinstance(result, AgentScore)
        # Strong earnings (40) + target raised (30) + strong gap (30) = 100
        assert result.score == 100


class TestMomentum12_1Agent:
    """Tests for Momentum12_1Agent."""

    def test_momentum_with_insufficient_data(self):
        """Momentum12_1Agent should handle insufficient data gracefully."""
        from tests.conftest import MockV2StockData

        # Only 60 days of data (need 252 for proper 12-1 momentum)
        data = MockV2StockData(
            symbol="TEST",
            prices=[100.0] * 60,
            volumes=[1_000_000.0] * 60,
        )

        agent = Momentum12_1Agent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        assert result.name == "momentum_12_1"
        # With 0% momentum (insufficient data), score should be low
        assert result.components["momentum_12_1"] == 0.0

    def test_strong_positive_momentum(self):
        """Momentum12_1Agent should score high for strong 12-1 momentum."""
        from tests.conftest import MockV2StockData

        # Create 252+ days of data with strong uptrend
        # Price goes from 100 to 180 over 12 months (80% gain)
        prices = []
        for i in range(260):
            # Steady uptrend, slightly lower in last month
            if i < 239:  # Before last month
                price = 100.0 + (i * 0.35)  # Gradual increase
            else:
                price = 183.0 + ((i - 239) * 0.1)  # Slight increase in last month
            prices.append(price)

        data = MockV2StockData(
            symbol="TEST",
            prices=prices,
            volumes=[1_000_000.0] * 260,
        )

        agent = Momentum12_1Agent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        assert result.name == "momentum_12_1"
        # Strong momentum should have high score
        assert result.components["momentum_12_1"] > 50
        assert "Strong 12-1 momentum" in result.reasoning or "Good 12-1 momentum" in result.reasoning

    def test_negative_momentum(self):
        """Momentum12_1Agent should score low for negative 12-1 momentum."""
        from tests.conftest import MockV2StockData

        # Create 252+ days of data with downtrend
        prices = []
        for i in range(260):
            if i < 239:
                price = 100.0 - (i * 0.15)  # Gradual decrease
            else:
                price = 64.0 - ((i - 239) * 0.05)
            prices.append(max(price, 50.0))  # Floor at 50

        data = MockV2StockData(
            symbol="TEST",
            prices=prices,
            volumes=[1_000_000.0] * 260,
        )

        agent = Momentum12_1Agent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        assert result.name == "momentum_12_1"
        assert result.components["momentum_12_1"] < 0
        assert "Negative momentum" in result.reasoning

    def test_calculate_momentum_12_1_function(self):
        """Test the calculate_momentum_12_1 helper function directly."""
        # Test with insufficient data
        short_prices = [100.0] * 100
        assert calculate_momentum_12_1(short_prices) == 0.0

        # Test with sufficient data and positive momentum
        prices = [100.0] * 252
        prices[-21] = 150.0  # Price 1 month ago
        momentum = calculate_momentum_12_1(prices)
        assert momentum == 50.0  # (150 - 100) / 100 * 100


class TestBreakoutAgent:
    """Tests for BreakoutAgent."""

    def test_no_breakout_insufficient_data(self):
        """BreakoutAgent should return no breakout for insufficient data."""
        from tests.conftest import MockV2StockData

        data = MockV2StockData(
            symbol="TEST",
            prices=[100.0] * 30,  # Less than 50 days
            volumes=[1_000_000.0] * 30,
        )

        agent = BreakoutAgent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        assert result.name == "breakout"
        assert result.components["breakout_detected"] == False

    def test_breakout_conditions_met(self):
        """BreakoutAgent should detect breakout when conditions are met."""
        from tests.conftest import MockV2StockData

        # Create data with tight consolidation and breakout
        prices = []
        volumes = []

        # Consolidation phase (days 0-49): tight range around 100
        for i in range(50):
            if i < 30:
                prices.append(100.0 + (i % 3) * 0.5)  # Tight range
            else:
                prices.append(102.0 + (i % 3) * 0.5)
            volumes.append(1_000_000.0)

        # Recent 19 days with normal volume
        for i in range(19):
            prices.append(103.0 + i * 0.1)
            volumes.append(1_000_000.0)

        # Last day: breakout with volume surge (current_volume vs avg_volume_20d)
        prices.append(max(prices) * 1.02)  # New high (above 98% of recent high)
        volumes.append(2_000_000.0)  # 2x average volume > 1.5 threshold

        data = MockV2StockData(
            symbol="TEST",
            prices=prices,
            volumes=volumes,
            week_52_high=max(prices),
        )

        agent = BreakoutAgent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        assert result.name == "breakout"
        # Should detect breakout with volume surge
        assert result.components["breakout_detected"] == True

    def test_no_breakout_without_volume(self):
        """BreakoutAgent should not detect breakout without volume confirmation."""
        from tests.conftest import MockV2StockData

        # Price at high but no volume surge
        prices = [100.0] * 50
        prices[-1] = 110.0  # New high
        volumes = [1_000_000.0] * 50  # Flat volume

        data = MockV2StockData(
            symbol="TEST",
            prices=prices,
            volumes=volumes,
            week_52_high=110.0,
        )

        agent = BreakoutAgent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        assert result.name == "breakout"
        # No breakout without volume confirmation
        assert result.components["breakout_detected"] == False

    def test_detect_breakout_function(self):
        """Test the detect_breakout helper function directly."""
        # Test with insufficient data
        result = detect_breakout([100.0] * 30, [1_000_000.0] * 30)
        assert result["is_breakout"] is False
        assert result["strength"] == 0

    def test_high_proximity_scoring(self, mock_v2_stock_data):
        """BreakoutAgent should score high for stocks near 52-week high."""
        # Set price at 52-week high
        mock_v2_stock_data.prices[-1] = mock_v2_stock_data.week_52_high

        agent = BreakoutAgent()
        result = agent.score(mock_v2_stock_data)

        assert isinstance(result, AgentScore)
        assert result.components["high_proximity"] == 25


class TestRiskAdjustedAgent:
    """Tests for RiskAdjustedAgent."""

    def test_low_vix_high_score(self):
        """RiskAdjustedAgent should score high when VIX is low."""
        from tests.conftest import MockV2StockData

        # Create stable price data (low volatility)
        prices = [100.0 + i * 0.1 for i in range(60)]  # Steady uptrend

        data = MockV2StockData(
            symbol="TEST",
            prices=prices,
            volumes=[1_000_000.0] * 60,
            vix_level=12.0,  # Low VIX
        )

        agent = RiskAdjustedAgent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        assert result.name == "risk_adjusted"
        assert result.components["vix_score"] == 40
        assert "Low volatility" in result.reasoning

    def test_high_vix_low_score(self):
        """RiskAdjustedAgent should score low when VIX is high."""
        from tests.conftest import MockV2StockData

        prices = [100.0 + i * 0.1 for i in range(60)]

        data = MockV2StockData(
            symbol="TEST",
            prices=prices,
            volumes=[1_000_000.0] * 60,
            vix_level=35.0,  # High VIX (extreme volatility)
        )

        agent = RiskAdjustedAgent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        assert result.name == "risk_adjusted"
        assert result.components["vix_score"] == 5
        assert "Extreme volatility" in result.reasoning

    def test_elevated_vix_moderate_score(self):
        """RiskAdjustedAgent should score moderately for elevated VIX."""
        from tests.conftest import MockV2StockData

        prices = [100.0 + i * 0.1 for i in range(60)]

        data = MockV2StockData(
            symbol="TEST",
            prices=prices,
            volumes=[1_000_000.0] * 60,
            vix_level=22.0,  # Elevated VIX
        )

        agent = RiskAdjustedAgent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        assert result.name == "risk_adjusted"
        assert result.components["vix_score"] == 25
        assert "Elevated volatility" in result.reasoning

    def test_stock_volatility_calculation(self):
        """RiskAdjustedAgent should calculate stock-specific volatility."""
        from tests.conftest import MockV2StockData

        # Create low volatility price data
        prices = [100.0 + i * 0.05 for i in range(60)]  # Very steady

        data = MockV2StockData(
            symbol="TEST",
            prices=prices,
            volumes=[1_000_000.0] * 60,
            vix_level=18.0,
        )

        agent = RiskAdjustedAgent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        # Stock volatility score should be high for low vol stock
        assert result.components["stock_volatility"] >= 25

    def test_drawdown_risk_scoring(self):
        """RiskAdjustedAgent should penalize stocks in drawdown."""
        from tests.conftest import MockV2StockData

        # Create price data with drawdown from peak
        prices = [100.0] * 30
        # Peak at 120, then decline to 100 (16.7% drawdown)
        prices.extend([120.0] * 10)
        prices.extend([100.0] * 20)

        data = MockV2StockData(
            symbol="TEST",
            prices=prices,
            volumes=[1_000_000.0] * 60,
            vix_level=18.0,
        )

        agent = RiskAdjustedAgent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        # Drawdown > 15% should get low score
        assert result.components["drawdown_risk"] == 5
        assert "In drawdown" in result.reasoning

    def test_no_drawdown_high_score(self):
        """RiskAdjustedAgent should score high for stocks near peak."""
        from tests.conftest import MockV2StockData

        # Create price data at all-time high
        prices = [100.0 + i * 0.2 for i in range(60)]  # Steady uptrend, at peak

        data = MockV2StockData(
            symbol="TEST",
            prices=prices,
            volumes=[1_000_000.0] * 60,
            vix_level=18.0,
        )

        agent = RiskAdjustedAgent()
        result = agent.score(data)

        assert isinstance(result, AgentScore)
        # At peak = 0% drawdown = high score
        assert result.components["drawdown_risk"] == 30

    def test_with_fixture(self, mock_v2_stock_data):
        """RiskAdjustedAgent should work with standard fixture."""
        agent = RiskAdjustedAgent()
        result = agent.score(mock_v2_stock_data)

        assert isinstance(result, AgentScore)
        assert result.name == "risk_adjusted"
        assert 0 <= result.score <= 100
        assert "vix_score" in result.components
        assert "stock_volatility" in result.components
        assert "drawdown_risk" in result.components


class TestAgentScoreStructure:
    """Tests to verify AgentScore structure is correct for all agents."""

    def test_all_agents_return_valid_scores(self, mock_v2_stock_data):
        """All V2 agents should return valid AgentScore objects."""
        agents = [
            CatalystAgent(),
            Momentum12_1Agent(),
            BreakoutAgent(),
            RiskAdjustedAgent(),
        ]

        for agent in agents:
            result = agent.score(mock_v2_stock_data)

            assert isinstance(result, AgentScore), f"{agent.__class__.__name__} did not return AgentScore"
            assert isinstance(result.name, str), f"{agent.__class__.__name__} name is not string"
            assert isinstance(result.score, int), f"{agent.__class__.__name__} score is not int"
            assert 0 <= result.score <= 100, f"{agent.__class__.__name__} score out of range"
            assert isinstance(result.components, dict), f"{agent.__class__.__name__} components is not dict"
            assert isinstance(result.reasoning, str), f"{agent.__class__.__name__} reasoning is not string"
