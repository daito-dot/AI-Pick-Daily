"""
Tests for judgment service response parsing.

Covers:
- Portfolio judgment response parsing
- Exit judgment response parsing
- JSON extraction from markdown code blocks
- Error handling for invalid responses
"""
import pytest
import json
from unittest.mock import MagicMock, patch

from src.judgment.models import (
    PortfolioJudgmentOutput,
    StockAllocation,
    ExitJudgmentOutput,
)


def _make_service():
    """Create JudgmentService with mocked config and LLM client."""
    mock_llm = MagicMock()
    mock_config = MagicMock()
    mock_config.llm.analysis_model = "test-model"
    with patch("src.judgment.service.config", mock_config):
        from src.judgment.service import JudgmentService
        return JudgmentService(llm_client=mock_llm)


class TestParsePortfolioResponse:
    """Tests for _parse_portfolio_response."""

    def test_parses_valid_json(self):
        service = _make_service()
        response = json.dumps({
            "recommended_buys": [
                {
                    "symbol": "AAPL",
                    "action": "buy",
                    "conviction": 0.85,
                    "allocation_hint": "high",
                    "reasoning": "Strong momentum",
                }
            ],
            "skipped": [
                {
                    "symbol": "MSFT",
                    "action": "skip",
                    "conviction": 0.3,
                    "allocation_hint": "normal",
                    "reasoning": "Overvalued",
                }
            ],
            "portfolio_reasoning": "Focus on tech momentum",
            "risk_assessment": "Sector concentration risk",
        })

        result = service._parse_portfolio_response(response)
        assert isinstance(result, PortfolioJudgmentOutput)
        assert len(result.recommended_buys) == 1
        assert result.recommended_buys[0].symbol == "AAPL"
        assert result.recommended_buys[0].conviction == 0.85
        assert len(result.skipped) == 1
        assert result.skipped[0].symbol == "MSFT"
        assert result.portfolio_reasoning == "Focus on tech momentum"

    def test_parses_json_in_markdown_code_block(self):
        service = _make_service()
        response = '```json\n{"recommended_buys": [], "skipped": [], "portfolio_reasoning": "None", "risk_assessment": "Low"}\n```'

        result = service._parse_portfolio_response(response)
        assert isinstance(result, PortfolioJudgmentOutput)
        assert result.portfolio_reasoning == "None"

    def test_parses_json_in_plain_code_block(self):
        service = _make_service()
        response = '```\n{"recommended_buys": [], "skipped": [], "portfolio_reasoning": "X", "risk_assessment": "Y"}\n```'

        result = service._parse_portfolio_response(response)
        assert result.portfolio_reasoning == "X"

    def test_handles_empty_buys_and_skipped(self):
        service = _make_service()
        response = json.dumps({
            "recommended_buys": [],
            "skipped": [],
            "portfolio_reasoning": "No candidates passed threshold",
            "risk_assessment": "",
        })

        result = service._parse_portfolio_response(response)
        assert len(result.recommended_buys) == 0
        assert len(result.skipped) == 0

    def test_raises_on_invalid_json(self):
        service = _make_service()
        with pytest.raises(ValueError, match="Invalid JSON"):
            service._parse_portfolio_response("not valid json at all")

    def test_defaults_for_missing_fields(self):
        service = _make_service()
        response = json.dumps({
            "recommended_buys": [{"symbol": "TSLA"}],
            "skipped": [],
        })

        result = service._parse_portfolio_response(response)
        buy = result.recommended_buys[0]
        assert buy.symbol == "TSLA"
        assert buy.action == "buy"  # default
        assert buy.conviction == 0.5  # default
        assert buy.allocation_hint == "normal"  # default


class TestParseExitResponse:
    """Tests for _parse_exit_response."""

    def test_parses_valid_exit_json(self):
        service = _make_service()
        response = json.dumps({
            "exit_decisions": [
                {
                    "symbol": "AAPL",
                    "decision": "hold",
                    "confidence": 0.8,
                    "reasoning": "Strong momentum continues",
                    "hold_duration_hint": 3,
                    "risks_of_holding": ["Gap down risk"],
                    "risks_of_closing": ["Miss further upside"],
                },
                {
                    "symbol": "MSFT",
                    "decision": "close",
                    "confidence": 0.7,
                    "reasoning": "Momentum fading",
                    "hold_duration_hint": None,
                    "risks_of_holding": ["Further decline"],
                    "risks_of_closing": ["Temporary dip"],
                },
            ]
        })

        results = service._parse_exit_response(response)
        assert len(results) == 2
        assert results[0].symbol == "AAPL"
        assert results[0].decision == "hold"
        assert results[0].hold_duration_hint == 3
        assert results[1].symbol == "MSFT"
        assert results[1].decision == "close"

    def test_parses_exit_json_in_code_block(self):
        service = _make_service()
        response = '```json\n{"exit_decisions": [{"symbol": "TSLA", "decision": "close", "confidence": 0.9, "reasoning": "Stop", "risks_of_holding": [], "risks_of_closing": []}]}\n```'

        results = service._parse_exit_response(response)
        assert len(results) == 1
        assert results[0].symbol == "TSLA"
        assert results[0].decision == "close"

    def test_raises_on_invalid_json(self):
        service = _make_service()
        with pytest.raises(ValueError, match="Invalid JSON"):
            service._parse_exit_response("broken json")

    def test_empty_exit_decisions(self):
        service = _make_service()
        response = json.dumps({"exit_decisions": []})
        results = service._parse_exit_response(response)
        assert len(results) == 0

    def test_defaults_for_missing_fields(self):
        service = _make_service()
        response = json.dumps({
            "exit_decisions": [{"symbol": "X"}],
        })

        results = service._parse_exit_response(response)
        r = results[0]
        assert r.symbol == "X"
        assert r.decision == "close"  # default
        assert r.confidence == 0.5  # default
        assert r.risks_of_holding == []
        assert r.risks_of_closing == []
