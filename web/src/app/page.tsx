import { getTodayPicks } from '@/lib/supabase';
import { StockCard } from '@/components/StockCard';
import { MarketRegimeStatus } from '@/components/MarketRegimeStatus';
import { format } from 'date-fns';
import { ja } from 'date-fns/locale';

export const revalidate = 300; // Revalidate every 5 minutes

export default async function HomePage() {
  const { picks, scores, regime } = await getTodayPicks();

  const today = format(new Date(), 'yyyy年MM月dd日 (E)', { locale: ja });

  // Filter scores to only show picked symbols
  const pickedSymbols = picks?.symbols || [];
  const pickedScores = scores.filter(s => pickedSymbols.includes(s.symbol));

  return (
    <div className="space-y-8">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold text-gray-900">本日のピック</h2>
          <p className="text-gray-500 mt-1">{today}</p>
        </div>
        {regime && (
          <MarketRegimeStatus
            regime={regime.market_regime}
            vixLevel={regime.vix_level}
            notes={regime.notes}
          />
        )}
      </div>

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
                リスク管理を優先してください。
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Stock Picks Grid */}
      {pickedScores.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {pickedScores.map((score) => (
            <StockCard
              key={score.id}
              symbol={score.symbol}
              compositeScore={score.composite_score}
              percentileRank={score.percentile_rank}
              trendScore={score.trend_score}
              momentumScore={score.momentum_score}
              valueScore={score.value_score}
              sentimentScore={score.sentiment_score}
              reasoning={score.reasoning}
              priceAtTime={score.price_at_time}
            />
          ))}
        </div>
      ) : (
        !regime?.market_regime || regime.market_regime !== 'crisis' ? (
          <div className="card text-center py-12">
            <p className="text-gray-500 text-lg">
              本日のピックはまだ生成されていません。
            </p>
            <p className="text-gray-400 text-sm mt-2">
              通常、日本時間 07:00 頃に更新されます。
            </p>
          </div>
        ) : null
      )}

      {/* All Scores Section */}
      {scores.length > pickedScores.length && (
        <div className="mt-12">
          <h3 className="text-xl font-semibold text-gray-800 mb-4">
            全スコア一覧（上位20銘柄）
          </h3>
          <div className="card overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b text-left text-sm text-gray-500">
                  <th className="pb-3">銘柄</th>
                  <th className="pb-3 text-center">総合</th>
                  <th className="pb-3 text-center">%ile</th>
                  <th className="pb-3 text-center">Trend</th>
                  <th className="pb-3 text-center">Mom</th>
                  <th className="pb-3 text-center">Value</th>
                  <th className="pb-3 text-center">Sent</th>
                </tr>
              </thead>
              <tbody>
                {scores.slice(0, 20).map((score) => (
                  <tr key={score.id} className="border-b last:border-0">
                    <td className="py-3 font-medium">
                      {pickedSymbols.includes(score.symbol) && (
                        <span className="text-yellow-500 mr-1">★</span>
                      )}
                      {score.symbol}
                    </td>
                    <td className="py-3 text-center font-semibold">
                      {score.composite_score}
                    </td>
                    <td className="py-3 text-center text-gray-500">
                      {score.percentile_rank}
                    </td>
                    <td className="py-3 text-center">{score.trend_score}</td>
                    <td className="py-3 text-center">{score.momentum_score}</td>
                    <td className="py-3 text-center">{score.value_score}</td>
                    <td className="py-3 text-center">{score.sentiment_score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
