#!/usr/bin/env python3
"""
Daily Scoring Script

Morning batch job that:
1. Fetches market data from Finnhub (with yfinance fallback)
2. Determines market regime (VIX, S&P 500)
3. Filters candidates (liquidity, earnings)
4. Scores stocks with 4 agents
5. Selects top picks
6. Saves to Supabase

Data Source Strategy:
- Primary: Finnhub API (higher quality, but free tier has limitations)
- Fallback: yfinance (free, but can be blocked)
- If both fail: Batch fails with clear error (no fake data)
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
from src.data.yfinance_client import get_yfinance_client, YFinanceClient
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
from src.portfolio import PortfolioManager
from src.judgment import (
    JudgmentService,
    run_judgment_for_candidates,
    filter_picks_by_judgment,
)


class DataFetchError(Exception):
    """Raised when data cannot be fetched from any source."""
    pass

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


def fetch_market_regime_data(finnhub: FinnhubClient, yf_client: YFinanceClient) -> dict:
    """
    Fetch data needed for market regime determination.

    Uses Finnhub as primary source, yfinance as fallback.
    Raises DataFetchError if critical data cannot be obtained from any source.
    """
    logger.info("Fetching market regime data...")

    vix = None
    sp500_price = None
    prices = []

    # === Get VIX ===
    # Try Finnhub first
    try:
        vix = finnhub.get_vix()
        if vix == 0 or vix is None:
            logger.warning("Finnhub VIX returned 0/None, trying yfinance...")
            vix = None
        else:
            logger.info(f"VIX from Finnhub: {vix}")
    except Exception as e:
        logger.warning(f"Finnhub VIX failed: {e}")

    # Fallback to yfinance
    if vix is None:
        try:
            vix = yf_client.get_vix()
            if vix and vix > 0:
                logger.info(f"VIX from yfinance: {vix}")
            else:
                vix = None
        except Exception as e:
            logger.warning(f"yfinance VIX failed: {e}")

    if vix is None:
        raise DataFetchError("Failed to get VIX from both Finnhub and yfinance")

    # === Get S&P 500 price ===
    # Try Finnhub first
    try:
        sp500 = finnhub.get_sp500()
        sp500_price = sp500.current_price
        if sp500_price and sp500_price > 0:
            logger.info(f"S&P 500 (SPY) from Finnhub: {sp500_price}")
        else:
            sp500_price = None
    except Exception as e:
        logger.warning(f"Finnhub S&P 500 failed: {e}")

    # Fallback to yfinance
    if sp500_price is None:
        try:
            sp500_price = yf_client.get_sp500_price()
            if sp500_price and sp500_price > 0:
                logger.info(f"S&P 500 (SPY) from yfinance: {sp500_price}")
            else:
                sp500_price = None
        except Exception as e:
            logger.warning(f"yfinance S&P 500 failed: {e}")

    if sp500_price is None:
        raise DataFetchError("Failed to get S&P 500 price from both Finnhub and yfinance")

    # === Get historical prices for SMA and volatility ===
    # Try Finnhub first
    try:
        candles = finnhub.get_stock_candles(
            "SPY",
            resolution="D",
            from_timestamp=int((datetime.now() - timedelta(days=60)).timestamp()),
        )
        prices = candles.get("close", [])
        if prices:
            logger.info(f"SPY candles from Finnhub: {len(prices)} days")
    except Exception as e:
        logger.warning(f"Finnhub SPY candles failed: {e}")

    # Fallback to yfinance
    if not prices:
        try:
            yf_candles = yf_client.get_candles("SPY", period="3mo", interval="1d")
            if yf_candles and yf_candles.closes:
                prices = yf_candles.closes
                logger.info(f"SPY candles from yfinance: {len(prices)} days")
        except Exception as e:
            logger.warning(f"yfinance SPY candles failed: {e}")

    if not prices:
        raise DataFetchError("Failed to get SPY historical data from both Finnhub and yfinance")

    # Calculate metrics
    sp500_sma20 = calculate_sma(prices, 20)
    volatility_5d = calculate_volatility(prices, 5)
    volatility_30d = calculate_volatility(prices, 30)

    logger.info(f"Market data: VIX={vix:.2f}, SP500={sp500_price:.2f}, SMA20={sp500_sma20:.2f}")

    return {
        "vix": vix,
        "sp500_price": sp500_price,
        "sp500_sma20": sp500_sma20,
        "volatility_5d": volatility_5d,
        "volatility_30d": volatility_30d,
    }


def fetch_stock_data(
    finnhub: FinnhubClient,
    yf_client: YFinanceClient,
    symbol: str,
    vix_level: float,
) -> tuple[StockData, V2StockData] | None:
    """
    Fetch all data needed to score a stock for both V1 and V2 strategies.

    Uses Finnhub as primary source, yfinance as fallback.
    Returns None if data cannot be obtained from any source.
    """
    prices = []
    volumes = []
    open_price = 0.0
    previous_close = 0.0
    pe_ratio = None
    pb_ratio = None
    dividend_yield = None
    week_52_high = None
    week_52_low = None
    news_count = 0

    # === Get historical prices ===
    # Try Finnhub first
    try:
        candles = finnhub.get_stock_candles(
            symbol,
            resolution="D",
            from_timestamp=int((datetime.now() - timedelta(days=250)).timestamp()),
        )
        prices = candles.get("close", [])
        volumes = candles.get("volume", [])
        if prices:
            logger.debug(f"{symbol}: candles from Finnhub ({len(prices)} days)")
    except Exception as e:
        logger.debug(f"{symbol}: Finnhub candles failed: {e}")

    # Fallback to yfinance
    if not prices:
        try:
            yf_candles = yf_client.get_candles(symbol, period="1y", interval="1d")
            if yf_candles and yf_candles.closes:
                prices = yf_candles.closes
                volumes = yf_candles.volumes
                logger.debug(f"{symbol}: candles from yfinance ({len(prices)} days)")
        except Exception as e:
            logger.debug(f"{symbol}: yfinance candles failed: {e}")

    if not prices:
        logger.warning(f"{symbol}: No price data from either source, skipping")
        return None

    # === Get quote ===
    # Try Finnhub first
    try:
        quote = finnhub.get_quote(symbol)
        open_price = quote.open
        previous_close = quote.previous_close
    except Exception as e:
        logger.debug(f"{symbol}: Finnhub quote failed: {e}")

    # Fallback to yfinance
    if open_price == 0:
        try:
            yf_quote = yf_client.get_quote(symbol)
            if yf_quote:
                open_price = yf_quote.open_price
                previous_close = yf_quote.previous_close
        except Exception as e:
            logger.debug(f"{symbol}: yfinance quote failed: {e}")

    # Use last close price as fallback for open
    if open_price == 0 and prices:
        open_price = prices[-1]

    # === Get financials ===
    # Try Finnhub first
    try:
        financials = finnhub.get_basic_financials(symbol)
        pe_ratio = financials.pe_ratio
        pb_ratio = financials.pb_ratio
        dividend_yield = financials.dividend_yield
        week_52_high = financials.week_52_high
        week_52_low = financials.week_52_low
    except Exception as e:
        logger.debug(f"{symbol}: Finnhub financials failed: {e}")

    # Fallback to yfinance
    if pe_ratio is None:
        try:
            yf_financials = yf_client.get_basic_financials(symbol)
            if yf_financials:
                pe_ratio = yf_financials.get("pe_ratio")
                pb_ratio = yf_financials.get("pb_ratio")
                dividend_yield = yf_financials.get("dividend_yield")
                week_52_high = yf_financials.get("week_52_high")
                week_52_low = yf_financials.get("week_52_low")
        except Exception as e:
            logger.debug(f"{symbol}: yfinance financials failed: {e}")

    # === Get news count (Finnhub only) ===
    try:
        news = finnhub.get_company_news(symbol)
        news_count = len(news)
    except Exception:
        news_count = 0

    # Calculate gap percentage (for V2)
    gap_pct = 0.0
    if previous_close and previous_close > 0:
        gap_pct = ((open_price - previous_close) / previous_close) * 100

    # V1 Stock Data
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

    # V2 Stock Data
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
        earnings_surprise_pct=None,
        analyst_revision_score=None,
    )

    return v1_data, v2_data


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
        yf_client = get_yfinance_client()
        supabase = SupabaseClient()
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        sys.exit(1)

    # 1. Determine market regime
    logger.info("Step 1: Determining market regime...")
    try:
        regime_data = fetch_market_regime_data(finnhub, yf_client)
    except DataFetchError as e:
        logger.error(f"FATAL: Cannot fetch market regime data: {e}")
        logger.error("Batch failed - no data sources available")
        sys.exit(1)

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
    failed_symbols = []

    for symbol in candidates:
        result = fetch_stock_data(finnhub, yf_client, symbol, regime_data["vix"])
        if result:
            v1_data, v2_data = result
            v1_stocks_data.append(v1_data)
            v2_stocks_data.append(v2_data)
        else:
            failed_symbols.append(symbol)
        # Small delay to avoid rate limiting
        time.sleep(0.5)

    logger.info(f"Successfully fetched data for {len(v1_stocks_data)} stocks")
    if failed_symbols:
        logger.warning(f"Failed to fetch data for {len(failed_symbols)} symbols: {failed_symbols[:10]}...")

    # Ensure we have enough data to make recommendations
    MIN_STOCKS_REQUIRED = 10
    if len(v1_stocks_data) < MIN_STOCKS_REQUIRED:
        logger.error(f"FATAL: Only {len(v1_stocks_data)} stocks with data (minimum {MIN_STOCKS_REQUIRED} required)")
        logger.error("Batch failed - insufficient data for reliable recommendations")
        sys.exit(1)

    # 4. Fetch dynamic thresholds from database (FEEDBACK LOOP)
    logger.info("Step 4: Fetching dynamic thresholds from scoring_config...")
    try:
        v1_config = supabase.get_scoring_config("conservative")
        v2_config = supabase.get_scoring_config("aggressive")
        v1_threshold = int(v1_config.get("threshold", 60)) if v1_config else None
        v2_threshold = int(v2_config.get("threshold", 75)) if v2_config else None
        logger.info(f"Dynamic thresholds: V1={v1_threshold}, V2={v2_threshold}")
    except Exception as e:
        logger.warning(f"Failed to fetch dynamic thresholds, using defaults: {e}")
        v1_threshold = None
        v2_threshold = None

    # 5. Run dual scoring (V1 Conservative + V2 Aggressive)
    logger.info("Step 5: Running dual scoring pipeline...")
    dual_result = run_dual_scoring(
        v1_stocks_data,
        v2_stocks_data,
        market_regime,
        v1_threshold=v1_threshold,
        v2_threshold=v2_threshold,
    )

    logger.info(f"V1 (Conservative) scored: {len(dual_result.v1_scores)} stocks")
    logger.info(f"V1 picks (rule-based): {dual_result.v1_picks}")
    logger.info(f"V2 (Aggressive) scored: {len(dual_result.v2_scores)} stocks")
    logger.info(f"V2 picks (rule-based): {dual_result.v2_picks}")

    # 5.5. Run LLM Judgment for top candidates (Layer 2)
    logger.info("Step 5.5: Running LLM judgment for top candidates...")

    # Check if LLM judgment is enabled (can be disabled for cost savings)
    use_llm_judgment = config.llm.enable_judgment

    v1_final_picks = dual_result.v1_picks
    v2_final_picks = dual_result.v2_picks

    if use_llm_judgment:
        try:
            judgment_service = JudgmentService()

            # Build candidate lists: (stock_data, scored_stock) sorted by composite score
            v1_candidates = []
            v1_score_map = {s.symbol: s for s in dual_result.v1_scores}
            for stock_data in v1_stocks_data:
                if stock_data.symbol in v1_score_map:
                    v1_candidates.append((stock_data, v1_score_map[stock_data.symbol]))
            v1_candidates.sort(key=lambda x: x[1].composite_score, reverse=True)

            v2_candidates = []
            v2_score_map = {s.symbol: s for s in dual_result.v2_scores}
            for stock_data in v2_stocks_data:
                if stock_data.symbol in v2_score_map:
                    v2_candidates.append((stock_data, v2_score_map[stock_data.symbol]))
            v2_candidates.sort(key=lambda x: x[1].composite_score, reverse=True)

            # Run V1 Conservative judgments
            v1_judgments = run_judgment_for_candidates(
                judgment_service=judgment_service,
                finnhub=finnhub,
                supabase=supabase,
                candidates=v1_candidates,
                strategy_mode="conservative",
                market_regime=market_regime.regime.value,
                batch_date=today,
                top_n=10,  # Judge top 10 candidates
            )

            # Filter V1 picks using LLM judgment
            v1_final_picks = filter_picks_by_judgment(
                rule_based_picks=dual_result.v1_picks,
                judgments=v1_judgments,
                min_confidence=0.6,  # Conservative requires 60% confidence
            )

            # Run V2 Aggressive judgments
            v2_judgments = run_judgment_for_candidates(
                judgment_service=judgment_service,
                finnhub=finnhub,
                supabase=supabase,
                candidates=v2_candidates,
                strategy_mode="aggressive",
                market_regime=market_regime.regime.value,
                batch_date=today,
                top_n=10,
            )

            # Filter V2 picks using LLM judgment
            v2_final_picks = filter_picks_by_judgment(
                rule_based_picks=dual_result.v2_picks,
                judgments=v2_judgments,
                min_confidence=0.5,  # Aggressive allows 50% confidence
            )

            logger.info(f"V1 picks after LLM judgment: {v1_final_picks}")
            logger.info(f"V2 picks after LLM judgment: {v2_final_picks}")

        except Exception as e:
            logger.error(f"LLM judgment failed, using rule-based picks: {e}")
            # Fall back to rule-based picks
            v1_final_picks = dual_result.v1_picks
            v2_final_picks = dual_result.v2_picks
    else:
        logger.info("LLM judgment disabled, using rule-based picks only")

    # 6. Save results for both strategies
    logger.info("Step 6: Saving results...")

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

    # Save V1 daily picks (using LLM-filtered picks if available)
    supabase.save_daily_picks(DailyPick(
        batch_date=today,
        symbols=v1_final_picks,
        pick_count=len(v1_final_picks),
        market_regime=market_regime.regime.value,
        strategy_mode="conservative",
        status="published",
    ))

    # Save V2 daily picks (using LLM-filtered picks if available)
    supabase.save_daily_picks(DailyPick(
        batch_date=today,
        symbols=v2_final_picks,
        pick_count=len(v2_final_picks),
        market_regime=market_regime.regime.value,
        strategy_mode="aggressive",
        status="published",
    ))

    # 7. PAPER TRADING: Open positions for picks
    logger.info("Step 7: Opening positions for paper trading...")

    # Check if we should open positions (not in crisis mode)
    if market_regime.max_picks > 0:
        portfolio = PortfolioManager(
            supabase=supabase,
            finnhub=finnhub,
            yfinance=yf_client,
        )

        # Build price dict from stock data
        prices = {d.symbol: d.open_price for d in v1_stocks_data if d.open_price > 0}

        # Build score dicts
        v1_score_dict = {s.symbol: s.composite_score for s in dual_result.v1_scores}
        v2_score_dict = {s.symbol: s.composite_score for s in dual_result.v2_scores}

        # Open positions for V1 Conservative (using LLM-filtered picks)
        if v1_final_picks:
            v1_opened = portfolio.open_positions_for_picks(
                picks=v1_final_picks,
                strategy_mode="conservative",
                scores=v1_score_dict,
                prices=prices,
            )
            logger.info(f"V1 opened {len(v1_opened)} positions")

        # Open positions for V2 Aggressive (using LLM-filtered picks)
        if v2_final_picks:
            v2_opened = portfolio.open_positions_for_picks(
                picks=v2_final_picks,
                strategy_mode="aggressive",
                scores=v2_score_dict,
                prices=prices,
            )
            logger.info(f"V2 opened {len(v2_opened)} positions")

        # 8. Update portfolio snapshots
        logger.info("Step 8: Updating portfolio snapshots...")

        # Get S&P 500 daily return for benchmark
        sp500_daily_pct = None
        try:
            sp500_candles = finnhub.get_stock_candles(
                "SPY",
                resolution="D",
                from_timestamp=int((datetime.now() - timedelta(days=2)).timestamp()),
            )
            if sp500_candles and len(sp500_candles.get("close", [])) >= 2:
                closes = sp500_candles["close"]
                sp500_daily_pct = ((closes[-1] - closes[-2]) / closes[-2]) * 100
                logger.info(f"S&P 500 daily return: {sp500_daily_pct:.2f}%")
        except Exception as e:
            logger.warning(f"Failed to get S&P 500 daily return: {e}")

        for strategy in ["conservative", "aggressive"]:
            try:
                portfolio.update_portfolio_snapshot(
                    strategy_mode=strategy,
                    sp500_daily_pct=sp500_daily_pct,
                )
            except Exception as e:
                logger.error(f"Failed to update snapshot for {strategy}: {e}")

    else:
        logger.info("Skipping position opening - market in crisis mode")

    logger.info("=" * 50)
    logger.info("Daily scoring batch completed successfully")
    logger.info(f"V1 Conservative Picks (final): {v1_final_picks}")
    logger.info(f"V2 Aggressive Picks (final): {v2_final_picks}")
    if use_llm_judgment:
        logger.info(f"  (Rule-based V1: {dual_result.v1_picks})")
        logger.info(f"  (Rule-based V2: {dual_result.v2_picks})")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
