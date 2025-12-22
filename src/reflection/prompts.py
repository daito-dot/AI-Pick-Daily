"""
Prompts for LLM-based reflection analysis.

These prompts implement the Reflexion framework pattern:
1. Analyze past judgments and outcomes
2. Identify patterns (success and failure)
3. Generate concrete improvement suggestions
"""

PROMPT_VERSION = "v1"


REFLECTION_SYSTEM_PROMPT = """You are an investment analyst reviewing past trading decisions.

Your role is to:
1. Analyze the outcomes of past investment judgments
2. Identify patterns that led to success or failure
3. Assess the reliability of different factors
4. Generate concrete, actionable improvement suggestions

CRITICAL PRINCIPLES:
1. Be honest about what worked and what didn't
2. Focus on systematic patterns, not individual outliers
3. Prioritize actionable insights over general observations
4. Consider market regime context when analyzing outcomes

OUTPUT REQUIREMENTS:
Respond in valid JSON format with the exact structure specified."""


def build_reflection_prompt(
    strategy_mode: str,
    reflection_type: str,
    period_start: str,
    period_end: str,
    judgments_with_outcomes: list[dict],
    performance_summary: dict,
) -> str:
    """
    Build the reflection analysis prompt.

    Args:
        strategy_mode: 'conservative' or 'aggressive'
        reflection_type: 'weekly', 'monthly', or 'post_trade'
        period_start: Start date of analysis period
        period_end: End date of analysis period
        judgments_with_outcomes: List of judgment-outcome pairs
        performance_summary: Summary statistics

    Returns:
        Complete prompt string for LLM
    """
    # Format judgments
    judgments_text = _format_judgments(judgments_with_outcomes)

    # Format performance summary
    summary_text = _format_performance_summary(performance_summary)

    # Strategy context
    strategy_context = _get_strategy_context(strategy_mode)

    prompt = f"""# Reflection Analysis Request

## Analysis Period
Strategy: {strategy_mode}
Type: {reflection_type}
Period: {period_start} to {period_end}

## Performance Summary
{summary_text}

## Past Judgments with Outcomes
{judgments_text}

## Strategy Context
{strategy_context}

## Your Analysis Task

Analyze the past judgments and their outcomes to identify:

1. **Patterns of Success**: What factors or conditions led to correct predictions?
2. **Patterns of Failure**: What factors or conditions led to incorrect predictions?
3. **Factor Reliability**: Which factor types (fundamental, technical, sentiment, etc.) were most/least reliable?
4. **Improvement Opportunities**: What concrete changes would improve future performance?

Consider:
- Market regime effects on accuracy
- Confidence calibration (did high confidence correlate with correctness?)
- Time sensitivity of factors
- Strategy-specific patterns

## Required Output Format (JSON)

```json
{{
  "factor_reliability": [
    {{
      "factor_type": "fundamental" | "technical" | "sentiment" | "macro" | "catalyst",
      "total_uses": number,
      "correct_predictions": number,
      "incorrect_predictions": number,
      "accuracy_rate": 0.0 to 1.0,
      "avg_confidence_when_used": 0.0 to 1.0,
      "reliability_grade": "A" | "B" | "C" | "D" | "F",
      "recommendation": "string"
    }}
  ],
  "success_patterns": [
    {{
      "description": "Clear description of the pattern",
      "frequency": number,
      "confidence": 0.0 to 1.0,
      "examples": ["AAPL 2024-01-15", "MSFT 2024-01-20"],
      "insight": "Why this pattern works",
      "suggested_action": "How to leverage this pattern"
    }}
  ],
  "failure_patterns": [
    {{
      "description": "Clear description of the failure pattern",
      "frequency": number,
      "confidence": 0.0 to 1.0,
      "examples": ["XYZ 2024-01-18"],
      "insight": "Why this pattern failed",
      "suggested_action": "How to avoid this pattern"
    }}
  ],
  "improvement_suggestions": [
    {{
      "category": "data" | "model" | "strategy" | "timing" | "risk",
      "priority": "high" | "medium" | "low",
      "suggestion": "Specific suggestion",
      "rationale": "Why this would help",
      "expected_impact": "Expected improvement",
      "implementation_difficulty": "easy" | "medium" | "hard"
    }}
  ],
  "regime_performance": {{
    "normal": {{"accuracy": 0.0, "count": 0}},
    "caution": {{"accuracy": 0.0, "count": 0}},
    "risk_off": {{"accuracy": 0.0, "count": 0}}
  }},
  "overall_assessment": "Brief summary of the reflection findings"
}}
```

Focus on actionable insights. Be specific, not generic.
Respond ONLY with the JSON object."""

    return prompt


def _format_judgments(judgments: list[dict]) -> str:
    """Format judgments with outcomes for the prompt."""
    if not judgments:
        return "No judgments to analyze"

    sections = []

    for j in judgments:
        # Basic info
        outcome_emoji = "✓" if j.get("was_correct") else "✗" if j.get("was_correct") is False else "?"
        return_5d = j.get("actual_return_5d", 0)
        return_str = f"{return_5d:+.2f}%" if return_5d is not None else "N/A"

        section = [
            f"\n### {j.get('symbol')} ({j.get('batch_date')}) {outcome_emoji}",
            f"Decision: {j.get('decision')} | Confidence: {j.get('confidence', 0):.0%}",
            f"5-Day Return: {return_str}",
            f"Regime: {j.get('market_regime', 'unknown')}",
        ]

        # Key factors used
        factors = j.get("key_factors", [])
        if factors:
            factor_types = [f.get("factor_type", "unknown") for f in factors]
            section.append(f"Factors Used: {', '.join(factor_types)}")

        # Reasoning steps
        steps = j.get("reasoning_steps", [])
        if steps:
            section.append(f"Decision Point: {steps[-1] if steps else 'N/A'}")

        sections.append("\n".join(section))

    return "\n".join(sections)


def _format_performance_summary(summary: dict) -> str:
    """Format performance summary for the prompt."""
    lines = [
        f"Total Judgments: {summary.get('total', 0)}",
        f"Correct: {summary.get('correct', 0)} ({summary.get('accuracy', 0):.0%})",
        f"Buy Recommendations: {summary.get('buy_count', 0)} (accuracy: {summary.get('buy_accuracy', 0):.0%})",
        f"Avoid Recommendations: {summary.get('avoid_count', 0)} (accuracy: {summary.get('avoid_accuracy', 0):.0%})",
        f"Average Confidence: {summary.get('avg_confidence', 0):.0%}",
        f"Confidence Calibration: {summary.get('calibration', 'N/A')}",
    ]

    return "\n".join(lines)


def _get_strategy_context(strategy_mode: str) -> str:
    """Get strategy-specific context for reflection."""
    if strategy_mode == "conservative":
        return """CONSERVATIVE STRATEGY CONTEXT:
- Expected holding period: 5-10 days
- Risk tolerance: Low
- Priority factors: Fundamentals, established trends
- Success criteria: Positive returns with low volatility
- Key concern: Avoid large drawdowns"""
    else:
        return """AGGRESSIVE STRATEGY CONTEXT:
- Expected holding period: 3-5 days
- Risk tolerance: High
- Priority factors: Momentum, breakouts, catalysts
- Success criteria: Capture large moves
- Key concern: Timing and quick exits on reversal"""


# Prompt for post-trade reflection
POST_TRADE_REFLECTION_PROMPT = """Analyze this specific trade outcome.

Trade Details:
Symbol: {symbol}
Entry Date: {entry_date}
Exit Date: {exit_date}
Decision: {decision}
Confidence: {confidence:.0%}
Actual Return: {actual_return:+.2f}%
Outcome: {outcome}

Original Reasoning:
{reasoning}

Key Factors Considered:
{factors}

Market Regime at Entry: {regime}

ANALYZE:
1. Was the reasoning sound given the information available?
2. Which factors proved accurate/inaccurate?
3. What could have been done differently?
4. What lessons apply to future similar situations?

Respond in JSON format with:
{{
  "reasoning_quality": "sound" | "partially_sound" | "flawed",
  "accurate_factors": ["factor1", "factor2"],
  "inaccurate_factors": ["factor3"],
  "missed_signals": ["signal1"],
  "lessons_learned": ["lesson1", "lesson2"],
  "future_action": "What to do differently next time"
}}"""
