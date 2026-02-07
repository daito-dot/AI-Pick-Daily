import { Card, Badge, PnLDisplay, EmptyState } from '@/components/ui';
import { getStockDisplayName } from '@/lib/jp-stocks';
import { format, parseISO } from 'date-fns';
import { ja } from 'date-fns/locale';
import type { StockScore } from '@/types';

interface MissedOpportunitiesProps {
  missedOpportunities: StockScore[];
}

export function MissedOpportunities({ missedOpportunities }: MissedOpportunitiesProps) {
  if (missedOpportunities.length === 0) return null;

  return (
    <div>
      <h3 className="section-title mb-3">見逃した上昇銘柄</h3>
      <Card className="!p-0 overflow-hidden border-loss/20">
        <div className="px-4 py-3 bg-red-50/50 border-b border-red-100">
          <p className="text-xs text-gray-500">
            推奨しなかったが、5日後に3%以上上昇した銘柄
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50/50">
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">日付</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">銘柄</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500">戦略</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500">スコア</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500">5日リターン</th>
              </tr>
            </thead>
            <tbody>
              {missedOpportunities.slice(0, 10).map((m) => (
                <tr key={m.id} className="border-t border-gray-50 hover:bg-red-50/30">
                  <td className="px-4 py-3 text-gray-500">
                    {format(parseISO(m.batch_date), 'MM/dd', { locale: ja })}
                  </td>
                  <td className="px-4 py-3 font-medium">{getStockDisplayName(m.symbol)}</td>
                  <td className="px-4 py-3 text-center">
                    <Badge variant="strategy" value={m.strategy_mode} />
                  </td>
                  <td className="px-4 py-3 text-right">{m.composite_score}</td>
                  <td className="px-4 py-3 text-right">
                    <PnLDisplay value={m.return_5d ?? 0} size="sm" showArrow={false} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
