import { getRecentPicks, getScoresForDate } from '@/lib/supabase';
import { format, parseISO } from 'date-fns';
import { ja } from 'date-fns/locale';

export const revalidate = 300;

export default async function HistoryPage() {
  const recentPicks = await getRecentPicks(14);

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold text-gray-900">過去のピック</h2>
        <p className="text-gray-500 mt-1">直近14日間の推奨銘柄履歴</p>
      </div>

      {recentPicks.length > 0 ? (
        <div className="space-y-4">
          {recentPicks.map((pick) => (
            <div key={pick.id} className="card">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-lg font-semibold">
                    {format(parseISO(pick.batch_date), 'yyyy年MM月dd日 (E)', { locale: ja })}
                  </h3>
                  <p className="text-sm text-gray-500">
                    {pick.pick_count}銘柄を推奨
                  </p>
                </div>
                <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                  pick.market_regime === 'normal'
                    ? 'bg-green-100 text-green-800'
                    : pick.market_regime === 'adjustment'
                    ? 'bg-yellow-100 text-yellow-800'
                    : 'bg-red-100 text-red-800'
                }`}>
                  {pick.market_regime === 'normal' ? '通常' :
                   pick.market_regime === 'adjustment' ? '調整' : 'クライシス'}
                </span>
              </div>

              {pick.symbols.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {pick.symbols.map((symbol) => (
                    <span
                      key={symbol}
                      className="px-3 py-1 bg-primary-100 text-primary-700 rounded-lg text-sm font-medium"
                    >
                      {symbol}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-gray-400 italic">推奨銘柄なし</p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="card text-center py-12">
          <p className="text-gray-500 text-lg">
            履歴データがありません。
          </p>
        </div>
      )}
    </div>
  );
}
