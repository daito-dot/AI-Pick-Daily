import { getTodayPicks, getTodayJudgments, getPortfolioSummary, getOpenPositions } from '@/lib/supabase';
import { PageHeader } from '@/components/ui';
import { MarketTabs } from '@/components/MarketTabs';
import { MarketRegimeStatus } from '@/components/MarketRegimeStatus';
import { QuickPortfolioSummary, TodaysPicks, ActivePositions } from '@/components/dashboard';
import { format } from 'date-fns';
import { ja } from 'date-fns/locale';
import type { PortfolioSummaryWithRisk, StrategyModeType } from '@/types';

export const revalidate = 300;

interface DashboardContentProps {
  picksData: Awaited<ReturnType<typeof getTodayPicks>>;
  judgments: Awaited<ReturnType<typeof getTodayJudgments>>;
  v1Summary: PortfolioSummaryWithRisk;
  v2Summary: PortfolioSummaryWithRisk;
  openPositions: any[];
  isJapan: boolean;
  conservativeStrategy: StrategyModeType;
  aggressiveStrategy: StrategyModeType;
}

function DashboardContent({
  picksData,
  judgments,
  v1Summary,
  v2Summary,
  openPositions,
  isJapan,
  conservativeStrategy,
  aggressiveStrategy,
}: DashboardContentProps) {
  const regime = picksData.regime;

  return (
    <div className="space-y-6">
      {/* Market Regime */}
      {regime && (
        <div className="flex items-center justify-between">
          <MarketRegimeStatus
            regime={regime.market_regime}
            vixLevel={regime.vix_level}
            notes={regime.notes}
          />
        </div>
      )}

      {/* Crisis Warning */}
      {regime?.market_regime === 'crisis' && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-5">
          <div className="flex items-center gap-3">
            <span className="text-2xl">⚠️</span>
            <div>
              <h3 className="font-semibold text-red-800">市場がクライシスモードです</h3>
              <p className="text-sm text-red-600">VIXが高水準のため、本日の推奨銘柄はありません。</p>
            </div>
          </div>
        </div>
      )}

      {/* Quick Portfolio Summary */}
      <QuickPortfolioSummary v1Summary={v1Summary} v2Summary={v2Summary} isJapan={isJapan} />

      {/* Today's Picks */}
      {regime?.market_regime !== 'crisis' && (
        <TodaysPicks
          conservativePicks={picksData.conservativePicks?.symbols || []}
          aggressivePicks={picksData.aggressivePicks?.symbols || []}
          conservativeScores={picksData.conservativeScores}
          aggressiveScores={picksData.aggressiveScores}
          judgments={judgments}
          isJapan={isJapan}
          conservativeStrategy={conservativeStrategy}
          aggressiveStrategy={aggressiveStrategy}
        />
      )}

      {/* Active Positions */}
      <ActivePositions positions={openPositions} isJapan={isJapan} />
    </div>
  );
}

export default async function DashboardPage() {
  const [
    usPicksData, jpPicksData,
    usJudgments, jpJudgments,
    usV1Summary, usV2Summary,
    jpV1Summary, jpV2Summary,
    usOpenPositions, jpOpenPositions,
  ] = await Promise.all([
    getTodayPicks('us'),
    getTodayPicks('jp'),
    getTodayJudgments('us'),
    getTodayJudgments('jp'),
    getPortfolioSummary('conservative'),
    getPortfolioSummary('aggressive'),
    getPortfolioSummary('jp_conservative'),
    getPortfolioSummary('jp_aggressive'),
    getOpenPositions('conservative').then(async (v1) => {
      const v2 = await getOpenPositions('aggressive');
      return [...v1, ...v2];
    }),
    getOpenPositions('jp_conservative').then(async (v1) => {
      const v2 = await getOpenPositions('jp_aggressive');
      return [...v1, ...v2];
    }),
  ]);

  const today = format(new Date(), 'yyyy年MM月dd日 (E)', { locale: ja });

  const usContent = (
    <DashboardContent
      picksData={usPicksData}
      judgments={usJudgments}
      v1Summary={usV1Summary}
      v2Summary={usV2Summary}
      openPositions={usOpenPositions}
      isJapan={false}
      conservativeStrategy="conservative"
      aggressiveStrategy="aggressive"
    />
  );

  const jpContent = (
    <DashboardContent
      picksData={jpPicksData}
      judgments={jpJudgments}
      v1Summary={jpV1Summary}
      v2Summary={jpV2Summary}
      openPositions={jpOpenPositions}
      isJapan={true}
      conservativeStrategy="jp_conservative"
      aggressiveStrategy="jp_aggressive"
    />
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" subtitle={today} />
      <MarketTabs usContent={usContent} jpContent={jpContent} />
    </div>
  );
}
