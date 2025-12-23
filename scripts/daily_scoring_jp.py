#!/usr/bin/env python3
"""
Daily Scoring Script - Japan Stocks

Morning batch job for Japanese stocks:
1. Fetches market data from yfinance (Japanese stocks)
2. Determines market regime (VIX as global indicator)
3. Scores stocks with 4 agents
4. Selects top picks
5. Saves to Supabase with market_type='jp'

Note: Japanese market hours are 9:00-15:00 JST
This script should run after market close (15:30 JST = 06:30 UTC)
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
from src.data.yfinance_client import get_yfinance_client, YFinanceClient
from src.data.supabase_client import SupabaseClient
from src.scoring.market_regime import decide_market_regime, calculate_sma, calculate_volatility
from src.scoring.agents import StockData
from src.scoring.agents_v2 import V2StockData
from src.scoring.composite_v2 import run_dual_scoring
from src.batch_logger import BatchLogger, BatchType
from src.symbols.jp_stocks import JP_STOCK_SYMBOLS, get_jp_stock_name


class DataFetchError(Exception):
    """Raised when data cannot be fetched."""
    pass


# Setup logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG if config.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / f"scoring_jp_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def fetch_market_regime_data_jp(yf_client: YFinanceClient) -> dict:
    """
    Fetch data needed for market regime determination.
    Uses VIX as global volatility indicator, Nikkei 225 as benchmark.
    """
    logger.info("Fetching market regime data for Japan stocks...")

    # Get VIX (global volatility indicator)
    vix = yf_client.get_vix()
    if vix is None or vix <= 0:
        raise DataFetchError("Failed to get VIX")
    logger.info(f"VIX: {vix}")

    # Get Nikkei 225 price
    nikkei_price = yf_client.get_nikkei_price()
    if nikkei_price is None or nikkei_price <= 0:
        raise DataFetchError("Failed to get Nikkei 225 price")
    logger.info(f"Nikkei 225: {nikkei_price}")

    # Get Nikkei 225 historical prices for SMA and volatility
    import yfinance as yf
    ticker = yf.Ticker("^N225")
    hist = ticker.history(period="60d")

    if hist.empty or len(hist) < 20:
        raise DataFetchError("Failed to get Nikkei 225 historical data")

    prices = hist["Close"].tolist()

    # Calculate metrics (same as US version)
    nikkei_sma20 = calculate_sma(prices, 20)
    volatility_5d = calculate_volatility(prices, 5)
    volatility_30d = calculate_volatility(prices, 30)

    logger.info(f"Market data: VIX={vix:.2f}, Nikkei={nikkei_price:.2f}, SMA20={nikkei_sma20:.2f}")

    return {
        "vix": vix,
        "benchmark_price": nikkei_price,
        "benchmark_sma20": nikkei_sma20,
        "volatility_5d": volatility_5d,
        "volatility_30d": volatility_30d,
    }


def fetch_stock_data_jp(
    yf_client: YFinanceClient,
    symbol: str,
) -> tuple[StockData | None, V2StockData | None]:
    """
    Fetch data for a single Japanese stock.
    Returns (StockData for V1, V2StockData for V2) or (None, None) if failed.
    """
    import yfinance as yf

    try:
        ticker = yf.Ticker(symbol)

        # Get current quote
        info = ticker.fast_info
        current_price = float(info.get("lastPrice", 0) or info.get("regularMarketPrice", 0))

        if current_price <= 0:
            hist_1d = ticker.history(period="1d")
            if not hist_1d.empty:
                current_price = float(hist_1d["Close"].iloc[-1])

        if current_price <= 0:
            logger.warning(f"{symbol}: No price data")
            return None, None

        # Get historical data
        hist = ticker.history(period="1y")
        if hist.empty or len(hist) < 50:
            logger.warning(f"{symbol}: Insufficient historical data")
            return None, None

        closes = hist["Close"].tolist()
        volumes = hist["Volume"].tolist()
        highs = hist["High"].tolist()
        lows = hist["Low"].tolist()

        # Calculate technical indicators
        # SMA
        sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        sma_50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
        sma_200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else None

        # RSI
        def calculate_rsi(prices, period=14):
            if len(prices) < period + 1:
                return None
            deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
            gains = [d if d > 0 else 0 for d in deltas[-period:]]
            losses = [-d if d < 0 else 0 for d in deltas[-period:]]
            avg_gain = sum(gains) / period
            avg_loss = sum(losses) / period
            if avg_loss == 0:
                return 100
            rs = avg_gain / avg_loss
            return 100 - (100 / (1 + rs))

        rsi_14 = calculate_rsi(closes)

        # Volume ratio
        avg_volume = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else sum(volumes) / len(volumes)
        current_volume = volumes[-1] if volumes else 0
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        # 52-week high/low
        high_52w = max(highs[-252:]) if len(highs) >= 252 else max(highs)
        low_52w = min(lows[-252:]) if len(lows) >= 252 else min(lows)

        # Returns
        return_5d = ((current_price / closes[-6]) - 1) * 100 if len(closes) >= 6 else 0
        return_20d = ((current_price / closes[-21]) - 1) * 100 if len(closes) >= 21 else 0
        return_60d = ((current_price / closes[-61]) - 1) * 100 if len(closes) >= 61 else 0

        # Get basic info
        try:
            full_info = ticker.info
            pe_ratio = full_info.get("trailingPE") or full_info.get("forwardPE")
            pb_ratio = full_info.get("priceToBook")
            dividend_yield = full_info.get("dividendYield")
            market_cap = full_info.get("marketCap")
        except:
            pe_ratio = None
            pb_ratio = None
            dividend_yield = None
            market_cap = None

        # Build StockData for V1
        stock_data = StockData(
            symbol=symbol,
            current_price=current_price,
            sma_20=sma_20,
            sma_50=sma_50,
            sma_200=sma_200,
            rsi_14=rsi_14,
            volume_ratio=volume_ratio,
            high_52w=high_52w,
            low_52w=low_52w,
            return_5d=return_5d,
            return_20d=return_20d,
            return_60d=return_60d,
            pe_ratio=pe_ratio,
            pb_ratio=pb_ratio,
            dividend_yield=dividend_yield * 100 if dividend_yield else None,
            news_count=0,  # Skip news for now
            positive_news_ratio=0.5,
        )

        # Build V2StockData
        # Calculate 12-1 momentum (12-month return excluding last month)
        if len(closes) >= 252:
            price_12m_ago = closes[-252]
            price_1m_ago = closes[-21]
            momentum_12_1 = ((price_1m_ago / price_12m_ago) - 1) * 100
        else:
            momentum_12_1 = return_60d  # Fallback

        # Breakout detection
        recent_high = max(highs[-20:]) if len(highs) >= 20 else max(highs)
        is_breakout = current_price > recent_high * 0.98 and volume_ratio > 1.5

        v2_data = V2StockData(
            symbol=symbol,
            current_price=current_price,
            momentum_12_1_pct=momentum_12_1,
            is_breakout=is_breakout,
            breakout_volume_ratio=volume_ratio if is_breakout else 1.0,
            distance_from_high_pct=((current_price / high_52w) - 1) * 100,
            has_earnings_catalyst=False,  # Skip for now
            earnings_surprise_pct=0,
            has_gap_up=False,
            gap_up_pct=0,
            volatility=calculate_volatility(closes[-20:]) if len(closes) >= 20 else 0.02,
            beta=1.0,  # Default
            rsi_14=rsi_14,
        )

        return stock_data, v2_data

    except Exception as e:
        logger.error(f"{symbol}: Failed to fetch data: {e}")
        return None, None


def calculate_volatility(prices: list[float]) -> float:
    """Calculate annualized volatility from daily prices."""
    if len(prices) < 2:
        return 0.02
    returns = [(prices[i] / prices[i-1]) - 1 for i in range(1, len(prices))]
    import math
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    daily_vol = math.sqrt(variance)
    return daily_vol * math.sqrt(252)


def save_results_jp(
    supabase: SupabaseClient,
    batch_date: str,
    market_regime: str,
    vix_level: float,
    all_scores: list[dict],
    v1_picks: list[str],
    v2_picks: list[str],
):
    """Save scoring results to Supabase with market_type='jp'."""

    # Save market regime
    supabase.save_market_regime(
        check_date=batch_date,
        vix_level=vix_level,
        sp500_price=0,  # Not applicable for Japan
        market_regime=market_regime,
        sp500_sma20_deviation_pct=0,
        volatility_cluster_flag=False,
        notes=f"Japan stocks batch - VIX: {vix_level}",
    )

    # Save V1 picks
    supabase._client.table("daily_picks").upsert({
        "batch_date": batch_date,
        "strategy_mode": "jp_conservative",
        "symbols": v1_picks,
        "pick_count": len(v1_picks),
        "market_regime": market_regime,
        "market_type": "jp",
    }, on_conflict="batch_date,strategy_mode").execute()

    # Save V2 picks
    supabase._client.table("daily_picks").upsert({
        "batch_date": batch_date,
        "strategy_mode": "jp_aggressive",
        "symbols": v2_picks,
        "pick_count": len(v2_picks),
        "market_regime": market_regime,
        "market_type": "jp",
    }, on_conflict="batch_date,strategy_mode").execute()

    # Save all scores
    for score in all_scores:
        # V1 score
        supabase._client.table("stock_scores").upsert({
            "batch_date": batch_date,
            "symbol": score["symbol"],
            "strategy_mode": "jp_conservative",
            "trend_score": score.get("v1_trend", 0),
            "momentum_score": score.get("v1_momentum", 0),
            "value_score": score.get("v1_value", 0),
            "sentiment_score": score.get("v1_sentiment", 50),
            "composite_score": score.get("v1_composite", 0),
            "was_picked": score["symbol"] in v1_picks,
            "market_regime_at_time": market_regime,
            "market_type": "jp",
        }, on_conflict="batch_date,symbol,strategy_mode").execute()

        # V2 score
        supabase._client.table("stock_scores").upsert({
            "batch_date": batch_date,
            "symbol": score["symbol"],
            "strategy_mode": "jp_aggressive",
            "momentum_12_1_score": score.get("v2_momentum", 0),
            "breakout_score": score.get("v2_breakout", 0),
            "catalyst_score": score.get("v2_catalyst", 0),
            "risk_adjusted_score": score.get("v2_risk", 0),
            "composite_score": score.get("v2_composite", 0),
            "was_picked": score["symbol"] in v2_picks,
            "market_regime_at_time": market_regime,
            "market_type": "jp",
        }, on_conflict="batch_date,symbol,strategy_mode").execute()

    logger.info(f"Saved results: V1 picks={len(v1_picks)}, V2 picks={len(v2_picks)}, Total scores={len(all_scores)}")


def main():
    """Main entry point for Japan stock scoring."""
    logger.info("=" * 60)
    logger.info("Starting Japan Stock Daily Scoring Batch")
    logger.info("=" * 60)

    # Start batch logging
    batch_ctx = BatchLogger.start(BatchType.MORNING_SCORING)

    try:
        today = datetime.now().strftime("%Y-%m-%d")

        # Initialize clients
        yf_client = get_yfinance_client()
        supabase = SupabaseClient()

        # Fetch market regime data
        logger.info("Step 1: Fetching market regime data...")
        regime_data = fetch_market_regime_data_jp(yf_client)

        vix = regime_data["vix"]
        nikkei_price = regime_data["benchmark_price"]

        # Determine market regime (same logic as US version)
        market_regime = decide_market_regime(
            vix=regime_data["vix"],
            sp500_price_today=regime_data["benchmark_price"],
            sp500_sma20=regime_data["benchmark_sma20"],
            volatility_5d_avg=regime_data["volatility_5d"],
            volatility_30d_avg=regime_data["volatility_30d"],
        )

        regime = market_regime.regime.value
        logger.info(f"Market Regime: {regime} (VIX={vix:.1f})")
        logger.info(f"Max Picks: {market_regime.max_picks}")

        # Check for crisis mode
        if regime == "crisis":
            logger.warning("Market in CRISIS mode - skipping stock scoring")
            save_results_jp(supabase, today, regime, vix, [], [], [])
            batch_ctx.total_items = 0
            batch_ctx.processed_items = 0
            BatchLogger.finish(batch_ctx)
            return

        # Fetch and score stocks
        logger.info("Step 2: Fetching and scoring Japanese stocks...")

        all_scores = []
        failed_count = 0

        batch_ctx.total_items = len(JP_STOCK_SYMBOLS)

        for i, symbol in enumerate(JP_STOCK_SYMBOLS):
            logger.info(f"Processing {symbol} ({i+1}/{len(JP_STOCK_SYMBOLS)})")

            stock_data, v2_data = fetch_stock_data_jp(yf_client, symbol)

            if stock_data is None or v2_data is None:
                failed_count += 1
                continue

            # Run dual scoring
            try:
                v1_scores, v2_scores = run_dual_scoring(stock_data, v2_data, regime)

                all_scores.append({
                    "symbol": symbol,
                    "v1_trend": v1_scores.get("trend_score", 0),
                    "v1_momentum": v1_scores.get("momentum_score", 0),
                    "v1_value": v1_scores.get("value_score", 0),
                    "v1_sentiment": v1_scores.get("sentiment_score", 50),
                    "v1_composite": v1_scores.get("composite_score", 0),
                    "v2_momentum": v2_scores.get("momentum_12_1_score", 0),
                    "v2_breakout": v2_scores.get("breakout_score", 0),
                    "v2_catalyst": v2_scores.get("catalyst_score", 0),
                    "v2_risk": v2_scores.get("risk_adjusted_score", 0),
                    "v2_composite": v2_scores.get("composite_score", 0),
                })

                batch_ctx.processed_items = i + 1 - failed_count

            except Exception as e:
                logger.error(f"{symbol}: Scoring failed: {e}")
                failed_count += 1

            # Rate limiting
            time.sleep(0.5)

        logger.info(f"Scored {len(all_scores)} stocks, {failed_count} failed")

        # Select top picks
        logger.info("Step 3: Selecting top picks...")

        # V1: Top 5 by composite score (threshold 60)
        v1_sorted = sorted(all_scores, key=lambda x: x["v1_composite"], reverse=True)
        v1_picks = [s["symbol"] for s in v1_sorted if s["v1_composite"] >= 60][:5]

        # V2: Top 3 by composite score (threshold 75)
        v2_sorted = sorted(all_scores, key=lambda x: x["v2_composite"], reverse=True)
        v2_picks = [s["symbol"] for s in v2_sorted if s["v2_composite"] >= 75][:3]

        # Adjust for regime
        if regime == "adjustment":
            v1_picks = v1_picks[:3]
            v2_picks = v2_picks[:2]

        logger.info(f"V1 (Conservative) picks: {v1_picks}")
        logger.info(f"V2 (Aggressive) picks: {v2_picks}")

        # Save results
        logger.info("Step 4: Saving results...")
        save_results_jp(supabase, today, regime, vix, all_scores, v1_picks, v2_picks)

        # Finish batch
        BatchLogger.finish(batch_ctx)

        logger.info("=" * 60)
        logger.info("Japan Stock Daily Scoring completed successfully")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Batch failed: {e}")
        BatchLogger.finish(batch_ctx, error=str(e))
        raise


if __name__ == "__main__":
    main()
