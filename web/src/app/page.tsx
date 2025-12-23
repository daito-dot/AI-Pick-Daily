import { getTodayPicks, getTodayJudgments, getTodayBatchStatus } from '@/lib/supabase';
import type { MarketType } from '@/lib/supabase';
import { getStockDisplayName } from '@/lib/jp-stocks';
import { MarketTabs } from '@/components/MarketTabs';
import { MarketRegimeStatus } from '@/components/MarketRegimeStatus';
import { JudgmentPanel } from '@/components/JudgmentPanel';
import { SystemStatusPanel } from '@/components/SystemStatus';
import { format } from 'date-fns';
import { ja } from 'date-fns/locale';
import type { StockScore, StrategyModeType, MarketRegimeHistory, JudgmentRecord } from '@/types';

export const revalidate = 300; // Revalidate every 5 minutes

interface StrategyCardProps {
  strategyMode: StrategyModeType;
  picks: string[];
  scores: StockScore[];
  isJapan?: boolean;
}

function StrategySection({ strategyMode, picks, scores, isJapan = false }: StrategyCardProps) {
  const isAggressive = strategyMode === 'aggressive' || strategyMode === 'jp_aggressive';
  const pickedScores = scores.filter(s => picks.includes(s.symbol));

  const config = {
    conservative: {
      title: 'V1: Conservative',
      subtitle: 'バランス型（低リスク）',
      bgColor: 'bg-blue-50',
      borderColor: 'border-blue-200',
      textColor: 'text-blue-800',
    },
    aggressive: {
      title: 'V2: Aggressive',
      subtitle: 'モメンタム重視（高リターン）',
      bgColor: 'bg-orange-50',
      borderColor: 'border-orange-200',
      textColor: 'text-orange-800',
    },
    jp_conservative: {
      title: 'V1: Conservative',
      subtitle: 'バランス型（低リスク）',
      bgColor: 'bg-blue-50',
      borderColor: 'border-blue-200',
      textColor: 'text-blue-800',
    },
    jp_aggressive: {
      title: 'V2: Aggressive',
      subtitle: 'モメンタム重視（高リターン）',
      bgColor: 'bg-orange-50',
      borderColor: 'border-orange-200',
      textColor: 'text-orange-800',
    },
  };

  const c = config[strategyMode];
  const currencySymbol = isJapan ? '¥' : '$';

  return (
    <div className={`rounded-xl ${c.bgColor} ${c.borderColor} border p-6`}>
      <div className="mb-4">
        <h3 className={`text-xl font-bold ${c.textColor}`}>{c.title}</h3>
        <p className="text-sm text-gray-600">{c.subtitle}</p>
      </div>

      {pickedScores.length > 0 ? (
        <div className="space-y-4">
          {pickedScores.map((score) => (
            <div key={score.id} className="bg-white rounded-lg p-4 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="font-bold text-lg">{getStockDisplayName(score.symbol)}</span>
                <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                  score.composite_score >= 75 ? 'bg-green-100 text-green-800' :
                  score.composite_score >= 60 ? 'bg-yellow-100 text-yellow-800' :
                  'bg-red-100 text-red-800'
                }`}>
                  {score.composite_score}点
                </span>
              </div>

              <div className="grid grid-cols-4 gap-2 text-xs text-center">
                {isAggressive ? (
                  <>
                    <div>
                      <div className="text-gray-500">Mom12-1</div>
                      <div className="font-medium">{score.momentum_12_1_score ?? '-'}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">Break</div>
                      <div className="font-medium">{score.breakout_score ?? '-'}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">Catalyst</div>
                      <div className="font-medium">{score.catalyst_score ?? '-'}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">Risk</div>
                      <div className="font-medium">{score.risk_adjusted_score ?? '-'}</div>
                    </div>
                  </>
                ) : (
                  <>
                    <div>
                      <div className="text-gray-500">Trend</div>
                      <div className="font-medium">{score.trend_score}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">Mom</div>
                      <div className="font-medium">{score.momentum_score}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">Value</div>
                      <div className="font-medium">{score.value_score}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">Sent</div>
                      <div className="font-medium">{score.sentiment_score}</div>
                    </div>
                  </>
                )}
              </div>

              {score.price_at_time && (
                <p className="mt-2 text-xs text-gray-400">
                  {currencySymbol}{isJapan ? Math.round(score.price_at_time).toLocaleString() : score.price_at_time.toFixed(2)}
                </p>
              )}

              {score.reasoning && (
                <p className="mt-2 text-xs text-gray-500 truncate">
                  {score.reasoning}
                </p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-gray-400 text-sm italic">本日のピックなし</p>
      )}
    </div>
  );
}

interface MarketContentProps {
  conservativePicks: string[];
  aggressivePicks: string[];
  conservativeScores: StockScore[];
  aggressiveScores: StockScore[];
  regime: MarketRegimeHistory | null;
  judgments: JudgmentRecord[];
  isJapan?: boolean;
  conservativeStrategyMode: StrategyModeType;
  aggressiveStrategyMode: StrategyModeType;
}

function MarketContent({
  conservativePicks,
  aggressivePicks,
  conservativeScores,
  aggressiveScores,
  regime,
  judgments,
  isJapan = false,
  conservativeStrategyMode,
  aggressiveStrategyMode,
}: MarketContentProps) {
  const benchmarkName = isJapan ? '日経225' : 'S&P 500';
  const benchmarkDesc = isJapan
    ? '日経225をベンチマークとして使用'
    : 'S&P 500をベンチマークとして使用';

  return (
    <div className="space-y-8">
      {/* Market Regime */}
      {regime && (
        <div className="flex justify-end">
          <MarketRegimeStatus
            regime={regime.market_regime}
            vixLevel={regime.vix_level}
            notes={regime.notes}
          />
        </div>
      )}

      {/* Crisis Mode Warning */}
      {regime?.market_regime === 'crisis' && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <div className="flex items-center gap-3">
            <span className="text-3xl">⚠️</span>
            <div>
              <h3 className="text-lg font-semibold text-red-800">
                市場がクライシスモードです
              </h3>
              <p className="text-red-600">
                VIXが高水準のため、本日の推奨銘柄はありません。
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Dual Strategy Display */}
      {regime?.market_regime !== 'crisis' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <StrategySection
            strategyMode={conservativeStrategyMode}
            picks={conservativePicks}
            scores={conservativeScores}
            isJapan={isJapan}
          />
          <StrategySection
            strategyMode={aggressiveStrategyMode}
            picks={aggressivePicks}
            scores={aggressiveScores}
            isJapan={isJapan}
          />
        </div>
      )}

      {/* Strategy Comparison Note */}
      <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-600">
        <h4 className="font-semibold mb-2">戦略の違い</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <span className="font-medium text-blue-700">V1 Conservative:</span>
            <p>4ファクター均衡型。Trend/Momentum/Value/Sentimentを35/35/20/10の配分で評価。安定志向。</p>
          </div>
          <div>
            <span className="font-medium text-orange-700">V2 Aggressive:</span>
            <p>モメンタム重視型。12-1モメンタム/ブレイクアウト/カタリストを40/25/20/15で評価。高リターン志向。</p>
          </div>
        </div>
        <p className="mt-2 text-xs text-gray-400">
          {benchmarkDesc}
        </p>
      </div>

      {/* LLM Judgment Panel (Layer 2) */}
      {judgments.length > 0 && (
        <div className="mt-8">
          <JudgmentPanel judgments={judgments} />
        </div>
      )}

      {/* Full Scores Table */}
      {(conservativeScores.length > 0 || aggressiveScores.length > 0) && (
        <div className="mt-12">
          <h3 className="text-xl font-semibold text-gray-800 mb-4">
            全スコア比較（上位10銘柄）
          </h3>
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-3">銘柄</th>
                  <th className="pb-3 text-center">V1スコア</th>
                  <th className="pb-3 text-center">V2スコア</th>
                  <th className="pb-3 text-center">差分</th>
                  <th className="pb-3 text-center">V1 Pick</th>
                  <th className="pb-3 text-center">V2 Pick</th>
                </tr>
              </thead>
              <tbody>
                {conservativeScores.slice(0, 10).map((v1Score) => {
                  const v2Score = aggressiveScores.find(s => s.symbol === v1Score.symbol);
                  const diff = v2Score ? v2Score.composite_score - v1Score.composite_score : 0;
                  const isV1Pick = conservativePicks.includes(v1Score.symbol);
                  const isV2Pick = aggressivePicks.includes(v1Score.symbol);

                  return (
                    <tr key={v1Score.id} className="border-b last:border-0">
                      <td className="py-3 font-medium">{getStockDisplayName(v1Score.symbol)}</td>
                      <td className="py-3 text-center">{v1Score.composite_score}</td>
                      <td className="py-3 text-center">{v2Score?.composite_score ?? '-'}</td>
                      <td className={`py-3 text-center font-medium ${
                        diff > 0 ? 'text-green-600' : diff < 0 ? 'text-red-600' : ''
                      }`}>
                        {diff > 0 ? '+' : ''}{diff}
                      </td>
                      <td className="py-3 text-center">
                        {isV1Pick && <span className="text-blue-500">★</span>}
                      </td>
                      <td className="py-3 text-center">
                        {isV2Pick && <span className="text-orange-500">★</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default async function HomePage() {
  // Fetch data for both US and Japan markets in parallel
  const [usPicksData, jpPicksData, usJudgments, jpJudgments, batchStatus] = await Promise.all([
    getTodayPicks('us'),
    getTodayPicks('jp'),
    getTodayJudgments('us'),
    getTodayJudgments('jp'),
    getTodayBatchStatus(),
  ]);

  const today = format(new Date(), 'yyyy年MM月dd日 (E)', { locale: ja });

  // US Content
  const usContent = (
    <MarketContent
      conservativePicks={usPicksData.conservativePicks?.symbols || []}
      aggressivePicks={usPicksData.aggressivePicks?.symbols || []}
      conservativeScores={usPicksData.conservativeScores}
      aggressiveScores={usPicksData.aggressiveScores}
      regime={usPicksData.regime}
      judgments={usJudgments}
      isJapan={false}
      conservativeStrategyMode="conservative"
      aggressiveStrategyMode="aggressive"
    />
  );

  // Japan Content
  const jpContent = (
    <MarketContent
      conservativePicks={jpPicksData.conservativePicks?.symbols || []}
      aggressivePicks={jpPicksData.aggressivePicks?.symbols || []}
      conservativeScores={jpPicksData.conservativeScores}
      aggressiveScores={jpPicksData.aggressiveScores}
      regime={jpPicksData.regime}
      judgments={jpJudgments}
      isJapan={true}
      conservativeStrategyMode="jp_conservative"
      aggressiveStrategyMode="jp_aggressive"
    />
  );

  return (
    <div className="space-y-8">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold text-gray-900">本日のピック</h2>
          <p className="text-gray-500 mt-1">{today}</p>
        </div>
      </div>

      {/* Market Tabs */}
      <MarketTabs usContent={usContent} jpContent={jpContent} />

      {/* System Status Panel */}
      <div className="mt-8">
        <SystemStatusPanel status={batchStatus} />
      </div>
    </div>
  );
}
