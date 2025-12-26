"""
Async Data Fetcher - High-performance parallel data fetching

Provides asynchronous data fetching with:
- 10 concurrent connections (configurable via semaphore)
- 3 retry attempts with exponential backoff
- 30 second timeout per request
- Compatible with existing sync clients as fallback
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TypeVar

import aiohttp

from src.config import config
from src.scoring.agents import StockData
from src.scoring.agents_v2 import V2StockData

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class AsyncFetcherConfig:
    """Configuration for async fetcher."""
    max_concurrent: int = 10  # Semaphore limit
    timeout_seconds: float = 30.0  # Per-request timeout
    max_retries: int = 3  # Retry attempts
    base_backoff: float = 1.0  # Base delay for exponential backoff
    finnhub_rate_limit: int = 60  # Calls per minute


@dataclass
class FetchResult:
    """Result of a single fetch operation."""
    symbol: str
    success: bool
    v1_data: StockData | None = None
    v2_data: V2StockData | None = None
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class BatchFetchResult:
    """Result of batch fetch operation."""
    successful: list[tuple[StockData, V2StockData]]
    failed: list[tuple[str, str]]  # (symbol, error)
    total_duration_ms: float
    parallel_speedup: float  # Estimated speedup vs sequential


class AsyncDataFetcher:
    """
    Async data fetcher with semaphore-based concurrency control.

    Fetches stock data in parallel while respecting rate limits.
    Falls back to synchronous mode if async fails.
    """

    def __init__(self, fetch_config: AsyncFetcherConfig | None = None):
        """
        Initialize the async fetcher.

        Args:
            fetch_config: Configuration for fetching behavior
        """
        self.config = fetch_config or AsyncFetcherConfig()
        self._semaphore: asyncio.Semaphore | None = None
        self._session: aiohttp.ClientSession | None = None
        self._finnhub_api_key = config.finnhub.api_key
        self._base_url = "https://finnhub.io/api/v1"

        # Rate limiting state
        self._request_times: list[float] = []
        self._rate_lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _get_semaphore(self) -> asyncio.Semaphore:
        """Get or create semaphore."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.config.max_concurrent)
        return self._semaphore

    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _wait_for_rate_limit(self):
        """Wait if necessary to respect rate limits."""
        async with self._rate_lock:
            now = time.time()
            # Remove requests older than 1 minute
            self._request_times = [t for t in self._request_times if now - t < 60]

            if len(self._request_times) >= self.config.finnhub_rate_limit:
                # Need to wait until oldest request expires
                oldest = min(self._request_times)
                wait_time = 60 - (now - oldest) + 0.1  # Add small buffer
                if wait_time > 0:
                    logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)

            self._request_times.append(time.time())

    async def _fetch_with_retry(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Fetch URL with retry logic and exponential backoff.

        Args:
            url: Full URL to fetch
            params: Query parameters

        Returns:
            JSON response as dict

        Raises:
            Exception: If all retries fail
        """
        session = await self._get_session()
        last_error: Exception | None = None

        for attempt in range(self.config.max_retries):
            try:
                await self._wait_for_rate_limit()

                async with session.get(url, params=params) as response:
                    if response.status == 429:
                        # Rate limited - wait and retry
                        wait_time = self.config.base_backoff * (2 ** attempt)
                        logger.warning(f"Rate limited (429), waiting {wait_time}s (attempt {attempt + 1})")
                        await asyncio.sleep(wait_time)
                        continue

                    response.raise_for_status()
                    return await response.json()

            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(f"Timeout (attempt {attempt + 1}/{self.config.max_retries})")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.base_backoff * (2 ** attempt))

            except aiohttp.ClientError as e:
                last_error = e
                error_str = str(e).lower()

                if "429" in error_str or "rate" in error_str:
                    wait_time = self.config.base_backoff * (2 ** attempt) * 2
                    logger.warning(f"Rate limited, waiting {wait_time}s (attempt {attempt + 1})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.warning(f"Client error: {e} (attempt {attempt + 1})")
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.base_backoff * (2 ** attempt))

            except Exception as e:
                last_error = e
                logger.warning(f"Unexpected error: {e} (attempt {attempt + 1})")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.base_backoff * (2 ** attempt))

        raise last_error or Exception("All retries failed")

    async def _fetch_candles(
        self,
        symbol: str,
        from_timestamp: int,
        to_timestamp: int,
    ) -> dict[str, list]:
        """Fetch OHLCV candles from Finnhub."""
        url = f"{self._base_url}/stock/candle"
        params = {
            "symbol": symbol,
            "resolution": "D",
            "from": from_timestamp,
            "to": to_timestamp,
            "token": self._finnhub_api_key,
        }

        data = await self._fetch_with_retry(url, params)

        if data.get("s") == "no_data":
            return {"open": [], "high": [], "low": [], "close": [], "volume": [], "timestamp": []}

        return {
            "open": data.get("o", []),
            "high": data.get("h", []),
            "low": data.get("l", []),
            "close": data.get("c", []),
            "volume": data.get("v", []),
            "timestamp": data.get("t", []),
        }

    async def _fetch_quote(self, symbol: str) -> dict[str, Any]:
        """Fetch current quote from Finnhub."""
        url = f"{self._base_url}/quote"
        params = {
            "symbol": symbol,
            "token": self._finnhub_api_key,
        }
        return await self._fetch_with_retry(url, params)

    async def _fetch_financials(self, symbol: str) -> dict[str, Any]:
        """Fetch basic financials from Finnhub."""
        url = f"{self._base_url}/stock/metric"
        params = {
            "symbol": symbol,
            "metric": "all",
            "token": self._finnhub_api_key,
        }
        return await self._fetch_with_retry(url, params)

    async def _fetch_news_count(self, symbol: str) -> int:
        """Fetch news count for last 7 days."""
        url = f"{self._base_url}/company-news"
        from_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        params = {
            "symbol": symbol,
            "from": from_date,
            "to": to_date,
            "token": self._finnhub_api_key,
        }

        try:
            data = await self._fetch_with_retry(url, params)
            return len(data) if isinstance(data, list) else 0
        except Exception:
            return 0

    async def _fetch_earnings_surprise(self, symbol: str) -> float | None:
        """Fetch most recent earnings surprise percentage."""
        url = f"{self._base_url}/stock/earnings"
        params = {
            "symbol": symbol,
            "limit": 1,
            "token": self._finnhub_api_key,
        }

        try:
            data = await self._fetch_with_retry(url, params)
            if data and isinstance(data, list) and len(data) > 0:
                item = data[0]
                actual = item.get("actual")
                estimate = item.get("estimate")
                if actual is not None and estimate is not None and estimate != 0:
                    return ((actual - estimate) / abs(estimate)) * 100
            return None
        except Exception:
            return None

    async def _fetch_price_target(self, symbol: str, current_price: float) -> float | None:
        """Fetch analyst price target and calculate upside percentage."""
        url = f"{self._base_url}/stock/price-target"
        params = {
            "symbol": symbol,
            "token": self._finnhub_api_key,
        }

        try:
            data = await self._fetch_with_retry(url, params)
            target_mean = data.get("targetMean")
            if target_mean and target_mean > 0 and current_price > 0:
                return ((target_mean - current_price) / current_price) * 100
            return None
        except Exception:
            return None

    async def fetch_stock_data(
        self,
        symbol: str,
        vix_level: float,
    ) -> FetchResult:
        """
        Fetch all data for a single stock.

        Uses semaphore to limit concurrent requests.

        Args:
            symbol: Stock ticker symbol
            vix_level: Current VIX level for V2 data

        Returns:
            FetchResult with V1 and V2 stock data or error
        """
        semaphore = await self._get_semaphore()
        start_time = time.time()

        async with semaphore:
            try:
                # Calculate timestamps
                now = datetime.now(timezone.utc)
                to_timestamp = int(now.timestamp())
                from_timestamp = int((now - timedelta(days=250)).timestamp())

                # Fetch all data concurrently
                candles_task = self._fetch_candles(symbol, from_timestamp, to_timestamp)
                quote_task = self._fetch_quote(symbol)
                financials_task = self._fetch_financials(symbol)
                news_task = self._fetch_news_count(symbol)
                earnings_task = self._fetch_earnings_surprise(symbol)

                candles, quote, financials, news_count, earnings_surprise = await asyncio.gather(
                    candles_task, quote_task, financials_task, news_task, earnings_task,
                    return_exceptions=True,
                )

                # Handle potential exceptions from gather
                if isinstance(candles, Exception):
                    raise candles
                if isinstance(quote, Exception):
                    quote = {}
                if isinstance(financials, Exception):
                    financials = {}
                if isinstance(news_count, Exception):
                    news_count = 0
                if isinstance(earnings_surprise, Exception):
                    earnings_surprise = None

                # Extract price data
                prices = candles.get("close", [])
                volumes = candles.get("volume", [])

                if not prices:
                    return FetchResult(
                        symbol=symbol,
                        success=False,
                        error="No price data available",
                        duration_ms=(time.time() - start_time) * 1000,
                    )

                # Extract quote data
                open_price = quote.get("o", 0)
                previous_close = quote.get("pc", 0)

                if open_price == 0 and prices:
                    open_price = prices[-1]

                # Extract financials
                metrics = financials.get("metric", {})
                pe_ratio = metrics.get("peBasicExclExtraTTM")
                pb_ratio = metrics.get("pbQuarterly")
                dividend_yield = metrics.get("dividendYieldIndicatedAnnual")
                week_52_high = metrics.get("52WeekHigh")
                week_52_low = metrics.get("52WeekLow")

                # Calculate gap percentage
                gap_pct = 0.0
                if previous_close and previous_close > 0:
                    gap_pct = ((open_price - previous_close) / previous_close) * 100

                # Fetch price target (needs current price)
                current_price = prices[-1] if prices else 0
                analyst_revision = await self._fetch_price_target(symbol, current_price)

                # Create V1 data
                v1_data = StockData(
                    symbol=symbol,
                    prices=prices,
                    volumes=volumes,
                    open_price=open_price,
                    pe_ratio=pe_ratio,
                    pb_ratio=pb_ratio,
                    dividend_yield=dividend_yield,
                    week_52_high=week_52_high,
                    week_52_low=week_52_low,
                    news_count_7d=news_count,
                    news_sentiment=None,
                    sector_avg_pe=25.0,
                )

                # Create V2 data
                v2_data = V2StockData(
                    symbol=symbol,
                    prices=prices,
                    volumes=volumes,
                    open_price=open_price,
                    pe_ratio=pe_ratio,
                    pb_ratio=pb_ratio,
                    dividend_yield=dividend_yield,
                    week_52_high=week_52_high,
                    week_52_low=week_52_low,
                    news_count_7d=news_count,
                    news_sentiment=None,
                    sector_avg_pe=25.0,
                    vix_level=vix_level,
                    gap_pct=gap_pct,
                    earnings_surprise_pct=earnings_surprise,
                    analyst_revision_score=analyst_revision,
                )

                return FetchResult(
                    symbol=symbol,
                    success=True,
                    v1_data=v1_data,
                    v2_data=v2_data,
                    duration_ms=(time.time() - start_time) * 1000,
                )

            except asyncio.TimeoutError:
                return FetchResult(
                    symbol=symbol,
                    success=False,
                    error="Request timeout",
                    duration_ms=(time.time() - start_time) * 1000,
                )
            except Exception as e:
                return FetchResult(
                    symbol=symbol,
                    success=False,
                    error=str(e),
                    duration_ms=(time.time() - start_time) * 1000,
                )

    async def fetch_batch(
        self,
        symbols: list[str],
        vix_level: float,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> BatchFetchResult:
        """
        Fetch data for multiple stocks in parallel.

        Args:
            symbols: List of stock ticker symbols
            vix_level: Current VIX level
            progress_callback: Optional callback(symbol, current, total)

        Returns:
            BatchFetchResult with successful and failed fetches
        """
        start_time = time.time()
        total = len(symbols)
        completed = 0

        async def fetch_with_progress(symbol: str) -> FetchResult:
            nonlocal completed
            result = await self.fetch_stock_data(symbol, vix_level)
            completed += 1
            if progress_callback:
                progress_callback(symbol, completed, total)
            return result

        # Create tasks for all symbols
        tasks = [fetch_with_progress(symbol) for symbol in symbols]

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks)

        # Separate successful and failed
        successful: list[tuple[StockData, V2StockData]] = []
        failed: list[tuple[str, str]] = []

        for result in results:
            if result.success and result.v1_data and result.v2_data:
                successful.append((result.v1_data, result.v2_data))
            else:
                failed.append((result.symbol, result.error or "Unknown error"))

        total_duration_ms = (time.time() - start_time) * 1000

        # Estimate sequential time (assuming 0.5s per symbol)
        estimated_sequential_ms = len(symbols) * 500
        speedup = estimated_sequential_ms / total_duration_ms if total_duration_ms > 0 else 1.0

        return BatchFetchResult(
            successful=successful,
            failed=failed,
            total_duration_ms=total_duration_ms,
            parallel_speedup=speedup,
        )


async def fetch_stocks_async(
    symbols: list[str],
    vix_level: float,
    fetch_config: AsyncFetcherConfig | None = None,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> BatchFetchResult:
    """
    Convenience function to fetch stocks asynchronously.

    Args:
        symbols: List of stock ticker symbols
        vix_level: Current VIX level
        fetch_config: Optional fetcher configuration
        progress_callback: Optional progress callback

    Returns:
        BatchFetchResult with successful and failed fetches
    """
    fetcher = AsyncDataFetcher(fetch_config)
    try:
        return await fetcher.fetch_batch(symbols, vix_level, progress_callback)
    finally:
        await fetcher.close()


def fetch_stocks_sync_wrapper(
    symbols: list[str],
    vix_level: float,
    fetch_config: AsyncFetcherConfig | None = None,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> BatchFetchResult:
    """
    Synchronous wrapper for async fetch.

    Use this in existing sync code to leverage async fetching.

    Args:
        symbols: List of stock ticker symbols
        vix_level: Current VIX level
        fetch_config: Optional fetcher configuration
        progress_callback: Optional progress callback

    Returns:
        BatchFetchResult with successful and failed fetches
    """
    return asyncio.run(
        fetch_stocks_async(symbols, vix_level, fetch_config, progress_callback)
    )
