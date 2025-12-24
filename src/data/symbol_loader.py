"""
Symbol Loader Module

Provides a unified interface to load stock symbols from multiple sources:
1. YAML configuration file (primary)
2. Supabase database (secondary)
3. Hardcoded defaults (fallback)

Usage:
    loader = SymbolLoader()
    us_symbols = loader.get_symbols(market="us")
    jp_symbols = loader.get_symbols(market="jp")
    all_symbols = loader.get_symbols()  # All enabled markets
"""
import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


logger = logging.getLogger(__name__)


# Default symbols as final fallback (subset of S&P 500 top holdings)
DEFAULT_US_SYMBOLS = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK.B", "UNH", "JNJ",
    "V", "XOM", "JPM", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "LLY",
    "PEP", "KO", "COST", "AVGO", "MCD", "WMT", "CSCO", "TMO", "ABT", "CRM",
    "DHR", "ACN", "NKE", "LIN", "ADBE", "ORCL", "TXN", "NEE", "PM", "VZ",
    "CMCSA", "RTX", "HON", "INTC", "UPS", "LOW", "MS", "QCOM", "SPGI", "BA",
]

DEFAULT_JP_SYMBOLS = [
    "7203.T", "6758.T", "8306.T", "9984.T", "9432.T",
    "8035.T", "6861.T", "7267.T", "6501.T", "8058.T",
]


@dataclass
class SymbolConfig:
    """Configuration for a market's symbol list."""

    market: str
    enabled: bool
    symbols: list[str]
    description: str = ""


@dataclass
class SymbolSettings:
    """Global settings for symbol loading."""

    max_symbols_per_batch: int = 100
    rate_limit_delay_ms: int = 500
    exclude_patterns: list[str] = field(default_factory=list)
    min_symbol_length: int = 1
    max_symbol_length: int = 10
    allow_japanese_tickers: bool = True


class SymbolLoader:
    """
    Unified symbol loader with multiple data sources.

    Priority order:
    1. YAML file (config/symbols.yaml)
    2. Supabase database (stock_universe table)
    3. Hardcoded defaults

    Example:
        loader = SymbolLoader()
        symbols = loader.get_symbols(market="us")
    """

    def __init__(
        self,
        yaml_path: str | Path | None = None,
        supabase_client: Any | None = None,
    ):
        """
        Initialize the symbol loader.

        Args:
            yaml_path: Path to symbols.yaml file. If None, uses default path.
            supabase_client: Optional SupabaseClient instance for DB loading.
        """
        # Default YAML path
        if yaml_path is None:
            yaml_path = Path(__file__).parent.parent.parent / "config" / "symbols.yaml"
        self.yaml_path = Path(yaml_path)

        self.supabase = supabase_client
        self._cache: dict[str, SymbolConfig] = {}
        self._settings: SymbolSettings | None = None
        self._loaded_from: str = ""

    def load_from_yaml(self) -> dict[str, SymbolConfig]:
        """
        Load symbols from YAML configuration file.

        Returns:
            Dict mapping market names to SymbolConfig objects.

        Raises:
            FileNotFoundError: If YAML file doesn't exist.
            yaml.YAMLError: If YAML parsing fails.
        """
        if not self.yaml_path.exists():
            raise FileNotFoundError(f"Symbols YAML not found: {self.yaml_path}")

        logger.info(f"Loading symbols from YAML: {self.yaml_path}")

        with open(self.yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        configs: dict[str, SymbolConfig] = {}

        # Load US stocks
        if "us_stocks" in data:
            us_data = data["us_stocks"]
            configs["us"] = SymbolConfig(
                market="us",
                enabled=us_data.get("enabled", True),
                symbols=us_data.get("symbols", []),
                description=us_data.get("description", ""),
            )

        # Load JP stocks
        if "jp_stocks" in data:
            jp_data = data["jp_stocks"]
            configs["jp"] = SymbolConfig(
                market="jp",
                enabled=jp_data.get("enabled", True),
                symbols=jp_data.get("symbols", []),
                description=jp_data.get("description", ""),
            )

        # Load settings
        if "settings" in data:
            settings_data = data["settings"]
            validation = settings_data.get("validation", {})
            self._settings = SymbolSettings(
                max_symbols_per_batch=settings_data.get("max_symbols_per_batch", 100),
                rate_limit_delay_ms=settings_data.get("rate_limit_delay_ms", 500),
                exclude_patterns=settings_data.get("exclude_patterns", []),
                min_symbol_length=validation.get("min_symbol_length", 1),
                max_symbol_length=validation.get("max_symbol_length", 10),
                allow_japanese_tickers=validation.get("allow_japanese_tickers", True),
            )

        self._loaded_from = "yaml"
        return configs

    def load_from_db(self) -> dict[str, SymbolConfig]:
        """
        Load symbols from Supabase database (stock_universe table).

        Returns:
            Dict mapping market names to SymbolConfig objects.

        Raises:
            RuntimeError: If database client is not configured.
        """
        if self.supabase is None:
            raise RuntimeError("Supabase client not configured")

        logger.info("Loading symbols from database (stock_universe table)")

        configs: dict[str, SymbolConfig] = {}

        try:
            # Load US stocks
            us_symbols = self.supabase.get_stock_universe(market_type="us")
            if us_symbols:
                configs["us"] = SymbolConfig(
                    market="us",
                    enabled=True,
                    symbols=[s["symbol"] for s in us_symbols if s.get("enabled", True)],
                    description="Loaded from database",
                )

            # Load JP stocks
            jp_symbols = self.supabase.get_stock_universe(market_type="jp")
            if jp_symbols:
                configs["jp"] = SymbolConfig(
                    market="jp",
                    enabled=True,
                    symbols=[s["symbol"] for s in jp_symbols if s.get("enabled", True)],
                    description="Loaded from database",
                )

            self._loaded_from = "db"
            return configs

        except Exception as e:
            logger.warning(f"Failed to load symbols from database: {e}")
            raise

    def load_defaults(self) -> dict[str, SymbolConfig]:
        """
        Load hardcoded default symbols.

        Returns:
            Dict mapping market names to SymbolConfig objects.
        """
        logger.info("Loading default hardcoded symbols")

        self._loaded_from = "default"
        return {
            "us": SymbolConfig(
                market="us",
                enabled=True,
                symbols=DEFAULT_US_SYMBOLS.copy(),
                description="Hardcoded defaults",
            ),
            "jp": SymbolConfig(
                market="jp",
                enabled=True,
                symbols=DEFAULT_JP_SYMBOLS.copy(),
                description="Hardcoded defaults",
            ),
        }

    def load(self, source: str = "auto") -> dict[str, SymbolConfig]:
        """
        Load symbols from specified source with fallback chain.

        Args:
            source: Source to load from:
                - "yaml": Load from YAML file only
                - "db": Load from database only
                - "default": Load hardcoded defaults only
                - "auto": Try YAML -> DB -> default (with fallback)

        Returns:
            Dict mapping market names to SymbolConfig objects.
        """
        if source == "yaml":
            self._cache = self.load_from_yaml()
        elif source == "db":
            self._cache = self.load_from_db()
        elif source == "default":
            self._cache = self.load_defaults()
        elif source == "auto":
            # Fallback chain: YAML -> DB -> Default
            try:
                self._cache = self.load_from_yaml()
                logger.info(f"Loaded symbols from YAML: {self._symbol_count_summary()}")
            except FileNotFoundError:
                logger.warning("YAML not found, trying database...")
                try:
                    self._cache = self.load_from_db()
                    logger.info(f"Loaded symbols from DB: {self._symbol_count_summary()}")
                except Exception as e:
                    logger.warning(f"DB load failed ({e}), using defaults...")
                    self._cache = self.load_defaults()
                    logger.info(f"Loaded default symbols: {self._symbol_count_summary()}")
            except Exception as e:
                logger.warning(f"YAML load failed ({e}), trying database...")
                try:
                    self._cache = self.load_from_db()
                    logger.info(f"Loaded symbols from DB: {self._symbol_count_summary()}")
                except Exception:
                    logger.warning("DB load also failed, using defaults...")
                    self._cache = self.load_defaults()
                    logger.info(f"Loaded default symbols: {self._symbol_count_summary()}")
        else:
            raise ValueError(f"Invalid source: {source}. Use 'yaml', 'db', 'default', or 'auto'")

        return self._cache

    def _symbol_count_summary(self) -> str:
        """Get a summary of loaded symbol counts."""
        parts = []
        for market, config in self._cache.items():
            if config.enabled:
                parts.append(f"{market.upper()}={len(config.symbols)}")
        return ", ".join(parts) if parts else "none"

    def get_symbols(
        self,
        market: str | None = None,
        source: str = "auto",
    ) -> list[str]:
        """
        Get symbols for specified market(s).

        Args:
            market: Market to get symbols for:
                - "us": US stocks only
                - "jp": Japanese stocks only
                - None: All enabled markets combined

            source: Source to load from (see load() for options).

        Returns:
            List of symbol strings.
        """
        # Load if cache is empty
        if not self._cache:
            self.load(source=source)

        symbols: list[str] = []

        if market:
            # Single market
            market_lower = market.lower()
            if market_lower in self._cache:
                config = self._cache[market_lower]
                if config.enabled:
                    symbols = config.symbols.copy()
        else:
            # All enabled markets
            for config in self._cache.values():
                if config.enabled:
                    symbols.extend(config.symbols)

        # Apply filtering
        symbols = self._filter_symbols(symbols)

        return symbols

    def _filter_symbols(self, symbols: list[str]) -> list[str]:
        """Apply exclude patterns and validation to symbol list."""
        if not self._settings:
            return symbols

        filtered = []
        for symbol in symbols:
            # Length validation
            if not (self._settings.min_symbol_length <= len(symbol) <= self._settings.max_symbol_length):
                continue

            # Exclude pattern matching
            excluded = False
            for pattern in self._settings.exclude_patterns:
                if fnmatch.fnmatch(symbol, pattern):
                    excluded = True
                    break

            if not excluded:
                filtered.append(symbol)

        return filtered

    def get_settings(self) -> SymbolSettings:
        """
        Get symbol loading settings.

        Returns:
            SymbolSettings object with current settings.
        """
        if not self._settings:
            # Load to populate settings
            self.load()

        return self._settings or SymbolSettings()

    @property
    def loaded_from(self) -> str:
        """Get the source from which symbols were loaded."""
        return self._loaded_from

    def reload(self, source: str = "auto") -> dict[str, SymbolConfig]:
        """
        Force reload symbols from source.

        Args:
            source: Source to load from.

        Returns:
            Dict mapping market names to SymbolConfig objects.
        """
        self._cache = {}
        self._settings = None
        return self.load(source=source)

    def get_market_config(self, market: str) -> SymbolConfig | None:
        """
        Get configuration for a specific market.

        Args:
            market: Market name ("us" or "jp").

        Returns:
            SymbolConfig for the market, or None if not found.
        """
        if not self._cache:
            self.load()

        return self._cache.get(market.lower())

    def is_market_enabled(self, market: str) -> bool:
        """
        Check if a market is enabled.

        Args:
            market: Market name.

        Returns:
            True if market is enabled, False otherwise.
        """
        config = self.get_market_config(market)
        return config.enabled if config else False


# Convenience function for simple usage
def get_symbols(
    market: str | None = None,
    source: str = "auto",
    supabase_client: Any | None = None,
) -> list[str]:
    """
    Convenience function to get symbols.

    Args:
        market: Market to get symbols for ("us", "jp", or None for all).
        source: Source to load from ("yaml", "db", "default", or "auto").
        supabase_client: Optional Supabase client for DB loading.

    Returns:
        List of symbol strings.

    Example:
        symbols = get_symbols(market="us")
    """
    loader = SymbolLoader(supabase_client=supabase_client)
    return loader.get_symbols(market=market, source=source)
