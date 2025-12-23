import { getRecentPicks } from '@/lib/supabase';
import { getStockDisplayName } from '@/lib/jp-stocks';
import { format, parseISO } from 'date-fns';
import { ja } from 'date-fns/locale';
import type { DailyPick, StrategyModeType } from '@/types';

export const revalidate = 300;

// Helper to check if strategy is V1 (conservative) type
function isV1Strategy(strategy: string): boolean {
  return strategy === 'conservative' || strategy === 'jp_conservative';
}

// Helper to check if strategy is JP market
function isJPStrategy(strategy: string): boolean {
  return strategy.startsWith('jp_');
}

// Get market type from strategy
function getMarketType(strategy: string): 'us' | 'jp' {
  return isJPStrategy(strategy) ? 'jp' : 'us';
}

interface GroupedPicks {
  date: string;
  market: 'us' | 'jp';
  v1: DailyPick | null;
  v2: DailyPick | null;
  regime: string;
}

function StrategyBadge({ strategy }: { strategy: StrategyModeType }) {
  const isV1 = isV1Strategy(strategy);
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
      isV1 ? 'bg-blue-100 text-blue-800' : 'bg-orange-100 text-orange-800'
    }`}>
      {isV1 ? 'V1 Conservative' : 'V2 Aggressive'}
    </span>
  );
}

function MarketBadge({ market }: { market: 'us' | 'jp' }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
      market === 'jp' ? 'bg-red-100 text-red-800' : 'bg-indigo-100 text-indigo-800'
    }`}>
      {market === 'jp' ? '🇯🇵 日本株' : '🇺🇸 米国株'}
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

function PicksList({ pick, strategy, market }: {
  pick: DailyPick | null;
  strategy: StrategyModeType;
  market: 'us' | 'jp';
}) {
  const isV1 = isV1Strategy(strategy);
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
        <StrategyBadge strategy={pick.strategy_mode} />
        <span className="text-sm text-gray-500">{pick.pick_count}銘柄</span>
      </div>
      {pick.symbols.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {pick.symbols.map((symbol) => (
            <span
              key={symbol}
              className={`px-3 py-1 rounded-lg text-sm font-medium ${symbolBg}`}
            >
              {getStockDisplayName(symbol)}
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

  // Group picks by date and market
  const groupedByDateAndMarket = recentPicks.reduce((acc, pick) => {
    const market = getMarketType(pick.strategy_mode);
    const key = `${pick.batch_date}-${market}`;
    const existing = acc.find(g => g.date === pick.batch_date && g.market === market);

    if (existing) {
      if (isV1Strategy(pick.strategy_mode)) {
        existing.v1 = pick;
      } else {
        existing.v2 = pick;
      }
    } else {
      acc.push({
        date: pick.batch_date,
        market,
        v1: isV1Strategy(pick.strategy_mode) ? pick : null,
        v2: !isV1Strategy(pick.strategy_mode) ? pick : null,
        regime: pick.market_regime,
      });
    }
    return acc;
  }, [] as GroupedPicks[]);

  // Sort by date descending, then JP before US
  groupedByDateAndMarket.sort((a, b) => {
    const dateCompare = b.date.localeCompare(a.date);
    if (dateCompare !== 0) return dateCompare;
    return a.market === 'jp' ? -1 : 1;
  });

  // Group by date for display
  const dateGroups = groupedByDateAndMarket.reduce((acc, item) => {
    const existing = acc.find(g => g.date === item.date);
    if (existing) {
      existing.markets.push(item);
    } else {
      acc.push({ date: item.date, markets: [item] });
    }
    return acc;
  }, [] as { date: string; markets: GroupedPicks[] }[]);

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold text-gray-900">過去のピック</h2>
        <p className="text-gray-500 mt-1">直近14日間の推奨銘柄履歴</p>
      </div>

      {dateGroups.length > 0 ? (
        <div className="space-y-6">
          {dateGroups.map((dateGroup) => (
            <div key={dateGroup.date} className="card">
              {/* Date Header */}
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold">
                  {format(parseISO(dateGroup.date), 'yyyy年MM月dd日 (E)', { locale: ja })}
                </h3>
              </div>

              {/* Markets */}
              <div className="space-y-4">
                {dateGroup.markets.map((group) => (
                  <div key={`${group.date}-${group.market}`} className="border-t pt-4 first:border-t-0 first:pt-0">
                    <div className="flex items-center gap-2 mb-3">
                      <MarketBadge market={group.market} />
                      <RegimeBadge regime={group.regime} />
                    </div>

                    {/* V1 and V2 side by side */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <PicksList
                        pick={group.v1}
                        strategy={group.market === 'jp' ? 'jp_conservative' : 'conservative'}
                        market={group.market}
                      />
                      <PicksList
                        pick={group.v2}
                        strategy={group.market === 'jp' ? 'jp_aggressive' : 'aggressive'}
                        market={group.market}
                      />
                    </div>
                  </div>
                ))}
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
