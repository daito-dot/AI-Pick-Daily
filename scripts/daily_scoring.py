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
import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
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
    select_final_picks,
)
from src.scoring.composite_v2 import get_threshold_passed_symbols
from src.batch_logger import BatchLogger, BatchType
from src.monitoring import BatchMetrics, record_batch_metrics, check_and_alert, send_alert, AlertLevel


# Checkpoint configuration
CHECKPOINT_DIR = Path("/tmp/ai_pick_daily_checkpoints")


@dataclass
class BatchCheckpoint:
    """Checkpoint for batch processing progress."""
    batch_date: str
    processed_symbols: list[str] = field(default_factory=list)
    failed_symbols: list[str] = field(default_factory=list)
    # Store fetched stock data (V1 and V2) keyed by symbol
    v1_stock_data: dict[str, dict] = field(default_factory=dict)
    v2_stock_data: dict[str, dict] = field(default_factory=dict)
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "batch_date": self.batch_date,
            "processed_symbols": self.processed_symbols,
            "failed_symbols": self.failed_symbols,
            "v1_stock_data": self.v1_stock_data,
            "v2_stock_data": self.v2_stock_data,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BatchCheckpoint":
        """Create from dictionary."""
        return cls(
            batch_date=data["batch_date"],
            processed_symbols=data.get("processed_symbols", []),
            failed_symbols=data.get("failed_symbols", []),
            v1_stock_data=data.get("v1_stock_data", {}),
            v2_stock_data=data.get("v2_stock_data", {}),
            last_updated=data.get("last_updated", datetime.now(timezone.utc).isoformat()),
        )


def get_checkpoint_path(batch_date: str) -> Path:
    """Get the checkpoint file path for a given batch date."""
    return CHECKPOINT_DIR / f"checkpoint_{batch_date}.json"


def save_checkpoint(checkpoint: BatchCheckpoint) -> None:
    """Save checkpoint to file."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint.last_updated = datetime.now(timezone.utc).isoformat()
    checkpoint_path = get_checkpoint_path(checkpoint.batch_date)

    # Write to temp file first, then rename for atomicity
    temp_path = checkpoint_path.with_suffix(".tmp")
    try:
        with open(temp_path, "w") as f:
            json.dump(checkpoint.to_dict(), f, indent=2)
        temp_path.rename(checkpoint_path)
    except Exception as e:
        # Clean up temp file if it exists
        if temp_path.exists():
            temp_path.unlink()
        raise e


def load_checkpoint(batch_date: str) -> BatchCheckpoint | None:
    """Load checkpoint if exists."""
    checkpoint_path = get_checkpoint_path(batch_date)

    if not checkpoint_path.exists():
        return None

    try:
        with open(checkpoint_path, "r") as f:
            data = json.load(f)
        return BatchCheckpoint.from_dict(data)
    except (json.JSONDecodeError, KeyError) as e:
        # Corrupted checkpoint file - log and return None
        logging.getLogger(__name__).warning(
            f"Corrupted checkpoint file {checkpoint_path}, ignoring: {e}"
        )
        return None


def clear_checkpoint(batch_date: str) -> None:
    """Clear checkpoint after successful completion."""
    checkpoint_path = get_checkpoint_path(batch_date)

    if checkpoint_path.exists():
        checkpoint_path.unlink()
        logging.getLogger(__name__).info(f"Cleared checkpoint for {batch_date}")


def stock_data_to_dict(stock_data: "StockData") -> dict:
    """Convert StockData to a JSON-serializable dictionary."""
    return {
        "symbol": stock_data.symbol,
        "prices": stock_data.prices,
        "volumes": stock_data.volumes,
        "open_price": stock_data.open_price,
        "pe_ratio": stock_data.pe_ratio,
        "pb_ratio": stock_data.pb_ratio,
        "dividend_yield": stock_data.dividend_yield,
        "week_52_high": stock_data.week_52_high,
        "week_52_low": stock_data.week_52_low,
        "news_count_7d": stock_data.news_count_7d,
        "news_sentiment": stock_data.news_sentiment,
        "sector_avg_pe": stock_data.sector_avg_pe,
    }


def v2_stock_data_to_dict(stock_data: "V2StockData") -> dict:
    """Convert V2StockData to a JSON-serializable dictionary."""
    base = stock_data_to_dict(stock_data)
    base.update({
        "vix_level": stock_data.vix_level,
        "gap_pct": stock_data.gap_pct,
        "earnings_surprise_pct": stock_data.earnings_surprise_pct,
        "analyst_revision_score": stock_data.analyst_revision_score,
    })
    return base


def dict_to_stock_data(data: dict) -> "StockData":
    """Convert dictionary back to StockData."""
    return StockData(
        symbol=data["symbol"],
        prices=data["prices"],
        volumes=data["volumes"],
        open_price=data["open_price"],
        pe_ratio=data.get("pe_ratio"),
        pb_ratio=data.get("pb_ratio"),
        dividend_yield=data.get("dividend_yield"),
        week_52_high=data.get("week_52_high"),
        week_52_low=data.get("week_52_low"),
        news_count_7d=data.get("news_count_7d", 0),
        news_sentiment=data.get("news_sentiment"),
        sector_avg_pe=data.get("sector_avg_pe", 25.0),
    )


def dict_to_v2_stock_data(data: dict) -> "V2StockData":
    """Convert dictionary back to V2StockData."""
    return V2StockData(
        symbol=data["symbol"],
        prices=data["prices"],
        volumes=data["volumes"],
        open_price=data["open_price"],
        pe_ratio=data.get("pe_ratio"),
        pb_ratio=data.get("pb_ratio"),
        dividend_yield=data.get("dividend_yield"),
        week_52_high=data.get("week_52_high"),
        week_52_low=data.get("week_52_low"),
        news_count_7d=data.get("news_count_7d", 0),
        news_sentiment=data.get("news_sentiment"),
        sector_avg_pe=data.get("sector_avg_pe", 25.0),
        vix_level=data.get("vix_level", 20.0),
        gap_pct=data.get("gap_pct"),
        earnings_surprise_pct=data.get("earnings_surprise_pct"),
        analyst_revision_score=data.get("analyst_revision_score"),
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
        logging.FileHandler(log_dir / f"scoring_{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"),
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
            from_timestamp=int((datetime.now(timezone.utc) - timedelta(days=60)).timestamp()),
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
            from_timestamp=int((datetime.now(timezone.utc) - timedelta(days=250)).timestamp()),
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
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        end_date = (datetime.now(timezone.utc) + timedelta(days=within_days)).strftime("%Y-%m-%d")

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


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Daily stock scoring batch job"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint if available",
    )
    return parser.parse_args()


def main():
    """Main scoring pipeline."""
    args = parse_args()

    # Track batch timing for monitoring
    batch_start_time = datetime.now(timezone.utc)
    batch_id = batch_start_time.strftime("%Y%m%d_%H%M%S")

    # Initialize judgment tracking variables
    total_successful_judgments = 0
    total_failed_judgments = 0

    logger.info("=" * 50)
    logger.info("Starting daily scoring batch")
    logger.info(f"Timestamp: {batch_start_time.isoformat()}")
    logger.info(f"Batch ID: {batch_id}")
    if args.resume:
        logger.info("Resume mode: enabled")
    logger.info("=" * 50)

    # Initialize clients
    try:
        finnhub = FinnhubClient()
        yf_client = get_yfinance_client()
        supabase = SupabaseClient()
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        sys.exit(1)

    # Track batch execution
    batch_ctx = BatchLogger.start(BatchType.MORNING_SCORING, model=config.llm.scoring_model)

    # 1. Determine market regime
    logger.info("Step 1: Determining market regime...")
    try:
        regime_data = fetch_market_regime_data(finnhub, yf_client)
    except DataFetchError as e:
        logger.error(f"FATAL: Cannot fetch market regime data: {e}")
        logger.error("Batch failed - no data sources available")
        BatchLogger.finish(batch_ctx, error=str(e))
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
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
        batch_ctx.metadata = {"market_regime": "crisis", "reason": "VIX too high"}
        BatchLogger.finish(batch_ctx)
        return

    # 2. Filter candidates
    logger.info("Step 2: Filtering candidates...")
    candidates = SP500_TOP_SYMBOLS.copy()
    candidates = filter_earnings(finnhub, candidates)
    logger.info(f"Candidates after filtering: {len(candidates)}")

    # 3. Fetch stock data (with checkpoint support)
    logger.info("Step 3: Fetching stock data...")

    # Initialize checkpoint
    checkpoint: BatchCheckpoint | None = None
    if args.resume:
        checkpoint = load_checkpoint(today)
        if checkpoint:
            logger.info(
                f"Resuming from checkpoint: {len(checkpoint.processed_symbols)} "
                f"symbols already processed (last updated: {checkpoint.last_updated})"
            )
        else:
            logger.info("No checkpoint found, starting fresh")

    # Create new checkpoint if needed
    if checkpoint is None:
        checkpoint = BatchCheckpoint(batch_date=today)

    v1_stocks_data = []
    v2_stocks_data = []
    failed_symbols = []
    restored_count = 0

    # First, restore data from checkpoint for already processed symbols
    if args.resume and checkpoint.v1_stock_data:
        for symbol in checkpoint.processed_symbols:
            if symbol in checkpoint.v1_stock_data and symbol in checkpoint.v2_stock_data:
                try:
                    v1_data = dict_to_stock_data(checkpoint.v1_stock_data[symbol])
                    v2_data = dict_to_v2_stock_data(checkpoint.v2_stock_data[symbol])
                    v1_stocks_data.append(v1_data)
                    v2_stocks_data.append(v2_data)
                    restored_count += 1
                except Exception as e:
                    logger.warning(f"Failed to restore {symbol} from checkpoint: {e}")
            elif symbol in checkpoint.failed_symbols:
                # Symbol was already marked as failed, skip it
                failed_symbols.append(symbol)

        if restored_count > 0:
            logger.info(f"Restored {restored_count} symbols from checkpoint")

    for symbol in candidates:
        # Skip already processed symbols (in resume mode)
        if symbol in checkpoint.processed_symbols:
            continue

        result = fetch_stock_data(finnhub, yf_client, symbol, regime_data["vix"])
        if result:
            v1_data, v2_data = result
            v1_stocks_data.append(v1_data)
            v2_stocks_data.append(v2_data)
            # Store in checkpoint
            checkpoint.v1_stock_data[symbol] = stock_data_to_dict(v1_data)
            checkpoint.v2_stock_data[symbol] = v2_stock_data_to_dict(v2_data)
        else:
            failed_symbols.append(symbol)
            checkpoint.failed_symbols.append(symbol)

        # Update checkpoint after each symbol
        checkpoint.processed_symbols.append(symbol)
        save_checkpoint(checkpoint)

        # Small delay to avoid rate limiting
        time.sleep(0.5)

    logger.info(f"Successfully fetched data for {len(v1_stocks_data)} stocks")
    if failed_symbols:
        logger.warning(f"Failed to fetch data for {len(failed_symbols)} symbols: {failed_symbols[:10]}...")

    # Ensure we have enough data to make recommendations
    MIN_STOCKS_REQUIRED = 10
    if len(v1_stocks_data) < MIN_STOCKS_REQUIRED:
        error_msg = f"Only {len(v1_stocks_data)} stocks with data (minimum {MIN_STOCKS_REQUIRED} required)"
        logger.error(f"FATAL: {error_msg}")
        logger.error("Batch failed - insufficient data for reliable recommendations")
        batch_ctx.failed_items = len(failed_symbols)
        batch_ctx.successful_items = len(v1_stocks_data)
        BatchLogger.finish(batch_ctx, error=error_msg)
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
        judgment_ctx = None  # Initialize to handle potential exceptions
        try:
            # Track LLM judgment separately
            judgment_ctx = BatchLogger.start(
                BatchType.LLM_JUDGMENT,
                model=config.llm.analysis_model
            )
            judgment_service = JudgmentService()

            # Get thresholds (use dynamic or fall back to config)
            v1_min_score = v1_threshold if v1_threshold is not None else config.strategy.v1_min_score
            v2_min_score = v2_threshold if v2_threshold is not None else config.strategy.v2_min_score

            # NEW LOGIC: Filter candidates by threshold (pass/fail) instead of top_n
            # This ensures all threshold-passed stocks get LLM evaluation
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
                finnhub=finnhub,
                supabase=supabase,
                candidates=v1_candidates,
                strategy_mode="conservative",
                market_regime=market_regime.regime.value,
                batch_date=today,
                top_n=None,  # Judge all threshold-passed candidates
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
                finnhub=finnhub,
                supabase=supabase,
                candidates=v2_candidates,
                strategy_mode="aggressive",
                market_regime=market_regime.regime.value,
                batch_date=today,
                top_n=None,  # Judge all threshold-passed candidates
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
            # Fall back to rule-based picks
            v1_final_picks = dual_result.v1_picks
            v2_final_picks = dual_result.v2_picks
    else:
        logger.info("LLM judgment disabled, using rule-based picks only")

    # 6. Save results for both strategies (with transaction-like error handling)
    logger.info("Step 6: Saving results...")

    # Helper to get price for a symbol
    def get_price(symbol: str) -> float:
        return next(
            (d.open_price for d in v1_stocks_data if d.symbol == symbol),
            0.0,
        )

    save_errors = []

    # Save V1 (Conservative) stock scores
    try:
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
        logger.info(f"Saved {len(v1_stock_scores)} V1 (conservative) stock scores")
    except Exception as e:
        error_msg = f"Failed to save V1 stock scores: {e}"
        logger.error(error_msg)
        save_errors.append(error_msg)

    # Save V2 (Aggressive) stock scores
    try:
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
        logger.info(f"Saved {len(v2_stock_scores)} V2 (aggressive) stock scores")
    except Exception as e:
        error_msg = f"Failed to save V2 stock scores: {e}"
        logger.error(error_msg)
        save_errors.append(error_msg)

    # Save daily picks with idempotency (batch save with existing record cleanup)
    # This ensures re-runs on the same day don't create duplicate records
    try:
        v1_pick = DailyPick(
            batch_date=today,
            symbols=v1_final_picks,
            pick_count=len(v1_final_picks),
            market_regime=market_regime.regime.value,
            strategy_mode="conservative",
            status="published",
        )
        v2_pick = DailyPick(
            batch_date=today,
            symbols=v2_final_picks,
            pick_count=len(v2_final_picks),
            market_regime=market_regime.regime.value,
            strategy_mode="aggressive",
            status="published",
        )

        # Use batch save for atomic-like behavior
        saved_picks, pick_errors = supabase.save_daily_picks_batch(
            [v1_pick, v2_pick],
            delete_existing=True,  # Idempotency: clean up before save
        )

        if pick_errors:
            for err in pick_errors:
                logger.error(err)
                save_errors.append(err)
        else:
            logger.info(f"Saved daily picks: V1={len(v1_final_picks)}, V2={len(v2_final_picks)}")

    except Exception as e:
        error_msg = f"Failed to save daily picks: {e}"
        logger.error(error_msg)
        save_errors.append(error_msg)

    # Check if any save operations failed
    if save_errors:
        logger.error(f"Save operation completed with {len(save_errors)} error(s)")
        batch_ctx.metadata = batch_ctx.metadata or {}
        batch_ctx.metadata["save_errors"] = save_errors

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
                from_timestamp=int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp()),
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

    # Record batch completion stats
    batch_ctx.successful_items = len(v1_stocks_data)
    batch_ctx.failed_items = len(failed_symbols)
    batch_ctx.total_items = len(candidates)
    batch_ctx.metadata = {
        "v1_picks": v1_final_picks,
        "v2_picks": v2_final_picks,
        "market_regime": market_regime.regime.value,
        "llm_judgment_enabled": use_llm_judgment,
    }

    # Finish batch logging
    BatchLogger.finish(batch_ctx)

    # Clear checkpoint on successful completion
    clear_checkpoint(today)

    # Record batch metrics for monitoring
    batch_end_time = datetime.now(timezone.utc)
    batch_metrics = BatchMetrics(
        batch_id=batch_id,
        start_time=batch_start_time,
        end_time=batch_end_time,
        total_symbols=len(candidates),
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
