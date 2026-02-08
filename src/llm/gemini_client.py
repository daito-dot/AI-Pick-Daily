"""
Gemini API Client

Implements LLMClient interface for Google Gemini API.
Supports:
- Standard generation
- Thinking mode (Gemini 3 Flash)
"""
import logging
import time
from functools import wraps
from typing import Any, Callable

import google.generativeai as genai

from src.config import config
from .client import LLMClient, LLMResponse


logger = logging.getLogger(__name__)


def rate_limit_aware(max_retries: int = 3, base_sleep: float = 2.0):
    """
    Decorator for handling Gemini API rate limits with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_sleep: Base sleep time in seconds (doubles each retry)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e).lower()
                    if "429" in error_str or "resource_exhausted" in error_str or "quota" in error_str:
                        if attempt < max_retries - 1:
                            sleep_time = base_sleep * (2 ** attempt)
                            print(f"Rate limited. Sleeping {sleep_time}s before retry {attempt + 1}")
                            time.sleep(sleep_time)
                        else:
                            raise
                    else:
                        raise
            raise Exception(f"Failed after {max_retries} retries")
        return wrapper
    return decorator


class GeminiClient(LLMClient):
    """Gemini API client implementation."""

    def __init__(self):
        """Initialize the Gemini client with API key from config."""
        api_key = config.llm.gemini_api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment variables")

        genai.configure(api_key=api_key)
        self._scoring_model = config.llm.scoring_model
        self._analysis_model = config.llm.analysis_model

    @rate_limit_aware(max_retries=3, base_sleep=2.0)
    def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Generate a response using Gemini API.

        Args:
            prompt: The input prompt
            model: Model to use (defaults to scoring_model)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            json_mode: If True, request JSON-formatted output

        Returns:
            LLMResponse with the generated content
        """
        model_name = model or self._scoring_model
        gemini_model = genai.GenerativeModel(model_name)

        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }

        if json_mode:
            generation_config["response_mime_type"] = "application/json"

        response = gemini_model.generate_content(
            prompt,
            generation_config=generation_config,
        )

        # Extract usage info if available
        usage = None
        if hasattr(response, "usage_metadata"):
            usage = {
                "prompt_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
                "completion_tokens": getattr(response.usage_metadata, "candidates_token_count", 0),
                "total_tokens": getattr(response.usage_metadata, "total_token_count", 0),
            }

        return LLMResponse(
            content=response.text,
            model=model_name,
            usage=usage,
            raw_response=response,
        )

    @rate_limit_aware(max_retries=3, base_sleep=2.0)
    def generate_with_thinking(
        self,
        prompt: str,
        model: str | None = None,
        thinking_level: str = "low",
    ) -> LLMResponse:
        """
        Generate a response using Gemini's thinking mode.

        For Gemini 3 models, uses thinking_level parameter via new SDK.
        Falls back to regular generation for unsupported models.

        Args:
            prompt: The input prompt
            model: Model to use (defaults to analysis_model)
            thinking_level: Thinking depth - "minimal", "low", "medium", "high"
                           (minimal/medium only for Gemini 3 Flash)

        Returns:
            LLMResponse with the generated content
        """
        model_name = model or self._analysis_model

        # Use new SDK for Gemini 3 models with thinking_level support
        if "gemini-3" in model_name:
            return self._generate_with_thinking_new_sdk(prompt, model_name, thinking_level)

        # Fall back to old SDK for other models
        return self._generate_with_thinking_old_sdk(prompt, model_name)

    def _generate_with_thinking_new_sdk(
        self,
        prompt: str,
        model_name: str,
        thinking_level: str,
    ) -> LLMResponse:
        """Use new google.genai SDK for Gemini 3 thinking mode."""
        try:
            from google import genai as genai_new
            from google.genai import types
        except ImportError:
            logger.warning("google-genai not installed, falling back to regular generation")
            return self._generate_with_thinking_old_sdk(prompt, model_name)

        api_key = config.llm.gemini_api_key
        client = genai_new.Client(api_key=api_key)

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
                    temperature=0.7,
                    max_output_tokens=8192,
                ),
            )

            usage = None
            if hasattr(response, "usage_metadata"):
                usage = {
                    "prompt_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
                    "completion_tokens": getattr(response.usage_metadata, "candidates_token_count", 0),
                    "total_tokens": getattr(response.usage_metadata, "total_token_count", 0),
                }

            return LLMResponse(
                content=response.text,
                model=model_name,
                usage=usage,
                raw_response=response,
            )
        except Exception as e:
            logger.warning(f"Thinking mode failed for {model_name}: {e}, falling back")
            return self._generate_with_thinking_old_sdk(prompt, model_name)

    def _generate_with_thinking_old_sdk(
        self,
        prompt: str,
        model_name: str,
    ) -> LLMResponse:
        """Fall back to regular generation using old SDK."""
        gemini_model = genai.GenerativeModel(model_name)

        generation_config = {
            "temperature": 0.7,
            "max_output_tokens": 8192,
        }

        response = gemini_model.generate_content(
            prompt,
            generation_config=generation_config,
        )

        usage = None
        if hasattr(response, "usage_metadata"):
            usage = {
                "prompt_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
                "completion_tokens": getattr(response.usage_metadata, "candidates_token_count", 0),
                "total_tokens": getattr(response.usage_metadata, "total_token_count", 0),
            }

        return LLMResponse(
            content=response.text,
            model=model_name,
            usage=usage,
            raw_response=response,
        )

    def generate_json(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """
        Convenience method for generating JSON output.

        Uses lower temperature for more deterministic output.

        Args:
            prompt: The input prompt (should request JSON format)
            model: Model to use
            temperature: Sampling temperature (default 0.3 for consistency)

        Returns:
            LLMResponse with JSON content
        """
        return self.generate(
            prompt=prompt,
            model=model,
            temperature=temperature,
            json_mode=True,
        )

