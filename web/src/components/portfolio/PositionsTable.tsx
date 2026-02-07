import { Card, Badge, EmptyState } from '@/components/ui';
import { getStockDisplayName } from '@/lib/jp-stocks';
import { format, parseISO } from 'date-fns';
import { ja } from 'date-fns/locale';

interface PositionsTableProps {
  positions: any[];
  isJapan: boolean;
}

export function PositionsTable({ positions, isJapan }: PositionsTableProps) {
  const fmtPrice = (p: number) =>
    isJapan ? `¥${Math.round(p).toLocaleString()}` : `$${p.toFixed(2)}`;
  const fmtValue = (v: number) =>
    isJapan ? `¥${Math.round(v).toLocaleString()}` : `$${Math.round(v).toLocaleString()}`;

  return (
    <div>
      <h3 className="section-title mb-3">オープンポジション</h3>
      <Card className="!p-0 overflow-hidden">
        {positions.length === 0 ? (
          <EmptyState message="オープンポジションはありません" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50/50">
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">戦略</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">銘柄</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 hidden md:table-cell">エントリー日</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 hidden md:table-cell">価格</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500">株数</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500">価値</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 hidden md:table-cell">スコア</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos: any) => (
                  <tr key={pos.id} className="border-t border-gray-50 hover:bg-gray-50/50">
                    <td className="px-4 py-3"><Badge variant="strategy" value={pos.strategy_mode} /></td>
                    <td className="px-4 py-3 font-medium">{getStockDisplayName(pos.symbol)}</td>
                    <td className="px-4 py-3 text-gray-500 hidden md:table-cell">
                      {format(parseISO(pos.entry_date), 'MM/dd', { locale: ja })}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-500 hidden md:table-cell">{fmtPrice(pos.entry_price)}</td>
                    <td className="px-4 py-3 text-right">{pos.shares?.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right font-medium">{fmtValue(pos.position_value)}</td>
                    <td className="px-4 py-3 text-right text-gray-500 hidden md:table-cell">{pos.entry_score ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
