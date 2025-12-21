# AI Pick Daily - アーキテクチャ設計書

## システム概要

AI Pick Dailyは、米国株のAI銘柄推奨システムです。2つの異なる投資戦略を並行運用し、パフォーマンスを比較・記録します。

---

## デュアル戦略アーキテクチャ

```
                    ┌─────────────────────────────────────┐
                    │         Morning Batch (07:00 JST)    │
                    │         daily_scoring.py             │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │         Market Regime Detection      │
                    │   VIX + S&P500 SMA Deviation Check   │
                    └─────────────────┬───────────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┐
              │                                               │
   ┌──────────▼──────────┐                     ┌──────────────▼──────────────┐
   │  V1: Conservative   │                     │     V2: Aggressive          │
   │  (agents.py)        │                     │     (agents_v2.py)          │
   ├─────────────────────┤                     ├─────────────────────────────┤
   │ Trend:     35%      │                     │ Momentum 12-1:  40%         │
   │ Momentum:  35%      │                     │ Breakout:       25%         │
   │ Value:     20%      │                     │ Catalyst:       20%         │
   │ Sentiment: 10%      │                     │ Risk Adjusted:  15%         │
   ├─────────────────────┤                     ├─────────────────────────────┤
   │ Max Picks: 5        │                     │ Max Picks: 3                │
   │ Min Score: 60       │                     │ Min Score: 75               │
   └──────────┬──────────┘                     └──────────────┬──────────────┘
              │                                               │
              └───────────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │            Supabase                  │
                    │   strategy_mode = 'conservative'     │
                    │   strategy_mode = 'aggressive'       │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │         Next.js Frontend             │
                    │   Side-by-side Strategy Display      │
                    └─────────────────────────────────────┘
```

---

## コンポーネント詳細

### 1. スコアリングエージェント

#### V1 Agents (Conservative)

| Agent | 責務 | 主要指標 |
|-------|------|----------|
| TrendAgent | トレンド方向判定 | SMA20/50/200、Golden Cross |
| MomentumAgent | モメンタム評価 | RSI、MACD、価格変化率 |
| ValueAgent | バリュエーション | P/E、P/B対セクター平均 |
| SentimentAgent | センチメント | ニュース量、センチメントスコア |

#### V2 Agents (Aggressive)

| Agent | 責務 | 主要指標 |
|-------|------|----------|
| Momentum12_1Agent | 12-1モメンタム | 12ヶ月リターン（直近1ヶ月除く） |
| BreakoutAgent | ブレイクアウト検出 | 新高値、出来高サージ、タイトベース |
| CatalystAgent | カタリスト検出 | 決算サプライズ、ギャップ、アナリスト修正 |
| RiskAdjustedAgent | リスク調整 | VIX、個別ボラティリティ、ドローダウン |

### 2. Market Regime（相場環境）

| Regime | 条件 | 影響 |
|--------|------|------|
| Normal | VIX < 20, SMA乖離 < 3% | 通常運用 |
| Adjustment | VIX 20-30 or SMA乖離 3-5% | ピック数削減 |
| Crisis | VIX > 30 or SMA乖離 > 5% | 推奨停止 |

### 3. データフロー

```
Finnhub API
    │
    ├── Quote（現在値、前日終値）
    ├── Candles（日足OHLCV、250日分）
    ├── Basic Financials（P/E、P/B、52週高値安値）
    ├── Company News（直近7日）
    └── Earnings Calendar（決算日程）
           │
           ▼
    ┌─────────────────┐
    │  StockData      │──▶ V1 Scoring
    │  (Base)         │
    └─────────────────┘
           │
           ▼
    ┌─────────────────┐
    │  V2StockData    │──▶ V2 Scoring
    │  (Extended)     │
    │  + vix_level    │
    │  + gap_pct      │
    │  + earnings_    │
    │    surprise_pct │
    └─────────────────┘
```

---

## データベーススキーマ

### 主要テーブル

```sql
-- 日次ピック（戦略別）
daily_picks (
  id, batch_date, symbols[], pick_count,
  market_regime, strategy_mode, status
)
UNIQUE (batch_date, strategy_mode)

-- 銘柄スコア（戦略別）
stock_scores (
  id, batch_date, symbol, strategy_mode,
  -- V1 scores
  trend_score, momentum_score, value_score, sentiment_score,
  -- V2 scores
  momentum_12_1_score, breakout_score, catalyst_score, risk_adjusted_score,
  -- Common
  composite_score, percentile_rank, reasoning
)
UNIQUE (batch_date, symbol, strategy_mode)

-- 相場環境履歴
market_regime_history (
  id, check_date, vix_level, market_regime,
  sp500_sma20_deviation_pct, volatility_cluster_flag
)
UNIQUE (check_date)
```

### ビュー

```sql
-- 戦略パフォーマンス比較
strategy_comparison (
  pick_date, strategy_mode, pick_count,
  avg_return_1d, avg_return_5d, win_rate_5d
)

-- 累積リターン
cumulative_performance (
  strategy_mode, pick_date,
  daily_return, cumulative_return
)
```

---

## 設定管理

### 環境変数

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `STRATEGY_MODE` | 実行戦略 | `both` |
| `LLM_PROVIDER` | LLMプロバイダー | `gemini` |
| `SCORING_MODEL` | スコアリングモデル | `gemini-2.5-flash-lite` |
| `ANALYSIS_MODEL` | 分析モデル | `gemini-3-flash` |

### StrategyConfig

```python
@dataclass
class StrategyConfig:
    mode: Literal["conservative", "aggressive", "both"] = "both"

    v1_weights = {"trend": 0.35, "momentum": 0.35, "value": 0.20, "sentiment": 0.10}
    v2_weights = {"momentum_12_1": 0.40, "breakout": 0.25, "catalyst": 0.20, "risk_adjusted": 0.15}

    v1_max_picks: int = 5
    v1_min_score: int = 60
    v2_max_picks: int = 3
    v2_min_score: int = 75
    v2_trailing_stop_pct: float = 0.08
```

---

## フロントエンド

### ページ構成

| ページ | 説明 |
|--------|------|
| `/` | 本日のピック（V1/V2並列表示） |
| `/history` | 過去のピック履歴 |
| `/performance` | パフォーマンス分析 |

### UI設計

- **V1 Conservative**: 青系カラー（bg-blue-50, text-blue-800）
- **V2 Aggressive**: オレンジ系カラー（bg-orange-50, text-orange-800）
- **Crisis Mode**: 赤系警告表示

---

## 今後の拡張

1. **バックテスト機能**: 過去データでの戦略検証
2. **アラート機能**: Slack/Discord通知
3. **モバイル対応**: レスポンシブUI改善
4. **追加戦略**: V3 (セクターローテーション) など
