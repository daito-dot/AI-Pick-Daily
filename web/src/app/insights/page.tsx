import {
  getJudgmentOutcomeStats,
  getOutcomeTrends,
  getMetaInterventions,
  getActivePromptOverrides,
  getReflections,
  getRollingMetrics,
  getConfidenceCalibration,
  getParameterChangeLog,
  getModelPerformanceStats,
} from '@/lib/supabase';
import { PageHeader } from '@/components/ui';
import { MarketTabs } from '@/components/MarketTabs';
import {
  JudgmentOutcomesPanel,
  ReflectionPanel,
  MetaMonitorPanel,
  RollingMetricsPanel,
  ConfidenceCalibrationChart,
  ModelPerformancePanel,
} from '@/components/insights';
import type {
  ReflectionRecord,
  JudgmentOutcomeStats,
  OutcomeTrend,
  MetaIntervention,
  PromptOverride,
  RollingMetrics,
  ConfidenceCalibrationBucket,
  ParameterChangeRecord,
  ModelPerformanceStats,
} from '@/types';

export const revalidate = 300;

interface InsightsContentProps {
  stats: JudgmentOutcomeStats[];
  trends: OutcomeTrend[];
  reflections: ReflectionRecord[];
  interventions: MetaIntervention[];
  overrides: PromptOverride[];
  parameterChanges: ParameterChangeRecord[];
  rollingMetrics: RollingMetrics[];
  calibration: ConfidenceCalibrationBucket[];
  modelStats: ModelPerformanceStats[];
  isJapan: boolean;
}

function InsightsContent({
  stats,
  trends,
  reflections,
  interventions,
  overrides,
  parameterChanges,
  rollingMetrics,
  calibration,
  modelStats,
  isJapan,
}: InsightsContentProps) {
  return (
    <div className="space-y-10">
      <RollingMetricsPanel metrics={rollingMetrics} isJapan={isJapan} />
      <JudgmentOutcomesPanel stats={stats} trends={trends} isJapan={isJapan} />
      <ConfidenceCalibrationChart buckets={calibration} />
      <ModelPerformancePanel models={modelStats} />
      <ReflectionPanel reflections={reflections} isJapan={isJapan} />
      <MetaMonitorPanel interventions={interventions} overrides={overrides} parameterChanges={parameterChanges} isJapan={isJapan} />
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
    usRolling,
    jpRolling,
    usCalibration,
    jpCalibration,
    usParamChanges,
    jpParamChanges,
    usModelStats,
    jpModelStats,
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
    getRollingMetrics('us'),
    getRollingMetrics('jp'),
    getConfidenceCalibration('us'),
    getConfidenceCalibration('jp'),
    getParameterChangeLog('us'),
    getParameterChangeLog('jp'),
    getModelPerformanceStats('us'),
    getModelPerformanceStats('jp'),
  ]);

  const usContent = (
    <InsightsContent
      stats={usStats}
      trends={usTrends}
      reflections={reflections}
      interventions={usInterventions}
      overrides={usOverrides}
      parameterChanges={usParamChanges}
      rollingMetrics={usRolling}
      calibration={usCalibration}
      modelStats={usModelStats}
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
      parameterChanges={jpParamChanges}
      rollingMetrics={jpRolling}
      calibration={jpCalibration}
      modelStats={jpModelStats}
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
