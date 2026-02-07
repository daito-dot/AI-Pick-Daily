import {
  getPortfolioSummary,
  getOpenPositions,
  getTradeHistory,
  getPortfolioSnapshots,
  getScoringConfigs,
  getThresholdHistory,
  getFactorWeights,
} from '@/lib/supabase';
import { PageHeader } from '@/components/ui';
import { MarketTabs } from '@/components/MarketTabs';
import { EquityCurveChart } from '@/components/EquityCurveChart';
import {
  PortfolioSummaryCards,
  TradeHistoryTable,
  ThresholdsDisplay,
  FactorWeightsSection,
  PositionsTable,
} from '@/components/portfolio';
import type { PortfolioSummaryWithRisk } from '@/types';

export const revalidate = 300;

interface PortfolioContentProps {
  v1Summary: PortfolioSummaryWithRisk;
  v2Summary: PortfolioSummaryWithRisk;
  openPositions: any[];
  trades: any[];
  v1Config: any;
  v2Config: any;
  thresholdHistory: any[];
  v1Snapshots: any[];
  v2Snapshots: any[];
  v1Weights: any;
  v2Weights: any;
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
  v1Weights,
  v2Weights,
  isJapan,
  v1Strategy,
  v2Strategy,
}: PortfolioContentProps) {
  const benchmarkName = isJapan ? '日経225' : 'S&P500';
  const initialFund = isJapan ? '¥100,000' : '$100,000';

  return (
    <div className="space-y-8">
      <p className="text-sm text-gray-400">仮想運用シミュレーション（初期資金: {initialFund}）</p>

      {/* Portfolio Summary Cards */}
      <PortfolioSummaryCards
        v1Summary={v1Summary}
        v2Summary={v2Summary}
        isJapan={isJapan}
        v1Strategy={v1Strategy}
        v2Strategy={v2Strategy}
      />

      {/* Equity Curve Chart */}
      <div>
        <h3 className="section-title mb-3">資産推移（直近30日）</h3>
        <div className="card">
          <EquityCurveChart
            v1Snapshots={v1Snapshots}
            v2Snapshots={v2Snapshots}
            benchmarkName={benchmarkName}
            isJapan={isJapan}
          />
        </div>
      </div>

      {/* Factor Weights */}
      <FactorWeightsSection v1Weights={v1Weights} v2Weights={v2Weights} />

      {/* Open Positions */}
      <PositionsTable positions={openPositions} isJapan={isJapan} />

      {/* Trade History */}
      <TradeHistoryTable trades={trades} isJapan={isJapan} />

      {/* Dynamic Thresholds */}
      <ThresholdsDisplay
        v1Config={v1Config}
        v2Config={v2Config}
        thresholdHistory={thresholdHistory}
      />
    </div>
  );
}

export default async function PortfolioPage() {
  const [
    // US
    usV1Summary,
    usV2Summary,
    usOpenPositions,
    usTrades,
    usV1Snapshots,
    usV2Snapshots,
    usWeights,
    // JP
    jpV1Summary,
    jpV2Summary,
    jpOpenPositions,
    jpTrades,
    jpV1Snapshots,
    jpV2Snapshots,
    jpWeights,
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
    getFactorWeights('us'),
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
    getFactorWeights('jp'),
    // Shared
    getScoringConfigs(),
    getThresholdHistory(30),
  ]);

  // Get configs for each market
  const usV1Config = configs.find((c: any) => c.strategy_mode === 'conservative');
  const usV2Config = configs.find((c: any) => c.strategy_mode === 'aggressive');
  const jpV1Config = configs.find((c: any) => c.strategy_mode === 'jp_conservative');
  const jpV2Config = configs.find((c: any) => c.strategy_mode === 'jp_aggressive');

  // Filter threshold history by market
  const usThresholdHistory = thresholdHistory.filter(
    (h: any) => h.strategy_mode === 'conservative' || h.strategy_mode === 'aggressive'
  );
  const jpThresholdHistory = thresholdHistory.filter(
    (h: any) => h.strategy_mode === 'jp_conservative' || h.strategy_mode === 'jp_aggressive'
  );

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
      v1Weights={usWeights.v1}
      v2Weights={usWeights.v2}
      isJapan={false}
      v1Strategy="conservative"
      v2Strategy="aggressive"
    />
  );

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
      v1Weights={jpWeights.v1}
      v2Weights={jpWeights.v2}
      isJapan={true}
      v1Strategy="jp_conservative"
      v2Strategy="jp_aggressive"
    />
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Portfolio" subtitle="ポートフォリオ管理 & パフォーマンス" />
      <MarketTabs usContent={usContent} jpContent={jpContent} />
    </div>
  );
}
