# ペーパートレード・シミュレーション戦略設計書

## 1. 概要

本ドキュメントは、AI Pick Daily の仮想運用シミュレーション（ペーパートレード）の戦略設計を定義する。

### 1.1 目的

- **検証**: AIスコアリングが実際に利益を生むか検証
- **学習**: フィードバックループを通じてシステムを改善
- **透明性**: ユーザーにシステムの実効性を示す

### 1.2 制約条件

- 初期資金: ¥100,000
- 対象市場: 米国株（NYSE, NASDAQ）
- 売買タイミング: 寄付価格（Open）で約定を仮定
- 取引コスト: 未考慮（個人投資家向けアプリでは無料〜低コスト）

---

## 2. 調査結果サマリー

### 2.1 ポジションサイジング

| 手法 | 特徴 | 適用可能性 |
|------|------|-----------|
| **Equal Weight** | シンプル、分散効果 | ◎ 初期実装向け |
| **Kelly Criterion** | 期待値最大化、ドローダウン大 | △ データ蓄積後 |
| **Half Kelly** | Kelly の 75% のリターンで DD 半減 | ○ 中期目標 |
| **Volatility Parity** | ボラティリティで重み付け | △ 複雑 |

**採用方針**: 初期は Equal Weight。20トレード以上蓄積後、勝率・期待リターンを計算して Half Kelly 移行を検討。

参考: [Kelly Criterion in Practice - Alpha Theory](https://www.alphatheory.com/blog/kelly-criterion-in-practice-1)

### 2.2 エグジット戦略

| 手法 | 設定値 | 根拠 |
|------|-------|------|
| **Stop Loss** | -7% | 研究では 15-20% が最適だが、個人投資家向けに保守的に |
| **Take Profit** | +15% | Risk:Reward = 1:2 を確保 |
| **Max Hold** | 10営業日 | 短期モメンタム戦略に合致 |
| **Score Drop** | 閾値以下 | AIシグナルに従う |
| **Regime Change** | 危機モード | 市場全体リスク回避 |

**優先度**:
1. Stop Loss / Take Profit（ハードストップ）
2. Regime Change（市場リスク）
3. Score Drop（AIシグナル）
4. Max Hold（時間ベース）

参考: [Stop Loss Strategies - TradersPost](https://blog.traderspost.io/article/stop-loss-strategies-algorithmic-trading)

### 2.3 リバランス頻度

| 頻度 | メリット | デメリット |
|------|---------|-----------|
| **Daily** | 機敏な対応 | 取引コスト増、税務複雑 |
| **Weekly** | バランス良い | 週末リスク |
| **Threshold-based** | 効率的 | 監視必要 |

**採用方針**: 日次チェック（Evening Batch）、閾値ベースでトリガー。

参考: [Portfolio Rebalancing - Zignaly](https://zignaly.com/crypto-trading/risk-management/cryptocurrency-portfolio-rebalancing)

### 2.4 ドローダウン管理

| 投資家タイプ | 許容 MDD | 対応 |
|-------------|---------|------|
| Conservative | 10-15% | ポジション縮小 |
| Moderate | 15-25% | 監視強化 |
| Aggressive | 25-40% | 継続 |

**採用方針**:
- MDD 10% 到達: 警告ログ、新規ポジション抑制
- MDD 15% 到達: 新規ポジション停止
- MDD 20% 到達: 全ポジションクローズ検討

参考: [Drawdown Management - Groww](https://groww.in/blog/manage-drawdowns-like-a-hedge-fund-manager)

### 2.5 LLM × 市場レジーム適応

**最新研究の知見**:
- LLM戦略は「ブル相場で保守的すぎ、ベア相場で攻撃的すぎ」という問題がある
- **レジーム認識**と**適応的リスク管理**がアーキテクチャ複雑化より重要
- Multi-Agent + Reflection パターンで 31% のパフォーマンス改善

**適用**:
- 現行の Market Regime 判定を活用
- Normal / Caution / Crisis に応じたポジションサイズ調整
- 閾値だけでなく、ポジションサイズも動的に変更

参考: [LLMs in Equity Markets - Frontiers](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1608365/full)

---

## 3. アーキテクチャ設計

### 3.1 二層構造

```
┌─────────────────────────────────────────────────────────┐
│  Layer B: ポートフォリオ/銘柄選択（LLM駆動）            │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 1. Market Regime 判定（LLM）                    │   │
│  │ 2. スコアリング（LLM + ルールベース）           │   │
│  │ 3. 閾値による選別（動的調整）                   │   │
│  │ 4. ポジションサイズ決定（Equal Weight）         │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  Layer A: 執行（ルールベース）                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 1. 寄付価格で約定（シミュレーション）           │   │
│  │ 2. Stop Loss / Take Profit 監視                 │   │
│  │ 3. 日次エグジット判定                           │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 3.2 バッチ処理フロー

#### Morning Batch（ポジション開設）

```python
def morning_batch():
    # 1. 今日のピックを取得
    picks = get_today_picks()  # daily_picks テーブル

    # 2. 現在のポートフォリオ状態を取得
    portfolio = get_portfolio_state()

    # 3. ドローダウンチェック
    if portfolio.current_drawdown >= MAX_DRAWDOWN_LIMIT:
        log("MDD limit reached, no new positions")
        return

    # 4. Market Regime チェック
    regime = get_market_regime()
    if regime == "crisis":
        log("Crisis mode, no new positions")
        return

    # 5. ポジションサイズ計算（Equal Weight）
    available_slots = MAX_POSITIONS - portfolio.open_count
    position_size = portfolio.cash / min(len(picks), available_slots)

    # 6. ポジション開設
    for pick in picks[:available_slots]:
        if pick not in portfolio.holdings:
            open_position(pick, position_size)

    # 7. スナップショット更新
    update_portfolio_snapshot()
```

#### Evening Batch（エグジット評価 + 閾値調整）

```python
def evening_batch():
    # 1. オープンポジションを取得
    positions = get_open_positions()

    # 2. 各ポジションのエグジット判定
    for pos in positions:
        current_price = get_current_price(pos.symbol)
        pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100

        # 優先度順にチェック
        if pnl_pct <= STOP_LOSS:
            close_position(pos, "stop_loss")
        elif pnl_pct >= TAKE_PROFIT:
            close_position(pos, "take_profit")
        elif market_regime == "crisis":
            close_position(pos, "regime_change")
        elif get_current_score(pos.symbol) < threshold:
            close_position(pos, "score_drop")
        elif pos.hold_days >= MAX_HOLD_DAYS:
            close_position(pos, "max_hold")

    # 3. ポートフォリオスナップショット更新
    update_portfolio_snapshot()

    # 4. リターン計算（5日前のスコアに対して）
    calculate_returns()

    # 5. 閾値調整（過学習防止チェック付き）
    adjust_thresholds()
```

### 3.3 レジーム適応型ポジションサイジング

```python
def get_position_size_multiplier(regime: str, current_drawdown: float) -> float:
    """
    Market Regime と現在のドローダウンに基づいてポジションサイズを調整
    """
    # Base multiplier by regime
    regime_multiplier = {
        "normal": 1.0,
        "caution": 0.7,
        "crisis": 0.0,  # No new positions
    }.get(regime, 1.0)

    # Drawdown-based scaling
    if current_drawdown >= 15:
        dd_multiplier = 0.0  # Stop new positions
    elif current_drawdown >= 10:
        dd_multiplier = 0.5  # Half size
    elif current_drawdown >= 5:
        dd_multiplier = 0.75
    else:
        dd_multiplier = 1.0

    return regime_multiplier * dd_multiplier
```

---

## 4. データベース設計（追加）

### 4.1 scoring_config への追加カラム

```sql
ALTER TABLE scoring_config ADD COLUMN IF NOT EXISTS
    position_size_multiplier DECIMAL(3, 2) DEFAULT 1.0;

-- レジームに応じた自動調整用
ALTER TABLE scoring_config ADD COLUMN IF NOT EXISTS
    regime_adjustment_enabled BOOLEAN DEFAULT TRUE;
```

### 4.2 portfolio_daily_snapshot への追加カラム

```sql
-- リスク指標追加
ALTER TABLE portfolio_daily_snapshot ADD COLUMN IF NOT EXISTS
    max_drawdown DECIMAL(8, 4);  -- 最大ドローダウン

ALTER TABLE portfolio_daily_snapshot ADD COLUMN IF NOT EXISTS
    sharpe_ratio DECIMAL(8, 4);  -- シャープレシオ（30日ローリング）

ALTER TABLE portfolio_daily_snapshot ADD COLUMN IF NOT EXISTS
    win_rate DECIMAL(5, 2);  -- 勝率
```

---

## 5. 実装優先度

### Phase 1: 基本フロー（即時）
1. Morning Batch にポジション開設処理を追加
2. Evening Batch にエグジット評価を追加
3. 日次スナップショット更新

### Phase 2: リスク管理（1週間後）
4. ドローダウン監視とポジションサイズ調整
5. シャープレシオ、勝率の計算と記録

### Phase 3: 高度な機能（データ蓄積後）
6. Half Kelly ポジションサイジングへの移行
7. トレーリングストップの導入

---

## 6. KPI と評価基準

| 指標 | 目標 | 計測方法 |
|------|------|---------|
| 累積リターン | > S&P 500 | portfolio_daily_snapshot.cumulative_pnl_pct |
| Alpha | > 0% | portfolio_daily_snapshot.alpha |
| 勝率 | > 50% | trade_history 集計 |
| Max Drawdown | < 15% | portfolio_daily_snapshot.max_drawdown |
| シャープレシオ | > 1.0 | 30日ローリング計算 |
| 平均保有期間 | 3-7日 | trade_history.hold_days 平均 |

---

## 7. リスクと対策

### 7.1 流動性リスク（重要）

**研究知見**:
- Market Cap < $100M の銘柄は、$1B-$5B と比較して著しく非流動的
- Bid-Ask スプレッドが広く、約定価格乖離が大きい
- アルゴリズム取引の流動性改善効果は大型株で強い

参考: [SEC Small Cap Liquidity Study](https://www.sec.gov/marketstructure/research/small_cap_liquidity.pdf)

**対策（フィルター追加）**:
```python
# 流動性フィルター
MINIMUM_MARKET_CAP = 1_000_000_000  # $1B
MINIMUM_AVG_VOLUME = 500_000        # 日平均出来高 50万株
MINIMUM_DOLLAR_VOLUME = 5_000_000   # 日平均売買代金 $500万

def is_liquid(stock) -> bool:
    return (
        stock.market_cap >= MINIMUM_MARKET_CAP and
        stock.avg_volume_20d >= MINIMUM_AVG_VOLUME and
        stock.avg_dollar_volume_20d >= MINIMUM_DOLLAR_VOLUME
    )
```

### 7.2 ペーパートレード vs 実運用の乖離

**研究知見（バックテスト→ライブの罠）**:

| 要因 | バックテスト | 実運用 | 影響 |
|------|-------------|--------|------|
| スリッページ | 0% | 0.1-0.5% | 年間 -2〜-5% |
| 約定率 | 100% | 95-99% | 機会損失 |
| 心理的影響 | なし | 恐怖/欲 | 戦略逸脱 |
| Market Impact | なし | あり | 大型注文で不利 |

参考: [PineConnector - Backtesting vs Live Trading](https://www.pineconnector.com/blogs/pico-blog/backtesting-vs-live-trading-bridging-the-gap-between-strategy-and-reality)

**対策**:
1. **保守的な期待値設定**: バックテスト結果の 70% を期待リターンとする
2. **スリッページ考慮**: 0.1% のスリッページをシミュレーションに組み込む
3. **Out-of-Sample 検証**: 閾値調整は未使用データで検証

### 7.3 Look-Ahead Bias 防止

**問題**: 「未来のデータを使って意思決定」を無意識にやってしまう

**チェックリスト**:
- [ ] スコアリングに使うデータは、取引日の前日終値まで
- [ ] Market Regime は前日 Close 時点で判定
- [ ] 閾値調整は 5日後のリターン確定後に実行

### 7.4 リスク一覧

| リスク | 影響 | 対策 |
|--------|------|------|
| 過学習 | 閾値調整が逆効果 | MIN_TRADES=20, クールダウン7日 |
| 流動性リスク | 約定価格乖離 | Market Cap > $1B, Volume > 50万株 |
| ギャップリスク | 寄付価格急変 | Stop Loss はハードストップとして機能 |
| レジーム誤判定 | 不適切なポジション | 複数指標でクロスチェック |
| Look-Ahead Bias | 非現実的な成績 | データカットオフ厳格化 |
| 心理的バイアス | ペーパーと実運用の乖離 | ルール厳守、自動化 |

---

## 8. 実装状況

**最終更新**: 2025-12-22

### 完了項目 ✅

| 項目 | 実装ファイル | 備考 |
|------|-------------|------|
| Morning Batch ポジション開設 | `scripts/daily_scoring.py` | Step 7-8 |
| Evening Batch エグジット評価 | `scripts/daily_review.py` | Step 3 |
| ポートフォリオスナップショット | `src/portfolio/manager.py` | 毎バッチ更新 |
| キャッシュ残高追跡 | `src/portfolio/manager.py` | 開設/クローズ時に反映 |
| リスク指標計算 | `src/portfolio/manager.py` | Sharpe, MDD, WinRate |
| 閾値自動調整 | `scripts/daily_review.py` | Step 6 |
| 過学習防止 | `src/scoring/threshold_optimizer.py` | MIN_TRADES=20, COOLDOWN=7日 |

### バッチ処理フロー（実装版）

```
Morning Batch (daily_scoring.py)
├── Step 1-6: スコアリング・保存（既存）
├── Step 7: ポジション開設
│   ├── PortfolioManager.open_positions_for_picks()
│   ├── Equal Weight でポジションサイズ計算
│   └── 既保有銘柄は除外
└── Step 8: スナップショット更新
    ├── S&P 500 日次リターン取得
    ├── リスク指標計算（Sharpe, MDD, WinRate）
    └── portfolio_daily_snapshot 保存

Evening Batch (daily_review.py)
├── Step 1-2: リターン計算（既存）
├── Step 3: エグジット評価（NEW）
│   ├── PortfolioManager.evaluate_exit_signals()
│   │   ├── Stop Loss (-7%)
│   │   ├── Take Profit (+15%)
│   │   ├── Regime Change (Crisis)
│   │   ├── Score Drop (< threshold)
│   │   └── Max Hold (10日)
│   ├── PortfolioManager.close_positions()
│   └── スナップショット更新
├── Step 4-5: AI振り返り（既存）
├── Step 6: 閾値調整（既存）
└── Step 7: パフォーマンスサマリー（既存）
```

### キャッシュ残高計算ロジック

```python
# ポジション開設時
cash_balance -= position_value

# ポジションクローズ時
cash_balance += exit_price * shares

# スナップショット更新時
# 前回のキャッシュ + 当日クローズ - 当日開設
cash_balance = prev_cash + closed_trades_value - new_positions_cost
```

### 未実装（将来）

| 項目 | 優先度 | 備考 |
|------|--------|------|
| 流動性フィルタ | LOW | S&P 500 Top 50 は全て大型株のため不要 |
| ドローダウン時のポジション縮小 | MEDIUM | MDD 10%/15%/20% で段階的対応 |
| Half Kelly ポジションサイジング | LOW | 20トレード以上蓄積後 |
| トレーリングストップ | LOW | 将来的な検討項目 |

---

## 参考文献

1. [Kelly Criterion in Practice - Alpha Theory](https://www.alphatheory.com/blog/kelly-criterion-in-practice-1)
2. [Stop Loss Strategies - TradersPost](https://blog.traderspost.io/article/stop-loss-strategies-algorithmic-trading)
3. [LLMs in Equity Markets - Frontiers AI](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1608365/full)
4. [Drawdown Management - Groww](https://groww.in/blog/manage-drawdowns-like-a-hedge-fund-manager)
5. [Portfolio Rebalancing - Zignaly](https://zignaly.com/crypto-trading/risk-management/cryptocurrency-portfolio-rebalancing)
6. Bailey et al. (2014). The Probability of Backtest Overfitting.
