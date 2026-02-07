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
from .models import (
    JudgmentOutput, ReasoningTrace, KeyFactor,
    PortfolioJudgmentOutput, StockAllocation,
    ExitJudgmentOutput,
)
from .prompts import (
    JUDGMENT_SYSTEM_PROMPT, build_judgment_prompt, PROMPT_VERSION,
    PORTFOLIO_SYSTEM_PROMPT, build_portfolio_judgment_prompt, PORTFOLIO_PROMPT_VERSION,
    EXIT_SYSTEM_PROMPT, build_exit_judgment_prompt,
)


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
        past_lessons: str | None = None,
        prompt_overrides: list[dict] | None = None,
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
            past_lessons: Optional formatted past lessons for context
            prompt_overrides: Optional dynamic overrides from meta-monitor

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
            past_lessons=past_lessons,
            prompt_overrides=prompt_overrides,
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

    def judge_portfolio(
        self,
        strategy_mode: str,
        market_regime: str,
        candidates: list,
        current_positions: list,
        available_slots: int,
        available_cash: float,
        news_by_symbol: dict[str, list[dict]] | None = None,
        performance_stats: dict | None = None,
    ) -> PortfolioJudgmentOutput:
        """Generate portfolio-level judgment for all candidates at once.

        Unlike judge_stock() which evaluates one stock at a time, this method
        sees ALL candidates simultaneously for comparative evaluation.

        No fallback: if LLM fails, exception propagates to caller.

        Args:
            strategy_mode: Strategy mode string
            market_regime: Current market regime
            candidates: List of PortfolioCandidateSummary
            current_positions: List of PortfolioHolding
            available_slots: Number of open investment slots
            available_cash: Available cash amount
            news_by_symbol: Dict mapping symbol -> list of news dicts
            performance_stats: Structured data from build_performance_stats()

        Returns:
            PortfolioJudgmentOutput with buy recommendations and reasoning

        Raises:
            ValueError: If LLM response cannot be parsed
            Exception: Any LLM communication error (no fallback)
        """
        logger.info(
            f"Generating portfolio judgment for {len(candidates)} candidates "
            f"({strategy_mode}, {available_slots} slots)"
        )

        prompt = build_portfolio_judgment_prompt(
            strategy_mode=strategy_mode,
            market_regime=market_regime,
            candidates=candidates,
            current_positions=current_positions,
            available_slots=available_slots,
            available_cash=available_cash,
            news_by_symbol=news_by_symbol,
            performance_stats=performance_stats,
        )

        full_prompt = f"{PORTFOLIO_SYSTEM_PROMPT}\n\n{prompt}"

        response = self.llm_client.generate_with_thinking(
            prompt=full_prompt,
            model=self.model_name,
            thinking_level="low",
        )

        logger.debug(f"Portfolio judgment response: {len(response.content)} chars")

        result = self._parse_portfolio_response(response.content)
        result.raw_llm_response = response.content

        logger.info(
            f"Portfolio judgment: {len(result.recommended_buys)} buys, "
            f"{len(result.skipped)} skipped"
        )

        return result

    def _parse_portfolio_response(self, response: str) -> PortfolioJudgmentOutput:
        """Parse LLM response into PortfolioJudgmentOutput."""
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
            raise ValueError(f"Invalid JSON in portfolio judgment response: {e}")

        recommended_buys = []
        for item in data.get("recommended_buys", []):
            recommended_buys.append(StockAllocation(
                symbol=item.get("symbol", ""),
                action=item.get("action", "buy"),
                conviction=float(item.get("conviction", 0.5)),
                allocation_hint=item.get("allocation_hint", "normal"),
                reasoning=item.get("reasoning", ""),
            ))

        skipped = []
        for item in data.get("skipped", []):
            skipped.append(StockAllocation(
                symbol=item.get("symbol", ""),
                action=item.get("action", "skip"),
                conviction=float(item.get("conviction", 0.0)),
                allocation_hint=item.get("allocation_hint", "normal"),
                reasoning=item.get("reasoning", ""),
            ))

        return PortfolioJudgmentOutput(
            recommended_buys=recommended_buys,
            skipped=skipped,
            portfolio_reasoning=data.get("portfolio_reasoning", ""),
            risk_assessment=data.get("risk_assessment", ""),
            prompt_version=PORTFOLIO_PROMPT_VERSION,
        )

    def judge_exits(
        self,
        positions_for_review: list[dict],
        market_regime: str,
    ) -> list[ExitJudgmentOutput]:
        """Generate exit judgments for positions with soft exit signals.

        Batch processes multiple positions in a single LLM call.
        No fallback: exceptions propagate to caller.

        Args:
            positions_for_review: List of dicts with symbol, pnl_pct,
                hold_days, trigger_reason, top_news
            market_regime: Current market regime

        Returns:
            List of ExitJudgmentOutput

        Raises:
            ValueError: If LLM response cannot be parsed
            Exception: Any LLM communication error
        """
        if not positions_for_review:
            return []

        logger.info(f"Generating exit judgment for {len(positions_for_review)} positions")

        prompt = build_exit_judgment_prompt(
            positions_for_review=positions_for_review,
            market_regime=market_regime,
        )

        full_prompt = f"{EXIT_SYSTEM_PROMPT}\n\n{prompt}"

        response = self.llm_client.generate_with_thinking(
            prompt=full_prompt,
            model=self.model_name,
            thinking_level="low",
        )

        results = self._parse_exit_response(response.content)

        for r in results:
            r.raw_llm_response = response.content

        logger.info(
            f"Exit judgment: {sum(1 for r in results if r.decision == 'close')} close, "
            f"{sum(1 for r in results if r.decision == 'hold')} hold"
        )

        return results

    def _parse_exit_response(self, response: str) -> list[ExitJudgmentOutput]:
        """Parse LLM response into list of ExitJudgmentOutput."""
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
            raise ValueError(f"Invalid JSON in exit judgment response: {e}")

        results = []
        for item in data.get("exit_decisions", []):
            results.append(ExitJudgmentOutput(
                symbol=item.get("symbol", ""),
                decision=item.get("decision", "close"),
                confidence=float(item.get("confidence", 0.5)),
                reasoning=item.get("reasoning", ""),
                hold_duration_hint=item.get("hold_duration_hint"),
                risks_of_holding=item.get("risks_of_holding", []),
                risks_of_closing=item.get("risks_of_closing", []),
            ))

        return results

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
