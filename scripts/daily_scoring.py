#!/usr/bin/env python3
"""
Daily Scoring Script

Morning batch job that:
1. Fetches market data from Finnhub
2. Determines market regime (VIX, S&P 500)
3. Filters candidates (liquidity, earnings)
4. Scores stocks with 4 agents
5. Selects top picks
6. Saves to Supabase
"""
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config
from src.data.finnhub_client import FinnhubClient
from src.data.supabase_client import (
    SupabaseClient,
    DailyPick,
    StockScore,
    MarketRegimeRecord,
)
from src.scoring.market_regime import decide_market_regime, calculate_sma, calculate_volatility
from src.scoring.agents import StockData
from src.scoring.agents_v2 import V2StockData
from src.scoring.composite_v2 import run_dual_scoring

# Setup logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG if config.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / f"scoring_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# S&P 500 top holdings (simplified for MVP)
SP500_TOP_SYMBOLS = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK.B", "UNH", "JNJ",
    "V", "XOM", "JPM", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "LLY",
    "PEP", "KO", "COST", "AVGO", "MCD", "WMT", "CSCO", "TMO", "ABT", "CRM",
    "DHR", "ACN", "NKE", "LIN", "ADBE", "ORCL", "TXN", "NEE", "PM", "VZ",
    "CMCSA", "RTX", "HON", "INTC", "UPS", "LOW", "MS", "QCOM", "SPGI", "BA",
]


def fetch_market_regime_data(finnhub: FinnhubClient) -> dict:
    """Fetch data needed for market regime determination."""
    logger.info("Fetching market regime data...")

    # Get VIX
    try:
        vix = finnhub.get_vix()
        logger.info(f"VIX: {vix}")
    except Exception as e:
        logger.warning(f"Failed to get VIX: {e}, using default 20")
        vix = 20.0

    # Get S&P 500 data
    sp500 = finnhub.get_sp500()
    sp500_price = sp500.current_price
    logger.info(f"S&P 500 (SPY): {sp500_price}")

    # Get historical prices for SMA and volatility
    candles = finnhub.get_stock_candles(
        "SPY",
        resolution="D",
        from_timestamp=int((datetime.now() - timedelta(days=60)).timestamp()),
    )
    prices = candles.get("close", [])

    sp500_sma20 = calculate_sma(prices, 20) if prices else sp500_price
    volatility_5d = calculate_volatility(prices, 5) if prices else 0.15
    volatility_30d = calculate_volatility(prices, 30) if prices else 0.15

    return {
        "vix": vix,
        "sp500_price": sp500_price,
        "sp500_sma20": sp500_sma20,
        "volatility_5d": volatility_5d,
        "volatility_30d": volatility_30d,
    }


def fetch_stock_data(
    finnhub: FinnhubClient,
    symbol: str,
    vix_level: float,
) -> tuple[StockData, V2StockData] | None:
    """Fetch all data needed to score a stock for both V1 and V2 strategies."""
    try:
        # Get quote
        quote = finnhub.get_quote(symbol)

        # Get historical prices
        candles = finnhub.get_stock_candles(
            symbol,
            resolution="D",
            from_timestamp=int((datetime.now() - timedelta(days=250)).timestamp()),
        )
        prices = candles.get("close", [])
        volumes = candles.get("volume", [])

        if not prices:
            logger.warning(f"No price data for {symbol}")
            return None

        # Get financials
        financials = finnhub.get_basic_financials(symbol)

        # Get news
        news = finnhub.get_company_news(symbol)

        # Calculate gap percentage (for V2)
        gap_pct = 0.0
        if quote.previous_close and quote.previous_close > 0:
            gap_pct = ((quote.open - quote.previous_close) / quote.previous_close) * 100

        # V1 Stock Data
        v1_data = StockData(
            symbol=symbol,
            prices=prices,
            volumes=volumes,
            open_price=quote.open,
            pe_ratio=financials.pe_ratio,
            pb_ratio=financials.pb_ratio,
            dividend_yield=financials.dividend_yield,
            week_52_high=financials.week_52_high,
            week_52_low=financials.week_52_low,
            news_count_7d=len(news),
            news_sentiment=None,  # Would need sentiment API
            sector_avg_pe=25.0,  # Simplified
        )

        # V2 Stock Data (with additional fields)
        v2_data = V2StockData(
            symbol=symbol,
            prices=prices,
            volumes=volumes,
            open_price=quote.open,
            pe_ratio=financials.pe_ratio,
            pb_ratio=financials.pb_ratio,
            dividend_yield=financials.dividend_yield,
            week_52_high=financials.week_52_high,
            week_52_low=financials.week_52_low,
            news_count_7d=len(news),
            news_sentiment=None,
            sector_avg_pe=25.0,
            # V2 specific fields
            vix_level=vix_level,
            gap_pct=gap_pct,
            # These would need additional API calls in production
            earnings_surprise_pct=None,
            analyst_revision_score=None,
        )

        return v1_data, v2_data

    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return None


def filter_earnings(
    finnhub: FinnhubClient,
    symbols: list[str],
    within_days: int = 3,
) -> list[str]:
    """Filter out stocks with upcoming earnings."""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=within_days)).strftime("%Y-%m-%d")

        earnings = finnhub.get_earnings_calendar(from_date=today, to_date=end_date)
        earnings_symbols = {e.symbol for e in earnings}

        filtered = [s for s in symbols if s not in earnings_symbols]
        removed = len(symbols) - len(filtered)

        if removed > 0:
            logger.info(f"Filtered out {removed} stocks with upcoming earnings")

        return filtered

    except Exception as e:
        logger.warning(f"Earnings filter failed: {e}, returning all symbols")
        return symbols


def main():
    """Main scoring pipeline."""
    logger.info("=" * 50)
    logger.info("Starting daily scoring batch")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    logger.info("=" * 50)

    # Initialize clients
    try:
        finnhub = FinnhubClient()
        supabase = SupabaseClient()
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        sys.exit(1)

    # 1. Determine market regime
    logger.info("Step 1: Determining market regime...")
    regime_data = fetch_market_regime_data(finnhub)

    market_regime = decide_market_regime(
        vix=regime_data["vix"],
        sp500_price_today=regime_data["sp500_price"],
        sp500_sma20=regime_data["sp500_sma20"],
        volatility_5d_avg=regime_data["volatility_5d"],
        volatility_30d_avg=regime_data["volatility_30d"],
    )

    logger.info(f"Market Regime: {market_regime.regime.value}")
    logger.info(f"Max Picks: {market_regime.max_picks}")
    logger.info(f"Notes: {market_regime.notes}")

    # Save market regime
    today = datetime.now().strftime("%Y-%m-%d")
    supabase.save_market_regime(MarketRegimeRecord(
        check_date=today,
        vix_level=market_regime.vix_level,
        market_regime=market_regime.regime.value,
        sp500_sma20_deviation_pct=market_regime.sp500_deviation_pct,
        volatility_cluster_flag=market_regime.volatility_cluster,
        notes=market_regime.notes,
    ))

    # Check if we should skip (crisis mode)
    if market_regime.max_picks == 0:
        logger.warning("Market in CRISIS mode - no recommendations today")
        # Save empty picks for both strategies
        supabase.save_daily_picks(DailyPick(
            batch_date=today,
            symbols=[],
            pick_count=0,
            market_regime=market_regime.regime.value,
            strategy_mode="conservative",
            status="published",
        ))
        supabase.save_daily_picks(DailyPick(
            batch_date=today,
            symbols=[],
            pick_count=0,
            market_regime=market_regime.regime.value,
            strategy_mode="aggressive",
            status="published",
        ))
        logger.info("Saved empty daily picks for both strategies")
        return

    # 2. Filter candidates
    logger.info("Step 2: Filtering candidates...")
    candidates = SP500_TOP_SYMBOLS.copy()
    candidates = filter_earnings(finnhub, candidates)
    logger.info(f"Candidates after filtering: {len(candidates)}")

    # 3. Fetch stock data
    logger.info("Step 3: Fetching stock data...")
    v1_stocks_data = []
    v2_stocks_data = []
    for symbol in candidates:
        result = fetch_stock_data(finnhub, symbol, regime_data["vix"])
        if result:
            v1_data, v2_data = result
            v1_stocks_data.append(v1_data)
            v2_stocks_data.append(v2_data)
        # Small delay to avoid rate limiting
        time.sleep(0.5)

    logger.info(f"Successfully fetched data for {len(v1_stocks_data)} stocks")

    # 4. Run dual scoring (V1 Conservative + V2 Aggressive)
    logger.info("Step 4: Running dual scoring pipeline...")
    dual_result = run_dual_scoring(v1_stocks_data, v2_stocks_data, market_regime)

    logger.info(f"V1 (Conservative) scored: {len(dual_result.v1_scores)} stocks")
    logger.info(f"V1 picks: {dual_result.v1_picks}")
    logger.info(f"V2 (Aggressive) scored: {len(dual_result.v2_scores)} stocks")
    logger.info(f"V2 picks: {dual_result.v2_picks}")

    # 5. Save results for both strategies
    logger.info("Step 5: Saving results...")

    # Helper to get price for a symbol
    def get_price(symbol: str) -> float:
        return next(
            (d.open_price for d in v1_stocks_data if d.symbol == symbol),
            0.0,
        )

    # Save V1 (Conservative) stock scores
    v1_stock_scores = [
        StockScore(
            batch_date=today,
            symbol=s.symbol,
            strategy_mode="conservative",
            trend_score=s.trend_score,
            momentum_score=s.momentum_score,
            value_score=s.value_score,
            sentiment_score=s.sentiment_score,
            composite_score=s.composite_score,
            percentile_rank=s.percentile_rank,
            reasoning=s.reasoning,
            price_at_time=get_price(s.symbol),
            market_regime_at_time=market_regime.regime.value,
            momentum_12_1_score=s.momentum_12_1_score,
            breakout_score=s.breakout_score,
            catalyst_score=s.catalyst_score,
            risk_adjusted_score=s.risk_adjusted_score,
            cutoff_timestamp=dual_result.cutoff_timestamp.isoformat(),
        )
        for s in dual_result.v1_scores
    ]
    supabase.save_stock_scores(v1_stock_scores)

    # Save V2 (Aggressive) stock scores
    v2_stock_scores = [
        StockScore(
            batch_date=today,
            symbol=s.symbol,
            strategy_mode="aggressive",
            trend_score=s.trend_score,
            momentum_score=s.momentum_score,
            value_score=s.value_score,
            sentiment_score=s.sentiment_score,
            composite_score=s.composite_score,
            percentile_rank=s.percentile_rank,
            reasoning=s.reasoning,
            price_at_time=get_price(s.symbol),
            market_regime_at_time=market_regime.regime.value,
            momentum_12_1_score=s.momentum_12_1_score,
            breakout_score=s.breakout_score,
            catalyst_score=s.catalyst_score,
            risk_adjusted_score=s.risk_adjusted_score,
            cutoff_timestamp=dual_result.cutoff_timestamp.isoformat(),
        )
        for s in dual_result.v2_scores
    ]
    supabase.save_stock_scores(v2_stock_scores)

    # Save V1 daily picks
    supabase.save_daily_picks(DailyPick(
        batch_date=today,
        symbols=dual_result.v1_picks,
        pick_count=len(dual_result.v1_picks),
        market_regime=market_regime.regime.value,
        strategy_mode="conservative",
        status="published",
    ))

    # Save V2 daily picks
    supabase.save_daily_picks(DailyPick(
        batch_date=today,
        symbols=dual_result.v2_picks,
        pick_count=len(dual_result.v2_picks),
        market_regime=market_regime.regime.value,
        strategy_mode="aggressive",
        status="published",
    ))

    logger.info("=" * 50)
    logger.info("Daily scoring batch completed successfully")
    logger.info(f"V1 Conservative Picks: {dual_result.v1_picks}")
    logger.info(f"V2 Aggressive Picks: {dual_result.v2_picks}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
