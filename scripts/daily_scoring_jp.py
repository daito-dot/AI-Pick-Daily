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
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config
from src.data.yfinance_client import get_yfinance_client, YFinanceClient
from src.data.supabase_client import SupabaseClient, MarketRegimeRecord, StockScore, DailyPick
from src.scoring.market_regime import decide_market_regime, calculate_sma, calculate_volatility
from src.scoring.agents import StockData
from src.scoring.agents_v2 import V2StockData
from src.scoring.composite_v2 import run_dual_scoring
from src.portfolio import PortfolioManager
from src.judgment import (
    JudgmentService,
    run_judgment_for_candidates,
    filter_picks_by_judgment,
    select_final_picks,
)
from src.scoring.composite_v2 import get_threshold_passed_symbols
from src.batch_logger import BatchLogger, BatchType
from src.symbols.jp_stocks import JP_STOCK_SYMBOLS, get_jp_stock_name
from src.monitoring import BatchMetrics, record_batch_metrics, check_and_alert, send_alert, AlertLevel


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

        # Build StockData for V1 (must match StockData dataclass fields)
        open_price = hist["Open"].iloc[-1] if not hist.empty else current_price

        stock_data = StockData(
            symbol=symbol,
            prices=closes,
            volumes=volumes,
            open_price=float(open_price),
            pe_ratio=pe_ratio,
            pb_ratio=pb_ratio,
            dividend_yield=dividend_yield * 100 if dividend_yield else None,
            week_52_high=high_52w,
            week_52_low=low_52w,
            news_count_7d=0,  # Skip news for JP stocks
            news_sentiment=None,
            sector_avg_pe=25.0,  # Default
        )

        # Calculate gap percentage for V2
        if len(hist) >= 2:
            prev_close = hist["Close"].iloc[-2]
            gap_pct = ((open_price - prev_close) / prev_close) * 100
        else:
            gap_pct = 0.0

        # Build V2StockData (extends StockData)
        # Note: vix_level will be updated after fetching all data
        v2_data = V2StockData(
            symbol=symbol,
            prices=closes,
            volumes=volumes,
            open_price=float(open_price),
            pe_ratio=pe_ratio,
            pb_ratio=pb_ratio,
            dividend_yield=dividend_yield * 100 if dividend_yield else None,
            week_52_high=high_52w,
            week_52_low=low_52w,
            news_count_7d=0,
            news_sentiment=None,
            sector_avg_pe=25.0,
            vix_level=20.0,  # Default, will be updated in main()
            gap_pct=gap_pct,
            earnings_surprise_pct=None,
            analyst_revision_score=None,  # Match US version
            price_1m_ago=closes[-21] if len(closes) >= 21 else None,
            price_12m_ago=closes[-252] if len(closes) >= 252 else None,
        )

        return stock_data, v2_data

    except Exception as e:
        logger.error(f"{symbol}: Failed to fetch data: {e}")
        return None, None


def save_results_jp(
    supabase: SupabaseClient,
    batch_date: str,
    market_regime: str,
    dual_result,  # DualScoringResult
    v1_stocks_data: list[StockData],
    v1_final_picks: list[str],
    v2_final_picks: list[str],
) -> list[str]:
    """Save scoring results to Supabase with market_type='jp'.

    Note: Market regime is saved before this function is called.
    Uses final picks (after LLM judgment) for daily_picks table.
    Follows same pattern as US version but adds market_type='jp'.

    Returns:
        List of error messages (empty if all succeeded)
    """
    save_errors = []

    # Helper to get price for a symbol
    def get_price(symbol: str) -> float:
        return next(
            (d.open_price for d in v1_stocks_data if d.symbol == symbol),
            0.0,
        )

    # Save V1 (jp_conservative) stock scores
    try:
        v1_score_data = [
            {
                "batch_date": batch_date,
                "symbol": s.symbol,
                "strategy_mode": "jp_conservative",
                "trend_score": int(s.trend_score),
                "momentum_score": int(s.momentum_score),
                "value_score": int(s.value_score),
                "sentiment_score": int(s.sentiment_score),
                "composite_score": int(s.composite_score),
                "percentile_rank": int(s.percentile_rank),
                "reasoning": s.reasoning,
                "price_at_time": float(get_price(s.symbol)),
                "market_regime_at_time": market_regime,
                "momentum_12_1_score": int(s.momentum_12_1_score) if s.momentum_12_1_score else None,
                "breakout_score": int(s.breakout_score) if s.breakout_score else None,
                "catalyst_score": int(s.catalyst_score) if s.catalyst_score else None,
                "risk_adjusted_score": int(s.risk_adjusted_score) if s.risk_adjusted_score else None,
                "cutoff_timestamp": dual_result.cutoff_timestamp.isoformat(),
                "market_type": "jp",
            }
            for s in dual_result.v1_scores
        ]
        supabase._client.table("stock_scores").upsert(
            v1_score_data,
            on_conflict="batch_date,symbol,strategy_mode",
        ).execute()
        logger.info(f"Saved {len(v1_score_data)} V1 (jp_conservative) stock scores")
    except Exception as e:
        error_msg = f"Failed to save V1 (jp_conservative) stock scores: {e}"
        logger.error(error_msg)
        save_errors.append(error_msg)

    # Save V2 (jp_aggressive) stock scores
    try:
        v2_score_data = [
            {
                "batch_date": batch_date,
                "symbol": s.symbol,
                "strategy_mode": "jp_aggressive",
                "trend_score": int(s.trend_score),
                "momentum_score": int(s.momentum_score),
                "value_score": int(s.value_score),
                "sentiment_score": int(s.sentiment_score),
                "composite_score": int(s.composite_score),
                "percentile_rank": int(s.percentile_rank),
                "reasoning": s.reasoning,
                "price_at_time": float(get_price(s.symbol)),
                "market_regime_at_time": market_regime,
                "momentum_12_1_score": int(s.momentum_12_1_score) if s.momentum_12_1_score else None,
                "breakout_score": int(s.breakout_score) if s.breakout_score else None,
                "catalyst_score": int(s.catalyst_score) if s.catalyst_score else None,
                "risk_adjusted_score": int(s.risk_adjusted_score) if s.risk_adjusted_score else None,
                "cutoff_timestamp": dual_result.cutoff_timestamp.isoformat(),
                "market_type": "jp",
            }
            for s in dual_result.v2_scores
        ]
        supabase._client.table("stock_scores").upsert(
            v2_score_data,
            on_conflict="batch_date,symbol,strategy_mode",
        ).execute()
        logger.info(f"Saved {len(v2_score_data)} V2 (jp_aggressive) stock scores")
    except Exception as e:
        error_msg = f"Failed to save V2 (jp_aggressive) stock scores: {e}"
        logger.error(error_msg)
        save_errors.append(error_msg)

    # Save daily picks with idempotency
    # Delete existing records first, then insert (ensures clean slate for re-runs)
    try:
        # Delete existing JP picks for this date
        supabase.delete_daily_picks_for_date(
            batch_date,
            strategy_modes=["jp_conservative", "jp_aggressive"],
        )

        # Save V1 daily picks (with market_type) - uses LLM-filtered final picks
        supabase._client.table("daily_picks").upsert({
            "batch_date": batch_date,
            "strategy_mode": "jp_conservative",
            "symbols": v1_final_picks,
            "pick_count": len(v1_final_picks),
            "market_regime": market_regime,
            "status": "published",
            "market_type": "jp",
        }, on_conflict="batch_date,strategy_mode").execute()

        # Save V2 daily picks (with market_type) - uses LLM-filtered final picks
        supabase._client.table("daily_picks").upsert({
            "batch_date": batch_date,
            "strategy_mode": "jp_aggressive",
            "symbols": v2_final_picks,
            "pick_count": len(v2_final_picks),
            "market_regime": market_regime,
            "status": "published",
            "market_type": "jp",
        }, on_conflict="batch_date,strategy_mode").execute()

        logger.info(f"Saved daily picks: V1={len(v1_final_picks)}, V2={len(v2_final_picks)}")

    except Exception as e:
        error_msg = f"Failed to save daily picks: {e}"
        logger.error(error_msg)
        save_errors.append(error_msg)

    if save_errors:
        logger.error(f"Save operation completed with {len(save_errors)} error(s)")
    else:
        logger.info(f"Saved: V1 scores={len(dual_result.v1_scores)}, V2 scores={len(dual_result.v2_scores)}")
        logger.info(f"Final Picks: V1={v1_final_picks}, V2={v2_final_picks}")

    return save_errors


def main():
    """Main entry point for Japan stock scoring."""
    # Track batch timing for monitoring
    batch_start_time = datetime.utcnow()
    batch_id = f"jp_{batch_start_time.strftime('%Y%m%d_%H%M%S')}"

    # Initialize judgment tracking variables
    total_successful_judgments = 0
    total_failed_judgments = 0

    logger.info("=" * 60)
    logger.info("Starting Japan Stock Daily Scoring Batch")
    logger.info(f"Timestamp: {batch_start_time.isoformat()}")
    logger.info(f"Batch ID: {batch_id}")
    logger.info("=" * 60)

    # Start batch logging (include model like US version)
    batch_ctx = BatchLogger.start(BatchType.MORNING_SCORING, model=config.llm.scoring_model)

    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

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

        # Save market regime first (like US version)
        supabase.save_market_regime(MarketRegimeRecord(
            check_date=today,
            vix_level=vix,
            market_regime=regime,
            sp500_sma20_deviation_pct=0,
            volatility_cluster_flag=False,
            notes=f"Japan stocks - VIX: {vix}",
        ))

        # Check for crisis mode
        if market_regime.max_picks == 0:
            logger.warning("Market in CRISIS mode - no recommendations today")
            # Save empty picks for both JP strategies
            supabase._client.table("daily_picks").upsert({
                "batch_date": today,
                "strategy_mode": "jp_conservative",
                "symbols": [],
                "pick_count": 0,
                "market_regime": regime,
                "status": "published",
                "market_type": "jp",
            }, on_conflict="batch_date,strategy_mode").execute()
            supabase._client.table("daily_picks").upsert({
                "batch_date": today,
                "strategy_mode": "jp_aggressive",
                "symbols": [],
                "pick_count": 0,
                "market_regime": regime,
                "status": "published",
                "market_type": "jp",
            }, on_conflict="batch_date,strategy_mode").execute()
            logger.info("Saved empty daily picks for JP strategies")
            batch_ctx.metadata = {"market_regime": "crisis", "reason": "VIX too high"}
            BatchLogger.finish(batch_ctx)
            return

        # Step 2: Fetch stock data for all JP stocks
        logger.info("Step 2: Fetching Japanese stock data...")
        v1_stocks_data = []
        v2_stocks_data = []
        failed_symbols = []

        batch_ctx.total_items = len(JP_STOCK_SYMBOLS)

        for i, symbol in enumerate(JP_STOCK_SYMBOLS):
            logger.info(f"Fetching {symbol} ({i+1}/{len(JP_STOCK_SYMBOLS)})")

            stock_data, v2_data = fetch_stock_data_jp(yf_client, symbol)

            if stock_data is not None and v2_data is not None:
                v1_stocks_data.append(stock_data)
                v2_stocks_data.append(v2_data)
            else:
                failed_symbols.append(symbol)

            batch_ctx.processed_items = i + 1

            # Rate limiting
            time.sleep(0.3)

        logger.info(f"Successfully fetched data for {len(v1_stocks_data)} stocks")
        if failed_symbols:
            logger.warning(f"Failed to fetch {len(failed_symbols)} stocks")

        # Update VIX level in all V2 stock data (like US version)
        for v2_data in v2_stocks_data:
            v2_data.vix_level = vix

        # Ensure minimum data
        MIN_STOCKS_REQUIRED = 10
        if len(v1_stocks_data) < MIN_STOCKS_REQUIRED:
            error_msg = f"Only {len(v1_stocks_data)} stocks with data (minimum {MIN_STOCKS_REQUIRED} required)"
            logger.error(f"FATAL: {error_msg}")
            batch_ctx.failed_items = len(failed_symbols)
            batch_ctx.successful_items = len(v1_stocks_data)
            BatchLogger.finish(batch_ctx, error=error_msg)
            sys.exit(1)

        # Step 3: Fetch dynamic thresholds from database (FEEDBACK LOOP)
        logger.info("Step 3: Fetching dynamic thresholds from scoring_config...")
        try:
            v1_config = supabase.get_scoring_config("jp_conservative")
            v2_config = supabase.get_scoring_config("jp_aggressive")
            v1_threshold = int(v1_config.get("threshold", 60)) if v1_config else None
            v2_threshold = int(v2_config.get("threshold", 75)) if v2_config else None
            logger.info(f"Dynamic thresholds: V1={v1_threshold}, V2={v2_threshold}")
        except Exception as e:
            logger.warning(f"Failed to fetch dynamic thresholds, using defaults: {e}")
            v1_threshold = None
            v2_threshold = None

        # Step 4: Run dual scoring (V1 Conservative + V2 Aggressive)
        logger.info("Step 4: Running dual scoring pipeline...")
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

        # Step 4.5: Run LLM Judgment for top candidates (Layer 2)
        logger.info("Step 4.5: Running LLM judgment for top candidates...")

        use_llm_judgment = config.llm.enable_judgment
        v1_final_picks = dual_result.v1_picks
        v2_final_picks = dual_result.v2_picks

        if use_llm_judgment:
            judgment_ctx = None
            try:
                judgment_ctx = BatchLogger.start(
                    BatchType.LLM_JUDGMENT,
                    model=config.llm.analysis_model
                )
                judgment_service = JudgmentService()

                # Get thresholds (use dynamic or fall back to config)
                v1_min_score = v1_threshold if v1_threshold is not None else config.strategy.v1_min_score
                v2_min_score = v2_threshold if v2_threshold is not None else config.strategy.v2_min_score

                # NEW LOGIC: Filter candidates by threshold (pass/fail) instead of top_n
                v1_passed_symbols = get_threshold_passed_symbols(dual_result.v1_scores, v1_min_score)
                v2_passed_symbols = get_threshold_passed_symbols(dual_result.v2_scores, v2_min_score)

                logger.info(f"V1 threshold-passed candidates: {len(v1_passed_symbols)}")
                logger.info(f"V2 threshold-passed candidates: {len(v2_passed_symbols)}")

                # Build candidate lists for threshold-passed stocks only
                v1_candidates = []
                v1_score_map = {s.symbol: s for s in dual_result.v1_scores}
                for stock_data in v1_stocks_data:
                    if stock_data.symbol in v1_passed_symbols:
                        v1_candidates.append((stock_data, v1_score_map[stock_data.symbol]))

                v2_candidates = []
                v2_score_map = {s.symbol: s for s in dual_result.v2_scores}
                for stock_data in v2_stocks_data:
                    if stock_data.symbol in v2_passed_symbols:
                        v2_candidates.append((stock_data, v2_score_map[stock_data.symbol]))

                # Run V1 Conservative judgments (judge ALL threshold-passed candidates)
                v1_judgment_result = run_judgment_for_candidates(
                    judgment_service=judgment_service,
                    finnhub=None,  # No Finnhub for JP stocks
                    supabase=supabase,
                    candidates=v1_candidates,
                    strategy_mode="jp_conservative",
                    market_regime=regime,
                    batch_date=today,
                    top_n=None,  # Judge all threshold-passed candidates
                    yfinance=yf_client,  # Use yfinance for news
                )

                # NEW: Use LLM-first selection (sort by confidence, not rule score)
                v1_final_picks = select_final_picks(
                    scores=dual_result.v1_scores,
                    judgments=v1_judgment_result.successful,
                    max_picks=market_regime.max_picks,  # V1 respects regime
                    min_rule_score=v1_min_score,
                    min_confidence=0.6,  # Conservative requires 60% confidence
                )

                # Log V1 failures if any
                if v1_judgment_result.failed:
                    logger.warning(
                        f"V1 judgment failures ({v1_judgment_result.failure_count}): "
                        f"{[(sym, err[:50]) for sym, err in v1_judgment_result.failed]}"
                    )

                # Run V2 Aggressive judgments (judge ALL threshold-passed candidates)
                v2_judgment_result = run_judgment_for_candidates(
                    judgment_service=judgment_service,
                    finnhub=None,
                    supabase=supabase,
                    candidates=v2_candidates,
                    strategy_mode="jp_aggressive",
                    market_regime=regime,
                    batch_date=today,
                    top_n=None,  # Judge all threshold-passed candidates
                    yfinance=yf_client,  # Use yfinance for news
                )

                # NEW: Use LLM-first selection (sort by confidence, not rule score)
                v2_max_picks = config.strategy.v2_max_picks if market_regime.max_picks > 0 else 0
                v2_final_picks = select_final_picks(
                    scores=dual_result.v2_scores,
                    judgments=v2_judgment_result.successful,
                    max_picks=v2_max_picks,
                    min_rule_score=v2_min_score,
                    min_confidence=0.5,  # Aggressive allows 50% confidence
                )

                # Log V2 failures if any
                if v2_judgment_result.failed:
                    logger.warning(
                        f"V2 judgment failures ({v2_judgment_result.failure_count}): "
                        f"{[(sym, err[:50]) for sym, err in v2_judgment_result.failed]}"
                    )

                logger.info(f"V1 picks after LLM judgment: {v1_final_picks}")
                logger.info(f"V2 picks after LLM judgment: {v2_final_picks}")

                # Track judgment results
                total_candidates = len(v1_candidates) + len(v2_candidates)
                judgment_ctx.successful_items = v1_judgment_result.success_count + v2_judgment_result.success_count
                judgment_ctx.total_items = total_candidates
                judgment_ctx.failed_items = v1_judgment_result.failure_count + v2_judgment_result.failure_count
                BatchLogger.finish(judgment_ctx)

                # Update monitoring tracking variables
                total_successful_judgments = v1_judgment_result.success_count + v2_judgment_result.success_count
                total_failed_judgments = v1_judgment_result.failure_count + v2_judgment_result.failure_count

            except Exception as e:
                logger.error(f"LLM judgment failed, using rule-based picks: {e}")
                if judgment_ctx is not None:
                    BatchLogger.finish(judgment_ctx, error=str(e))
                v1_final_picks = dual_result.v1_picks
                v2_final_picks = dual_result.v2_picks
        else:
            logger.info("LLM judgment disabled, using rule-based picks only")

        # Step 5: Save results (uses final picks after LLM judgment)
        logger.info("Step 5: Saving results...")
        save_errors = save_results_jp(
            supabase=supabase,
            batch_date=today,
            market_regime=regime,
            dual_result=dual_result,
            v1_stocks_data=v1_stocks_data,
            v1_final_picks=v1_final_picks,
            v2_final_picks=v2_final_picks,
        )

        # Track save errors in batch metadata
        if save_errors:
            batch_ctx.metadata = batch_ctx.metadata or {}
            batch_ctx.metadata["save_errors"] = save_errors

        # Step 6: Paper Trading - Open positions for picks
        logger.info("Step 6: Opening positions for paper trading...")

        if market_regime.max_picks > 0:
            portfolio = PortfolioManager(
                supabase=supabase,
                finnhub=None,  # No Finnhub for JP
                yfinance=yf_client,
            )

            # Build price dict from stock data
            prices = {d.symbol: d.open_price for d in v1_stocks_data if d.open_price > 0}

            # Build score dicts
            v1_score_dict = {s.symbol: s.composite_score for s in dual_result.v1_scores}
            v2_score_dict = {s.symbol: s.composite_score for s in dual_result.v2_scores}

            # Open positions for V1 Conservative
            if v1_final_picks:
                v1_opened = portfolio.open_positions_for_picks(
                    picks=v1_final_picks,
                    strategy_mode="jp_conservative",
                    scores=v1_score_dict,
                    prices=prices,
                )
                logger.info(f"V1 opened {len(v1_opened)} positions")

            # Open positions for V2 Aggressive
            if v2_final_picks:
                v2_opened = portfolio.open_positions_for_picks(
                    picks=v2_final_picks,
                    strategy_mode="jp_aggressive",
                    scores=v2_score_dict,
                    prices=prices,
                )
                logger.info(f"V2 opened {len(v2_opened)} positions")

            # Step 7: Update portfolio snapshots
            logger.info("Step 7: Updating portfolio snapshots...")

            # Get Nikkei 225 daily return for benchmark
            nikkei_daily_pct = None
            try:
                import yfinance as yf
                nikkei = yf.Ticker("^N225")
                nikkei_hist = nikkei.history(period="5d")
                if len(nikkei_hist) >= 2:
                    closes = nikkei_hist["Close"].tolist()
                    nikkei_daily_pct = ((closes[-1] - closes[-2]) / closes[-2]) * 100
                    logger.info(f"Nikkei 225 daily return: {nikkei_daily_pct:.2f}%")
            except Exception as e:
                logger.warning(f"Failed to get Nikkei 225 daily return: {e}")

            for strategy in ["jp_conservative", "jp_aggressive"]:
                try:
                    portfolio.update_portfolio_snapshot(
                        strategy_mode=strategy,
                        sp500_daily_pct=nikkei_daily_pct,  # Using Nikkei as benchmark
                    )
                except Exception as e:
                    logger.error(f"Failed to update snapshot for {strategy}: {e}")

        else:
            logger.info("Skipping position opening - market in crisis mode")

        # Record batch completion stats
        batch_ctx.successful_items = len(v1_stocks_data)
        batch_ctx.failed_items = len(failed_symbols)
        batch_ctx.total_items = len(JP_STOCK_SYMBOLS)
        batch_ctx.metadata = {
            "v1_picks": v1_final_picks,
            "v2_picks": v2_final_picks,
            "market_regime": regime,
            "market": "jp",
            "llm_judgment_enabled": use_llm_judgment,
        }

        # Finish batch
        BatchLogger.finish(batch_ctx)

        # Record batch metrics for monitoring
        batch_end_time = datetime.utcnow()
        batch_metrics = BatchMetrics(
            batch_id=batch_id,
            start_time=batch_start_time,
            end_time=batch_end_time,
            total_symbols=len(JP_STOCK_SYMBOLS),
            successful_judgments=total_successful_judgments,
            failed_judgments=total_failed_judgments,
            v1_picks_count=len(v1_final_picks),
            v2_picks_count=len(v2_final_picks),
        )
        record_batch_metrics(batch_metrics)

        # Check and send alerts if thresholds exceeded
        alerts = check_and_alert(batch_metrics)
        for alert_message in alerts:
            send_alert(alert_message, AlertLevel.WARNING)

        logger.info("=" * 60)
        logger.info("Japan Stock Daily Scoring completed successfully")
        logger.info(f"JP Conservative Picks (final): {v1_final_picks}")
        logger.info(f"JP Aggressive Picks (final): {v2_final_picks}")
        if use_llm_judgment:
            logger.info(f"  (Rule-based V1: {dual_result.v1_picks})")
            logger.info(f"  (Rule-based V2: {dual_result.v2_picks})")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Batch failed: {e}")
        BatchLogger.finish(batch_ctx, error=str(e))
        raise


if __name__ == "__main__":
    main()
