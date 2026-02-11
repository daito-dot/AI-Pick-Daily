"""
Information Collector - Gathers and structures time-sensitive information.

This is the primary component of Layer 1, responsible for:
1. Collecting data from multiple sources
2. Categorizing by time sensitivity
3. Enriching with calculated metrics
4. Providing structured output for Layer 2 (Judgment)
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from src.data.finnhub_client import FinnhubClient, NewsItem as FinnhubNewsItem
from src.data.yfinance_client import YFinanceClient
from .models import (
    TimedInformation,
    NewsItem,
    TechnicalContext,
    FundamentalContext,
    MarketContext,
    TimeCategory,
)


logger = logging.getLogger(__name__)


class InformationCollector:
    """
    Collects and structures information for investment judgment.

    Implements time-sensitive information processing based on research:
    - Breaking news: 3-5 hour impact window
    - Short-term news: 1-5 day effect
    - Technical patterns: 5-20 day lead time
    - Fundamental changes: up to 13 weeks
    """

    # Time thresholds (in hours)
    IMMEDIATE_THRESHOLD = 24  # Less than 24 hours
    SHORT_TERM_THRESHOLD = 120  # 5 days
    MEDIUM_TERM_THRESHOLD = 672  # 28 days (4 weeks)

    # Keywords for categorizing news impact
    EARNINGS_KEYWORDS = [
        "earnings", "eps", "revenue", "profit", "loss", "quarter", "fiscal",
        "beat", "miss", "guidance", "forecast", "outlook",
    ]
    ANALYST_KEYWORDS = [
        "upgrade", "downgrade", "price target", "rating", "analyst",
        "buy", "sell", "hold", "overweight", "underweight",
    ]
    INSIDER_KEYWORDS = [
        "insider", "executive", "ceo", "cfo", "director", "purchase", "sale",
        "filing", "sec", "form 4",
    ]
    MACRO_KEYWORDS = [
        "fed", "interest rate", "inflation", "gdp", "employment", "tariff",
        "regulation", "policy", "government",
    ]

    def __init__(
        self,
        finnhub: FinnhubClient,
        yfinance: YFinanceClient | None = None,
    ):
        """
        Initialize the collector.

        Args:
            finnhub: Finnhub client for data
            yfinance: Optional yfinance client as fallback
        """
        self.finnhub = finnhub
        self.yfinance = yfinance

    def collect(
        self,
        symbol: str,
        market_context: MarketContext,
        news_days: int = 30,
        price_days: int = 250,
    ) -> TimedInformation:
        """
        Collect all information for a symbol.

        Args:
            symbol: Stock ticker symbol
            market_context: Current market context
            news_days: Days of news to fetch
            price_days: Days of price history to fetch

        Returns:
            TimedInformation with structured data
        """
        logger.info(f"Collecting information for {symbol}")

        # Collect news
        news_items = self._collect_news(symbol, days=news_days)

        # Categorize news by time
        immediate, short_term, medium_term, older = self._categorize_news(news_items)

        # Collect technical context
        technical = self._collect_technical_context(symbol, days=price_days)

        # Collect fundamental context
        fundamental = self._collect_fundamental_context(symbol)

        # Calculate data quality scores
        data_freshness = self._calculate_freshness_score(news_items)
        data_completeness = self._calculate_completeness_score(technical, fundamental)

        return TimedInformation(
            symbol=symbol,
            collected_at=datetime.now(),
            immediate_news=immediate,
            short_term_news=short_term,
            medium_term_news=medium_term,
            older_news=older,
            technical=technical,
            fundamental=fundamental,
            market=market_context,
            data_freshness_score=data_freshness,
            data_completeness_score=data_completeness,
        )

    def _collect_news(self, symbol: str, days: int = 30) -> list[NewsItem]:
        """Collect and process news from Finnhub."""
        try:
            from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            to_date = datetime.now().strftime("%Y-%m-%d")

            finnhub_news = self.finnhub.get_company_news(
                symbol,
                from_date=from_date,
                to_date=to_date,
            )

            processed_news = []
            for item in finnhub_news:
                news = self._process_finnhub_news(item)
                if news:
                    processed_news.append(news)

            logger.debug(f"{symbol}: Collected {len(processed_news)} news items")
            return processed_news

        except Exception as e:
            logger.warning(f"Failed to collect news for {symbol}: {e}")
            return []

    def _process_finnhub_news(self, item: FinnhubNewsItem) -> NewsItem | None:
        """Process a Finnhub news item into our structured format."""
        try:
            # Calculate time category
            now = datetime.now()
            hours_ago = (now - item.datetime).total_seconds() / 3600 if item.datetime else 0

            if hours_ago < self.IMMEDIATE_THRESHOLD:
                category = TimeCategory.IMMEDIATE
            elif hours_ago < self.SHORT_TERM_THRESHOLD:
                category = TimeCategory.SHORT_TERM
            elif hours_ago < self.MEDIUM_TERM_THRESHOLD:
                category = TimeCategory.MEDIUM_TERM
            else:
                category = TimeCategory.OLDER

            # Detect news type from content
            headline_lower = item.headline.lower() if item.headline else ""
            summary_lower = item.summary.lower() if item.summary else ""
            combined = headline_lower + " " + summary_lower

            is_earnings = any(kw in combined for kw in self.EARNINGS_KEYWORDS)
            is_guidance = "guidance" in combined or "outlook" in combined
            is_analyst = any(kw in combined for kw in self.ANALYST_KEYWORDS)
            is_insider = any(kw in combined for kw in self.INSIDER_KEYWORDS)
            is_macro = any(kw in combined for kw in self.MACRO_KEYWORDS)

            # Convert Finnhub sentiment to our format
            sentiment_score = item.sentiment
            sentiment_level = None
            if sentiment_score is not None:
                if sentiment_score >= 0.6:
                    sentiment_level = "very_positive"
                elif sentiment_score >= 0.2:
                    sentiment_level = "positive"
                elif sentiment_score >= -0.2:
                    sentiment_level = "neutral"
                elif sentiment_score >= -0.6:
                    sentiment_level = "negative"
                else:
                    sentiment_level = "very_negative"

            return NewsItem(
                headline=item.headline,
                summary=item.summary[:500] if item.summary else "",  # Truncate long summaries
                source="finnhub",
                published_at=item.datetime,
                category=category,
                sentiment=sentiment_level,
                sentiment_score=sentiment_score,
                is_earnings_related=is_earnings,
                is_guidance_related=is_guidance,
                is_analyst_action=is_analyst,
                is_insider_activity=is_insider,
                is_macro_event=is_macro,
                url=item.url,
            )

        except Exception as e:
            logger.warning(f"Failed to process news item: {e}")
            return None

    def _categorize_news(
        self,
        news_items: list[NewsItem],
    ) -> tuple[list[NewsItem], list[NewsItem], list[NewsItem], list[NewsItem]]:
        """Categorize news items by time category."""
        immediate = []
        short_term = []
        medium_term = []
        older = []

        for item in news_items:
            if item.category == TimeCategory.IMMEDIATE:
                immediate.append(item)
            elif item.category == TimeCategory.SHORT_TERM:
                short_term.append(item)
            elif item.category == TimeCategory.MEDIUM_TERM:
                medium_term.append(item)
            else:
                older.append(item)

        # Sort each category by recency (most recent first)
        immediate.sort(key=lambda x: x.hours_ago)
        short_term.sort(key=lambda x: x.hours_ago)
        medium_term.sort(key=lambda x: x.hours_ago)
        older.sort(key=lambda x: x.hours_ago)

        return immediate, short_term, medium_term, older

    def _collect_technical_context(
        self,
        symbol: str,
        days: int = 250,
    ) -> TechnicalContext | None:
        """Collect technical analysis context."""
        try:
            # Get candle data
            from_timestamp = int((datetime.now() - timedelta(days=days)).timestamp())
            candles = self.finnhub.get_stock_candles(
                symbol,
                resolution="D",
                from_timestamp=from_timestamp,
            )

            prices = candles.get("close", [])
            volumes = candles.get("volume", [])

            if not prices or len(prices) < 20:
                logger.warning(f"{symbol}: Insufficient price data")
                return None

            # Get quote for current price
            quote = self.finnhub.get_quote(symbol)
            current_price = prices[-1]
            previous_close = prices[-2] if len(prices) >= 2 else current_price

            # Calculate metrics
            change_pct = ((current_price - previous_close) / previous_close) * 100

            # Moving averages
            sma_20 = sum(prices[-20:]) / 20 if len(prices) >= 20 else None
            sma_50 = sum(prices[-50:]) / 50 if len(prices) >= 50 else None
            sma_200 = sum(prices[-200:]) / 200 if len(prices) >= 200 else None

            # RSI
            rsi = self._calculate_rsi(prices)

            # Volume analysis
            current_volume = volumes[-1] if volumes else None
            avg_volume = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else None
            volume_ratio = current_volume / avg_volume if current_volume and avg_volume else None

            # 52-week high/low
            year_prices = prices[-252:] if len(prices) >= 252 else prices
            week_52_high = max(year_prices)
            week_52_low = min(year_prices)
            distance_from_high = ((current_price - week_52_high) / week_52_high) * 100
            distance_from_low = ((current_price - week_52_low) / week_52_low) * 100

            # Detect signals
            breakout = (
                sma_20 and sma_50 and
                current_price > sma_20 > sma_50 and
                volume_ratio and volume_ratio > 1.5
            )
            breakdown = (
                sma_20 and sma_50 and
                current_price < sma_20 < sma_50 and
                volume_ratio and volume_ratio > 1.5
            )

            return TechnicalContext(
                current_price=current_price,
                previous_close=previous_close,
                change_pct=change_pct,
                sma_20=sma_20,
                sma_50=sma_50,
                sma_200=sma_200,
                above_sma_20=current_price > sma_20 if sma_20 else None,
                above_sma_50=current_price > sma_50 if sma_50 else None,
                above_sma_200=current_price > sma_200 if sma_200 else None,
                rsi_14=rsi,
                volume=current_volume,
                avg_volume_20d=avg_volume,
                volume_ratio=volume_ratio,
                week_52_high=week_52_high,
                week_52_low=week_52_low,
                distance_from_52w_high_pct=distance_from_high,
                distance_from_52w_low_pct=distance_from_low,
                breakout_signal=breakout,
                breakdown_signal=breakdown,
            )

        except Exception as e:
            logger.warning(f"Failed to collect technical context for {symbol}: {e}")
            return None

    def _collect_fundamental_context(self, symbol: str) -> FundamentalContext | None:
        """Collect fundamental analysis context."""
        try:
            financials = self.finnhub.get_basic_financials(symbol)

            return FundamentalContext(
                pe_ratio=financials.pe_ratio,
                pb_ratio=financials.pb_ratio,
                dividend_yield=financials.dividend_yield,
            )

        except Exception as e:
            logger.warning(f"Failed to collect fundamental context for {symbol}: {e}")
            return None

    def _calculate_rsi(self, prices: list[float], period: int = 14) -> float | None:
        """Calculate RSI for a price series."""
        if len(prices) < period + 1:
            return None

        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]

        gains = [c if c > 0 else 0 for c in changes[-period:]]
        losses = [-c if c < 0 else 0 for c in changes[-period:]]

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _calculate_freshness_score(self, news_items: list[NewsItem]) -> float:
        """
        Calculate how fresh the news data is.

        Returns a score from 0-1 where 1 means very fresh data.
        """
        if not news_items:
            return 0.5  # No news is neutral

        # Check for recent news
        recent_count = sum(1 for n in news_items if n.hours_ago < 24)
        total_count = len(news_items)

        # More recent news = higher freshness
        if recent_count >= 3:
            return 1.0
        elif recent_count >= 1:
            return 0.8
        elif total_count >= 5:
            return 0.6
        else:
            return 0.4

    def _calculate_completeness_score(
        self,
        technical: TechnicalContext | None,
        fundamental: FundamentalContext | None,
    ) -> float:
        """
        Calculate how complete the data is.

        Returns a score from 0-1 where 1 means all expected data is available.
        """
        score = 0.0
        max_score = 0.0

        # Technical completeness (50% weight)
        if technical:
            max_score += 0.5
            tech_points = 0
            if technical.sma_20 is not None:
                tech_points += 1
            if technical.sma_50 is not None:
                tech_points += 1
            if technical.rsi_14 is not None:
                tech_points += 1
            if technical.volume_ratio is not None:
                tech_points += 1
            score += 0.5 * (tech_points / 4)
        else:
            max_score += 0.5

        # Fundamental completeness (50% weight)
        if fundamental:
            max_score += 0.5
            fund_points = 0
            if fundamental.pe_ratio is not None:
                fund_points += 1
            if fundamental.pb_ratio is not None:
                fund_points += 1
            if fundamental.dividend_yield is not None:
                fund_points += 1
            score += 0.5 * (fund_points / 3)
        else:
            max_score += 0.5

        return score / max_score if max_score > 0 else 0.5

    def collect_batch(
        self,
        symbols: list[str],
        market_context: MarketContext,
    ) -> dict[str, TimedInformation]:
        """
        Collect information for multiple symbols.

        Args:
            symbols: List of stock ticker symbols
            market_context: Current market context

        Returns:
            Dict mapping symbol to TimedInformation
        """
        results = {}

        for symbol in symbols:
            try:
                info = self.collect(symbol, market_context)
                results[symbol] = info
            except Exception as e:
                logger.error(f"Failed to collect information for {symbol}: {e}")

        return results
