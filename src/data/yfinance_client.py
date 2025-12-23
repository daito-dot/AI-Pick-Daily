"""
yfinance Client - Fallback data source

Used when Finnhub API fails or hits rate limits.
Implements conservative rate limiting to avoid Yahoo blocks.
"""
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

# Rate limiting: Be conservative to avoid blocks
MIN_REQUEST_INTERVAL = 1.0  # Minimum 1 second between requests
MAX_REQUEST_INTERVAL = 2.0  # Add random delay up to 2 seconds
_last_request_time = 0.0


def _rate_limit():
    """Apply rate limiting with random jitter to avoid detection."""
    global _last_request_time

    elapsed = time.time() - _last_request_time
    min_wait = MIN_REQUEST_INTERVAL - elapsed

    if min_wait > 0:
        # Add random jitter to avoid predictable patterns
        jitter = random.uniform(0, MAX_REQUEST_INTERVAL - MIN_REQUEST_INTERVAL)
        wait_time = min_wait + jitter
        logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
        time.sleep(wait_time)

    _last_request_time = time.time()


def _retry_with_backoff(func, max_retries: int = 3):
    """Execute function with exponential backoff on failure."""
    last_error = None

    for attempt in range(max_retries):
        try:
            _rate_limit()
            return func()
        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            # Check for common blocking indicators
            if any(x in error_str for x in ["429", "too many", "blocked", "forbidden"]):
                wait_time = (2 ** attempt) * 5  # 5s, 10s, 20s
                logger.warning(f"yfinance blocked (attempt {attempt + 1}), waiting {wait_time}s")
                time.sleep(wait_time)
            else:
                # Other errors - shorter backoff
                wait_time = 2 ** attempt
                logger.warning(f"yfinance error (attempt {attempt + 1}): {e}, waiting {wait_time}s")
                time.sleep(wait_time)

    raise last_error


@dataclass
class YFinanceQuote:
    """Stock quote from yfinance."""
    symbol: str
    current_price: float
    previous_close: float
    open_price: float
    high: float
    low: float
    volume: int


@dataclass
class YFinanceCandles:
    """Historical candle data from yfinance."""
    symbol: str
    dates: list[datetime]
    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    volumes: list[int]


class YFinanceClient:
    """
    yfinance client with rate limiting and error handling.

    Used as fallback when Finnhub fails.
    """

    def __init__(self):
        """Initialize the yfinance client."""
        logger.info("Initializing yfinance client (fallback data source)")

    def get_quote(self, symbol: str) -> YFinanceQuote | None:
        """
        Get current quote for a symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            YFinanceQuote or None if failed
        """
        def _fetch():
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info

            return YFinanceQuote(
                symbol=symbol,
                current_price=float(info.get("lastPrice", 0) or info.get("regularMarketPrice", 0)),
                previous_close=float(info.get("previousClose", 0) or info.get("regularMarketPreviousClose", 0)),
                open_price=float(info.get("open", 0) or info.get("regularMarketOpen", 0)),
                high=float(info.get("dayHigh", 0) or info.get("regularMarketDayHigh", 0)),
                low=float(info.get("dayLow", 0) or info.get("regularMarketDayLow", 0)),
                volume=int(info.get("lastVolume", 0) or info.get("regularMarketVolume", 0)),
            )

        try:
            return _retry_with_backoff(_fetch)
        except Exception as e:
            logger.error(f"yfinance failed to get quote for {symbol}: {e}")
            return None

    def get_candles(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
    ) -> YFinanceCandles | None:
        """
        Get historical candle data.

        Args:
            symbol: Stock ticker symbol
            period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)

        Returns:
            YFinanceCandles or None if failed
        """
        def _fetch():
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, interval=interval)

            if hist.empty:
                raise ValueError(f"No historical data returned for {symbol}")

            return YFinanceCandles(
                symbol=symbol,
                dates=hist.index.tolist(),
                opens=hist["Open"].tolist(),
                highs=hist["High"].tolist(),
                lows=hist["Low"].tolist(),
                closes=hist["Close"].tolist(),
                volumes=hist["Volume"].astype(int).tolist(),
            )

        try:
            return _retry_with_backoff(_fetch)
        except Exception as e:
            logger.error(f"yfinance failed to get candles for {symbol}: {e}")
            return None

    def get_vix(self) -> float | None:
        """
        Get current VIX value.

        Returns:
            VIX value or None if failed
        """
        def _fetch():
            ticker = yf.Ticker("^VIX")
            info = ticker.fast_info
            vix = float(info.get("lastPrice", 0) or info.get("regularMarketPrice", 0))

            if vix <= 0:
                # Try from history
                hist = ticker.history(period="1d")
                if not hist.empty:
                    vix = float(hist["Close"].iloc[-1])

            return vix if vix > 0 else None

        try:
            return _retry_with_backoff(_fetch)
        except Exception as e:
            logger.error(f"yfinance failed to get VIX: {e}")
            return None

    def get_sp500_price(self) -> float | None:
        """
        Get current S&P 500 price (via SPY ETF).

        Returns:
            SPY price or None if failed
        """
        quote = self.get_quote("SPY")
        return quote.current_price if quote else None

    def get_sp500_daily_return(self) -> float | None:
        """
        Get S&P 500 daily return percentage.

        Returns:
            Daily return as percentage (e.g., 1.5 for +1.5%) or None if failed
        """
        def _fetch():
            ticker = yf.Ticker("SPY")
            hist = ticker.history(period="5d")
            if len(hist) < 2:
                return None
            prev_close = float(hist["Close"].iloc[-2])
            curr_close = float(hist["Close"].iloc[-1])
            if prev_close <= 0:
                return None
            return ((curr_close - prev_close) / prev_close) * 100

        try:
            return _retry_with_backoff(_fetch)
        except Exception as e:
            logger.error(f"yfinance failed to get S&P500 daily return: {e}")
            return None

    def get_nikkei_daily_return(self) -> float | None:
        """
        Get Nikkei 225 daily return percentage.

        Returns:
            Daily return as percentage (e.g., 1.5 for +1.5%) or None if failed
        """
        def _fetch():
            ticker = yf.Ticker("^N225")
            hist = ticker.history(period="5d")
            if len(hist) < 2:
                return None
            prev_close = float(hist["Close"].iloc[-2])
            curr_close = float(hist["Close"].iloc[-1])
            if prev_close <= 0:
                return None
            return ((curr_close - prev_close) / prev_close) * 100

        try:
            return _retry_with_backoff(_fetch)
        except Exception as e:
            logger.error(f"yfinance failed to get Nikkei daily return: {e}")
            return None

    def get_nikkei_price(self) -> float | None:
        """
        Get current Nikkei 225 price.

        Returns:
            Nikkei 225 price or None if failed
        """
        def _fetch():
            ticker = yf.Ticker("^N225")
            info = ticker.fast_info
            price = float(info.get("lastPrice", 0) or info.get("regularMarketPrice", 0))
            if price <= 0:
                hist = ticker.history(period="1d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            return price if price > 0 else None

        try:
            return _retry_with_backoff(_fetch)
        except Exception as e:
            logger.error(f"yfinance failed to get Nikkei price: {e}")
            return None

    def get_basic_financials(self, symbol: str) -> dict[str, Any] | None:
        """
        Get basic financial metrics.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with pe_ratio, pb_ratio, etc. or None if failed
        """
        def _fetch():
            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
                "pb_ratio": info.get("priceToBook"),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
                "eps": info.get("trailingEps"),
                "week_52_high": info.get("fiftyTwoWeekHigh"),
                "week_52_low": info.get("fiftyTwoWeekLow"),
                "market_cap": info.get("marketCap"),
            }

        try:
            return _retry_with_backoff(_fetch)
        except Exception as e:
            logger.error(f"yfinance failed to get financials for {symbol}: {e}")
            return None


# Singleton instance
_client: YFinanceClient | None = None


def get_yfinance_client() -> YFinanceClient:
    """Get the singleton yfinance client instance."""
    global _client
    if _client is None:
        _client = YFinanceClient()
    return _client
