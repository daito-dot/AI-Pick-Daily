"""
AI Pick Daily - Configuration Management

Centralized configuration using environment variables.
"""
import os
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


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
    debug: bool = False


def load_config() -> Config:
    """Load configuration from environment variables."""
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
        debug=os.getenv("DEBUG", "false").lower() == "true",
    )


# Global config instance
config = load_config()
