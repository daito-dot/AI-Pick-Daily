"""
Prompts for Deep Research analysis.

These prompts are designed for use with advanced LLM models
(Gemini Pro / Deep Research) for comprehensive analysis.
"""

PROMPT_VERSION = "v1"


RESEARCH_SYSTEM_PROMPT = """You are a senior investment strategist conducting deep research.

Your role is to provide comprehensive, well-researched analysis that goes beyond
surface-level observations. Your analysis should:

1. Be grounded in data and facts
2. Consider multiple perspectives and scenarios
3. Identify non-obvious insights and second-order effects
4. Provide actionable investment implications
5. Acknowledge uncertainties and limitations

OUTPUT: Respond in valid JSON format as specified."""


def build_sector_analysis_prompt(
    sector: str,
    recent_news: list[dict],
    market_context: dict,
    current_holdings: list[str] | None = None,
) -> str:
    """
    Build prompt for sector-level analysis.

    Args:
        sector: Sector name (e.g., "Technology", "Healthcare")
        recent_news: Recent news items for context
        market_context: Current market regime and conditions
        current_holdings: Stocks currently held in this sector

    Returns:
        Complete prompt string
    """
    news_summary = "\n".join([
        f"- {n.get('headline', 'No headline')}"
        for n in recent_news[:10]
    ]) if recent_news else "No recent news available"

    holdings_info = (
        f"Current holdings in sector: {', '.join(current_holdings)}"
        if current_holdings else "No current holdings in this sector"
    )

    return f"""# Sector Deep Dive: {sector}

## Current Market Context
Market Regime: {market_context.get('regime', 'normal')}
VIX Level: {market_context.get('vix', 'N/A')}
S&P 500 Trend: {market_context.get('sp500_trend', 'N/A')}

## Recent Sector News
{news_summary}

## Current Position
{holdings_info}

## Analysis Request

Provide a comprehensive analysis of the {sector} sector including:

1. **Sector Outlook**: Bullish, neutral, or bearish view with confidence level
2. **Key Drivers**: What's driving the sector (tailwinds and headwinds)
3. **Relative Performance**: Expected performance vs broader market
4. **Top Opportunities**: Specific stocks to consider
5. **Stocks to Avoid**: Stocks with elevated risk
6. **Key Metrics**: What metrics to watch for early signals

## Required Output Format (JSON)

```json
{{
  "sector": "{sector}",
  "outlook": "bullish" | "neutral" | "bearish",
  "confidence": 0.0 to 1.0,
  "tailwinds": ["tailwind 1", "tailwind 2"],
  "headwinds": ["headwind 1", "headwind 2"],
  "vs_market_outlook": "outperform" | "inline" | "underperform",
  "top_opportunities": ["SYMBOL1", "SYMBOL2"],
  "stocks_to_avoid": ["SYMBOL3"],
  "time_horizon": "1-3 months",
  "key_metrics": ["metric 1", "metric 2"],
  "detailed_rationale": "Comprehensive explanation of the analysis"
}}
```

Be specific and actionable. Avoid generic statements."""


def build_thematic_analysis_prompt(
    theme: str,
    related_stocks: list[str] | None = None,
) -> str:
    """
    Build prompt for thematic analysis.

    Args:
        theme: Investment theme to analyze
        related_stocks: Stocks potentially related to the theme

    Returns:
        Complete prompt string
    """
    stocks_info = (
        f"Potentially related stocks: {', '.join(related_stocks)}"
        if related_stocks else "No specific stocks identified yet"
    )

    return f"""# Thematic Deep Dive: {theme}

## Theme Context
{stocks_info}

## Analysis Request

Provide comprehensive analysis of the "{theme}" investment theme:

1. **Theme Description**: Clear explanation of what this theme encompasses
2. **Relevance Assessment**: How relevant is this theme to current markets?
3. **Stage Analysis**: Is this emerging, developing, mature, or declining?
4. **Investment Implications**: Bullish and bearish implications
5. **Beneficiaries**: Stocks that stand to benefit
6. **At Risk**: Stocks that face headwinds from this theme
7. **Duration**: Expected lifespan of this theme

## Required Output Format (JSON)

```json
{{
  "theme": "{theme}",
  "description": "Clear description of the theme",
  "relevance": "high" | "medium" | "low",
  "stage": "emerging" | "developing" | "mature" | "declining",
  "bullish_implications": ["implication 1", "implication 2"],
  "bearish_implications": ["implication 1"],
  "beneficiaries": ["SYMBOL1", "SYMBOL2"],
  "at_risk": ["SYMBOL3"],
  "expected_duration": "6-12 months",
  "detailed_analysis": "Comprehensive analysis..."
}}
```

Focus on actionable insights."""


def build_macro_outlook_prompt(
    current_data: dict,
    recent_events: list[str],
) -> str:
    """
    Build prompt for macro-economic outlook.

    Args:
        current_data: Current economic data points
        recent_events: Recent macro events

    Returns:
        Complete prompt string
    """
    events_text = "\n".join([f"- {e}" for e in recent_events]) if recent_events else "No major recent events"

    return f"""# Macro-Economic Outlook Analysis

## Current Data
VIX: {current_data.get('vix', 'N/A')}
10Y Treasury: {current_data.get('treasury_10y', 'N/A')}
S&P 500 YTD: {current_data.get('sp500_ytd', 'N/A')}
Unemployment: {current_data.get('unemployment', 'N/A')}

## Recent Events
{events_text}

## Analysis Request

Provide a comprehensive macro-economic outlook:

1. **Overall Market Outlook**: Bullish, neutral, or bearish
2. **Risk Assessment**: Current risk level
3. **Key Factors**: Positive and negative factors driving the outlook
4. **Rate Outlook**: Direction of interest rates
5. **Inflation Outlook**: Inflation trajectory
6. **Sector Recommendations**: Which sectors to over/underweight
7. **Portfolio Implications**: Asset allocation suggestions

## Required Output Format (JSON)

```json
{{
  "horizon": "Q1 2025",
  "market_outlook": "bullish" | "neutral" | "bearish",
  "risk_level": "low" | "moderate" | "elevated" | "high",
  "positive_factors": ["factor 1", "factor 2"],
  "negative_factors": ["factor 1"],
  "uncertainties": ["uncertainty 1"],
  "rate_outlook": "rising" | "stable" | "falling",
  "inflation_outlook": "rising" | "stable" | "falling",
  "overweight_sectors": ["Technology", "Healthcare"],
  "underweight_sectors": ["Utilities"],
  "equity_allocation": "overweight" | "neutral" | "underweight",
  "cash_recommendation": "Maintain normal cash levels",
  "detailed_analysis": "Comprehensive analysis..."
}}
```

Be forward-looking but grounded in current data."""


def build_company_deep_dive_prompt(
    symbol: str,
    company_name: str,
    financial_data: dict,
    recent_news: list[dict],
) -> str:
    """
    Build prompt for company deep dive analysis.

    Args:
        symbol: Stock ticker
        company_name: Company name
        financial_data: Financial metrics
        recent_news: Recent company news

    Returns:
        Complete prompt string
    """
    financials = "\n".join([
        f"- {k}: {v}" for k, v in financial_data.items()
    ]) if financial_data else "Limited financial data available"

    news = "\n".join([
        f"- {n.get('headline', 'No headline')}"
        for n in recent_news[:5]
    ]) if recent_news else "No recent news"

    return f"""# Company Deep Dive: {company_name} ({symbol})

## Financial Data
{financials}

## Recent News
{news}

## Analysis Request

Provide comprehensive analysis of {company_name}:

1. **Investment Thesis**: Clear thesis with confidence level
2. **Fundamental Analysis**: Key strengths and weaknesses
3. **Competitive Position**: Moat assessment and competitive dynamics
4. **Growth Outlook**: Growth trajectory and drivers
5. **Valuation**: Fair value assessment
6. **Catalysts**: Upcoming events that could move the stock
7. **Risks**: Key risks and mitigation factors
8. **Recommendation**: Buy/Hold/Sell with target and timeline

## Required Output Format (JSON)

```json
{{
  "symbol": "{symbol}",
  "company_name": "{company_name}",
  "thesis": "Clear investment thesis",
  "thesis_confidence": 0.0 to 1.0,
  "fundamental_score": 0 to 100,
  "fundamental_summary": "Summary of fundamentals",
  "key_strengths": ["strength 1", "strength 2"],
  "key_weaknesses": ["weakness 1"],
  "moat_rating": "wide" | "narrow" | "none",
  "competitive_advantages": ["advantage 1"],
  "competitive_threats": ["threat 1"],
  "growth_outlook": "accelerating" | "stable" | "decelerating",
  "growth_drivers": ["driver 1", "driver 2"],
  "valuation_verdict": "undervalued" | "fair" | "overvalued",
  "valuation_rationale": "Explanation",
  "upcoming_catalysts": [
    {{"event": "Q4 Earnings", "date": "2025-01-15", "impact": "high"}}
  ],
  "key_risks": ["risk 1", "risk 2"],
  "risk_mitigation": ["mitigation 1"],
  "recommendation": "strong_buy" | "buy" | "hold" | "sell" | "strong_sell",
  "target_price": 150.00,
  "time_horizon": "12 months",
  "detailed_analysis": "Comprehensive analysis..."
}}
```

Be thorough but focused on investable insights."""
