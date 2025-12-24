"""
Pytest fixtures for AI Pick Daily tests.
"""
import pytest
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class MockStockData:
    """Mock StockData for testing."""
    symbol: str
    prices: list[float]
    volumes: list[float]
    open_price: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    dividend_yield: float | None = None
    week_52_high: float | None = None
    week_52_low: float | None = None
    news_count_7d: int = 0
    news_sentiment: float | None = None
    sector_avg_pe: float = 20.0


@dataclass
class MockV2StockData:
    """Mock V2StockData for testing."""
    symbol: str
    prices: list[float]
    volumes: list[float]
    open_price: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    dividend_yield: float | None = None
    week_52_high: float | None = None
    week_52_low: float | None = None
    news_count_7d: int = 0
    news_sentiment: float | None = None
    sector_avg_pe: float = 20.0
    vix_level: float | None = None
    gap_pct: float | None = None
    earnings_surprise_pct: float | None = None
    analyst_revision_score: float | None = None
    short_interest_pct: float | None = None


@dataclass
class MockJudgmentOutput:
    """Mock JudgmentOutput for testing."""
    symbol: str
    decision: str  # 'buy', 'hold', 'avoid'
    confidence: float
    score: int = 70
    strategy_mode: str = "conservative"


@pytest.fixture
def sample_prices() -> list[float]:
    """Generate sample price series (60 days of data)."""
    import random
    random.seed(42)
    base_price = 100.0
    prices = [base_price]
    for _ in range(59):
        change = random.uniform(-0.02, 0.025)  # Slight upward bias
        prices.append(prices[-1] * (1 + change))
    return prices


@pytest.fixture
def sample_volumes() -> list[float]:
    """Generate sample volume series (60 days)."""
    import random
    random.seed(42)
    return [random.uniform(1_000_000, 5_000_000) for _ in range(60)]


@pytest.fixture
def mock_stock_data(sample_prices: list[float], sample_volumes: list[float]) -> MockStockData:
    """Create a mock StockData instance."""
    return MockStockData(
        symbol="AAPL",
        prices=sample_prices,
        volumes=sample_volumes,
        open_price=sample_prices[-2],
        pe_ratio=25.0,
        pb_ratio=10.0,
        dividend_yield=0.5,
        week_52_high=max(sample_prices),
        week_52_low=min(sample_prices),
        news_count_7d=5,
        news_sentiment=0.3,
        sector_avg_pe=22.0,
    )


@pytest.fixture
def mock_v2_stock_data(sample_prices: list[float], sample_volumes: list[float]) -> MockV2StockData:
    """Create a mock V2StockData instance."""
    return MockV2StockData(
        symbol="AAPL",
        prices=sample_prices,
        volumes=sample_volumes,
        open_price=sample_prices[-2],
        pe_ratio=25.0,
        pb_ratio=10.0,
        dividend_yield=0.5,
        week_52_high=max(sample_prices),
        week_52_low=min(sample_prices),
        news_count_7d=5,
        news_sentiment=0.3,
        sector_avg_pe=22.0,
        vix_level=18.0,
        gap_pct=2.5,
        earnings_surprise_pct=15.0,
        analyst_revision_score=8.0,
        short_interest_pct=5.0,
    )


@pytest.fixture
def sample_judgments() -> list[MockJudgmentOutput]:
    """Create sample LLM judgments for testing."""
    return [
        MockJudgmentOutput(symbol="AAPL", decision="buy", confidence=0.85),
        MockJudgmentOutput(symbol="MSFT", decision="buy", confidence=0.75),
        MockJudgmentOutput(symbol="GOOGL", decision="buy", confidence=0.65),
        MockJudgmentOutput(symbol="AMZN", decision="hold", confidence=0.70),
        MockJudgmentOutput(symbol="META", decision="buy", confidence=0.55),
        MockJudgmentOutput(symbol="NVDA", decision="avoid", confidence=0.80),
    ]


@pytest.fixture
def v1_weights() -> dict[str, float]:
    """Default V1 weights."""
    return {
        "trend": 0.35,
        "momentum": 0.35,
        "value": 0.20,
        "sentiment": 0.10,
    }


@pytest.fixture
def v2_weights() -> dict[str, float]:
    """Default V2 weights."""
    return {
        "momentum_12_1": 0.40,
        "breakout": 0.25,
        "catalyst": 0.20,
        "risk_adjusted": 0.15,
    }
