---
allowed-tools: WebSearch, WebFetch, Bash(python:*), Read, Grep
argument-hint: <symbol|all|market|jp|us|history>
description: 銘柄/マーケットの追加リサーチ（保存・判断変更追跡機能付き）
---

# Stock Research Command

指定された銘柄またはマーケット全体について追加リサーチを行います。
リサーチ結果はDBに保存され、判断変更の追跡が可能です。

## 引数

- `$ARGUMENTS`: 以下のいずれか
  - **銘柄シンボル**: `AAPL`, `TSLA`, `7203.T` など → 個別銘柄リサーチ
  - **`all`**: 本日の全採用銘柄のサマリー
  - **`market`**: マーケット状況（VIX、レジーム、主要指数）
  - **`jp`**: 日本株のみのサマリー
  - **`us`**: 米国株のみのサマリー
  - **`history`**: リサーチ履歴を表示
  - **`history AAPL`**: 特定銘柄のリサーチ履歴

## 実行フロー

### Step 1: システムデータ取得

```bash
python scripts/research_stock.py $ARGUMENTS --save
```

`--save` フラグでリサーチをDBに保存。Research IDが返される。

### Step 2: 外部リサーチ（WebSearch）

**個別銘柄の場合:**
- `[SYMBOL] stock news today`
- `[SYMBOL] analyst rating upgrade downgrade`
- 日本株: `[SYMBOL] 株価 ニュース 最新`

**マーケット全体の場合:**
- `stock market news today`
- `S&P 500 VIX volatility`
- `日経平均 市況`

### Step 3: 比較分析

以下の観点で分析し、ユーザーに報告：

1. **センチメント整合性**: 最新ニュースの雰囲気はシステム判断と一致？
2. **新規材料**: バッチ実行後に出た重要ニュース
3. **リスク更新**: 新たに識別すべきリスク
4. **判断変更の必要性**: システム判断を見直すべき材料があるか

### Step 4: 判断記録（オプション）

リサーチ結果に基づいてユーザーが判断を変更する場合：

```bash
python scripts/research_stock.py override <research_id> <decision> "理由"
```

- `decision`: `buy`, `hold`, `avoid`, `no_change`

## 出力フォーマット

### 個別銘柄

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 リサーチ結果: [SYMBOL]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【システム判断】
  判定: BUY (信頼度: 75%)
  スコア: ルールベース 68点 / LLM 82点
  更新日時: 2024-12-26 16:00

【キーファクター】
  ✅ Strong momentum continuation
  ✅ Positive earnings catalyst upcoming
  ⚠️ High valuation relative to sector

【識別済みリスク】
  • Market volatility risk
  • Sector rotation concern

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【最新ニュース】(WebSearch結果)
  📰 [ニュースタイトル]
     [要約]

【アナリスト動向】
  • [最新情報]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【比較分析】
  センチメント整合性: 一致 ✓

  🟢 判断を支持する材料:
    • ニュースがポジティブ

  🔴 注意すべき材料:
    • 特になし

【結論】
  システム判断は現在も有効

[Saved] Research ID: abc12345
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 履歴表示

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📜 リサーチ履歴
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [AAPL] 2024-12-26 15:30
    System: BUY (75%)
    Override: HOLD
    Reason: ニュースでリスク発覚...
    ID: abc12345...

  [MARKET] 2024-12-26 09:00
    VIX上昇傾向を確認
    ID: def67890...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 判断変更の記録

リサーチ後に判断を変更する場合、必ず記録：

```bash
# システム判断を支持（変更なし）
python scripts/research_stock.py override abc12345 no_change

# 判断を変更
python scripts/research_stock.py override abc12345 hold "決算後のガイダンスが弱気だったため"
```

これにより：
- 後から「なぜ判断を変えたか」を追跡可能
- システム判断の精度評価に活用
- 学習データとして将来のモデル改善に貢献

## データベーステーブル

`research_logs` テーブルに保存：
- `research_type`: symbol/all/market/jp/us
- `symbol`: 銘柄（個別の場合）
- `system_data`: リサーチ時点のシステムデータ（JSON）
- `external_findings`: 外部リサーチの要約
- `news_sentiment`: positive/negative/neutral/mixed
- `sentiment_alignment`: aligned/conflicting/partial
- `override_decision`: buy/hold/avoid/no_change
- `override_reason`: 変更理由

## 注意事項

- リサーチはDBに自動保存される（`--save` フラグ使用時）
- 投資判断は自己責任
- バッチ実行からの時間経過を考慮すること
