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
                    if e.response.status_code in (429, 502, 503) and attempt < max_retries - 1:
                        sleep_time = base_sleep * (2 ** attempt)
                        logger.warning(f"HTTP {e.response.status_code}. Retrying in {sleep_time}s...")
                        time.sleep(sleep_time)
                    else:
                        raise
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.TimeoutException):
                    if attempt < max_retries - 1:
                        sleep_time = base_sleep * (2 ** attempt)
                        logger.warning(f"Connection/timeout error. Retrying in {sleep_time}s...")
                        time.sleep(sleep_time)
                    else:
                        raise
            raise RuntimeError(f"Failed after {max_retries} retries")
        return wrapper
    return decorator


class OpenAIClient(LLMClient):
    """OpenAI-compatible API client for arbitrary model endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
    ):
        self._base_url = (base_url or config.llm.openai_base_url).rstrip("/")
        self._api_key = api_key or config.llm.openai_api_key
        self._default_model = default_model or config.llm.openai_model
        if not self._default_model:
            raise ValueError(
                "Model must be specified either via parameter or OPENAI_MODEL env var. "
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

        content = data["choices"][0]["message"]["content"] or ""
        finish_reason = data["choices"][0].get("finish_reason", "")
        if finish_reason == "length":
            logger.warning(
                f"Response truncated (finish_reason=length, max_tokens={max_tokens}). "
                f"Model: {model_name}"
            )
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

    # Thinking level → generation parameters
    THINKING_PARAMS: dict[str, dict] = {
        "minimal": {"temperature": 0.7, "max_tokens": 4096, "system": ""},
        "low": {
            "temperature": 0.5,
            "max_tokens": 16384,
            "system": (
                "Think through this step-by-step before giving your final answer. "
                "Show your reasoning process, then provide the final output.\n\n"
            ),
        },
        "medium": {
            "temperature": 0.3,
            "max_tokens": 12288,
            "system": (
                "Analyze this problem carefully and thoroughly. Consider multiple angles, "
                "weigh the evidence for and against each conclusion, identify uncertainties, "
                "then present your well-reasoned final answer.\n\n"
            ),
        },
        "high": {
            "temperature": 0.2,
            "max_tokens": 16384,
            "system": (
                "This requires deep, rigorous analysis. Systematically examine all relevant factors, "
                "consider counterarguments, assess confidence levels for each claim, "
                "identify what you're uncertain about, and only then provide your final answer "
                "with explicit confidence ratings.\n\n"
            ),
        },
    }

    @retry_on_error(max_retries=3, base_sleep=2.0)
    def generate_with_thinking(
        self,
        prompt: str,
        model: str | None = None,
        thinking_level: str = "low",
    ) -> LLMResponse:
        """Generate with thinking mode.

        Maps thinking_level to appropriate temperature, max_tokens, and
        system prompt depth. For models that produce <think> tags natively
        (e.g. DeepSeek-R1), the tags are stripped from the final output.

        Args:
            prompt: The input prompt
            model: Model override
            thinking_level: "minimal", "low", "medium", "high"
        """
        model_name = model or self._default_model
        params = self.THINKING_PARAMS.get(thinking_level, self.THINKING_PARAMS["low"])

        messages: list[dict] = []
        if params["system"]:
            messages.append({"role": "system", "content": params["system"]})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": model_name,
            "messages": messages,
            "temperature": params["temperature"],
            "max_tokens": params["max_tokens"],
        }

        response = self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"] or ""

        # Warn if response was truncated by max_tokens
        finish_reason = data["choices"][0].get("finish_reason", "")
        if finish_reason == "length":
            logger.warning(
                f"Response truncated (finish_reason=length, max_tokens={params['max_tokens']}). "
                f"Model: {model_name}"
            )

        # Strip native <think> blocks (DeepSeek-R1, QwQ, etc.)
        content = self._strip_think_tags(content)

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

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        """Remove <think>...</think> blocks from model output.

        If stripping removes ALL content (e.g. DeepSeek-R1 wrapping entire
        response in think tags), fall back to the original text.
        """
        import re
        stripped = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()
        if not stripped and text.strip():
            logger.warning("_strip_think_tags removed all content, returning original")
            return text.strip()
        return stripped
