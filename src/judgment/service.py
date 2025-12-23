"""
Judgment Service - Layer 2 of the 4-layer architecture.

Uses LLM with Chain-of-Thought (CoT) prompting to make
investment judgments with transparent reasoning.
"""
import json
import logging
from datetime import datetime
from typing import Any

from src.llm import get_llm_client, LLMClient
from src.config import config
from .models import JudgmentOutput, ReasoningTrace, KeyFactor
from .prompts import JUDGMENT_SYSTEM_PROMPT, build_judgment_prompt, PROMPT_VERSION


logger = logging.getLogger(__name__)


class JudgmentService:
    """
    Service for generating LLM-based investment judgments.

    Uses Gemini Flash Thinking mode for built-in CoT reasoning.
    Records full reasoning trace for later reflection and learning.
    """

    def __init__(self, llm_client: LLMClient | None = None):
        """
        Initialize the judgment service.

        Args:
            llm_client: Optional LLM client (uses default if not provided)
        """
        self.llm_client = llm_client or get_llm_client()
        self.model_name = config.llm.analysis_model  # gemini-3-flash for thinking mode

    def judge_stock(
        self,
        symbol: str,
        strategy_mode: str,
        stock_data: dict,
        news_data: list[dict],
        rule_based_scores: dict,
        market_regime: str = "normal",
    ) -> JudgmentOutput:
        """
        Generate an investment judgment for a single stock.

        Uses CoT prompting via Gemini's thinking mode to produce
        transparent, auditable reasoning.

        Args:
            symbol: Stock ticker symbol
            strategy_mode: "conservative" or "aggressive"
            stock_data: Current price, technicals, fundamentals
            news_data: Recent news with timestamps and sentiment
            rule_based_scores: Existing rule-based agent scores
            market_regime: Current market regime

        Returns:
            JudgmentOutput with decision and full reasoning trace
        """
        logger.info(f"Generating judgment for {symbol} ({strategy_mode})")

        # Build the prompt
        prompt = build_judgment_prompt(
            symbol=symbol,
            strategy_mode=strategy_mode,
            stock_data=stock_data,
            news_data=news_data,
            rule_based_scores=rule_based_scores,
            market_regime=market_regime,
        )

        # Create full prompt with system context
        full_prompt = f"{JUDGMENT_SYSTEM_PROMPT}\n\n{prompt}"

        # Generate judgment using thinking mode
        try:
            response = self.llm_client.generate_with_thinking(
                prompt=full_prompt,
                model=self.model_name,
                thinking_level="low",  # Balance between reasoning depth and speed
            )

            logger.debug(f"LLM response for {symbol}: {len(response.content)} chars")

            # Parse the response
            judgment = self._parse_judgment_response(
                response.content,
                symbol=symbol,
                strategy_mode=strategy_mode,
                market_regime=market_regime,
                stock_data=stock_data,
                model_version=response.model,
            )

            # Store raw response for debugging
            judgment.raw_llm_response = response.content

            logger.info(
                f"Judgment for {symbol}: {judgment.decision} "
                f"(score={judgment.score}, confidence={judgment.confidence:.0%})"
            )

            return judgment

        except Exception as e:
            logger.error(f"Failed to generate judgment for {symbol}: {e}")
            # Return a fallback judgment based on rule-based scores
            return self._create_fallback_judgment(
                symbol=symbol,
                strategy_mode=strategy_mode,
                rule_based_scores=rule_based_scores,
                market_regime=market_regime,
                error_message=str(e),
            )

    def judge_batch(
        self,
        candidates: list[dict],
        strategy_mode: str,
        market_regime: str = "normal",
    ) -> list[JudgmentOutput]:
        """
        Generate judgments for multiple stocks.

        Processes stocks sequentially to maintain quality and
        avoid rate limiting issues.

        Args:
            candidates: List of dicts with symbol, stock_data, news_data, scores
            strategy_mode: "conservative" or "aggressive"
            market_regime: Current market regime

        Returns:
            List of JudgmentOutput objects
        """
        judgments = []

        for i, candidate in enumerate(candidates):
            logger.info(f"Processing {i+1}/{len(candidates)}: {candidate['symbol']}")

            judgment = self.judge_stock(
                symbol=candidate["symbol"],
                strategy_mode=strategy_mode,
                stock_data=candidate.get("stock_data", {}),
                news_data=candidate.get("news_data", []),
                rule_based_scores=candidate.get("scores", {}),
                market_regime=market_regime,
            )

            judgments.append(judgment)

        return judgments

    def _parse_judgment_response(
        self,
        response: str,
        symbol: str,
        strategy_mode: str,
        market_regime: str,
        stock_data: dict,
        model_version: str,
    ) -> JudgmentOutput:
        """Parse the LLM response into a structured JudgmentOutput."""
        # Clean the response - extract JSON from markdown code blocks if present
        cleaned = response.strip()
        if "```json" in cleaned:
            start = cleaned.find("```json") + 7
            end = cleaned.find("```", start)
            cleaned = cleaned[start:end].strip()
        elif "```" in cleaned:
            start = cleaned.find("```") + 3
            end = cleaned.find("```", start)
            cleaned = cleaned[start:end].strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON for {symbol}: {e}")
            raise ValueError(f"Invalid JSON response: {e}")

        # Parse reasoning trace
        reasoning_data = data.get("reasoning", {})
        reasoning = ReasoningTrace(
            steps=reasoning_data.get("steps", ["No steps provided"]),
            top_factors=reasoning_data.get("top_factors", []),
            decision_point=reasoning_data.get("decision_point", "No decision point specified"),
            uncertainties=reasoning_data.get("uncertainties", []),
            confidence_explanation=reasoning_data.get("confidence_explanation", ""),
        )

        # Parse key factors
        key_factors = []
        for factor_data in data.get("key_factors", []):
            try:
                factor = KeyFactor(
                    factor_type=factor_data.get("factor_type", "fundamental"),
                    description=factor_data.get("description", ""),
                    source=factor_data.get("source", "unknown"),
                    impact=factor_data.get("impact", "neutral"),
                    weight=float(factor_data.get("weight", 0.5)),
                    verifiable=factor_data.get("verifiable", True),
                )
                key_factors.append(factor)
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping invalid factor: {e}")

        # Create input summary
        input_summary = self._create_input_summary(stock_data)

        return JudgmentOutput(
            symbol=symbol,
            strategy_mode=strategy_mode,
            decision=data.get("decision", "hold"),
            confidence=float(data.get("confidence", 0.5)),
            score=int(data.get("score", 50)),
            reasoning=reasoning,
            key_factors=key_factors,
            identified_risks=data.get("identified_risks", []),
            market_regime=market_regime,
            input_summary=input_summary,
            model_version=model_version,
            prompt_version=PROMPT_VERSION,
        )

    def _create_fallback_judgment(
        self,
        symbol: str,
        strategy_mode: str,
        rule_based_scores: dict,
        market_regime: str,
        error_message: str,
    ) -> JudgmentOutput:
        """Create a fallback judgment when LLM fails."""
        composite_score = rule_based_scores.get("composite_score", 50)

        # Determine decision based on rule-based score
        if strategy_mode == "conservative":
            threshold = 60
        else:
            threshold = 75

        if composite_score >= threshold:
            decision = "buy"
            confidence = 0.4  # Lower confidence due to fallback
        else:
            decision = "avoid"
            confidence = 0.3

        return JudgmentOutput(
            symbol=symbol,
            strategy_mode=strategy_mode,
            decision=decision,
            confidence=confidence,
            score=composite_score,
            reasoning=ReasoningTrace(
                steps=["LLM judgment failed, using rule-based fallback"],
                top_factors=["Rule-based composite score"],
                decision_point=f"Composite score {composite_score} vs threshold {threshold}",
                uncertainties=[f"LLM error: {error_message}"],
                confidence_explanation="Low confidence due to LLM failure",
            ),
            key_factors=[
                KeyFactor(
                    factor_type="technical",
                    description="Rule-based composite score",
                    source="rule_based_scoring",
                    impact="positive" if composite_score >= threshold else "negative",
                    weight=1.0,
                    verifiable=True,
                )
            ],
            identified_risks=["Judgment based on fallback logic, not full analysis"],
            market_regime=market_regime,
            input_summary="Fallback judgment - LLM unavailable",
            model_version="fallback",
            prompt_version=PROMPT_VERSION,
        )

    def _create_input_summary(self, stock_data: dict) -> str:
        """Create a brief summary of input data for record-keeping."""
        parts = []

        if stock_data.get("price"):
            parts.append(f"price=${stock_data['price']:.2f}")
        if stock_data.get("change_pct"):
            parts.append(f"change={stock_data['change_pct']:+.2f}%")
        if stock_data.get("rsi"):
            parts.append(f"RSI={stock_data['rsi']:.0f}")
        if stock_data.get("volume") and stock_data.get("avg_volume"):
            vol_ratio = stock_data['volume'] / stock_data['avg_volume']
            parts.append(f"vol={vol_ratio:.1f}x")

        return ", ".join(parts) if parts else "minimal data"
