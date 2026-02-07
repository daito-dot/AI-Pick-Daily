import {
  getPerformanceStats,
  getPerformanceComparison,
  getMissedOpportunities,
  getRecentPicks,
  getTodayPicks,
  getTodayJudgments,
  getScoringConfigs,
} from '@/lib/supabase';
import { PageHeader } from '@/components/ui';
import { MarketTabs } from '@/components/MarketTabs';
import {
  JudgmentAccuracyStats,
  PerformanceComparison,
  MissedOpportunities,
  PastPicksHistory,
  JudgmentDetailPanel,
} from '@/components/analytics';
import type { PerformanceStats, DailyPick, JudgmentRecord } from '@/types';

export const revalidate = 300;

interface AnalyticsContentProps {
  stats: PerformanceStats | null;
  comparison: {
    pickedCount: number;
    pickedAvgReturn: number;
    notPickedCount: number;
    notPickedAvgReturn: number;
    missedOpportunities: number;
  };
  missed: any[];
  recentPicks: DailyPick[];
  judgments: JudgmentRecord[];
  picksData: Awaited<ReturnType<typeof getTodayPicks>>;
  isJapan: boolean;
  v1Config: any;
  v2Config: any;
}

function AnalyticsContent({
  stats,
  comparison,
  missed,
  recentPicks,
  judgments,
  picksData,
  isJapan,
  v1Config,
  v2Config,
}: AnalyticsContentProps) {
  const conservativeStrategy = isJapan ? 'jp_conservative' : 'conservative';
  const aggressiveStrategy = isJapan ? 'jp_aggressive' : 'aggressive';

  const finalPicks = {
    conservative: picksData.conservativePicks?.symbols || [],
    aggressive: picksData.aggressivePicks?.symbols || [],
  };

  const confidenceThreshold = {
    conservative: v1Config?.confidence_threshold ?? 0.6,
    aggressive: v2Config?.confidence_threshold ?? 0.5,
  };

  const scoreThreshold = {
    conservative: v1Config?.threshold ?? 60,
    aggressive: v2Config?.threshold ?? 75,
  };

  const ruleBasedScores = {
    conservative: picksData.conservativeScores.map((s) => ({
      symbol: s.symbol,
      composite_score: s.composite_score,
      percentile_rank: s.percentile_rank ?? 0,
      price_at_time: s.price_at_time,
      return_1d: s.return_1d,
      return_5d: s.return_5d,
    })),
    aggressive: picksData.aggressiveScores.map((s) => ({
      symbol: s.symbol,
      composite_score: s.composite_score,
      percentile_rank: s.percentile_rank ?? 0,
      price_at_time: s.price_at_time,
      return_1d: s.return_1d,
      return_5d: s.return_5d,
    })),
  };

  return (
    <div className="space-y-8">
      {/* AI Judgment Accuracy */}
      <div>
        <h3 className="section-title mb-3">AI判断精度（直近30日）</h3>
        <JudgmentAccuracyStats stats={stats} />
      </div>

      {/* Performance Comparison */}
      <PerformanceComparison comparison={comparison} />

      {/* Missed Opportunities */}
      <MissedOpportunities missedOpportunities={missed} />

      {/* Past Picks */}
      <PastPicksHistory recentPicks={recentPicks} isJapan={isJapan} />

      {/* Judgment Detail Panel */}
      <JudgmentDetailPanel
        judgments={judgments}
        finalPicks={finalPicks}
        confidenceThreshold={confidenceThreshold}
        ruleBasedScores={ruleBasedScores}
        scoreThreshold={scoreThreshold}
        isJapan={isJapan}
      />
    </div>
  );
}

export default async function AnalyticsPage() {
  const [
    usStats,
    jpStats,
    usComparison,
    jpComparison,
    usMissed,
    jpMissed,
    recentPicks,
    usPicksData,
    jpPicksData,
    usJudgments,
    jpJudgments,
    configs,
  ] = await Promise.all([
    getPerformanceStats('us'),
    getPerformanceStats('jp'),
    getPerformanceComparison(30, 'us'),
    getPerformanceComparison(30, 'jp'),
    getMissedOpportunities(30, 3.0, 'us'),
    getMissedOpportunities(30, 3.0, 'jp'),
    getRecentPicks(14),
    getTodayPicks('us'),
    getTodayPicks('jp'),
    getTodayJudgments('us'),
    getTodayJudgments('jp'),
    getScoringConfigs(),
  ]);

  const usV1Config = configs.find((c: any) => c.strategy_mode === 'conservative');
  const usV2Config = configs.find((c: any) => c.strategy_mode === 'aggressive');
  const jpV1Config = configs.find((c: any) => c.strategy_mode === 'jp_conservative');
  const jpV2Config = configs.find((c: any) => c.strategy_mode === 'jp_aggressive');

  const usContent = (
    <AnalyticsContent
      stats={usStats}
      comparison={usComparison}
      missed={usMissed}
      recentPicks={recentPicks}
      judgments={usJudgments}
      picksData={usPicksData}
      isJapan={false}
      v1Config={usV1Config}
      v2Config={usV2Config}
    />
  );

  const jpContent = (
    <AnalyticsContent
      stats={jpStats}
      comparison={jpComparison}
      missed={jpMissed}
      recentPicks={recentPicks}
      judgments={jpJudgments}
      picksData={jpPicksData}
      isJapan={true}
      v1Config={jpV1Config}
      v2Config={jpV2Config}
    />
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Analytics" subtitle="AI判断の精度分析 & パフォーマンス追跡" />
      <MarketTabs usContent={usContent} jpContent={jpContent} />
    </div>
  );
}
