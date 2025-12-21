"""
AI Pick Daily - Configuration Management

Centralized configuration using environment variables.
"""
import os
from dataclasses import dataclass, field
from typing import Literal

from dotenv import load_dotenv

# Debug: Check env vars BEFORE load_dotenv
print("=== Config Debug: Before load_dotenv ===")
print(f"SUPABASE_URL: {bool(os.environ.get('SUPABASE_URL'))}")
print(f"SUPABASE_SERVICE_ROLE_KEY: {bool(os.environ.get('SUPABASE_SERVICE_ROLE_KEY'))}")

# Load environment variables from .env file (does NOT override existing vars)
load_dotenv(override=False)

# Debug: Check env vars AFTER load_dotenv
print("=== Config Debug: After load_dotenv ===")
print(f"SUPABASE_URL: {bool(os.environ.get('SUPABASE_URL'))}")
print(f"SUPABASE_SERVICE_ROLE_KEY: {bool(os.environ.get('SUPABASE_SERVICE_ROLE_KEY'))}")
print("========================================")


# Strategy mode types
StrategyMode = Literal["conservative", "aggressive", "both"]


@dataclass
class StrategyConfig:
    """Strategy-related configuration."""
    mode: StrategyMode = "both"  # Run both strategies by default

    # V1 Conservative weights
    v1_weights: dict = field(default_factory=lambda: {
        "trend": 0.35,
        "momentum": 0.35,
        "value": 0.20,
        "sentiment": 0.10,
    })

    # V2 Aggressive weights
    v2_weights: dict = field(default_factory=lambda: {
        "momentum_12_1": 0.40,
        "breakout": 0.25,
        "catalyst": 0.20,
        "risk_adjusted": 0.15,
    })

    # V1 settings
    v1_max_picks: int = 5
    v1_min_score: int = 60

    # V2 settings
    v2_max_picks: int = 3
    v2_min_score: int = 75
    v2_trailing_stop_pct: float = 0.08  # 8%


@dataclass
class LLMConfig:
    """LLM-related configuration."""
    provider: Literal["gemini", "claude"] = "gemini"
    scoring_model: str = "gemini-2.5-flash-lite"
    analysis_model: str = "gemini-3-flash"
    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None


@dataclass
class FinnhubConfig:
    """Finnhub API configuration."""
    api_key: str | None = None
    base_url: str = "https://finnhub.io/api/v1"


@dataclass
class SupabaseConfig:
    """Supabase configuration."""
    url: str | None = None
    anon_key: str | None = None
    service_role_key: str | None = None


@dataclass
class Config:
    """Main configuration class."""
    llm: LLMConfig
    finnhub: FinnhubConfig
    supabase: SupabaseConfig
    strategy: StrategyConfig
    debug: bool = False


def load_config() -> Config:
    """Load configuration from environment variables."""
    strategy_mode = os.getenv("STRATEGY_MODE", "both")
    if strategy_mode not in ("conservative", "aggressive", "both"):
        strategy_mode = "both"

    return Config(
        llm=LLMConfig(
            provider=os.getenv("LLM_PROVIDER", "gemini"),  # type: ignore
            scoring_model=os.getenv("SCORING_MODEL", "gemini-2.5-flash-lite"),
            analysis_model=os.getenv("ANALYSIS_MODEL", "gemini-3-flash"),
            gemini_api_key=os.getenv("GEMINI_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        ),
        finnhub=FinnhubConfig(
            api_key=os.getenv("FINNHUB_API_KEY"),
        ),
        supabase=SupabaseConfig(
            url=os.getenv("SUPABASE_URL"),
            anon_key=os.getenv("SUPABASE_ANON_KEY"),
            service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        ),
        strategy=StrategyConfig(
            mode=strategy_mode,  # type: ignore
        ),
        debug=os.getenv("DEBUG", "false").lower() == "true",
    )


# Global config instance
config = load_config()
