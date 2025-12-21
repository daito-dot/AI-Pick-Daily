# AI Pick Daily - デプロイ手順書

本ドキュメントでは、AI Pick Dailyを本番環境にデプロイする手順を説明します。

---

## 目次

1. [前提条件](#1-前提条件)
2. [Supabaseセットアップ](#2-supabaseセットアップ)
3. [APIキーの取得](#3-apiキーの取得)
4. [GitHub Secretsの設定](#4-github-secretsの設定)
5. [Vercelデプロイ](#5-vercelデプロイ)
6. [動作確認](#6-動作確認)
7. [トラブルシューティング](#7-トラブルシューティング)

---

## 1. 前提条件

以下のアカウントが必要です（すべて無料枠で開始可能）:

- [ ] GitHub アカウント
- [ ] Supabase アカウント (https://supabase.com)
- [ ] Vercel アカウント (https://vercel.com)
- [ ] Finnhub アカウント (https://finnhub.io)
- [ ] Google AI Studio アカウント (https://aistudio.google.com)

---

## 2. Supabaseセットアップ

### 2.1 プロジェクト作成

1. [Supabase Dashboard](https://supabase.com/dashboard) にログイン
2. **New Project** をクリック
3. 以下を入力:
   - **Name**: `ai-pick-daily`
   - **Database Password**: 強力なパスワードを生成（保存しておく）
   - **Region**: `Northeast Asia (Tokyo)` を推奨
4. **Create new project** をクリック（2-3分待つ）

### 2.2 データベーススキーマ作成

1. 左メニューから **SQL Editor** を開く
2. **New query** をクリック
3. `supabase/migrations/001_initial_schema.sql` の内容を貼り付け
4. **Run** をクリック
5. 成功メッセージを確認

### 2.3 デュアル戦略モード対応（V1/V2）

1. **SQL Editor** で新しいクエリを作成
2. `supabase/migrations/002_add_strategy_mode.sql` の内容を貼り付け
3. **Run** をクリック
4. 以下が追加されたことを確認:
   - `strategy_mode` カラム（daily_picks, stock_scores, performance_log）
   - V2スコアカラム（momentum_12_1_score, breakout_score, catalyst_score, risk_adjusted_score）
   - `strategy_comparison` ビュー
   - `cumulative_performance` ビュー

### 2.4 接続情報の取得

1. 左メニューから **Project Settings** → **API** を開く
2. 以下をメモ:
   - **Project URL**: `https://xxxxx.supabase.co`
   - **anon public key**: `eyJhbGciOiJI...`（公開用）
   - **service_role key**: `eyJhbGciOiJI...`（サーバー用、秘密）

---

## 3. APIキーの取得

### 3.1 Finnhub API Key

1. [Finnhub](https://finnhub.io) にログイン
2. **Dashboard** → **API Keys** を開く
3. **Free** プランのAPIキーをコピー

> 無料枠: 60 calls/minute

### 3.2 Gemini API Key

1. [Google AI Studio](https://aistudio.google.com/apikey) にアクセス
2. **Create API Key** をクリック
3. プロジェクトを選択（または新規作成）
4. APIキーをコピー

> 無料枠: 詳細は[料金ページ](https://ai.google.dev/pricing)参照

---

## 4. GitHub Secretsの設定

### 4.1 リポジトリSecrets追加

1. GitHubリポジトリの **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** で以下を追加:

| Name | Value | 説明 |
|------|-------|------|
| `SUPABASE_URL` | `https://xxxxx.supabase.co` | Supabase Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJhbGciOiJI...` | Supabase service_role key |
| `FINNHUB_API_KEY` | `xxxxxxxxxx` | Finnhub APIキー |
| `GEMINI_API_KEY` | `AIza...` | Google AI APIキー |

### 4.2 Variables追加（オプション）

**Settings** → **Secrets and variables** → **Actions** → **Variables** タブ:

| Name | Value | 説明 |
|------|-------|------|
| `LLM_PROVIDER` | `gemini` | LLMプロバイダー |
| `SCORING_MODEL` | `gemini-2.5-flash-lite` | スコアリング用モデル |
| `ANALYSIS_MODEL` | `gemini-3-flash` | 分析用モデル |
| `STRATEGY_MODE` | `both` | 戦略モード（`conservative`, `aggressive`, `both`） |

---

## 5. Vercelデプロイ

### 5.1 Vercelプロジェクト作成

1. [Vercel Dashboard](https://vercel.com/dashboard) にログイン
2. **Add New** → **Project**
3. **Import Git Repository** でリポジトリを選択
4. **Configure Project**:
   - **Framework Preset**: `Next.js`
   - **Root Directory**: `web`
   - **Build Command**: `npm run build`
   - **Output Directory**: `.next`

### 5.2 環境変数設定

**Environment Variables** セクションで追加:

| Key | Value |
|-----|-------|
| `NEXT_PUBLIC_SUPABASE_URL` | `https://xxxxx.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `eyJhbGciOiJI...`（anon key） |

### 5.3 デプロイ実行

1. **Deploy** をクリック
2. ビルド完了を待つ（2-3分）
3. デプロイURLを確認（例: `https://ai-pick-daily.vercel.app`）

### 5.4 カスタムドメイン（オプション）

1. **Project Settings** → **Domains**
2. カスタムドメインを追加
3. DNS設定を行う

---

## 6. 動作確認

### 6.1 GitHub Actions確認

1. **Actions** タブを開く
2. **Morning Scoring Batch** ワークフローを手動実行:
   - **Run workflow** → **Run workflow**
3. ログを確認し、エラーがないことを確認

### 6.2 Supabaseデータ確認

1. Supabase Dashboard → **Table Editor**
2. 以下のテーブルにデータが入っていることを確認:
   - `market_regime_history`
   - `stock_scores`（`strategy_mode` = 'conservative' と 'aggressive' の両方）
   - `daily_picks`（`strategy_mode` = 'conservative' と 'aggressive' の両方）

3. **SQL Editor** で戦略比較ビューを確認:
   ```sql
   SELECT * FROM strategy_comparison ORDER BY pick_date DESC LIMIT 10;
   ```

### 6.3 フロントエンド確認

1. Vercelの本番URLにアクセス
2. V1 (Conservative) と V2 (Aggressive) が並んで表示されることを確認
3. 各戦略のピック銘柄とスコアが正しく表示されることを確認
4. 「全スコア比較」テーブルでV1/V2の差分が表示されることを確認

---

## 7. トラブルシューティング

### GitHub Actions が失敗する

**症状**: `ModuleNotFoundError` や `ImportError`

**解決策**:
```bash
# requirements.txt が正しいか確認
pip install -r requirements.txt
```

### Supabase接続エラー

**症状**: `supabaseUrl is required`

**解決策**:
1. 環境変数が正しく設定されているか確認
2. Vercelの環境変数を再確認
3. 再デプロイを実行

### Finnhub Rate Limit

**症状**: `429 Too Many Requests`

**解決策**:
- 無料枠は60 calls/minute
- バッチ処理間隔を調整（現在0.5秒）
- 有料プランへのアップグレードを検討

### Gemini API エラー

**症状**: `quota exceeded` または `invalid API key`

**解決策**:
1. APIキーが正しいか確認
2. [Google AI Studio](https://aistudio.google.com) で使用量を確認
3. 必要に応じて課金を有効化

---

## スケジュール一覧

| ワークフロー | スケジュール (UTC) | 日本時間 |
|-------------|-------------------|---------|
| Morning Scoring | 22:00 Sun-Thu | 07:00 Mon-Fri |
| Evening Review | 21:00 Mon-Fri | 06:00 Tue-Sat |

---

## 次のステップ

- [ ] モニタリング設定（Slack/Discord通知）
- [ ] バックテスト実行
- [ ] パフォーマンス分析レポート自動化

---

## サポート

問題が発生した場合:
1. GitHub Issuesで報告
2. ログファイル（`logs/`）を確認
3. Supabaseのログを確認
