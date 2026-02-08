"""
LLM Client Abstraction Layer

Provides a unified interface for different LLM providers (Gemini, Claude).
Allows easy switching between providers via environment variables.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from src.config import config


@dataclass
class LLMResponse:
    """Standardized response from LLM."""
    content: str
    model: str
    usage: dict[str, int] | None = None
    raw_response: Any = None


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Generate a response from the LLM.

        Args:
            prompt: The input prompt
            model: Model to use (defaults to scoring_model from config)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens in response
            json_mode: If True, request JSON-formatted output

        Returns:
            LLMResponse with the generated content
        """
        pass

    @abstractmethod
    def generate_with_thinking(
        self,
        prompt: str,
        model: str | None = None,
        thinking_level: str = "low",
    ) -> LLMResponse:
        """
        Generate a response using thinking/reasoning mode.

        Args:
            prompt: The input prompt
            model: Model to use (defaults to analysis_model from config)
            thinking_level: Thinking depth - "minimal", "low", "medium", "high"

        Returns:
            LLMResponse with the generated content
        """
        pass


def get_llm_client() -> LLMClient:
    """
    Factory function to get the appropriate LLM client based on configuration.

    Returns:
        LLMClient instance (GeminiClient or ClaudeClient)

    Raises:
        ValueError: If provider is not supported
    """
    provider = config.llm.provider

    if provider == "gemini":
        from .gemini_client import GeminiClient
        return GeminiClient()
    elif provider == "claude":
        from .claude_client import ClaudeClient
        return ClaudeClient()
    elif provider == "openai":
        from .openai_client import OpenAIClient
        return OpenAIClient()
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def get_llm_client_for_model(model_name: str | None = None) -> LLMClient:
    """
    Get an LLM client appropriate for the given model name.

    If the model name looks like an OpenRouter model (contains '/' and is not
    a Gemini model), returns an OpenAIClient pointed at OpenRouter.
    Otherwise, returns the default provider client.

    Args:
        model_name: Model identifier (e.g. 'moonshotai/kimi-k2.5', 'gemini-3-pro-preview')

    Returns:
        LLMClient instance
    """
    if model_name and "/" in model_name and not model_name.startswith("gemini"):
        from .openai_client import OpenAIClient
        return OpenAIClient(
            base_url=config.llm.openrouter_base_url,
            api_key=config.llm.openrouter_api_key,
            default_model=model_name,
        )
    return get_llm_client()
