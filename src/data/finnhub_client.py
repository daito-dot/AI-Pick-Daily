"""
Finnhub API Client

Provides access to market data:
- Stock prices (OHLCV)
- Company financials (PER, PBR, etc.)
- News & sentiment
- Earnings calendar
- Market indices (VIX, S&P 500)
"""
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable

import finnhub

from src.config import config

# Thread-safe rate limiter state
_rate_limit_lock = threading.Lock()
_last_call_time = 0.0


def rate_limit_aware(calls_per_minute: int = 60, base_sleep: float = 1.0):
    """
    Decorator for handling Finnhub API rate limits.

    Finnhub free tier: 60 calls/minute.
    Thread-safe implementation using Lock.
    """
    min_interval = 60.0 / calls_per_minute

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            global _last_call_time

            with _rate_limit_lock:
                elapsed = time.time() - _last_call_time
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)
                _last_call_time = time.time()

            for attempt in range(3):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if "429" in str(e) or "limit" in str(e).lower():
                        sleep_time = base_sleep * (2 ** attempt)
                        print(f"Rate limited. Sleeping {sleep_time}s...")
                        time.sleep(sleep_time)
                    else:
                        raise
            raise Exception("Failed after 3 retries")
        return wrapper
    return decorator


@dataclass
class StockQuote:
    """Stock quote data."""
    symbol: str
    current_price: float
    change: float
    change_percent: float
    high: float
    low: float
    open: float
    previous_close: float
    timestamp: datetime


@dataclass
class CompanyProfile:
    """Company profile data."""
    symbol: str
    name: str
    market_cap: float
    sector: str
    industry: str
    exchange: str


@dataclass
class BasicFinancials:
    """Basic financial metrics."""
    symbol: str
    pe_ratio: float | None
    pb_ratio: float | None
    dividend_yield: float | None
    beta: float | None
    eps: float | None
    week_52_high: float | None
    week_52_low: float | None


@dataclass
class EarningsEvent:
    """Earnings calendar event."""
    symbol: str
    date: str
    hour: str  # 'bmo' (before market open), 'amc' (after market close), 'dmh' (during market hours)
    estimate_eps: float | None
    actual_eps: float | None


@dataclass
class EarningsSurprise:
    """Historical earnings surprise data."""
    symbol: str
    period: str  # e.g., "2024-09-30"
    actual: float
    estimate: float
    surprise_pct: float  # (actual - estimate) / |estimate| * 100


@dataclass
class PriceTarget:
    """Analyst price target data."""
    symbol: str
    target_high: float
    target_low: float
    target_mean: float
    target_median: float
    last_updated: str


@dataclass
class NewsItem:
    """News article data."""
    id: int
    symbol: str
    headline: str
    summary: str
    source: str
    url: str
    datetime: datetime
    sentiment: float | None


class FinnhubClient:
    """Finnhub API client with rate limiting."""

    def __init__(self):
        """Initialize the Finnhub client."""
        api_key = config.finnhub.api_key
        if not api_key:
            raise ValueError("FINNHUB_API_KEY is not set in environment variables")

        self._client = finnhub.Client(api_key=api_key)

    @rate_limit_aware(calls_per_minute=60)
    def get_quote(self, symbol: str) -> StockQuote:
        """
        Get real-time quote for a stock.

        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL')

        Returns:
            StockQuote with current price data
        """
        data = self._client.quote(symbol)
        return StockQuote(
            symbol=symbol,
            current_price=data.get("c", 0),
            change=data.get("d", 0),
            change_percent=data.get("dp", 0),
            high=data.get("h", 0),
            low=data.get("l", 0),
            open=data.get("o", 0),
            previous_close=data.get("pc", 0),
            timestamp=datetime.fromtimestamp(data.get("t", 0)),
        )

    @rate_limit_aware(calls_per_minute=60)
    def get_company_profile(self, symbol: str) -> CompanyProfile:
        """
        Get company profile.

        Args:
            symbol: Stock ticker symbol

        Returns:
            CompanyProfile with company info
        """
        data = self._client.company_profile2(symbol=symbol)
        return CompanyProfile(
            symbol=symbol,
            name=data.get("name", ""),
            market_cap=data.get("marketCapitalization", 0) * 1_000_000,  # Convert to actual value
            sector=data.get("finnhubIndustry", ""),
            industry=data.get("finnhubIndustry", ""),
            exchange=data.get("exchange", ""),
        )

    @rate_limit_aware(calls_per_minute=60)
    def get_basic_financials(self, symbol: str) -> BasicFinancials:
        """
        Get basic financial metrics.

        Args:
            symbol: Stock ticker symbol

        Returns:
            BasicFinancials with PE, PB, etc.
        """
        data = self._client.company_basic_financials(symbol, "all")
        metrics = data.get("metric", {})

        return BasicFinancials(
            symbol=symbol,
            pe_ratio=metrics.get("peBasicExclExtraTTM"),
            pb_ratio=metrics.get("pbQuarterly"),
            dividend_yield=metrics.get("dividendYieldIndicatedAnnual"),
            beta=metrics.get("beta"),
            eps=metrics.get("epsBasicExclExtraItemsTTM"),
            week_52_high=metrics.get("52WeekHigh"),
            week_52_low=metrics.get("52WeekLow"),
        )

    @rate_limit_aware(calls_per_minute=60)
    def get_earnings_calendar(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        symbol: str | None = None,
    ) -> list[EarningsEvent]:
        """
        Get earnings calendar.

        Args:
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            symbol: Optional symbol to filter

        Returns:
            List of EarningsEvent
        """
        if from_date is None:
            from_date = datetime.now().strftime("%Y-%m-%d")
        if to_date is None:
            to_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        data = self._client.earnings_calendar(
            _from=from_date,
            to=to_date,
            symbol=symbol,
        )

        events = []
        for item in data.get("earningsCalendar", []):
            events.append(EarningsEvent(
                symbol=item.get("symbol", ""),
                date=item.get("date", ""),
                hour=item.get("hour", "unknown"),
                estimate_eps=item.get("epsEstimate"),
                actual_eps=item.get("epsActual"),
            ))
        return events

    @rate_limit_aware(calls_per_minute=60)
    def get_company_news(
        self,
        symbol: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[NewsItem]:
        """
        Get company news.

        Args:
            symbol: Stock ticker symbol
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)

        Returns:
            List of NewsItem
        """
        if from_date is None:
            from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        if to_date is None:
            to_date = datetime.now().strftime("%Y-%m-%d")

        data = self._client.company_news(symbol, _from=from_date, to=to_date)

        news = []
        for item in data:
            news.append(NewsItem(
                id=item.get("id", 0),
                symbol=symbol,
                headline=item.get("headline", ""),
                summary=item.get("summary", ""),
                source=item.get("source", ""),
                url=item.get("url", ""),
                datetime=datetime.fromtimestamp(item.get("datetime", 0)),
                sentiment=None,  # Sentiment requires separate API call
            ))
        return news

    @rate_limit_aware(calls_per_minute=60)
    def get_market_status(self) -> dict[str, Any]:
        """
        Get current market status.

        Returns:
            Dict with market status info
        """
        return self._client.market_status(exchange="US")

    @rate_limit_aware(calls_per_minute=60)
    def get_stock_candles(
        self,
        symbol: str,
        resolution: str = "D",
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
    ) -> dict[str, list]:
        """
        Get historical OHLCV data.

        Args:
            symbol: Stock ticker symbol
            resolution: Candle resolution (1, 5, 15, 30, 60, D, W, M)
            from_timestamp: Start Unix timestamp
            to_timestamp: End Unix timestamp

        Returns:
            Dict with OHLCV arrays
        """
        if to_timestamp is None:
            to_timestamp = int(datetime.now().timestamp())
        if from_timestamp is None:
            from_timestamp = int((datetime.now() - timedelta(days=30)).timestamp())

        data = self._client.stock_candles(
            symbol,
            resolution,
            from_timestamp,
            to_timestamp,
        )

        if data.get("s") == "no_data":
            return {"o": [], "h": [], "l": [], "c": [], "v": [], "t": []}

        return {
            "open": data.get("o", []),
            "high": data.get("h", []),
            "low": data.get("l", []),
            "close": data.get("c", []),
            "volume": data.get("v", []),
            "timestamp": data.get("t", []),
        }

    def get_vix(self) -> float:
        """
        Get current VIX (Volatility Index).

        Returns:
            Current VIX value
        """
        # VIX is traded as ^VIX or VIX index
        quote = self.get_quote("VIX")
        return quote.current_price

    def get_sp500(self) -> StockQuote:
        """
        Get S&P 500 index quote.

        Returns:
            StockQuote for SPY (S&P 500 ETF)
        """
        return self.get_quote("SPY")

    @rate_limit_aware(calls_per_minute=60)
    def get_earnings_surprise(self, symbol: str, limit: int = 4) -> list[EarningsSurprise]:
        """
        Get historical earnings surprise data.

        Args:
            symbol: Stock ticker symbol
            limit: Number of quarters to fetch (default: 4, max on free tier)

        Returns:
            List of EarningsSurprise with actual vs estimate EPS
        """
        data = self._client.company_earnings(symbol, limit=limit)

        surprises = []
        for item in data:
            actual = item.get("actual")
            estimate = item.get("estimate")

            # Calculate surprise percentage
            surprise_pct = 0.0
            if actual is not None and estimate is not None and estimate != 0:
                surprise_pct = ((actual - estimate) / abs(estimate)) * 100

            surprises.append(EarningsSurprise(
                symbol=symbol,
                period=item.get("period", ""),
                actual=actual or 0.0,
                estimate=estimate or 0.0,
                surprise_pct=surprise_pct,
            ))

        return surprises

    @rate_limit_aware(calls_per_minute=60)
    def get_price_target(self, symbol: str) -> PriceTarget | None:
        """
        Get analyst price target consensus.

        Args:
            symbol: Stock ticker symbol

        Returns:
            PriceTarget with analyst consensus, or None if not available
        """
        data = self._client.price_target(symbol)

        if not data or not data.get("targetMean"):
            return None

        return PriceTarget(
            symbol=symbol,
            target_high=data.get("targetHigh", 0.0),
            target_low=data.get("targetLow", 0.0),
            target_mean=data.get("targetMean", 0.0),
            target_median=data.get("targetMedian", 0.0),
            last_updated=data.get("lastUpdated", ""),
        )
