import { getRecentPicks } from '@/lib/supabase';
import { format, parseISO } from 'date-fns';
import { ja } from 'date-fns/locale';
import type { DailyPick, StrategyModeType } from '@/types';

export const revalidate = 300;

interface GroupedPicks {
  date: string;
  v1: DailyPick | null;
  v2: DailyPick | null;
  regime: string;
}

function StrategyBadge({ strategy }: { strategy: StrategyModeType }) {
  const isV1 = strategy === 'conservative';
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
      isV1 ? 'bg-blue-100 text-blue-800' : 'bg-orange-100 text-orange-800'
    }`}>
      {isV1 ? 'V1 Conservative' : 'V2 Aggressive'}
    </span>
  );
}

function RegimeBadge({ regime }: { regime: string }) {
  return (
    <span className={`px-3 py-1 rounded-full text-sm font-medium ${
      regime === 'normal'
        ? 'bg-green-100 text-green-800'
        : regime === 'adjustment'
        ? 'bg-yellow-100 text-yellow-800'
        : 'bg-red-100 text-red-800'
    }`}>
      {regime === 'normal' ? '通常' :
       regime === 'adjustment' ? '調整' : 'クライシス'}
    </span>
  );
}

function PicksList({ pick, strategy }: { pick: DailyPick | null; strategy: StrategyModeType }) {
  const isV1 = strategy === 'conservative';
  const bgColor = isV1 ? 'bg-blue-50' : 'bg-orange-50';
  const borderColor = isV1 ? 'border-blue-200' : 'border-orange-200';
  const symbolBg = isV1 ? 'bg-blue-100 text-blue-700' : 'bg-orange-100 text-orange-700';

  if (!pick) {
    return (
      <div className={`p-4 rounded-lg ${bgColor} ${borderColor} border`}>
        <div className="flex items-center gap-2 mb-2">
          <StrategyBadge strategy={strategy} />
        </div>
        <p className="text-gray-400 text-sm italic">データなし</p>
      </div>
    );
  }

  return (
    <div className={`p-4 rounded-lg ${bgColor} ${borderColor} border`}>
      <div className="flex items-center justify-between mb-2">
        <StrategyBadge strategy={strategy} />
        <span className="text-sm text-gray-500">{pick.pick_count}銘柄</span>
      </div>
      {pick.symbols.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {pick.symbols.map((symbol) => (
            <span
              key={symbol}
              className={`px-3 py-1 rounded-lg text-sm font-medium ${symbolBg}`}
            >
              {symbol}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-gray-400 text-sm italic">推奨銘柄なし</p>
      )}
    </div>
  );
}

export default async function HistoryPage() {
  const recentPicks = await getRecentPicks(14);

  // Group picks by date
  const groupedByDate = recentPicks.reduce((acc, pick) => {
    const existing = acc.find(g => g.date === pick.batch_date);
    if (existing) {
      if (pick.strategy_mode === 'conservative') {
        existing.v1 = pick;
      } else {
        existing.v2 = pick;
      }
    } else {
      acc.push({
        date: pick.batch_date,
        v1: pick.strategy_mode === 'conservative' ? pick : null,
        v2: pick.strategy_mode === 'aggressive' ? pick : null,
        regime: pick.market_regime,
      });
    }
    return acc;
  }, [] as GroupedPicks[]);

  // Sort by date descending
  groupedByDate.sort((a, b) => b.date.localeCompare(a.date));

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold text-gray-900">過去のピック</h2>
        <p className="text-gray-500 mt-1">直近14日間の推奨銘柄履歴</p>
      </div>

      {groupedByDate.length > 0 ? (
        <div className="space-y-6">
          {groupedByDate.map((group) => (
            <div key={group.date} className="card">
              {/* Date Header */}
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold">
                  {format(parseISO(group.date), 'yyyy年MM月dd日 (E)', { locale: ja })}
                </h3>
                <RegimeBadge regime={group.regime} />
              </div>

              {/* V1 and V2 side by side */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <PicksList pick={group.v1} strategy="conservative" />
                <PicksList pick={group.v2} strategy="aggressive" />
              </div>
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
