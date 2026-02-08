"""Tests for LLM client routing and OpenAI client thinking mode."""

import re
import pytest
from unittest.mock import patch, MagicMock

from src.llm.client import get_llm_client_for_model
from src.llm.openai_client import OpenAIClient


# ─── get_llm_client_for_model tests ──────────────────────────


class TestGetLLMClientForModel:
    """Test model-name-based client routing."""

    @patch("src.llm.client.config")
    def test_openrouter_model_returns_openai_client(self, mock_config):
        """Models with '/' that aren't Gemini should route to OpenRouter."""
        mock_config.llm.openrouter_base_url = "https://openrouter.ai/api/v1"
        mock_config.llm.openrouter_api_key = "test-key"
        mock_config.llm.openai_model = ""

        client = get_llm_client_for_model("moonshotai/kimi-k2.5")

        assert isinstance(client, OpenAIClient)
        assert client._default_model == "moonshotai/kimi-k2.5"
        assert client._base_url == "https://openrouter.ai/api/v1"

    @patch("src.llm.client.config")
    def test_openrouter_model_with_free_suffix(self, mock_config):
        """Free-tier models with ':free' suffix should still route to OpenRouter."""
        mock_config.llm.openrouter_base_url = "https://openrouter.ai/api/v1"
        mock_config.llm.openrouter_api_key = "test-key"
        mock_config.llm.openai_model = ""

        client = get_llm_client_for_model("openai/gpt-oss-120b:free")

        assert isinstance(client, OpenAIClient)
        assert client._default_model == "openai/gpt-oss-120b:free"

    @patch("src.llm.client.config")
    def test_gemini_model_returns_default_provider(self, mock_config):
        """Gemini models should NOT route to OpenRouter."""
        mock_config.llm.provider = "gemini"
        mock_config.llm.gemini_api_key = "test-key"

        # Should call get_llm_client() which returns GeminiClient
        with patch("src.llm.client.get_llm_client") as mock_get:
            mock_get.return_value = MagicMock()
            client = get_llm_client_for_model("gemini-3-flash-preview")
            mock_get.assert_called_once()

    @patch("src.llm.client.config")
    def test_none_model_returns_default_provider(self, mock_config):
        """None model should return default provider client."""
        with patch("src.llm.client.get_llm_client") as mock_get:
            mock_get.return_value = MagicMock()
            client = get_llm_client_for_model(None)
            mock_get.assert_called_once()

    @patch("src.llm.client.config")
    def test_plain_model_name_returns_default_provider(self, mock_config):
        """Model names without '/' should return default provider."""
        with patch("src.llm.client.get_llm_client") as mock_get:
            mock_get.return_value = MagicMock()
            client = get_llm_client_for_model("gemini-2.5-flash-lite")
            mock_get.assert_called_once()

    @patch("src.llm.client.config")
    def test_various_openrouter_models(self, mock_config):
        """Various OpenRouter model formats should all be detected."""
        mock_config.llm.openrouter_base_url = "https://openrouter.ai/api/v1"
        mock_config.llm.openrouter_api_key = "test-key"
        mock_config.llm.openai_model = ""

        models = [
            "deepseek/deepseek-r1-0528:free",
            "qwen/qwen3-235b-a22b-2507",
            "x-ai/grok-4.1-fast",
            "meta-llama/llama-3.3-70b-instruct",
            "anthropic/claude-sonnet-4",
            "stepfun/step-3.5-flash:free",
        ]
        for model in models:
            client = get_llm_client_for_model(model)
            assert isinstance(client, OpenAIClient), f"Failed for {model}"
            assert client._default_model == model

    @patch("src.llm.client.config")
    def test_google_openrouter_model_still_routes_openrouter(self, mock_config):
        """google/gemini-2.5-flash via OpenRouter should route to OpenRouter
        (starts with 'google/', not 'gemini')."""
        mock_config.llm.openrouter_base_url = "https://openrouter.ai/api/v1"
        mock_config.llm.openrouter_api_key = "test-key"
        mock_config.llm.openai_model = ""

        client = get_llm_client_for_model("google/gemini-2.5-flash")
        assert isinstance(client, OpenAIClient)


# ─── OpenAIClient._strip_think_tags tests ────────────────────


class TestStripThinkTags:
    """Test stripping of native <think> blocks."""

    def test_strips_think_block(self):
        text = "<think>reasoning here</think>\nFinal answer"
        assert OpenAIClient._strip_think_tags(text) == "Final answer"

    def test_strips_multiline_think(self):
        text = "<think>\nStep 1: ...\nStep 2: ...\n</think>\n\nThe answer is 42."
        assert OpenAIClient._strip_think_tags(text) == "The answer is 42."

    def test_no_think_tags_unchanged(self):
        text = "Just a normal response"
        assert OpenAIClient._strip_think_tags(text) == "Just a normal response"

    def test_empty_think_block(self):
        text = "<think></think>Result"
        assert OpenAIClient._strip_think_tags(text) == "Result"

    def test_multiple_think_blocks(self):
        text = "<think>first</think>A<think>second</think>B"
        assert OpenAIClient._strip_think_tags(text) == "AB"


# ─── OpenAIClient.generate_with_thinking parameter tests ─────


class TestGenerateWithThinkingParams:
    """Test that thinking_level maps to correct parameters."""

    def test_thinking_params_keys(self):
        """All expected levels should be defined."""
        assert set(OpenAIClient.THINKING_PARAMS.keys()) == {
            "minimal", "low", "medium", "high"
        }

    def test_minimal_has_no_system_prompt(self):
        params = OpenAIClient.THINKING_PARAMS["minimal"]
        assert params["system"] == ""

    def test_temperature_decreases_with_depth(self):
        temps = [
            OpenAIClient.THINKING_PARAMS[level]["temperature"]
            for level in ["minimal", "low", "medium", "high"]
        ]
        assert temps == sorted(temps, reverse=True)

    def test_max_tokens_increases_with_depth(self):
        tokens = [
            OpenAIClient.THINKING_PARAMS[level]["max_tokens"]
            for level in ["minimal", "low", "medium", "high"]
        ]
        assert tokens == sorted(tokens)

    @patch.object(OpenAIClient, "__init__", lambda self, **kw: None)
    def test_minimal_sends_no_system_message(self):
        """thinking_level='minimal' should not include a system message."""
        client = OpenAIClient()
        client._default_model = "test-model"
        client._client = MagicMock()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "answer"}}],
            "model": "test-model",
        }
        mock_response.raise_for_status = MagicMock()
        client._client.post.return_value = mock_response

        client.generate_with_thinking("prompt", thinking_level="minimal")

        call_args = client._client.post.call_args
        payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
        messages = payload["messages"]
        # No system message for minimal
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    @patch.object(OpenAIClient, "__init__", lambda self, **kw: None)
    def test_high_sends_system_message(self):
        """thinking_level='high' should include system message."""
        client = OpenAIClient()
        client._default_model = "test-model"
        client._client = MagicMock()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "answer"}}],
            "model": "test-model",
        }
        mock_response.raise_for_status = MagicMock()
        client._client.post.return_value = mock_response

        client.generate_with_thinking("prompt", thinking_level="high")

        call_args = client._client.post.call_args
        payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
        messages = payload["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "rigorous" in messages[0]["content"].lower()
        assert payload["temperature"] == 0.2
        assert payload["max_tokens"] == 16384

    @patch.object(OpenAIClient, "__init__", lambda self, **kw: None)
    def test_think_tags_stripped_from_response(self):
        """<think> tags in model output should be stripped."""
        client = OpenAIClient()
        client._default_model = "deepseek/deepseek-r1"
        client._client = MagicMock()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "<think>reasoning</think>\nFinal answer"}}],
            "model": "deepseek/deepseek-r1",
        }
        mock_response.raise_for_status = MagicMock()
        client._client.post.return_value = mock_response

        result = client.generate_with_thinking("prompt", thinking_level="low")
        assert result.content == "Final answer"
        assert "<think>" not in result.content

    @patch.object(OpenAIClient, "__init__", lambda self, **kw: None)
    def test_unknown_level_falls_back_to_low(self):
        """Unknown thinking_level should fall back to 'low' params."""
        client = OpenAIClient()
        client._default_model = "test-model"
        client._client = MagicMock()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "answer"}}],
            "model": "test-model",
        }
        mock_response.raise_for_status = MagicMock()
        client._client.post.return_value = mock_response

        client.generate_with_thinking("prompt", thinking_level="unknown_level")

        call_args = client._client.post.call_args
        payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
        # Should use low's params as fallback
        assert payload["temperature"] == 0.5
        assert payload["max_tokens"] == 8192
