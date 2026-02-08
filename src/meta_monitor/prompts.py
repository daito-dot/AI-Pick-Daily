"""Prompt templates for meta-monitor LLM diagnosis."""

META_DIAGNOSIS_SYSTEM_PROMPT = """あなたは株式AIシステムのメタ監視エージェントです。
パフォーマンス劣化の根本原因を分析し、具体的な修正アクションを提案してください。

以下のアクションタイプが利用可能です:
1. prompt_override: 判断プロンプトに追加ガイダンスを注入（最大500文字）
2. threshold_adjust: スコア閾値の調整（step制約あり）
3. weight_adjust: ファクター重みの調整（step制約あり）
4. parameter_adjust: ポートフォリオ・検知パラメータの調整
   利用可能パラメータ: take_profit_pct, stop_loss_pct, max_hold_days,
   max_positions, mdd_warning_pct, win_rate_drop_ratio, return_decline_threshold,
   missed_spike_threshold, cooldown_days, prompt_expiry_days, confidence_drift_threshold
   ※各パラメータにはmin/max/stepの安全制約があり、自動的にクランプされます

回答は必ず以下のJSON形式で返してください:
{
  "root_causes": ["原因1", "原因2"],
  "confidence": 0.7,
  "recommended_actions": [
    {
      "type": "prompt_override",
      "override_text": "追加ガイダンス文",
      "rationale": "この変更を提案する理由"
    },
    {
      "type": "threshold_adjust",
      "target": "threshold",
      "change": -5,
      "rationale": "理由"
    },
    {
      "type": "weight_adjust",
      "factor": "momentum",
      "change": 0.05,
      "rationale": "理由"
    },
    {
      "type": "parameter_adjust",
      "param_name": "take_profit_pct",
      "change": -2.0,
      "rationale": "理由"
    }
  ]
}"""


def build_diagnosis_prompt(
    strategy_mode: str,
    signals: list[dict],
    metrics: dict,
    recent_reflections: list[dict],
    recent_judgments: list[dict],
    current_config: dict,
    active_overrides: list[dict],
    strategy_parameters: list[dict] | None = None,
) -> str:
    """Build diagnosis prompt with all available context."""

    # Format signals
    signals_text = "\n".join(
        f"- [{s['severity'].upper()}] {s['trigger_type']}: {s['details']}"
        for s in signals
    )

    # Format metrics
    metrics_text = f"""現在のローリング指標:
- 7日勝率: {metrics.get('win_rate_7d', 'N/A')}%
- 30日勝率: {metrics.get('win_rate_30d', 'N/A')}%
- 7日平均リターン: {metrics.get('avg_return_7d', 'N/A')}%
- 30日平均リターン: {metrics.get('avg_return_30d', 'N/A')}%
- 7日見逃し率: {metrics.get('missed_rate_7d', 'N/A')}%
- 7日判断数: {metrics.get('total_judgments_7d', 0)}
- 30日判断数: {metrics.get('total_judgments_30d', 0)}"""

    # Format reflections (from existing write-only reflection_records)
    if recent_reflections:
        reflection_parts = []
        for r in recent_reflections[:3]:
            analysis = r.get("analysis", {})
            if isinstance(analysis, str):
                reflection_parts.append(f"- {analysis[:300]}")
            elif isinstance(analysis, dict):
                suggestions = analysis.get("suggestions", [])
                patterns = analysis.get("failure_patterns", [])
                if suggestions:
                    reflection_parts.append(f"- 提案: {suggestions[:3]}")
                if patterns:
                    reflection_parts.append(f"- 失敗パターン: {patterns[:3]}")
        reflections_text = "\n".join(reflection_parts) if reflection_parts else "なし"
    else:
        reflections_text = "なし"

    # Format recent judgments summary
    if recent_judgments:
        buy_count = sum(1 for j in recent_judgments if j.get("decision") == "buy")
        avoid_count = sum(1 for j in recent_judgments if j.get("decision") == "avoid")
        correct = sum(1 for j in recent_judgments if j.get("outcome_aligned"))
        incorrect = sum(1 for j in recent_judgments if j.get("outcome_aligned") is False)

        # Find common failure patterns
        failed = [j for j in recent_judgments if j.get("outcome_aligned") is False]
        failed_symbols = [j.get("symbol", "?") for j in failed[:5]]

        judgments_text = f"""直近7日の判断サマリー:
- Buy判断: {buy_count}件
- Avoid判断: {avoid_count}件
- 正解: {correct}件, 不正解: {incorrect}件
- 不正解銘柄: {', '.join(failed_symbols) if failed_symbols else 'なし'}"""
    else:
        judgments_text = "判断データなし"

    # Format current config
    config_text = f"""現在の設定:
- 閾値: {current_config.get('threshold', 'N/A')}
- Confidence閾値: {current_config.get('confidence_threshold', 'N/A')}
- ファクター重み: {current_config.get('factor_weights', {})}"""

    # Format active overrides
    if active_overrides:
        overrides_text = "\n".join(
            f"- {o.get('override_text', '')[:100]} (期限: {o.get('expires_at', 'N/A')})"
            for o in active_overrides
        )
    else:
        overrides_text = "なし"

    # Format strategy parameters
    if strategy_parameters:
        params_lines = []
        for p in strategy_parameters:
            params_lines.append(
                f"- {p['param_name']}: {p['current_value']} "
                f"(範囲: {p['min_value']}-{p['max_value']}, step: {p['step']})"
            )
        params_text = "\n".join(params_lines)
    else:
        params_text = "パラメータ情報なし"

    return f"""# パフォーマンス劣化の診断

## 戦略: {strategy_mode}

## 検知されたシグナル
{signals_text}

## {metrics_text}

## 直近のリフレクション分析結果
{reflections_text}

## {judgments_text}

## {config_text}

## 現在のプロンプトオーバーライド
{overrides_text}

## 現在のパラメータ設定
{params_text}

## 診断タスク

上記のデータを分析し、パフォーマンス劣化の根本原因を特定してください。
そして、利用可能なアクション（prompt_override, threshold_adjust, weight_adjust, parameter_adjust）から
最も効果的な修正を1-3個提案してください。

注意:
- 変更は控えめに（大きな変更より小さな調整を優先）
- 市場環境の変化（レジーム転換）が原因の場合はプロンプト修正を優先
- parameter_adjustでは各パラメータのstep制約に注意（1回の変更はstep以内に制限されます）
- データ不足が原因の場合は介入を見送る判断も可
- 回答は指定のJSON形式で返してください"""
