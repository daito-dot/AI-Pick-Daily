# 4層アーキテクチャ実装サマリー

## 実装完了日: 2024-12-22

## 概要

研究知見に基づき、表面的なそれっぽさを排除した実践的な4層アーキテクチャを実装しました。

### 採用した知見（価値あり）
- **Chain-of-Thought (CoT)**: +17%の精度向上（FinCoT研究より）
- **時間軸別情報分類**: リードタイム3-5時間〜13週間を考慮
- **判断理由の記録**: 推論トレースの完全保存
- **振り返りフレームワーク**: Reflexionパターン（メモリ+反省）
- **情報の妥当性評価**: 結果ではなく推論過程を評価

### 排除した概念（表面的）
- マルチエージェント構成（複雑性のわりに効果不明）
- 動的重み調整（過学習リスク、検証不十分）
- センチメントのみの判断（ノイズが多い）

---

## 実装された4層

### Layer 1: 情報収集（Information）
**ファイル**: `src/information/`
- `collector.py`: 時間軸別情報収集
- `models.py`: TimedInformation, NewsItem, TechnicalContext, FundamentalContext

**特徴**:
- ニュースを時間感度で分類（immediate/short_term/medium_term/older）
- 指数減衰ウェイト（半減期4時間）
- データ鮮度・完全性スコア

### Layer 2: 判断（Judgment）
**ファイル**: `src/judgment/`
- `service.py`: JudgmentService（CoT推論）
- `models.py`: JudgmentOutput, ReasoningTrace, KeyFactor
- `prompts.py`: 時間感度を考慮したプロンプト
- `integration.py`: daily_scoring.pyとの統合

**特徴**:
- Gemini Flash Thinking modeでCoT推論
- 推論ステップ・決定ポイント・不確実性を完全記録
- ルールベースとLLM判断のハイブリッド

### Layer 3: 振り返り（Reflection）
**ファイル**: `src/reflection/`
- `service.py`: ReflectionService（週次分析）
- `models.py`: ReflectionResult, PatternAnalysis, FactorReliability
- `prompts.py`: 振り返り分析プロンプト

**特徴**:
- 過去の判断と結果を比較
- 成功/失敗パターンの識別
- 要因信頼性分析
- 具体的な改善提案生成

### Layer 4: 深層調査（Deep Research）
**ファイル**: `src/research/`
- `service.py`: DeepResearchService
- `models.py`: ResearchReport, SectorAnalysis, ThematicInsight, MacroOutlook
- `prompts.py`: セクター/テーマ/マクロ分析プロンプト

**特徴**:
- 週次でセクター・テーマ・マクロ分析
- 戦略的コンテキストの提供
- 投資示唆の抽出

---

## データベース追加

**マイグレーション**: `supabase/migrations/006_add_judgment_records.sql`

### judgment_records
- 全判断の推論トレースを保存
- JSON形式でkey_factors、reasoning保存
- batch_date, symbol, strategy_modeで一意

### judgment_outcomes
- 判断に対する実際の結果を記録
- 1日/5日/10日リターン
- 振り返り分析用

### reflection_records
- 週次/月次振り返り結果
- パターン分析結果
- 改善提案

---

## 設定追加

**config.py更新**:
```python
# 新規設定
reflection_model: str = "gemini-2.5-pro"
deep_research_model: str = "gemini-2.5-pro"
enable_judgment: bool = True
enable_reflection: bool = True
judgment_thinking_budget: int = 4096
```

---

## GitHub Actionsワークフロー

### morning_batch.yml（更新）
- LLM判断を統合
- 新環境変数追加（ENABLE_JUDGMENT等）

### weekly_analysis.yml（新規）
- 毎週日曜12:00 UTC実行
- 週次振り返り + 深層調査

---

## 改善提案

### 高優先度

1. **判断結果の自動追跡**
   - 5日後に自動でoutcome記録するジョブを追加
   - 現在はoutcomeテーブルはあるが自動投入がない

2. **振り返りからの学習適用**
   - 振り返りで得た改善提案をプロンプトに反映する仕組み
   - 例: 信頼性の低い要因の重み付けを下げる

3. **コスト最適化**
   - LLM呼び出し回数のモニタリング
   - 低確信度候補はスキップするロジック

### 中優先度

4. **InformationCollectorとJudgmentServiceの統合強化**
   - 現在は別々に動作
   - TimedInformationをJudgmentに直接渡す統合パス

5. **Deep Researchの結果活用**
   - 週次研究結果を日次判断に反映する仕組み
   - セクター見通しに基づくバイアス調整

6. **A/Bテスト機能**
   - プロンプトバージョン別の性能比較
   - 現在はPROMPT_VERSIONを記録しているが比較ロジックなし

### 低優先度

7. **マルチソース情報統合**
   - 現在はFinnhub中心
   - SEC filing、Twitter等の追加

8. **リアルタイム監視**
   - 保有銘柄の重要ニュースアラート
   - 現在はバッチ処理のみ

---

## 自己評価

### 良かった点
- 研究知見を批判的に評価し、表面的な採用を避けた
- 推論トレースの完全記録により透明性を確保
- 時間軸別情報分類は実用的で理論的根拠がある
- 4層が明確に分離され、テスト・保守が容易

### 改善が必要な点
- 層間の統合がまだ疎結合
- 振り返りの学習ループが未完成
- コスト管理の仕組みが不十分
- テストコードが未実装

---

## 次のステップ

1. マイグレーション実行（Supabaseダッシュボードから）
2. 環境変数設定（GitHub Secrets/Variables）
3. テストラン実行（workflow_dispatchで手動トリガー）
4. 1週間後に振り返り実行、パフォーマンス評価
5. 改善提案の優先度に沿って順次実装
