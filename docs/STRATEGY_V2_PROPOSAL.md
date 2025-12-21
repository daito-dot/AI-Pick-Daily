# AI Pick Daily - 戦略 V2 提案書

## 現行戦略 (V1) の評価

### 現在のアプローチ
| 項目 | V1 (現行) |
|------|-----------|
| 戦略タイプ | マルチファクター（4エージェント均衡） |
| リスク許容度 | 低〜中 |
| 期待リターン | 市場+α（年5-10%超過） |
| 銘柄数 | 3-5銘柄/日 |
| 保有期間 | 1-5日 |

### V1の問題点
- **分散しすぎ**: 4つのファクターを均等に見るため、強いシグナルが薄まる
- **コンセンサス重視**: 全エージェント合意 = 既に市場に織り込み済み
- **モメンタム軽視**: トレンド35%だが、2024年はモメンタム単独で+58%

---

## リサーチ結果

### 2024年ファクターパフォーマンス

[Morgan Stanley](https://www.morganstanley.com/im/en-us/individual-investor/insights/articles/momentum-ruled-in-2024.html)のレポートより:

| ファクター | 2024年リターン |
|-----------|---------------|
| **モメンタム** | **+58%** |
| 成長 | +20% |
| 品質 | +15% |
| バリュー | +5% |
| S&P 500 | +23% |

> モメンタムは他のファクターを38ポイント以上アウトパフォーム

### 注意点
[SSGA](https://www.ssga.com/us/en/intermediary/insights/what-drove-momentums-strong-2024-and-what-it-could-mean-for-2025)によると:
- 2025年はモメンタム反転リスクあり（過去11回中7回で翌年マイナス）
- 極端なパフォーマンス後は2:1の確率で反転

---

## 戦略 V2 提案: 3つのオプション

### Option A: ピュアモメンタム戦略

```
コンセプト: 12-1モメンタムファクターに集中

銘柄選定基準:
- 過去12ヶ月リターン上位10%（直近1ヶ月除く）
- 出来高増加トレンド
- 52週高値近辺（5%以内）

リスク管理:
- VIX > 25 で現金比率50%
- 個別銘柄上限20%
- トレーリングストップ8%
```

| 項目 | 値 |
|------|-----|
| 期待リターン | 年+30-50% |
| 最大ドローダウン | -25-35% |
| シャープレシオ | 0.8-1.2 |

### Option B: カタリスト・ブレイクアウト戦略

[Warrior Trading](https://www.warriortrading.com/gap-go/)のGap and Go戦略を参考:

```
コンセプト: ニュース/決算でギャップアップした銘柄を狙う

銘柄選定基準:
- 前日比+4%以上のギャップ
- 明確なカタリスト（決算、FDA承認、M&A等）
- 出来高が平均の3倍以上
- プレマーケットで強い

エントリー:
- 9:30 AM（市場オープン）で1分足高値ブレイク
- ストップは1分足安値

イグジット:
- 10:00 AM までに利確
- または目標+5%達成
```

| 項目 | 値 |
|------|-----|
| 期待リターン | 日+1-3%（勝率60%） |
| 最大ドローダウン | -15-20% |
| 取引頻度 | 週2-5回 |

### Option C: LLM強化アルファ戦略

[最新研究](https://arxiv.org/html/2401.02710v2)を参考にした機械学習アプローチ:

```
コンセプト: LLMでアルファファクターを動的生成

アーキテクチャ:
1. マルチソースデータ融合
   - OHLCV
   - オーダーブック
   - ニュースセンチメント
   - SNS言及量

2. LLMアルファマイニング
   - Gemini/Claudeで相場コンテキスト理解
   - 複数アルファファクター候補生成
   - 強化学習で最適ウェイト決定

3. アンサンブル予測
   - XGBoost + LSTM + Transformer
   - オンライン学習で適応
```

| 項目 | 値 |
|------|-----|
| 期待リターン | 年+20-40% |
| 開発コスト | 高 |
| 複雑性 | 非常に高 |

---

## V2 推奨案: ハイブリッドモメンタム

現実的なV2として、**Option A + B のハイブリッド**を提案:

### アーキテクチャ変更

```
V1 (現行):
  Trend (35%) + Momentum (35%) + Value (20%) + Sentiment (10%)
  → 均衡型、低リスク

V2 (提案):
  Phase 1: モメンタムスクリーニング (必須条件)
    - 12-1 momentum > 上位20%
    - RSI 50-80
    - 出来高トレンド上昇

  Phase 2: カタリスト検出 (加点)
    - 直近決算サプライズ > +5%
    - アナリスト目標株価上方修正
    - ニュースセンチメント positive

  Phase 3: ブレイクアウト確認 (トリガー)
    - 新高値 or ベースからのブレイク
    - 出来高急増（平均の2倍以上）
```

### 具体的な変更点

| 項目 | V1 | V2 |
|------|-----|-----|
| 銘柄プール | S&P 500 上位50 | NASDAQ 100 + 高成長小型株 |
| 推奨銘柄数 | 3-5 | 1-3（集中投資） |
| 最低スコア | 60点 | 75点 |
| 保有期間 | 5日 | 3-10日（トレンド追従） |
| ストップロス | なし | 8%トレーリング |
| 利確目標 | なし | +15%または新高値更新停止 |

### 新エージェント構成

```python
# V2 Agent Weights
WEIGHTS_V2 = {
    "momentum_12_1": 0.40,      # 12ヶ月モメンタム（核心）
    "breakout_strength": 0.25,  # ブレイクアウト強度
    "catalyst_score": 0.20,     # カタリスト検出
    "risk_adjusted": 0.15,      # リスク調整（VIX連動）
}
```

### リスク管理強化

```python
class RiskManager:
    def calculate_position_size(self, signal_strength: float, vix: float) -> float:
        """VIX連動のポジションサイジング"""
        base_size = 0.20  # 基本20%/銘柄

        if vix > 30:
            return 0  # クライシス: ノーポジション
        elif vix > 25:
            return base_size * 0.5 * signal_strength
        elif vix > 20:
            return base_size * 0.75 * signal_strength
        else:
            return base_size * signal_strength

    def trailing_stop(self, entry_price: float, current_price: float) -> float:
        """8%トレーリングストップ"""
        high_water_mark = max(entry_price, current_price)
        stop_price = high_water_mark * 0.92
        return stop_price
```

---

## 期待パフォーマンス比較

| 指標 | V1 (現行) | V2 (提案) |
|------|-----------|-----------|
| 年間期待リターン | +10-15% | +25-40% |
| 最大ドローダウン | -10-15% | -20-30% |
| シャープレシオ | 0.8-1.0 | 1.0-1.5 |
| 勝率 | 55-60% | 50-55% |
| 平均利益/損失比 | 1.2:1 | 2.0:1 |

---

## 実装ロードマップ

### Phase 1: モメンタムエンジン (1週間)
- [ ] 12-1 モメンタム計算実装
- [ ] ブレイクアウト検出ロジック
- [ ] NASDAQ 100 + 成長株ユニバース追加

### Phase 2: カタリスト検出 (1週間)
- [ ] 決算サプライズAPI統合
- [ ] アナリスト目標株価追跡
- [ ] ニュースカタリスト分類

### Phase 3: リスク管理 (1週間)
- [ ] トレーリングストップ実装
- [ ] ポジションサイジングエンジン
- [ ] バックテストフレームワーク

---

## 注意事項

1. **2025年はモメンタム反転リスクあり** - 分散は必要
2. **小型株は流動性リスク** - 出来高フィルター必須
3. **頻繁な取引 = コスト増** - 手数料考慮
4. **バックテストと実運用の乖離** - ペーパートレードで検証

---

## 参考文献

- [Morgan Stanley: Momentum Ruled In 2024](https://www.morganstanley.com/im/en-us/individual-investor/insights/articles/momentum-ruled-in-2024.html)
- [SSGA: What Drove Momentum's Strong 2024](https://www.ssga.com/us/en/intermediary/insights/what-drove-momentums-strong-2024-and-what-it-could-mean-for-2025)
- [Warrior Trading: Gap and Go Strategy](https://www.warriortrading.com/gap-go/)
- [Quantpedia: Momentum Factor Effect](https://quantpedia.com/strategies/momentum-factor-effect-in-stocks)
- [arXiv: Synergistic Alpha Generation with RL](https://arxiv.org/html/2401.02710v2)
