import {
  getPortfolioSummary,
  getOpenPositions,
  getTradeHistory,
  getPortfolioSnapshots,
  getScoringConfigs,
  getThresholdHistory,
} from '@/lib/supabase';
import { MarketTabs } from '@/components/MarketTabs';
import { EquityCurveChart } from '@/components/EquityCurveChart';
import { getStockDisplayName } from '@/lib/jp-stocks';
import { format, parseISO } from 'date-fns';
import { ja } from 'date-fns/locale';

export const revalidate = 300;

function formatCurrency(value: number, isJapan: boolean = false): string {
  if (isJapan) {
    return new Intl.NumberFormat('ja-JP', {
      style: 'currency',
      currency: 'JPY',
      maximumFractionDigits: 0,
    }).format(value);
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPrice(price: number, isJapan: boolean = false): string {
  if (isJapan) {
    return `¥${Math.round(price).toLocaleString()}`;
  }
  return `$${price.toFixed(2)}`;
}

function PnLBadge({ pnl }: { pnl: number }) {
  const isPositive = pnl >= 0;
  return (
    <span className={`font-bold ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
      {isPositive ? '+' : ''}{pnl.toFixed(2)}%
    </span>
  );
}

function ExitReasonBadge({ reason }: { reason: string }) {
  const config: Record<string, { label: string; className: string }> = {
    take_profit: { label: '利確', className: 'bg-green-100 text-green-800' },
    stop_loss: { label: '損切', className: 'bg-red-100 text-red-800' },
    score_drop: { label: 'スコア低下', className: 'bg-yellow-100 text-yellow-800' },
    max_hold: { label: '保有期限', className: 'bg-gray-100 text-gray-800' },
    regime_change: { label: '相場変化', className: 'bg-purple-100 text-purple-800' },
  };
  const c = config[reason] || { label: reason, className: 'bg-gray-100 text-gray-800' };

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${c.className}`}>
      {c.label}
    </span>
  );
}

function StrategyBadge({ strategy }: { strategy: string }) {
  const isConservative = strategy === 'conservative' || strategy === 'jp_conservative';
  const isJapan = strategy.startsWith('jp_');
  const label = isConservative ? 'V1' : 'V2';
  const marketLabel = isJapan ? '🇯🇵' : '🇺🇸';

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${
      isConservative ? 'bg-blue-100 text-blue-800' : 'bg-orange-100 text-orange-800'
    }`}>
      {marketLabel} {label}
    </span>
  );
}

interface PortfolioContentProps {
  v1Summary: {
    totalValue: number;
    cashBalance: number;
    positionsValue: number;
    openPositions: number;
    cumulativePnlPct: number;
    alpha: number;
  };
  v2Summary: {
    totalValue: number;
    cashBalance: number;
    positionsValue: number;
    openPositions: number;
    cumulativePnlPct: number;
    alpha: number;
  };
  openPositions: any[];
  trades: any[];
  v1Config: any;
  v2Config: any;
  thresholdHistory: any[];
  v1Snapshots: any[];
  v2Snapshots: any[];
  isJapan: boolean;
  v1Strategy: string;
  v2Strategy: string;
}

function PortfolioContent({
  v1Summary,
  v2Summary,
  openPositions,
  trades,
  v1Config,
  v2Config,
  thresholdHistory,
  v1Snapshots,
  v2Snapshots,
  isJapan,
  v1Strategy,
  v2Strategy,
}: PortfolioContentProps) {
  // Calculate trade stats
  const totalTrades = trades.length;
  const winningTrades = trades.filter(t => t.pnl_pct > 0).length;
  const winRate = totalTrades > 0 ? ((winningTrades / totalTrades) * 100).toFixed(1) : '---';
  const avgPnl = totalTrades > 0
    ? (trades.reduce((sum, t) => sum + (t.pnl_pct || 0), 0) / totalTrades).toFixed(2)
    : '---';

  const benchmarkName = isJapan ? '日経225' : 'S&P500';
  const initialFund = isJapan ? '¥100,000' : '$100,000';

  return (
    <div className="space-y-8">
      <p className="text-gray-500 mt-1">仮想運用シミュレーション（初期資金: {initialFund}）</p>

      {/* Portfolio Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* V1 Conservative */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">V1 Conservative</h3>
            <StrategyBadge strategy={v1Strategy} />
          </div>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-500">総資産</span>
              <span className="font-bold">{formatCurrency(v1Summary.totalValue, isJapan)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">現金</span>
              <span>{formatCurrency(v1Summary.cashBalance, isJapan)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">ポジション価値</span>
              <span>{formatCurrency(v1Summary.positionsValue, isJapan)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">保有銘柄数</span>
              <span>{v1Summary.openPositions}</span>
            </div>
            <hr />
            <div className="flex justify-between">
              <span className="text-gray-500">累積リターン</span>
              <PnLBadge pnl={v1Summary.cumulativePnlPct} />
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Alpha (vs {benchmarkName})</span>
              <PnLBadge pnl={v1Summary.alpha} />
            </div>
          </div>
        </div>

        {/* V2 Aggressive */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">V2 Aggressive</h3>
            <StrategyBadge strategy={v2Strategy} />
          </div>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-500">総資産</span>
              <span className="font-bold">{formatCurrency(v2Summary.totalValue, isJapan)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">現金</span>
              <span>{formatCurrency(v2Summary.cashBalance, isJapan)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">ポジション価値</span>
              <span>{formatCurrency(v2Summary.positionsValue, isJapan)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">保有銘柄数</span>
              <span>{v2Summary.openPositions}</span>
            </div>
            <hr />
            <div className="flex justify-between">
              <span className="text-gray-500">累積リターン</span>
              <PnLBadge pnl={v2Summary.cumulativePnlPct} />
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Alpha (vs {benchmarkName})</span>
              <PnLBadge pnl={v2Summary.alpha} />
            </div>
          </div>
        </div>
      </div>

      {/* Equity Curve Chart */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">資産推移（直近30日）</h3>
        <EquityCurveChart
          v1Snapshots={v1Snapshots}
          v2Snapshots={v2Snapshots}
          benchmarkName={benchmarkName}
          isJapan={isJapan}
        />
      </div>

      {/* Trade Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="card text-center">
          <p className="text-gray-500 text-sm">総トレード数</p>
          <p className="text-4xl font-bold text-gray-700">{totalTrades}</p>
        </div>
        <div className="card text-center">
          <p className="text-gray-500 text-sm">勝率（実現）</p>
          <p className="text-4xl font-bold text-primary-600">{winRate}%</p>
        </div>
        <div className="card text-center">
          <p className="text-gray-500 text-sm">平均リターン</p>
          <p className={`text-4xl font-bold ${Number(avgPnl) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {avgPnl !== '---' ? `${avgPnl}%` : avgPnl}
          </p>
        </div>
        <div className="card text-center">
          <p className="text-gray-500 text-sm">オープンポジション</p>
          <p className="text-4xl font-bold text-gray-700">{openPositions.length}</p>
        </div>
      </div>

      {/* Dynamic Thresholds */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">動的閾値（フィードバックループ）</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="p-4 bg-blue-50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-blue-800">V1 Conservative</span>
              <span className="text-2xl font-bold text-blue-900">
                {v1Config?.threshold ?? 60}点
              </span>
            </div>
            <p className="text-sm text-blue-600">
              範囲: {v1Config?.min_threshold ?? 40} - {v1Config?.max_threshold ?? 80}
            </p>
            {v1Config?.last_adjustment_date && (
              <p className="text-xs text-blue-500 mt-2">
                最終調整: {v1Config.last_adjustment_date}
              </p>
            )}
          </div>
          <div className="p-4 bg-orange-50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-orange-800">V2 Aggressive</span>
              <span className="text-2xl font-bold text-orange-900">
                {v2Config?.threshold ?? 75}点
              </span>
            </div>
            <p className="text-sm text-orange-600">
              範囲: {v2Config?.min_threshold ?? 50} - {v2Config?.max_threshold ?? 90}
            </p>
            {v2Config?.last_adjustment_date && (
              <p className="text-xs text-orange-500 mt-2">
                最終調整: {v2Config.last_adjustment_date}
              </p>
            )}
          </div>
        </div>

        {/* Threshold History */}
        {thresholdHistory.length > 0 && (
          <div className="mt-4">
            <h4 className="font-medium text-gray-700 mb-2">閾値変更履歴</h4>
            <div className="space-y-2">
              {thresholdHistory.slice(0, 5).map((h, i) => (
                <div key={i} className="text-sm p-2 bg-gray-50 rounded flex items-center justify-between">
                  <div>
                    <StrategyBadge strategy={h.strategy_mode} />
                    <span className="ml-2">
                      {h.old_threshold} → {h.new_threshold}
                    </span>
                  </div>
                  <div className="text-gray-500 text-xs">
                    {h.adjustment_date}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Open Positions */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">オープンポジション</h3>
        {openPositions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b text-left text-sm text-gray-500">
                  <th className="pb-3">戦略</th>
                  <th className="pb-3">銘柄</th>
                  <th className="pb-3">エントリー日</th>
                  <th className="pb-3 text-right">エントリー価格</th>
                  <th className="pb-3 text-right">株数</th>
                  <th className="pb-3 text-right">ポジション価値</th>
                  <th className="pb-3 text-right">スコア</th>
                </tr>
              </thead>
              <tbody>
                {openPositions.map((pos) => (
                  <tr key={pos.id} className="border-b last:border-0">
                    <td className="py-3">
                      <StrategyBadge strategy={pos.strategy_mode} />
                    </td>
                    <td className="py-3 font-medium">{getStockDisplayName(pos.symbol)}</td>
                    <td className="py-3 text-sm text-gray-600">
                      {format(parseISO(pos.entry_date), 'MM/dd', { locale: ja })}
                    </td>
                    <td className="py-3 text-right">{formatPrice(pos.entry_price, isJapan)}</td>
                    <td className="py-3 text-right">{pos.shares?.toFixed(2)}</td>
                    <td className="py-3 text-right">{formatCurrency(pos.position_value, isJapan)}</td>
                    <td className="py-3 text-right">{pos.entry_score ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-gray-500 text-center py-8">
            オープンポジションはありません
          </p>
        )}
      </div>

      {/* Trade History */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">トレード履歴（直近30日）</h3>
        {trades.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b text-left text-sm text-gray-500">
                  <th className="pb-3">戦略</th>
                  <th className="pb-3">銘柄</th>
                  <th className="pb-3">エントリー</th>
                  <th className="pb-3">エグジット</th>
                  <th className="pb-3 text-right">保有日数</th>
                  <th className="pb-3 text-right">損益</th>
                  <th className="pb-3 text-center">理由</th>
                </tr>
              </thead>
              <tbody>
                {trades.slice(0, 20).map((trade) => (
                  <tr key={trade.id} className="border-b last:border-0">
                    <td className="py-3">
                      <StrategyBadge strategy={trade.strategy_mode} />
                    </td>
                    <td className="py-3 font-medium">{getStockDisplayName(trade.symbol)}</td>
                    <td className="py-3 text-sm text-gray-600">
                      {format(parseISO(trade.entry_date), 'MM/dd', { locale: ja })}
                      <span className="text-gray-400 ml-1">{formatPrice(trade.entry_price, isJapan)}</span>
                    </td>
                    <td className="py-3 text-sm text-gray-600">
                      {format(parseISO(trade.exit_date), 'MM/dd', { locale: ja })}
                      <span className="text-gray-400 ml-1">{formatPrice(trade.exit_price, isJapan)}</span>
                    </td>
                    <td className="py-3 text-right">{trade.hold_days}日</td>
                    <td className="py-3 text-right">
                      <PnLBadge pnl={trade.pnl_pct} />
                    </td>
                    <td className="py-3 text-center">
                      <ExitReasonBadge reason={trade.exit_reason} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-gray-500 text-center py-8">
            トレード履歴がありません
          </p>
        )}
      </div>
    </div>
  );
}

export default async function PortfolioPage() {
  // Fetch data for both US and Japan portfolios in parallel
  const [
    // US
    usV1Summary,
    usV2Summary,
    usOpenPositions,
    usTrades,
    usV1Snapshots,
    usV2Snapshots,
    // JP
    jpV1Summary,
    jpV2Summary,
    jpOpenPositions,
    jpTrades,
    jpV1Snapshots,
    jpV2Snapshots,
    // Shared
    configs,
    thresholdHistory,
  ] = await Promise.all([
    // US
    getPortfolioSummary('conservative'),
    getPortfolioSummary('aggressive'),
    getOpenPositions('conservative').then(async (v1) => {
      const v2 = await getOpenPositions('aggressive');
      return [...v1, ...v2];
    }),
    getTradeHistory(30, 'conservative').then(async (v1) => {
      const v2 = await getTradeHistory(30, 'aggressive');
      return [...v1, ...v2].sort((a, b) =>
        new Date(b.exit_date).getTime() - new Date(a.exit_date).getTime()
      );
    }),
    getPortfolioSnapshots('conservative', 30),
    getPortfolioSnapshots('aggressive', 30),
    // JP
    getPortfolioSummary('jp_conservative'),
    getPortfolioSummary('jp_aggressive'),
    getOpenPositions('jp_conservative').then(async (v1) => {
      const v2 = await getOpenPositions('jp_aggressive');
      return [...v1, ...v2];
    }),
    getTradeHistory(30, 'jp_conservative').then(async (v1) => {
      const v2 = await getTradeHistory(30, 'jp_aggressive');
      return [...v1, ...v2].sort((a, b) =>
        new Date(b.exit_date).getTime() - new Date(a.exit_date).getTime()
      );
    }),
    getPortfolioSnapshots('jp_conservative', 30),
    getPortfolioSnapshots('jp_aggressive', 30),
    // Shared
    getScoringConfigs(),
    getThresholdHistory(30),
  ]);

  // Get configs for each market
  const usV1Config = configs.find(c => c.strategy_mode === 'conservative');
  const usV2Config = configs.find(c => c.strategy_mode === 'aggressive');
  const jpV1Config = configs.find(c => c.strategy_mode === 'jp_conservative');
  const jpV2Config = configs.find(c => c.strategy_mode === 'jp_aggressive');

  // Filter threshold history by market
  const usThresholdHistory = thresholdHistory.filter(
    h => h.strategy_mode === 'conservative' || h.strategy_mode === 'aggressive'
  );
  const jpThresholdHistory = thresholdHistory.filter(
    h => h.strategy_mode === 'jp_conservative' || h.strategy_mode === 'jp_aggressive'
  );

  // US Content
  const usContent = (
    <PortfolioContent
      v1Summary={usV1Summary}
      v2Summary={usV2Summary}
      openPositions={usOpenPositions}
      trades={usTrades}
      v1Config={usV1Config}
      v2Config={usV2Config}
      thresholdHistory={usThresholdHistory}
      v1Snapshots={usV1Snapshots}
      v2Snapshots={usV2Snapshots}
      isJapan={false}
      v1Strategy="conservative"
      v2Strategy="aggressive"
    />
  );

  // JP Content
  const jpContent = (
    <PortfolioContent
      v1Summary={jpV1Summary}
      v2Summary={jpV2Summary}
      openPositions={jpOpenPositions}
      trades={jpTrades}
      v1Config={jpV1Config}
      v2Config={jpV2Config}
      thresholdHistory={jpThresholdHistory}
      v1Snapshots={jpV1Snapshots}
      v2Snapshots={jpV2Snapshots}
      isJapan={true}
      v1Strategy="jp_conservative"
      v2Strategy="jp_aggressive"
    />
  );

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold text-gray-900">ポートフォリオ</h2>
      </div>

      {/* Market Tabs */}
      <MarketTabs usContent={usContent} jpContent={jpContent} />
    </div>
  );
}
