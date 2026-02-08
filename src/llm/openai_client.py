"""
OpenAI-Compatible API Client

Implements LLMClient interface for any OpenAI-compatible endpoint:
- vLLM
- Ollama (with OpenAI compatibility layer)
- Together AI
- Fireworks AI
- Any other OpenAI API-compatible server

Enables testing arbitrary OSS models (Llama, Qwen, Mistral, etc.)
without code changes — just set OPENAI_BASE_URL, OPENAI_API_KEY,
and OPENAI_MODEL environment variables.
"""
import json
import logging
import time
from functools import wraps
from typing import Callable

import httpx

from src.config import config
from .client import LLMClient, LLMResponse


logger = logging.getLogger(__name__)


def retry_on_error(max_retries: int = 3, base_sleep: float = 2.0):
    """Retry decorator with exponential backoff for transient errors."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < max_retries - 1:
                        sleep_time = base_sleep * (2 ** attempt)
                        logger.warning(f"Rate limited. Retrying in {sleep_time}s...")
                        time.sleep(sleep_time)
                    else:
                        raise
                except httpx.ConnectError:
                    if attempt < max_retries - 1:
                        sleep_time = base_sleep * (2 ** attempt)
                        logger.warning(f"Connection failed. Retrying in {sleep_time}s...")
                        time.sleep(sleep_time)
                    else:
                        raise
            raise RuntimeError(f"Failed after {max_retries} retries")
        return wrapper
    return decorator


class OpenAIClient(LLMClient):
    """OpenAI-compatible API client for arbitrary model endpoints."""

    def __init__(self):
        self._base_url = config.llm.openai_base_url.rstrip("/")
        self._api_key = config.llm.openai_api_key
        self._default_model = config.llm.openai_model
        if not self._default_model:
            raise ValueError(
                "OPENAI_MODEL must be set when using openai provider. "
                "Example: meta-llama/Llama-3.3-70B-Instruct"
            )
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )
        logger.info(
            f"OpenAI client initialized: {self._base_url}, model={self._default_model}"
        )

    @retry_on_error(max_retries=3, base_sleep=2.0)
    def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        model_name = model or self._default_model

        payload: dict = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        response = self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage_data = data.get("usage")
        usage = None
        if usage_data:
            usage = {
                "prompt_tokens": usage_data.get("prompt_tokens", 0),
                "completion_tokens": usage_data.get("completion_tokens", 0),
                "total_tokens": usage_data.get("total_tokens", 0),
            }

        return LLMResponse(
            content=content,
            model=data.get("model", model_name),
            usage=usage,
            raw_response=data,
        )

    @retry_on_error(max_retries=3, base_sleep=2.0)
    def generate_with_thinking(
        self,
        prompt: str,
        model: str | None = None,
        thinking_level: str = "low",
    ) -> LLMResponse:
        """Generate with thinking — falls back to standard generation.

        Most OSS models don't have a native thinking mode, so we simulate it
        by prepending a think-step-by-step instruction to the prompt.
        """
        model_name = model or self._default_model

        thinking_instruction = (
            "Think through this step-by-step before giving your final answer. "
            "Show your reasoning process, then provide the final output.\n\n"
        )

        payload: dict = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": thinking_instruction},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 8192,
        }

        response = self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage_data = data.get("usage")
        usage = None
        if usage_data:
            usage = {
                "prompt_tokens": usage_data.get("prompt_tokens", 0),
                "completion_tokens": usage_data.get("completion_tokens", 0),
                "total_tokens": usage_data.get("total_tokens", 0),
            }

        return LLMResponse(
            content=content,
            model=data.get("model", model_name),
            usage=usage,
            raw_response=data,
        )
