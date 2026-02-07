import { Card, Badge, EmptyState } from '@/components/ui';
import { getStockDisplayName } from '@/lib/jp-stocks';
import { format, parseISO } from 'date-fns';
import { ja } from 'date-fns/locale';
import type { DailyPick } from '@/types';

interface PastPicksHistoryProps {
  recentPicks: DailyPick[];
  isJapan: boolean;
}

interface GroupedPicks {
  date: string;
  v1: DailyPick | null;
  v2: DailyPick | null;
  regime: string;
}

function isV1Strategy(strategy: string): boolean {
  return strategy === 'conservative' || strategy === 'jp_conservative';
}

export function PastPicksHistory({ recentPicks, isJapan }: PastPicksHistoryProps) {
  // Filter picks for current market
  const marketPicks = recentPicks.filter((p) =>
    isJapan ? p.strategy_mode.startsWith('jp_') : !p.strategy_mode.startsWith('jp_')
  );

  // Group by date
  const grouped = marketPicks.reduce((acc, pick) => {
    const existing = acc.find((g) => g.date === pick.batch_date);
    if (existing) {
      if (isV1Strategy(pick.strategy_mode)) {
        existing.v1 = pick;
      } else {
        existing.v2 = pick;
      }
    } else {
      acc.push({
        date: pick.batch_date,
        v1: isV1Strategy(pick.strategy_mode) ? pick : null,
        v2: !isV1Strategy(pick.strategy_mode) ? pick : null,
        regime: pick.market_regime,
      });
    }
    return acc;
  }, [] as GroupedPicks[]);

  grouped.sort((a, b) => b.date.localeCompare(a.date));

  if (grouped.length === 0) {
    return (
      <div>
        <h3 className="section-title mb-3">過去のピック（14日間）</h3>
        <Card>
          <EmptyState message="過去のピックデータがありません" />
        </Card>
      </div>
    );
  }

  return (
    <div>
      <h3 className="section-title mb-3">過去のピック（14日間）</h3>
      <div className="space-y-3">
        {grouped.map((group) => (
          <Card key={group.date}>
            <div className="flex items-center gap-3 mb-3">
              <span className="text-sm font-medium text-gray-700">
                {format(parseISO(group.date), 'MM/dd (E)', { locale: ja })}
              </span>
              <Badge variant="regime" value={group.regime} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* V1 */}
              <div className="p-3 bg-blue-50/50 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-medium text-blue-700">V1 Conservative</span>
                  <span className="text-xs text-gray-400">{group.v1?.pick_count ?? 0}銘柄</span>
                </div>
                {group.v1?.symbols && group.v1.symbols.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {group.v1.symbols.map((sym) => (
                      <span key={sym} className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded font-medium">
                        {getStockDisplayName(sym)}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-400 italic">なし</p>
                )}
              </div>
              {/* V2 */}
              <div className="p-3 bg-orange-50/50 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-medium text-orange-700">V2 Aggressive</span>
                  <span className="text-xs text-gray-400">{group.v2?.pick_count ?? 0}銘柄</span>
                </div>
                {group.v2?.symbols && group.v2.symbols.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {group.v2.symbols.map((sym) => (
                      <span key={sym} className="px-2 py-0.5 bg-orange-100 text-orange-700 text-xs rounded font-medium">
                        {getStockDisplayName(sym)}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-400 italic">なし</p>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
