"""
Claude API Client (Stub)

Placeholder for future Claude API implementation.
Implements LLMClient interface for Anthropic Claude API.
"""
from .client import LLMClient, LLMResponse
from src.config import config


class ClaudeClient(LLMClient):
    """
    Claude API client implementation.

    This is a placeholder for future implementation when migrating to Claude.
    """

    def __init__(self):
        """Initialize the Claude client."""
        api_key = config.llm.anthropic_api_key
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set in environment variables")

        # TODO: Initialize Anthropic client
        # from anthropic import Anthropic
        # self._client = Anthropic(api_key=api_key)
        raise NotImplementedError(
            "Claude client is not yet implemented. "
            "Set LLM_PROVIDER=gemini in your environment variables."
        )

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Generate a response using Claude API."""
        raise NotImplementedError("Claude client is not yet implemented")

    def generate_with_thinking(
        self,
        prompt: str,
        model: str | None = None,
        thinking_level: str = "low",
    ) -> LLMResponse:
        """Generate a response using Claude's extended thinking."""
        raise NotImplementedError("Claude client is not yet implemented")
