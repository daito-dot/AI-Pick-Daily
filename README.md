# AI Pick Daily

AIを活用した米国株の日次銘柄推奨システム。2つの戦略モード（Conservative / Aggressive）を並行運用し、パフォーマンスを比較・記録します。

## 戦略モード

### V1: Conservative（バランス型）
4ファクター均衡型の低リスク戦略。

| ファクター | ウェイト | 説明 |
|-----------|---------|------|
| Trend | 35% | SMA20/50/200のトレンド方向 |
| Momentum | 35% | RSI、MACD、価格モメンタム |
| Value | 20% | P/E、P/Bの相対バリュエーション |
| Sentiment | 10% | ニュース量とセンチメント |

- 最大5銘柄/日
- 最低スコア: 60点
- 対象: S&P 500 上位50銘柄

### V2: Aggressive（モメンタム重視型）
高リターン志向のモメンタム集中戦略。

| ファクター | ウェイト | 説明 |
|-----------|---------|------|
| Momentum 12-1 | 40% | 12ヶ月リターン（直近1ヶ月除く） |
| Breakout | 25% | 出来高を伴うブレイクアウト検出 |
| Catalyst | 20% | 決算サプライズ、ギャップアップ |
| Risk Adjusted | 15% | VIX連動リスク調整 |

- 最大3銘柄/日
- 最低スコア: 75点
- 8%トレーリングストップ推奨

## アーキテクチャ

```
┌─────────────────────────────────────────────────────┐
│                  GitHub Actions                      │
│  ┌─────────────┐              ┌─────────────┐       │
│  │ Morning Batch│              │ Evening Batch│       │
│  │  (07:00 JST) │              │  (06:00 JST) │       │
│  └──────┬──────┘              └──────┬──────┘       │
└─────────┼────────────────────────────┼──────────────┘
          │                            │
          ▼                            ▼
┌─────────────────────────────────────────────────────┐
│                    Python Backend                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ Finnhub  │  │  Gemini  │  │  Dual Scoring    │   │
│  │  Client  │  │  Client  │  │  V1 + V2 Pipeline │   │
│  └──────────┘  └──────────┘  └──────────────────┘   │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│                     Supabase                         │
│  ┌────────────┐  ┌────────────┐  ┌────────────────┐ │
│  │ daily_picks │  │stock_scores│  │ market_regime  │ │
│  │(+strategy)  │  │(+strategy) │  │    _history    │ │
│  └────────────┘  └────────────┘  └────────────────┘ │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│                  Next.js Frontend                    │
│  ┌──────────────────────────────────────────────┐   │
│  │   V1 Conservative  │   V2 Aggressive          │   │
│  │   (Blue Theme)     │   (Orange Theme)         │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

## プロジェクト構成

```
AI-Pick-Daily/
├── src/                          # Python バックエンド
│   ├── config.py                 # 設定管理
│   ├── data/
│   │   ├── finnhub_client.py     # 市場データ取得
│   │   └── supabase_client.py    # DB操作
│   ├── llm/
│   │   ├── client.py             # LLM抽象化
│   │   └── gemini_client.py      # Gemini実装
│   └── scoring/
│       ├── agents.py             # V1エージェント（Trend/Mom/Value/Sent）
│       ├── agents_v2.py          # V2エージェント（Mom12-1/Breakout/Catalyst/Risk）
│       ├── composite.py          # V1スコアリング
│       ├── composite_v2.py       # デュアルスコアリング
│       └── market_regime.py      # 相場環境判定
├── scripts/
│   ├── daily_scoring.py          # 朝バッチ（デュアルモード）
│   └── daily_review.py           # 夕方バッチ
├── web/                          # Next.js フロントエンド
│   └── src/
│       ├── app/
│       │   └── page.tsx          # デュアル戦略表示
│       ├── components/
│       └── lib/
│           └── supabase.ts       # Supabase クライアント
├── supabase/
│   └── migrations/
│       ├── 001_initial_schema.sql
│       └── 002_add_strategy_mode.sql  # デュアルモード対応
├── .github/
│   └── workflows/
│       ├── morning_batch.yml     # 朝スコアリング
│       └── evening_batch.yml     # 夕方レビュー
└── docs/
    ├── DEPLOYMENT.md             # デプロイ手順
    └── STRATEGY_V2_PROPOSAL.md   # V2戦略提案書
```

## セットアップ

### 必要なもの

- Python 3.11+
- Node.js 18+
- Supabase アカウント
- Finnhub API キー
- Gemini API キー

### ローカル開発

```bash
# Python依存関係
pip install -r requirements.txt

# 環境変数設定
cp .env.example .env
# .env を編集

# フロントエンド
cd web
npm install
npm run dev
```

### 環境変数

```env
# LLM
GEMINI_API_KEY=your_gemini_api_key

# Data
FINNHUB_API_KEY=your_finnhub_api_key

# Database
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# Strategy (optional)
STRATEGY_MODE=both  # conservative, aggressive, or both
```

## デプロイ

詳細は [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) を参照。

1. Supabase: マイグレーション実行
2. GitHub: Secrets設定
3. Vercel: Next.jsデプロイ

## 免責事項

本システムは教育・研究目的で作成されています。投資判断は自己責任で行ってください。過去のパフォーマンスは将来の結果を保証するものではありません。
