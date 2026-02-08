"""
Prompts for LLM-based investment judgment.

These prompts implement Chain-of-Thought (CoT) reasoning for
transparent and auditable investment decisions.

Based on research findings:
- FinCoT shows +17% accuracy improvement with CoT
- Explicit reasoning steps improve judgment quality
- Structured output enables later reflection and learning
"""

# Version tracking for A/B testing and iteration
PROMPT_VERSION = "v1"
PORTFOLIO_PROMPT_VERSION = "v2_portfolio"


JUDGMENT_SYSTEM_PROMPT = """あなたは経験豊富な投資アナリストです。株式投資判断を行います。

提供された情報を分析し、明確な投資判断を下してください。

重要な原則:
1. 結論に至る前にステップごとに考える
2. 判断に影響を与える要因を明示する
3. 不確実性とリスクを認識する
4. 推論は追跡可能で検証可能でなければならない

信頼度（confidence）の校正ガイドライン:
- 0.90以上: 極めて稀。複数の強力な独立した根拠が必要（例: 好決算+アナリスト上方修正+セクター上昇が同時に発生）
- 0.70-0.85: 標準的な「自信のある判断」。大半の判断はこの範囲に収まるべき
- 0.50-0.70: テクニカルとファンダメンタルが混在・矛盾する場合
- 0.50未満: 情報不足やシグナルが矛盾する場合。この範囲ではholdを推奨
- 過信に注意: 高い信頼度は高い精度を意味しなければならない。根拠が曖昧なまま0.80以上を付けないこと

情報の時間感度:
- 即時 (24時間以内): 最重要、まだ価格に織り込まれていない可能性が高い
- 短期 (1-5日): 重要、部分的に織り込み済み
- 中期 (1-4週間): 参考値、ほぼ織り込み済み
- 古い (5日以上): 背景情報のみ

出力要件:
- 指定された構造のJSON形式で回答
- すべてのテキスト（reasoning, key_factors, identified_risksなど）は日本語で記述"""


def build_judgment_prompt(
    symbol: str,
    strategy_mode: str,
    stock_data: dict,
    news_data: list[dict],
    rule_based_scores: dict,
    market_regime: str,
    past_lessons: str | None = None,
    prompt_overrides: list[dict] | None = None,
) -> str:
    """
    Build the judgment prompt for a single stock.

    Args:
        symbol: Stock ticker symbol
        strategy_mode: "conservative" or "aggressive"
        stock_data: Price, volume, fundamentals data
        news_data: Recent news with timestamps
        rule_based_scores: Existing rule-based agent scores
        market_regime: Current market regime
        past_lessons: Optional formatted string of past AI lessons
        prompt_overrides: Optional dynamic overrides from meta-monitor

    Returns:
        Complete prompt string for LLM
    """
    # Format stock data
    stock_info = _format_stock_data(stock_data)

    # Format news by time sensitivity
    news_by_time = _categorize_news_by_time(news_data)
    news_info = _format_news_data(news_by_time)

    # Format existing rule-based scores
    scores_info = _format_rule_based_scores(rule_based_scores, strategy_mode)

    # Strategy-specific guidance (with dynamic overrides from meta-monitor)
    strategy_guidance = _get_strategy_guidance(strategy_mode, prompt_overrides)

    # Past lessons section (optional)
    lessons_section = ""
    if past_lessons:
        lessons_section = f"\n## Past Lessons (from recent reviews)\n{past_lessons}\n"

    prompt = f"""# Investment Judgment Request

## Target Stock
Symbol: {symbol}
Strategy: {strategy_mode}
Market Regime: {market_regime}

## Stock Data
{stock_info}

## Recent News (by time sensitivity)
{news_info}

## Rule-Based Analysis Scores
{scores_info}

## Strategy Guidance
{strategy_guidance}
{lessons_section}
## Your Task

Analyze all provided information and make an investment judgment.

Think through the following steps:
1. Assess the current price action and technicals
2. Evaluate fundamental factors
3. Consider news sentiment and timing
4. Weigh risks against potential rewards
5. Make a final judgment considering the strategy mode

## 出力フォーマット (JSON) - 日本語で記述

```json
{{
  "decision": "buy" | "hold" | "avoid",
  "confidence": 0.0 to 1.0,
  "score": 0 to 100,
  "reasoning": {{
    "steps": [
      "ステップ1: 価格動向とテクニカル指標を確認...",
      "ステップ2: ファンダメンタルズを評価...",
      "ステップ3: 最終判断..."
    ],
    "top_factors": [
      "最も重要な要因",
      "2番目に重要な要因",
      "3番目に重要な要因"
    ],
    "decision_point": "判断を決定した重要な洞察",
    "uncertainties": [
      "不確実性1",
      "不確実性2"
    ],
    "confidence_explanation": "この信頼度レベルの理由"
  }},
  "key_factors": [
    {{
      "factor_type": "fundamental" | "technical" | "sentiment" | "macro" | "catalyst",
      "description": "要因の説明",
      "source": "データソース",
      "impact": "positive" | "negative" | "neutral",
      "weight": 0.0 to 1.0,
      "verifiable": true | false
    }}
  ],
  "identified_risks": [
    "リスク1",
    "リスク2"
  ]
}}
```

JSONオブジェクトのみを返してください。追加テキストは不要です。"""

    return prompt


def _format_stock_data(stock_data: dict) -> str:
    """Format stock data for the prompt."""
    if not stock_data:
        return "No stock data available"

    lines = []

    # Price data
    if "price" in stock_data:
        lines.append(f"Current Price: ${stock_data['price']:.2f}")
    if "change_pct" in stock_data:
        lines.append(f"Daily Change: {stock_data['change_pct']:.2f}%")
    if "volume" in stock_data:
        lines.append(f"Volume: {stock_data['volume']:,}")
    if "avg_volume" in stock_data:
        vol_ratio = stock_data['volume'] / stock_data['avg_volume'] if stock_data['avg_volume'] else 0
        lines.append(f"Volume vs Avg: {vol_ratio:.1f}x")

    # Technical indicators
    if "rsi" in stock_data:
        lines.append(f"RSI(14): {stock_data['rsi']:.1f}")
    if "sma_50" in stock_data:
        lines.append(f"SMA(50): ${stock_data['sma_50']:.2f}")
    if "sma_200" in stock_data:
        lines.append(f"SMA(200): ${stock_data['sma_200']:.2f}")
    if "high_52w" in stock_data:
        pct_from_high = ((stock_data['price'] / stock_data['high_52w']) - 1) * 100 if stock_data.get('price') else 0
        lines.append(f"52W High: ${stock_data['high_52w']:.2f} ({pct_from_high:+.1f}%)")

    # Fundamentals
    if "pe_ratio" in stock_data and stock_data["pe_ratio"]:
        lines.append(f"P/E Ratio: {stock_data['pe_ratio']:.1f}")
    if "market_cap" in stock_data and stock_data["market_cap"]:
        cap_b = stock_data['market_cap'] / 1e9
        lines.append(f"Market Cap: ${cap_b:.1f}B")
    if "sector" in stock_data:
        lines.append(f"Sector: {stock_data['sector']}")

    return "\n".join(lines) if lines else "Limited data available"


def _categorize_news_by_time(news_data: list[dict]) -> dict:
    """Categorize news by time sensitivity."""
    from datetime import datetime, timedelta

    now = datetime.now()
    categories = {
        "immediate": [],  # < 24h
        "short_term": [],  # 1-5 days
        "medium_term": [],  # 1-4 weeks
        "older": [],  # > 4 weeks
    }

    for news in news_data:
        # Parse timestamp
        timestamp = news.get("datetime") or news.get("published_at")
        if isinstance(timestamp, (int, float)):
            news_time = datetime.fromtimestamp(timestamp)
        elif isinstance(timestamp, str):
            try:
                news_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                news_time = now - timedelta(days=7)  # Default to medium-term
        else:
            news_time = now - timedelta(days=7)

        age = now - news_time
        age_hours = age.total_seconds() / 3600

        if age_hours < 24:
            categories["immediate"].append(news)
        elif age_hours < 120:  # 5 days
            categories["short_term"].append(news)
        elif age_hours < 672:  # 4 weeks
            categories["medium_term"].append(news)
        else:
            categories["older"].append(news)

    return categories


def _format_news_data(news_by_time: dict) -> str:
    """Format news data grouped by time sensitivity."""
    sections = []

    for category, label, importance in [
        ("immediate", "IMMEDIATE (< 24h) - Highest Priority", "***"),
        ("short_term", "SHORT-TERM (1-5 days) - High Priority", "**"),
        ("medium_term", "MEDIUM-TERM (1-4 weeks) - Reference", "*"),
        ("older", "OLDER (> 4 weeks) - Background Only", ""),
    ]:
        news_list = news_by_time.get(category, [])
        if news_list:
            section_lines = [f"\n### {label}"]
            for news in news_list[:5]:  # Limit to 5 per category
                headline = news.get("headline") or news.get("title", "No headline")
                sentiment = news.get("sentiment", "unknown")
                section_lines.append(f"{importance} {headline} [sentiment: {sentiment}]")
            sections.append("\n".join(section_lines))

    return "\n".join(sections) if sections else "No recent news available"


def _format_rule_based_scores(scores: dict, strategy_mode: str) -> str:
    """Format existing rule-based scores."""
    if not scores:
        return "No rule-based scores available"

    lines = []

    if strategy_mode == "conservative":
        for name, weight in [("trend", 0.35), ("momentum", 0.35), ("value", 0.20), ("sentiment", 0.10)]:
            score = scores.get(f"{name}_score", 0)
            lines.append(f"{name.capitalize()}: {score}/100 (weight: {weight:.0%})")
    else:
        for name, weight in [("momentum_12_1", 0.40), ("breakout", 0.25), ("catalyst", 0.20), ("risk_adjusted", 0.15)]:
            score = scores.get(f"{name}_score", 0)
            lines.append(f"{name.replace('_', ' ').title()}: {score}/100 (weight: {weight:.0%})")

    composite = scores.get("composite_score", 0)
    percentile = scores.get("percentile_rank", 0)
    lines.append(f"\nComposite Score: {composite}/100")
    lines.append(f"Percentile Rank: {percentile}")

    return "\n".join(lines)


def _get_strategy_guidance(
    strategy_mode: str,
    prompt_overrides: list[dict] | None = None,
) -> str:
    """Get strategy-specific guidance with optional dynamic overrides."""
    if strategy_mode == "jp_conservative":
        base = """保守的戦略ガイダンス (V1 - 日本株):
- 安定性と一貫したパフォーマンスを重視
- 堅実なファンダメンタルズ（P/E、利益率）の銘柄を優先
- 確認されたトレンドを探す
- 高ボラティリティ銘柄には慎重に
- 最小保有期間: 5-10日
- 目標: 限定的な下落リスクで安定した利益

⚠️ 重要な校正フィードバック:
- 過去のavoid判断の精度が低い（約27%）。避けた銘柄の多くが実際には上昇した
- avoidを選ぶ場合は、明確なネガティブカタリスト（悪決算、不祥事、規制リスク等）がある場合に限定する
- 単にモメンタムが弱い・バリュエーションが高い程度では、holdを選択する方が精度が高い
- 不確実な場合はavoidではなくholdを選択すること"""
    elif strategy_mode == "conservative":
        base = """保守的戦略ガイダンス (V1):
- 安定性と一貫したパフォーマンスを重視
- 堅実なファンダメンタルズ（P/E、利益率）の銘柄を優先
- 確認されたトレンドを探す
- 高ボラティリティ銘柄には慎重に
- 最小保有期間: 5-10日
- 目標: 限定的な下落リスクで安定した利益"""
    else:
        base = """積極的戦略ガイダンス (V2):
- より高いリスクを許容してより高いリターンを追求
- モメンタムとブレイクアウトパターンに注目
- カタリスト（決算、ニュース）は重要なトリガー
- ボラティリティの高い銘柄も保有可能
- 短い保有期間も許容（3-5日）
- 目標: 強い動きを捉える、一部の損失は受容"""

    # Append dynamic overrides from meta-monitor
    if prompt_overrides:
        active_texts = [
            o["override_text"]
            for o in prompt_overrides
            if o.get("override_text") and o.get("active", True)
        ]
        if active_texts:
            base += "\n\n## 直近の分析に基づく追加ガイダンス\n"
            base += "\n".join(f"- {text}" for text in active_texts)

    return base


# Prompt for batch processing multiple stocks
BATCH_JUDGMENT_INTRO = """You will analyze multiple stocks for investment judgment.
For each stock, provide a complete judgment with reasoning.

Important: Process each stock independently. Do not let one stock's analysis
influence another's judgment.

Respond with a JSON array of judgment objects."""


def build_judgment_prompt_v2(
    symbol: str,
    strategy_mode: str,
    timed_info: "TimedInformation",
    rule_based_scores: dict,
    prompt_overrides: list[dict] | None = None,
) -> str:
    """
    Build judgment prompt using TimedInformation structure.

    This is the enhanced version that uses the Layer 1 structured output.

    Args:
        symbol: Stock ticker symbol
        strategy_mode: "conservative" or "aggressive"
        timed_info: Structured TimedInformation from collector
        rule_based_scores: Existing rule-based agent scores
        prompt_overrides: Optional dynamic prompt overrides from meta-monitor

    Returns:
        Complete prompt string for LLM
    """
    # Format technical context
    tech_info = _format_technical_context(timed_info.technical)

    # Format fundamental context
    fund_info = _format_fundamental_context(timed_info.fundamental)

    # Format structured news with time weights
    news_info = _format_timed_news(timed_info)

    # Format existing rule-based scores
    scores_info = _format_rule_based_scores(rule_based_scores, strategy_mode)

    # Data quality notice
    quality_info = _format_data_quality(timed_info)

    # Strategy-specific guidance (with dynamic overrides from meta-monitor)
    strategy_guidance = _get_strategy_guidance(strategy_mode, prompt_overrides)

    # Market context
    market_info = _format_market_context(timed_info.market)

    prompt = f"""# Investment Judgment Request (Structured Input)

## Target Stock
Symbol: {symbol}
Strategy: {strategy_mode}
Data Collected: {timed_info.collected_at.strftime("%Y-%m-%d %H:%M")}

## Market Context
{market_info}

## Technical Analysis
{tech_info}

## Fundamental Analysis
{fund_info}

## News Analysis (Time-Weighted)
{news_info}

## Rule-Based Scores
{scores_info}

## Data Quality Assessment
{quality_info}

## Strategy Guidance
{strategy_guidance}

## Your Task

Using the time-structured information above, make an investment judgment.

CRITICAL TIME-WEIGHTING RULES:
1. IMMEDIATE news (<24h) has HIGHEST weight - likely NOT priced in yet
2. SHORT-TERM news (1-5d) has HIGH weight - partially priced in
3. MEDIUM-TERM news (1-4w) has LOWER weight - mostly priced in
4. OLDER news provides context only - fully priced in

Think through these steps:
1. Assess breaking/immediate news first (highest impact potential)
2. Evaluate technical signals and price action
3. Consider fundamental context
4. Weigh the rule-based scores as a cross-reference
5. Identify key risks and uncertainties
6. Make a final judgment aligned with strategy mode

## 出力フォーマット (JSON) - 日本語で記述

```json
{{
  "decision": "buy" | "hold" | "avoid",
  "confidence": 0.0 to 1.0,
  "score": 0 to 100,
  "reasoning": {{
    "steps": [
      "ステップ1: 価格動向とテクニカル指標を確認...",
      "ステップ2: ファンダメンタルズを評価...",
      "ステップ3: 最終判断..."
    ],
    "top_factors": [
      "最も重要な要因",
      "2番目に重要な要因",
      "3番目に重要な要因"
    ],
    "decision_point": "判断を決定した重要な洞察",
    "uncertainties": [
      "不確実性1",
      "不確実性2"
    ],
    "confidence_explanation": "この信頼度レベルの理由"
  }},
  "key_factors": [
    {{
      "factor_type": "fundamental" | "technical" | "sentiment" | "macro" | "catalyst",
      "description": "要因の説明",
      "source": "データソース",
      "impact": "positive" | "negative" | "neutral",
      "weight": 0.0 to 1.0,
      "verifiable": true | false
    }}
  ],
  "identified_risks": [
    "リスク1",
    "リスク2"
  ]
}}
```

JSONオブジェクトのみを返してください。追加テキストは不要です。"""

    return prompt


def _format_technical_context(tech) -> str:
    """Format TechnicalContext for the prompt."""
    if not tech:
        return "No technical data available"

    lines = []

    # Price action
    lines.append(f"Current Price: ${tech.current_price:.2f}")
    lines.append(f"Daily Change: {tech.change_pct:+.2f}%")

    # Moving averages
    if tech.sma_20:
        status = "ABOVE" if tech.above_sma_20 else "BELOW"
        lines.append(f"SMA(20): ${tech.sma_20:.2f} ({status})")
    if tech.sma_50:
        status = "ABOVE" if tech.above_sma_50 else "BELOW"
        lines.append(f"SMA(50): ${tech.sma_50:.2f} ({status})")
    if tech.sma_200:
        status = "ABOVE" if tech.above_sma_200 else "BELOW"
        lines.append(f"SMA(200): ${tech.sma_200:.2f} ({status})")

    # RSI
    if tech.rsi_14:
        rsi_status = "OVERBOUGHT" if tech.rsi_14 > 70 else "OVERSOLD" if tech.rsi_14 < 30 else "NEUTRAL"
        lines.append(f"RSI(14): {tech.rsi_14:.1f} ({rsi_status})")

    # Volume
    if tech.volume_ratio:
        vol_status = "HIGH" if tech.volume_ratio > 1.5 else "LOW" if tech.volume_ratio < 0.5 else "NORMAL"
        lines.append(f"Volume Ratio: {tech.volume_ratio:.2f}x ({vol_status})")

    # 52-week range
    if tech.distance_from_52w_high_pct is not None:
        lines.append(f"From 52W High: {tech.distance_from_52w_high_pct:+.1f}%")
    if tech.distance_from_52w_low_pct is not None:
        lines.append(f"From 52W Low: {tech.distance_from_52w_low_pct:+.1f}%")

    # Signals
    signals = []
    if tech.breakout_signal:
        signals.append("BREAKOUT DETECTED")
    if tech.breakdown_signal:
        signals.append("BREAKDOWN DETECTED")
    if signals:
        lines.append(f"\nSIGNALS: {', '.join(signals)}")

    return "\n".join(lines)


def _format_fundamental_context(fund) -> str:
    """Format FundamentalContext for the prompt."""
    if not fund:
        return "No fundamental data available"

    lines = []

    # Valuation
    if fund.pe_ratio:
        lines.append(f"P/E Ratio: {fund.pe_ratio:.1f}")
    if fund.pb_ratio:
        lines.append(f"P/B Ratio: {fund.pb_ratio:.2f}")
    if fund.dividend_yield:
        lines.append(f"Dividend Yield: {fund.dividend_yield:.2f}%")

    # Earnings
    if fund.days_to_earnings is not None:
        if fund.days_to_earnings <= 7:
            lines.append(f"⚠️ EARNINGS IN {fund.days_to_earnings} DAYS")
        else:
            lines.append(f"Next Earnings: {fund.days_to_earnings} days")

    if fund.last_earnings_surprise:
        beat_miss = "BEAT" if fund.last_earnings_surprise > 0 else "MISS"
        lines.append(f"Last Earnings: {beat_miss} by {abs(fund.last_earnings_surprise):.1f}%")

    return "\n".join(lines) if lines else "Limited fundamental data"


def _format_timed_news(timed_info) -> str:
    """Format TimedInformation news with weights."""
    sections = []

    # Get weighted summary
    summary = timed_info.get_weighted_news_summary()

    # Breaking news alert
    if timed_info.has_breaking_news():
        sections.append("🚨 BREAKING NEWS DETECTED - HIGH PRIORITY 🚨\n")

    # Earnings catalyst alert
    if timed_info.has_earnings_catalyst():
        sections.append("📊 EARNINGS CATALYST DETECTED\n")

    # Immediate news
    if timed_info.immediate_news:
        section = ["### IMMEDIATE (<24h) - Weight: 1.0 ***"]
        for news in timed_info.immediate_news[:5]:
            decay = f"(decay: {news.decay_weight:.2f})"
            sentiment = f"[{news.sentiment}]" if news.sentiment else ""
            flags = []
            if news.is_earnings_related:
                flags.append("📊")
            if news.is_analyst_action:
                flags.append("📈")
            if news.is_insider_activity:
                flags.append("👤")
            flag_str = " ".join(flags)
            section.append(f"  • {news.headline} {sentiment} {flag_str} {decay}")
        sections.append("\n".join(section))

    # Short-term news
    if timed_info.short_term_news:
        section = ["### SHORT-TERM (1-5d) - Weight: 0.5 **"]
        for news in timed_info.short_term_news[:3]:
            sentiment = f"[{news.sentiment}]" if news.sentiment else ""
            section.append(f"  • {news.headline} {sentiment}")
        sections.append("\n".join(section))

    # Medium-term news
    if timed_info.medium_term_news:
        section = ["### MEDIUM-TERM (1-4w) - Weight: 0.2 *"]
        for news in timed_info.medium_term_news[:2]:
            section.append(f"  • {news.headline}")
        sections.append("\n".join(section))

    # Weighted sentiment
    if summary.get("weighted_sentiment") is not None:
        ws = summary["weighted_sentiment"]
        sentiment_label = (
            "Very Positive" if ws > 0.6 else
            "Positive" if ws > 0.2 else
            "Neutral" if ws > -0.2 else
            "Negative" if ws > -0.6 else
            "Very Negative"
        )
        sections.append(f"\nWeighted Sentiment Score: {ws:.2f} ({sentiment_label})")

    return "\n\n".join(sections) if sections else "No recent news"


def _format_market_context(market) -> str:
    """Format MarketContext for the prompt."""
    if not market:
        return "Market context unavailable"

    regime_emoji = {
        "risk_on": "🟢",
        "normal": "🔵",
        "caution": "🟡",
        "risk_off": "🟠",
        "crisis": "🔴",
    }

    emoji = regime_emoji.get(market.regime, "⚪")

    lines = [
        f"Regime: {emoji} {market.regime.upper()}",
        f"VIX: {market.vix_level:.1f}",
        f"S&P 500 Trend: {market.sp500_trend.upper()}",
    ]

    if market.sector:
        lines.append(f"Sector: {market.sector}")
        if market.sector_vs_market:
            lines.append(f"Sector vs Market: {market.sector_vs_market}")

    return "\n".join(lines)


def _format_data_quality(timed_info) -> str:
    """Format data quality assessment."""
    freshness = timed_info.data_freshness_score
    completeness = timed_info.data_completeness_score

    freshness_label = (
        "Excellent" if freshness >= 0.9 else
        "Good" if freshness >= 0.7 else
        "Fair" if freshness >= 0.5 else
        "Poor"
    )

    completeness_label = (
        "Complete" if completeness >= 0.9 else
        "Good" if completeness >= 0.7 else
        "Partial" if completeness >= 0.5 else
        "Limited"
    )

    return f"""Data Freshness: {freshness_label} ({freshness:.0%})
Data Completeness: {completeness_label} ({completeness:.0%})
Total News Items: {timed_info.total_news_count}
Immediate News: {timed_info.immediate_news_count}"""


# === Portfolio-Level Judgment ===


PORTFOLIO_SYSTEM_PROMPT = """あなたはポートフォリオマネージャーです。
複数の投資候補を同時に評価し、最適な銘柄の組み合わせを選定します。

重要な原則:
1. 銘柄間の比較を行い、相対的に最も有望な銘柄を選ぶ
2. 現在の保有ポジションとの重複・セクター相関を考慮する
3. 確信度の高い銘柄を優先する
4. 過去の実績データを参考に判断精度を高める
5. 情報が不足する場合は保守的に判断する

出力要件:
- 指定された構造のJSON形式で回答
- すべてのテキストは日本語で記述"""


def build_portfolio_judgment_prompt(
    strategy_mode: str,
    market_regime: str,
    candidates: list,
    current_positions: list,
    available_slots: int,
    available_cash: float,
    news_by_symbol: dict[str, list[dict]] | None = None,
    performance_stats: dict | None = None,
) -> str:
    """Build prompt for portfolio-level judgment.

    Args:
        strategy_mode: Strategy mode string
        market_regime: Current market regime
        candidates: List of PortfolioCandidateSummary
        current_positions: List of PortfolioHolding
        available_slots: Number of open slots
        available_cash: Available cash amount
        news_by_symbol: Dict mapping symbol -> list of news dicts
        performance_stats: Structured performance data from build_performance_stats()

    Returns:
        Complete prompt string for LLM
    """
    strategy_guidance = _get_strategy_guidance(strategy_mode)

    # Current holdings table
    holdings_section = ""
    if current_positions:
        rows = []
        for pos in current_positions:
            rows.append(
                f"| {pos.symbol} | {pos.pnl_pct:+.1f}% | {pos.hold_days}日 |"
            )
        holdings_section = f"""## 現在の保有ポジション（{len(current_positions)}銘柄）
| Symbol | PnL% | 保有日数 |
|--------|------|----------|
{chr(10).join(rows)}"""
    else:
        holdings_section = "## 現在の保有ポジション\nなし"

    # Candidates table
    candidate_rows = []
    for c in candidates:
        rsi_str = f"{c.rsi:.0f}" if c.rsi is not None else "-"
        vol_str = f"{c.volume_ratio:.1f}x" if c.volume_ratio is not None else "-"
        sector_str = c.sector or "-"
        candidate_rows.append(
            f"| {c.symbol} | {c.composite_score} | {c.percentile_rank} | "
            f"{c.price:.2f} | {c.change_pct:+.1f}% | {rsi_str} | "
            f"{c.key_signal} | {sector_str} |"
        )

    candidates_section = f"""## 投資候補（{len(candidates)}銘柄）
| Symbol | Score | Pctile | Price | Chg% | RSI | Signal | Sector |
|--------|-------|--------|-------|------|-----|--------|--------|
{chr(10).join(candidate_rows)}"""

    # News section (top candidates only)
    news_section = ""
    if news_by_symbol:
        news_lines = ["## 候補の注目ニュース"]
        for symbol, news_list in list(news_by_symbol.items())[:10]:
            for news in news_list[:2]:
                headline = news.get("headline", "")[:100]
                sentiment = news.get("sentiment", "")
                sent_str = f" [{sentiment}]" if sentiment else ""
                news_lines.append(f"- **{symbol}**: {headline}{sent_str}")
        if len(news_lines) > 1:
            news_section = "\n".join(news_lines)

    # Performance stats section
    perf_section = ""
    if performance_stats:
        perf_lines = ["## 過去の判断実績（構造化データ）"]
        if "buy_count" in performance_stats:
            win_rate = performance_stats.get("buy_win_rate", 0)
            avg_ret = performance_stats.get("buy_avg_return", 0)
            perf_lines.append(
                f"- Buy判断: {performance_stats['buy_count']}件中"
                f"{performance_stats.get('buy_win_count', 0)}件が利益"
                f"（勝率{win_rate:.1f}%、平均リターン{avg_ret:+.2f}%）"
            )
        if "avoid_count" in performance_stats:
            accuracy = performance_stats.get("avoid_accuracy", 0)
            perf_lines.append(
                f"- Avoid判断: {performance_stats['avoid_count']}件中"
                f"{performance_stats.get('avoid_correct_count', 0)}件が正解"
                f"（精度{accuracy:.1f}%）"
            )
        if len(perf_lines) > 1:
            perf_section = "\n".join(perf_lines)

    prompt = f"""# ポートフォリオ判断リクエスト

## 市場環境
- マーケットレジーム: {market_regime}
- 戦略: {strategy_mode}
- 投資枠: {available_slots}枠
- 利用可能資金: {available_cash:,.0f}

{holdings_section}

{candidates_section}

{news_section}

{perf_section}

## 戦略ガイダンス
{strategy_guidance}

## タスク
上記候補を比較し、最大{available_slots}銘柄の買い推奨を確信度順に選定してください。

判断のポイント:
1. 候補同士を比較して相対的な魅力度を評価
2. 現在の保有銘柄とのセクター分散を考慮
3. 確信度が低い銘柄は無理に買わない（0枠推奨も可）
4. 各銘柄の推奨理由を具体的に説明

## 出力フォーマット (JSON) - 日本語で記述

```json
{{
  "recommended_buys": [
    {{
      "symbol": "AAPL",
      "action": "buy",
      "conviction": 0.85,
      "allocation_hint": "high",
      "reasoning": "買い推奨の理由..."
    }}
  ],
  "skipped": [
    {{
      "symbol": "TSLA",
      "action": "skip",
      "conviction": 0.0,
      "allocation_hint": "normal",
      "reasoning": "見送り理由..."
    }}
  ],
  "portfolio_reasoning": "ポートフォリオ全体の判断理由...",
  "risk_assessment": "全体リスク評価..."
}}
```

JSONオブジェクトのみを返してください。追加テキストは不要です。"""

    return prompt


# === Exit Judgment ===

EXIT_SYSTEM_PROMPT = """あなたは売却判断の専門家です。
保有ポジションについて、売却すべきか保持すべきかを判断します。

重要な原則:
1. 利益が出ている銘柄はモメンタムが続く限り保持を優先
2. ただし、反転シグナルがあれば利確も推奨
3. スコアが下がった銘柄でも、ニュースやカタリストがあれば保持を検討
4. 保有期間が長い銘柄は、明確な理由がなければ売却を推奨

出力要件:
- 指定された構造のJSON形式で回答
- すべてのテキストは日本語で記述"""


def build_exit_judgment_prompt(
    positions_for_review: list[dict],
    market_regime: str,
) -> str:
    """Build prompt for exit judgment on multiple positions.

    Args:
        positions_for_review: List of dicts with position info + trigger reason
        market_regime: Current market regime

    Returns:
        Complete prompt string
    """
    position_rows = []
    for p in positions_for_review:
        news_str = ""
        if p.get("top_news"):
            news_str = f" | ニュース: {p['top_news'][:80]}"
        position_rows.append(
            f"- **{p['symbol']}**: PnL {p['pnl_pct']:+.1f}%, "
            f"保有{p['hold_days']}日, トリガー: {p['trigger_reason']}"
            f"{news_str}"
        )

    prompt = f"""# 売却判断リクエスト

## 市場環境
- マーケットレジーム: {market_regime}

## 判断対象ポジション
以下のポジションについて、ルールベースの売却シグナルが出ていますが、
AI判断で保持を延長すべきかを評価してください。

{chr(10).join(position_rows)}

## 判断基準
- take_profit: +8%以上の利益。モメンタムが継続しているなら保持延長も可
- score_drop: スコアが閾値以下に低下。ニュースやカタリストで回復の見込みがあるか
- max_hold: 保有10日超。明確なカタリスト待ちでなければ売却推奨

## 制約
- 保持延長は最大5日（合計15日で強制売却）
- 不確実な場合は売却を推奨（リスク回避）

## 出力フォーマット (JSON)

```json
{{
  "exit_decisions": [
    {{
      "symbol": "AAPL",
      "decision": "close" | "hold",
      "confidence": 0.0 to 1.0,
      "reasoning": "判断理由...",
      "hold_duration_hint": null | 1-5,
      "risks_of_holding": ["リスク1"],
      "risks_of_closing": ["リスク1"]
    }}
  ]
}}
```

JSONオブジェクトのみを返してください。"""

    return prompt
