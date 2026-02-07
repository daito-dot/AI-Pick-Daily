import { Card, Badge, PnLDisplay, EmptyState } from '@/components/ui';
import { getStockDisplayName } from '@/lib/jp-stocks';

interface Position {
  id: string;
  strategy_mode: string;
  symbol: string;
  entry_date: string;
  entry_price: number;
  shares: number;
  position_value: number;
  entry_score: number | null;
}

interface ActivePositionsProps {
  positions: Position[];
  isJapan: boolean;
}

export function ActivePositions({ positions, isJapan }: ActivePositionsProps) {
  if (positions.length === 0) {
    return null;
  }

  return (
    <div>
      <h3 className="section-title mb-3">保有ポジション（{positions.length}件）</h3>
      <Card className="!p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50/50">
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">戦略</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">銘柄</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 hidden md:table-cell">エントリー</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500">価値</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 hidden md:table-cell">スコア</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos) => {
                const currency = isJapan ? '¥' : '$';
                const price = isJapan
                  ? `${currency}${Math.round(pos.entry_price).toLocaleString()}`
                  : `${currency}${pos.entry_price.toFixed(2)}`;
                const value = isJapan
                  ? `${currency}${Math.round(pos.position_value).toLocaleString()}`
                  : `${currency}${Math.round(pos.position_value).toLocaleString()}`;

                return (
                  <tr key={pos.id} className="border-t border-gray-50 hover:bg-gray-50/50">
                    <td className="px-4 py-3">
                      <Badge variant="strategy" value={pos.strategy_mode} />
                    </td>
                    <td className="px-4 py-3 font-medium">{getStockDisplayName(pos.symbol)}</td>
                    <td className="px-4 py-3 text-right text-gray-500 hidden md:table-cell">
                      {price}
                    </td>
                    <td className="px-4 py-3 text-right font-medium">{value}</td>
                    <td className="px-4 py-3 text-right text-gray-500 hidden md:table-cell">
                      {pos.entry_score ?? '-'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
