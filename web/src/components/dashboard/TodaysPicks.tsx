import { Card } from '@/components/ui';
import { PickCard } from './PickCard';
import type { StockScore, JudgmentRecord, StrategyModeType } from '@/types';

interface TodaysPicksProps {
  conservativePicks: string[];
  aggressivePicks: string[];
  conservativeScores: StockScore[];
  aggressiveScores: StockScore[];
  judgments: JudgmentRecord[];
  isJapan: boolean;
  conservativeStrategy: StrategyModeType;
  aggressiveStrategy: StrategyModeType;
}

export function TodaysPicks({
  conservativePicks,
  aggressivePicks,
  conservativeScores,
  aggressiveScores,
  judgments,
  isJapan,
  conservativeStrategy,
  aggressiveStrategy,
}: TodaysPicksProps) {
  const v1Scores = conservativeScores.filter((s) => conservativePicks.includes(s.symbol));
  const v2Scores = aggressiveScores.filter((s) => aggressivePicks.includes(s.symbol));

  // Extract portfolio reasoning from judgments (stored in reasoning.decision_point for v2_portfolio)
  const portfolioJudgments = judgments.filter((j) => j.prompt_version === 'v2_portfolio');
  const portfolioReasoning = portfolioJudgments[0]?.reasoning?.decision_point;

  const judgmentMap = new Map<string, JudgmentRecord>();
  for (const j of judgments) {
    judgmentMap.set(`${j.symbol}-${j.strategy_mode}`, j);
  }

  const hasNoPicks = v1Scores.length === 0 && v2Scores.length === 0;

  return (
    <div className="space-y-6">
      {/* Portfolio Reasoning */}
      {portfolioReasoning && (
        <Card variant="highlighted" className="!p-4">
          <div className="flex items-start gap-3">
            <span className="text-lg">🤖</span>
            <div>
              <h4 className="text-sm font-semibold text-primary-800 mb-1">AIポートフォリオ判断</h4>
              <p className="text-sm text-primary-700">{portfolioReasoning}</p>
            </div>
          </div>
        </Card>
      )}

      {hasNoPicks ? (
        <Card className="text-center py-8">
          <p className="text-gray-400">本日の推奨銘柄はありません</p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* V1 Conservative */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <div className="w-1 h-5 bg-blue-500 rounded-full" />
              <h3 className="font-semibold text-gray-800">安定型（V1）</h3>
              <span className="text-xs text-gray-400">トレンド・バリュー重視</span>
            </div>
            {v1Scores.length > 0 ? (
              <div className="space-y-3">
                {v1Scores.map((score) => (
                  <PickCard
                    key={score.id}
                    score={score}
                    judgment={judgmentMap.get(`${score.symbol}-${conservativeStrategy}`)}
                    isJapan={isJapan}
                  />
                ))}
              </div>
            ) : (
              <Card className="!p-4 text-center">
                <p className="text-gray-400 text-sm">ピックなし</p>
              </Card>
            )}
          </div>

          {/* V2 Aggressive */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <div className="w-1 h-5 bg-orange-500 rounded-full" />
              <h3 className="font-semibold text-gray-800">成長型（V2）</h3>
              <span className="text-xs text-gray-400">モメンタム・ブレイクアウト重視</span>
            </div>
            {v2Scores.length > 0 ? (
              <div className="space-y-3">
                {v2Scores.map((score) => (
                  <PickCard
                    key={score.id}
                    score={score}
                    judgment={judgmentMap.get(`${score.symbol}-${aggressiveStrategy}`)}
                    isJapan={isJapan}
                  />
                ))}
              </div>
            ) : (
              <Card className="!p-4 text-center">
                <p className="text-gray-400 text-sm">ピックなし</p>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
