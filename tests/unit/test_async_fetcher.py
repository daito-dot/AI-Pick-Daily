"""
Tests for AsyncDataFetcher

Tests async data fetching with mocked API responses.
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import importlib.util

import pytest

# Create mocks for dependencies before any imports
class MockConfig:
    class Finnhub:
        api_key = "test_api_key"
    finnhub = Finnhub()


class MockStockData:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# Pre-populate sys.modules with mocks to avoid import errors
if "src.config" not in sys.modules:
    mock_config_module = MagicMock()
    mock_config_module.config = MockConfig()
    sys.modules["src.config"] = mock_config_module

if "src.scoring.agents" not in sys.modules:
    mock_agents_module = MagicMock()
    mock_agents_module.StockData = MockStockData
    sys.modules["src.scoring.agents"] = mock_agents_module

if "src.scoring.agents_v2" not in sys.modules:
    mock_agents_v2_module = MagicMock()
    mock_agents_v2_module.V2StockData = MockStockData
    sys.modules["src.scoring.agents_v2"] = mock_agents_v2_module

# Load async_fetcher directly without going through __init__.py
async_fetcher_path = Path(__file__).parent.parent.parent / "src" / "data" / "async_fetcher.py"
spec = importlib.util.spec_from_file_location("src.data.async_fetcher", async_fetcher_path)
async_fetcher = importlib.util.module_from_spec(spec)
sys.modules["src.data.async_fetcher"] = async_fetcher
spec.loader.exec_module(async_fetcher)

# Import what we need from the loaded module
AsyncDataFetcher = async_fetcher.AsyncDataFetcher
AsyncFetcherConfig = async_fetcher.AsyncFetcherConfig
BatchFetchResult = async_fetcher.BatchFetchResult
FetchResult = async_fetcher.FetchResult
fetch_stocks_async = async_fetcher.fetch_stocks_async
fetch_stocks_sync_wrapper = async_fetcher.fetch_stocks_sync_wrapper


@pytest.fixture
def fetcher_config():
    """Create a test fetcher config with lower limits."""
    return AsyncFetcherConfig(
        max_concurrent=2,
        timeout_seconds=5.0,
        max_retries=2,
        base_backoff=0.1,
        finnhub_rate_limit=100,
    )


@pytest.fixture
def mock_candles_response():
    """Mock candles API response."""
    return {
        "s": "ok",
        "o": [100.0, 101.0, 102.0],
        "h": [105.0, 106.0, 107.0],
        "l": [99.0, 100.0, 101.0],
        "c": [104.0, 105.0, 106.0],
        "v": [1000000, 1100000, 1200000],
        "t": [1700000000, 1700086400, 1700172800],
    }


@pytest.fixture
def mock_quote_response():
    """Mock quote API response."""
    return {
        "c": 150.0,
        "d": 2.5,
        "dp": 1.69,
        "h": 152.0,
        "l": 148.0,
        "o": 149.0,
        "pc": 147.5,
        "t": 1700000000,
    }


@pytest.fixture
def mock_financials_response():
    """Mock financials API response."""
    return {
        "metric": {
            "peBasicExclExtraTTM": 25.5,
            "pbQuarterly": 4.2,
            "dividendYieldIndicatedAnnual": 0.5,
            "52WeekHigh": 200.0,
            "52WeekLow": 100.0,
        }
    }


class TestAsyncFetcherConfig:
    """Tests for AsyncFetcherConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AsyncFetcherConfig()
        assert config.max_concurrent == 10
        assert config.timeout_seconds == 30.0
        assert config.max_retries == 3
        assert config.base_backoff == 1.0
        assert config.finnhub_rate_limit == 60

    def test_custom_config(self, fetcher_config):
        """Test custom configuration values."""
        assert fetcher_config.max_concurrent == 2
        assert fetcher_config.timeout_seconds == 5.0
        assert fetcher_config.max_retries == 2


class TestFetchResult:
    """Tests for FetchResult dataclass."""

    def test_success_result(self):
        """Test successful fetch result."""
        result = FetchResult(
            symbol="AAPL",
            success=True,
            duration_ms=100.0,
        )
        assert result.symbol == "AAPL"
        assert result.success is True
        assert result.error is None

    def test_failure_result(self):
        """Test failed fetch result."""
        result = FetchResult(
            symbol="AAPL",
            success=False,
            error="Connection timeout",
            duration_ms=5000.0,
        )
        assert result.symbol == "AAPL"
        assert result.success is False
        assert result.error == "Connection timeout"


class TestBatchFetchResult:
    """Tests for BatchFetchResult dataclass."""

    def test_batch_result(self):
        """Test batch fetch result."""
        result = BatchFetchResult(
            successful=[],
            failed=[("AAPL", "timeout")],
            total_duration_ms=1000.0,
            parallel_speedup=2.5,
        )
        assert len(result.successful) == 0
        assert len(result.failed) == 1
        assert result.parallel_speedup == 2.5


class TestAsyncDataFetcher:
    """Tests for AsyncDataFetcher class."""

    @pytest.mark.asyncio
    async def test_fetcher_initialization(self, fetcher_config):
        """Test fetcher initialization."""
        fetcher = AsyncDataFetcher(fetcher_config)
        assert fetcher.config.max_concurrent == 2
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_semaphore(self, fetcher_config):
        """Test semaphore creation."""
        fetcher = AsyncDataFetcher(fetcher_config)
        semaphore = await fetcher._get_semaphore()
        assert isinstance(semaphore, asyncio.Semaphore)
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_fetch_stock_data_success(
        self,
        fetcher_config,
        mock_candles_response,
        mock_quote_response,
        mock_financials_response,
    ):
        """Test successful stock data fetch."""
        fetcher = AsyncDataFetcher(fetcher_config)

        with patch.object(
            fetcher,
            "_fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch:
            # Setup mock responses
            mock_fetch.side_effect = [
                mock_candles_response,
                mock_quote_response,
                mock_financials_response,
                [],  # news
            ]

            result = await fetcher.fetch_stock_data("AAPL", vix_level=15.0)

            assert result.success is True
            assert result.symbol == "AAPL"
            assert result.v1_data is not None
            assert result.v2_data is not None

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_fetch_stock_data_no_prices(self, fetcher_config):
        """Test fetch with no price data."""
        fetcher = AsyncDataFetcher(fetcher_config)

        with patch.object(
            fetcher,
            "_fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch:
            # Return empty candles
            mock_fetch.side_effect = [
                {"s": "no_data"},  # candles
                {},  # quote
                {},  # financials
                0,  # news
            ]

            result = await fetcher.fetch_stock_data("INVALID", vix_level=15.0)

            assert result.success is False
            assert "No price data" in result.error

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_fetch_batch(self, fetcher_config):
        """Test batch fetch with multiple symbols."""
        fetcher = AsyncDataFetcher(fetcher_config)

        # Mock the fetch_stock_data method
        async def mock_fetch_stock(symbol, vix_level):
            if symbol == "FAIL":
                return FetchResult(
                    symbol=symbol,
                    success=False,
                    error="API error",
                    duration_ms=100.0,
                )
            return FetchResult(
                symbol=symbol,
                success=True,
                v1_data=MagicMock(symbol=symbol),
                v2_data=MagicMock(symbol=symbol),
                duration_ms=100.0,
            )

        with patch.object(fetcher, "fetch_stock_data", side_effect=mock_fetch_stock):
            result = await fetcher.fetch_batch(
                symbols=["AAPL", "MSFT", "FAIL"],
                vix_level=15.0,
            )

            assert len(result.successful) == 2
            assert len(result.failed) == 1
            assert result.failed[0][0] == "FAIL"
            assert result.parallel_speedup > 0

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_fetch_batch_with_progress(self, fetcher_config):
        """Test batch fetch with progress callback."""
        fetcher = AsyncDataFetcher(fetcher_config)
        progress_calls = []

        def progress_callback(symbol, current, total):
            progress_calls.append((symbol, current, total))

        async def mock_fetch_stock(symbol, vix_level):
            return FetchResult(
                symbol=symbol,
                success=True,
                v1_data=MagicMock(symbol=symbol),
                v2_data=MagicMock(symbol=symbol),
                duration_ms=100.0,
            )

        with patch.object(fetcher, "fetch_stock_data", side_effect=mock_fetch_stock):
            await fetcher.fetch_batch(
                symbols=["AAPL", "MSFT"],
                vix_level=15.0,
                progress_callback=progress_callback,
            )

            assert len(progress_calls) == 2

        await fetcher.close()


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limit_tracking(self):
        """Test that rate limit tracking works."""
        config = AsyncFetcherConfig(
            max_concurrent=2,
            finnhub_rate_limit=5,  # Low limit for testing
        )
        fetcher = AsyncDataFetcher(config)

        # The rate limiter should track requests
        assert len(fetcher._request_times) == 0

        await fetcher.close()
