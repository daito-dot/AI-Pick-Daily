import {
  getJudgmentOutcomeStats,
  getOutcomeTrends,
  getMetaInterventions,
  getActivePromptOverrides,
  getReflections,
} from '@/lib/supabase';
import { PageHeader } from '@/components/ui';
import { MarketTabs } from '@/components/MarketTabs';
import {
  JudgmentOutcomesPanel,
  ReflectionPanel,
  MetaMonitorPanel,
} from '@/components/insights';
import type { ReflectionRecord, JudgmentOutcomeStats, OutcomeTrend, MetaIntervention, PromptOverride } from '@/types';

export const revalidate = 300;

interface InsightsContentProps {
  stats: JudgmentOutcomeStats[];
  trends: OutcomeTrend[];
  reflections: ReflectionRecord[];
  interventions: MetaIntervention[];
  overrides: PromptOverride[];
  isJapan: boolean;
}

function InsightsContent({
  stats,
  trends,
  reflections,
  interventions,
  overrides,
  isJapan,
}: InsightsContentProps) {
  return (
    <div className="space-y-10">
      <JudgmentOutcomesPanel stats={stats} trends={trends} isJapan={isJapan} />
      <ReflectionPanel reflections={reflections} isJapan={isJapan} />
      <MetaMonitorPanel interventions={interventions} overrides={overrides} isJapan={isJapan} />
    </div>
  );
}

export default async function InsightsPage() {
  const [
    usStats,
    jpStats,
    usTrends,
    jpTrends,
    reflections,
    usInterventions,
    jpInterventions,
    usOverrides,
    jpOverrides,
  ] = await Promise.all([
    getJudgmentOutcomeStats('us'),
    getJudgmentOutcomeStats('jp'),
    getOutcomeTrends('us', 30),
    getOutcomeTrends('jp', 30),
    getReflections(10),
    getMetaInterventions('us', 20),
    getMetaInterventions('jp', 20),
    getActivePromptOverrides('us'),
    getActivePromptOverrides('jp'),
  ]);

  const usContent = (
    <InsightsContent
      stats={usStats}
      trends={usTrends}
      reflections={reflections}
      interventions={usInterventions}
      overrides={usOverrides}
      isJapan={false}
    />
  );

  const jpContent = (
    <InsightsContent
      stats={jpStats}
      trends={jpTrends}
      reflections={reflections}
      interventions={jpInterventions}
      overrides={jpOverrides}
      isJapan={true}
    />
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Insights" subtitle="AI判断精度・リフレクション・メタ監視" />
      <MarketTabs usContent={usContent} jpContent={jpContent} />
    </div>
  );
}
