# AI Pick Daily - 新アーキテクチャ設計 v2

## 設計原則

### 調査から得た核心的知見

1. **CoT (Chain-of-Thought) の効果**: 金融推論タスクで正答率+17%向上（63.2%→80.5%）
2. **リードタイム**: ニュース3-5時間、複雑な業績情報5日、完全織り込み1-13週間
3. **RAG必須**: ハルシネーション防止と監査可能性
4. **成功パターン**: 人間-AI協働（Citadel型）
5. **評価軸**: 「予測が当たったか」ではなく「根拠となった情報は正確だったか」

### 排除した「それっぽい」要素

- マルチエージェント構造（複雑さに見合う効果なし、Citadel実績が証拠）
- 独自モデル訓練（コスト非現実的）
- センチメント単独での判断（頑健な予測力に欠ける）
- 動的Weight調整（効果の証拠なし）

---

## 4層アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                    Layer 4: Deep Research                       │
│                 (Gemini Deep Research - 週次)                   │
│  ・市場レジーム分析（強気/弱気/レンジ）                          │
│  ・セクター/テーマの深層調査                                     │
│  ・新興トレンドの発見                                            │
│  → Layer 1の「何を収集すべきか」を更新                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓ 調査結果・収集指針
┌─────────────────────────────────────────────────────────────────┐
│                    Layer 3: Reflection                          │
│                    (Gemini 3 Pro - 週次)                        │
│  ・過去判断の振り返り                                            │
│  ・「情報の妥当性」評価                                          │
│  ・Layer 1へのフィードバック生成                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↑ フィードバック
┌─────────────────────────────────────────────────────────────────┐
│                    Layer 2: Judgment                            │
│              (Gemini 3 Flash Thinking - 日次)                   │
│  ・構造化情報を受け取り投資判断                                   │
│  ・CoTによる明示的推論                                           │
│  ・判断理由の構造化出力                                          │
└─────────────────────────────────────────────────────────────────┘
                              ↑ 構造化情報
┌─────────────────────────────────────────────────────────────────┐
│                    Layer 1: Information                         │
│                (Gemini 3 Flash + Program - 日次)                │
│  ・データ収集（既存機能）                                        │
│  ・情報抽出と構造化                                              │
│  ・時間軸別の情報整理                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Information（情報収集・構造化層）

### 目的
- プログラムによるデータ収集
- LLM (Gemini Flash) による情報抽出と構造化
- 時間軸を意識した情報整理

### モデル: Gemini 3 Flash
- **理由**: 高速・低コスト、大量情報の並列処理に最適
- **タスク**: 情報抽出、センチメント分類、要約

### 時間軸別の情報分類

```python
@dataclass
class TimedInformation:
    """時間軸を意識した情報構造"""

    # 即時性情報（3-5時間以内に影響）
    immediate: list[dict]  # 当日ニュース、プレマーケット動向

    # 短期情報（1-5日で影響）
    short_term: list[dict]  # 直近決算、アナリスト評価変更

    # 中期情報（1-4週間で影響）
    medium_term: list[dict]  # セクター動向、マクロ指標

    # 既に織り込み済みの可能性が高い情報
    likely_priced_in: list[dict]  # 5日以上前のニュース
```

### 情報構造化プロンプト（Gemini Flash用）

```
あなたは金融情報を構造化するアシスタントです。
以下の情報を時間軸で分類し、構造化してください。

【分類基準】
- immediate: 24時間以内のニュース/イベント
- short_term: 1-5日前の重要情報
- medium_term: 1-4週間前のトレンド情報
- likely_priced_in: 5日以上経過した情報（参考のみ）

【出力形式】
各情報について以下を抽出:
1. 要約（1文）
2. 時間軸分類
3. 方向性（positive/negative/neutral）
4. 信頼度（high/medium/low）
5. ソースタイプ（news/filing/analyst/social）
```

---

## Layer 2: Judgment（判断層）

### 目的
- 構造化情報に基づく投資判断
- **明示的な推論プロセス**（CoT）
- 判断理由の構造化保存

### モデル: Gemini 3 Flash (Thinking Mode)
- **理由**: 内蔵CoTにより推論が明示化される
- **タスク**: 投資判断、スコアリング、理由生成

### 判断出力構造

```python
@dataclass
class JudgmentOutput:
    """判断層の出力構造"""

    # 判断結果
    symbol: str
    decision: Literal["buy", "hold", "sell", "avoid"]
    confidence: float  # 0.0-1.0
    score: int  # 0-100

    # 推論プロセス（CoTの結果）
    reasoning: ReasoningTrace

    # 判断の根拠となった情報
    key_factors: list[KeyFactor]

    # リスク認識
    identified_risks: list[str]

    # メタデータ
    judged_at: datetime
    model_version: str


@dataclass
class ReasoningTrace:
    """推論の過程を記録"""

    # ステップバイステップの思考
    steps: list[str]

    # 最も重視した情報TOP3
    top_factors: list[str]

    # 判断を左右した分岐点
    decision_point: str

    # 不確実性の認識
    uncertainties: list[str]


@dataclass
class KeyFactor:
    """判断の根拠となった要因"""

    factor_type: Literal["fundamental", "technical", "sentiment", "macro"]
    description: str
    source: str
    impact: Literal["positive", "negative", "neutral"]
    weight: float  # この要因が判断に与えた重み（0.0-1.0）
    verifiable: bool  # 後で検証可能か
```

### 判断プロンプト（Gemini Flash Thinking用）

```
あなたは投資判断を行うアナリストです。
以下の構造化情報に基づいて、投資判断を行ってください。

【重要な指示】
1. ステップバイステップで考えてください
2. 判断の根拠となった情報を明示してください
3. 不確実性がある場合は明記してください
4. 「なぜその判断に至ったか」を説明してください

【時間軸の重要度】
- immediate情報: 最重視（まだ織り込まれていない可能性）
- short_term情報: 重視（部分的に織り込み中）
- medium_term情報: 参考（大部分は織り込み済み）
- likely_priced_in: 背景情報のみ

【出力形式】
1. 推論ステップ（箇条書き）
2. 最も重視した要因TOP3
3. 判断を左右した分岐点
4. 認識している不確実性
5. 最終判断と信頼度
```

---

## Layer 3: Reflection（振り返り層）

### 目的
- 過去の判断と結果の照合
- **「情報の妥当性」評価**（結果ではなく根拠を評価）
- Layer 1へのフィードバック生成

### モデル: Gemini 3 Pro
- **理由**: 最高の推論能力、複雑な分析タスクに最適
- **タスク**: 振り返り分析、パターン抽出、改善提案
- **頻度**: 週次（計算コスト削減）

### 評価の核心: 「情報の妥当性」

```python
@dataclass
class ReflectionInput:
    """振り返りの入力データ"""

    # 過去の判断
    judgment: JudgmentOutput

    # 結果
    actual_outcome: TradeResult

    # 判断時点では未知だった後続情報
    subsequent_information: list[dict]


@dataclass
class ReflectionOutput:
    """振り返りの出力"""

    # 情報の妥当性評価（これが核心）
    information_validity: InformationValidity

    # 推論プロセスの評価
    reasoning_quality: ReasoningQuality

    # 学習ポイント
    lessons_learned: list[str]

    # Layer 1へのフィードバック
    feedback_to_layer1: Layer1Feedback


@dataclass
class InformationValidity:
    """情報の妥当性評価（結果ではなく根拠を評価）"""

    # 根拠となった各情報の妥当性
    factor_evaluations: list[FactorEvaluation]

    # 見落としていた重要情報
    missed_information: list[str]

    # 過大評価していた情報
    overweighted_information: list[str]

    # 情報ソースの信頼性評価
    source_reliability: dict[str, float]


@dataclass
class FactorEvaluation:
    """個別要因の事後評価"""

    factor: KeyFactor  # 判断時の要因

    # 事後評価
    was_accurate: bool  # 情報自体は正確だったか
    was_relevant: bool  # 株価変動に関連していたか
    timing_assessment: str  # タイミングは適切だったか

    # 学び
    insight: str


@dataclass
class Layer1Feedback:
    """情報収集層へのフィードバック"""

    # 重視すべき情報ソース
    prioritize_sources: list[str]

    # 軽視すべき情報ソース
    deprioritize_sources: list[str]

    # 新たに収集すべき情報タイプ
    new_information_needs: list[str]

    # 時間軸の調整提案
    timing_adjustments: dict[str, str]
```

### 振り返りプロンプト（Gemini Pro用）

```
あなたは投資判断の振り返りを行うシニアアナリストです。
以下の判断記録と実際の結果を分析してください。

【重要な評価軸】
「予測が当たったかどうか」ではなく
「判断の根拠となった情報は正確で関連性があったか」を評価してください。

株価は多くの外部要因で動くため、結果だけで判断の良し悪しは測れません。
重要なのは「情報の選択と解釈が適切だったか」です。

【分析項目】
1. 根拠となった各情報の事後評価
   - その情報は正確だったか？
   - 株価変動に関連していたか？
   - タイミングは適切だったか？

2. 見落としていた情報
   - 後から分かった重要情報は何か？
   - なぜ見落としたのか？

3. 過大/過小評価
   - 重視しすぎた情報は？
   - 軽視しすぎた情報は？

4. 情報収集の改善提案
   - 優先すべきソース
   - 新たに収集すべき情報タイプ

【出力形式】
構造化されたJSON形式で出力してください。
```

---

## Layer 4: Deep Research（深層調査層）

### 目的
- 市場全体のレジーム（強気/弱気/レンジ）の判定
- セクター/テーマの包括的調査
- 新興トレンドの早期発見
- **Layer 1の収集対象を動的に更新**

### モデル: Gemini Deep Research
- **理由**: 広範な調査と深い分析が可能、複数ソースの統合
- **タスク**: 市場環境分析、テーマリサーチ、情報収集戦略の策定
- **頻度**: 週次（日曜または市場休日）

### Deep Researchの活用パターン

#### パターン1: 市場レジーム分析

```python
@dataclass
class MarketRegimeAnalysis:
    """市場レジームの分析結果"""

    # レジーム判定
    regime: Literal["bull", "bear", "range", "transition"]
    confidence: float

    # 根拠
    supporting_evidence: list[str]

    # セクター別の見通し
    sector_outlook: dict[str, SectorOutlook]

    # リスク要因
    key_risks: list[str]

    # 推奨される戦略調整
    strategy_adjustments: StrategyAdjustment

    # 有効期間
    valid_until: date


@dataclass
class StrategyAdjustment:
    """レジームに基づく戦略調整"""

    # ポジションサイズ調整
    position_size_modifier: float  # 1.0 = 通常, 0.5 = 縮小

    # 優先セクター
    priority_sectors: list[str]

    # 回避セクター
    avoid_sectors: list[str]

    # 保持期間の調整
    hold_period_modifier: float  # 1.0 = 通常

    # 利確/損切りの調整
    take_profit_modifier: float
    stop_loss_modifier: float
```

#### パターン2: テーマリサーチ

```python
@dataclass
class ThemeResearch:
    """テーマ別の深層調査結果"""

    theme: str  # e.g., "AI Infrastructure", "Energy Transition"

    # 調査サマリー
    executive_summary: str

    # 成長ドライバー
    growth_drivers: list[str]

    # リスク要因
    risk_factors: list[str]

    # 関連銘柄（ティア別）
    tier1_stocks: list[str]  # 直接的な恩恵
    tier2_stocks: list[str]  # 間接的な恩恵

    # 時間軸
    investment_horizon: Literal["short", "medium", "long"]

    # 監視すべき指標
    key_metrics_to_watch: list[str]

    # 次回レビュー予定
    next_review_date: date
```

#### パターン3: 情報収集戦略の更新

```python
@dataclass
class InformationStrategy:
    """Layer 1への収集指針"""

    # 優先的に監視すべき銘柄リスト
    priority_watchlist: list[str]

    # 重点的に収集すべき情報タイプ
    priority_information_types: list[str]

    # 新たに追加すべきデータソース
    new_data_sources: list[str]

    # 軽視してよい情報タイプ
    deprioritize_types: list[str]

    # キーワード監視リスト
    keyword_alerts: list[str]

    # 決算カレンダー注目銘柄
    earnings_focus: list[str]
```

### Deep Research プロンプト例

```
【市場レジーム分析】
現在の米国株式市場の状況を包括的に分析してください。

調査項目:
1. マクロ経済指標の動向（GDP、雇用、インフレ、金利）
2. 市場のテクニカル状況（主要指数、ブレッドス、VIX）
3. セクターローテーションの兆候
4. 地政学的リスク
5. 機関投資家のポジショニング

出力:
1. 市場レジームの判定（強気/弱気/レンジ/移行期）と根拠
2. 各セクターの見通し
3. 今後1-2週間の主要リスク
4. 推奨される戦略調整
```

### 週次ワークフロー

```
日曜日 (市場休日)
├── Deep Research実行（Layer 4）
│   ├── 市場レジーム分析
│   ├── 注目テーマのリサーチ
│   └── 情報収集戦略の更新
│
├── Reflection実行（Layer 3）
│   ├── 先週の判断レビュー
│   ├── 情報妥当性の評価
│   └── 学習ポイントの抽出
│
└── Layer 1の設定更新
    ├── 監視銘柄リストの更新
    ├── 収集優先度の調整
    └── アラートキーワードの設定

月曜日-金曜日
├── Layer 1: 情報収集・構造化（日次）
├── Layer 2: 判断・スコアリング（日次）
└── 判断記録の蓄積
```

---

## データベーススキーマ追加

### judgment_records テーブル

```sql
CREATE TABLE judgment_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 基本情報
    symbol VARCHAR(10) NOT NULL,
    strategy_mode VARCHAR(20) NOT NULL,
    judged_at TIMESTAMP WITH TIME ZONE NOT NULL,

    -- 判断結果
    decision VARCHAR(10) NOT NULL,  -- buy/hold/sell/avoid
    confidence FLOAT NOT NULL,
    score INTEGER NOT NULL,

    -- 推論プロセス（JSONB）
    reasoning_trace JSONB NOT NULL,

    -- 根拠となった情報（JSONB）
    key_factors JSONB NOT NULL,

    -- 認識していたリスク
    identified_risks TEXT[],

    -- メタデータ
    model_version VARCHAR(50),
    input_information JSONB,  -- Layer 1からの入力

    -- インデックス
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_judgment_symbol ON judgment_records(symbol);
CREATE INDEX idx_judgment_strategy ON judgment_records(strategy_mode);
CREATE INDEX idx_judgment_date ON judgment_records(judged_at);
```

### reflection_records テーブル

```sql
CREATE TABLE reflection_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 対象の判断
    judgment_id UUID REFERENCES judgment_records(id),

    -- 実際の結果
    trade_id UUID REFERENCES trade_history(id),
    actual_return_pct FLOAT,

    -- 情報妥当性評価（JSONB）
    information_validity JSONB NOT NULL,

    -- 推論品質評価
    reasoning_quality JSONB,

    -- 学習ポイント
    lessons_learned TEXT[],

    -- Layer 1へのフィードバック（JSONB）
    layer1_feedback JSONB,

    -- メタデータ
    reflected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    model_version VARCHAR(50)
);

CREATE INDEX idx_reflection_judgment ON reflection_records(judgment_id);
CREATE INDEX idx_reflection_date ON reflection_records(reflected_at);
```

---

## モデル使用戦略

### コスト・速度・能力のバランス

| 層 | モデル | 頻度 | 理由 |
|----|--------|------|------|
| Layer 1 | Gemini 3 Flash | 日次×複数銘柄 | 高速・低コスト、並列処理 |
| Layer 2 | Gemini 3 Flash (Thinking) | 日次×候補銘柄 | CoT内蔵、推論可視化 |
| Layer 3 | Gemini 3 Pro | 週次 | 最高推論能力、低頻度でコスト抑制 |
| Layer 4 | Gemini Deep Research | 週次 | 広範な調査、複数ソース統合 |

### モデル別の特性と活用

| モデル | 強み | 適切なタスク | 注意点 |
|--------|------|-------------|--------|
| Flash | 速度、コスト効率 | 大量処理、抽出 | 複雑な推論は苦手 |
| Flash Thinking | 推論の可視化、CoT | 判断、スコアリング | 速度はFlashより遅い |
| Pro | 最高精度、複雑な推論 | 振り返り、分析 | コスト高 |
| Deep Research | 網羅的調査、統合 | 市場分析、テーマ調査 | 時間がかかる |

### トークン使用量見積もり

```
【日次処理】
Layer 1 (Flash):
  - 入力: 約20銘柄 × 2000トークン = 40,000トークン
  - 出力: 約20銘柄 × 500トークン = 10,000トークン

Layer 2 (Flash Thinking):
  - 入力: 約10候補 × 3000トークン = 30,000トークン
  - 出力: 約10候補 × 1000トークン = 10,000トークン

日次合計: 約90,000トークン

【週次処理】
Layer 3 (Pro):
  - 入力: 約50判断 × 3000トークン = 150,000トークン
  - 出力: 約50判断 × 1500トークン = 75,000トークン

Layer 4 (Deep Research):
  - 市場レジーム分析: 入出力合計 約50,000トークン
  - テーマリサーチ: 入出力合計 約100,000トークン

週次合計: 約375,000トークン

【月次見積もり】
日次: 90,000 × 22日 = 1,980,000トークン
週次: 375,000 × 4週 = 1,500,000トークン
月次合計: 約3,500,000トークン
```

---

## 実装フェーズ

### Phase 1: 判断理由の記録（Layer 2基盤）
**期間**: 1-2週間
**目標**: 判断の可視化と記録

- `JudgmentOutput`データ構造の実装
- 既存スコアリングにCoTプロンプトを追加
- Gemini Flash Thinkingへの移行
- judgment_recordsテーブル作成とマイグレーション
- 判断理由のDB保存

**成果物**: 全ての判断に推論トレースが記録される状態

### Phase 2: 時間軸別情報構造化（Layer 1強化）
**期間**: 1-2週間
**目標**: 情報の時間的価値を反映

- `TimedInformation`データ構造の実装
- ニュース/決算情報の時間軸分類ロジック
- Layer 1プロンプトの実装（Gemini Flash用）
- Layer 2への構造化情報受け渡し

**成果物**: 情報が時間軸で分類されLayer 2に渡される状態

### Phase 3: 振り返り機能（Layer 3）
**期間**: 1-2週間
**目標**: 学習ループの確立

- reflection_recordsテーブル作成
- Layer 3プロンプト実装（Gemini Pro用）
- 週次振り返りワークフロー作成
- 「情報妥当性」評価ロジック
- Layer 1へのフィードバック反映機構

**成果物**: 週次で過去判断が評価されフィードバックが生成される状態

### Phase 4: 深層調査機能（Layer 4）
**期間**: 1-2週間
**目標**: 戦略的視点の獲得

- market_regime_analysisテーブル作成
- Deep Researchワークフロー実装
- 市場レジーム分析プロンプト
- テーマリサーチプロンプト
- 情報収集戦略の動的更新機構

**成果物**: 週次で市場環境が分析され収集戦略が更新される状態

### Phase 5: 統合と最適化（継続）
**期間**: 継続的

- 全層の統合テスト
- プロンプトのA/Bテスト
- パフォーマンス監視
- コスト最適化
- フィードバックループの効果測定

---

## 成功指標

### 測定可能な指標

1. **情報妥当性スコア**: 振り返りで「正確かつ関連性あり」と評価された情報の割合
2. **見落とし率**: 重要情報を見落とした判断の割合
3. **推論一貫性**: 類似状況での判断の一貫性

### 測定困難だが重要な指標

1. **学習の累積**: Layer 3フィードバックがLayer 1を改善しているか
2. **推論の質**: 人間が読んで納得できる推論か

---

## リスクと対策

| リスク | 対策 |
|--------|------|
| プロンプト依存性 | 複数バージョンのA/Bテスト |
| モデル更新による挙動変化 | バージョン管理、定期的な再評価 |
| コスト増大 | トークン使用量の監視、キャッシング |
| 振り返りの形骸化 | フィードバックの実際の反映を追跡 |

---

## 現行アーキテクチャとの違い

### Before（現行）

```
Program → LLM(スコアリング) → 結果
           ↑
      固定プロンプト
      判断理由なし
      学習ループなし
```

### After（新アーキテクチャ）

```
Deep Research → 収集戦略 → 時間軸別情報 → 判断+理由 → 結果
      ↑                                        ↓
      └──────── 振り返り（情報妥当性評価）←──────┘
```

### 具体的な変更点

| 項目 | 現行 | 新アーキテクチャ |
|------|------|------------------|
| プロンプト | 固定 | CoT + 構造化出力 |
| 判断理由 | なし | 全て記録・保存 |
| 情報の時間軸 | 考慮なし | 4段階で分類 |
| 学習ループ | なし | 週次振り返り |
| 市場環境認識 | なし | Deep Researchで週次分析 |
| モデル使い分け | 単一 | タスク別に4モデル |

---

## なぜこの設計が「それっぽい」ではないか

### 調査に基づく根拠

1. **CoTの採用**
   - 根拠: FinCoTで正答率+17%（63.2%→80.5%）
   - 実装: Gemini Flash Thinkingで内蔵CoTを活用

2. **時間軸の考慮**
   - 根拠: リードタイム3-5時間〜13週間の実証研究
   - 実装: 情報を4段階で分類、新鮮な情報を重視

3. **判断理由の記録**
   - 根拠: Citadel型「人間-AI協働」モデルの成功
   - 実装: 全判断をトレース可能な形式で保存

4. **情報妥当性評価**
   - 根拠: 「結果」より「根拠の正確性」が重要という知見
   - 実装: 振り返りで「情報は正確だったか」を評価

5. **マルチエージェント不採用**
   - 根拠: Citadel「AIはアルファに貢献していない」
   - 判断: 複雑さに見合う効果なし

### 排除した「それっぽい」要素

- 動的Weight調整（効果の証拠なし）
- 複数エージェントの議論（Citadel実績が否定）
- センチメント単独での判断（頑健性に欠ける）
- 独自モデル訓練（コスト非現実的）

---

## 次のアクション

1. **即時**: Phase 1の詳細タスク分解
2. **今週**: judgment_recordsテーブルの作成
3. **来週**: Gemini Flash ThinkingでのCoTプロンプトテスト
