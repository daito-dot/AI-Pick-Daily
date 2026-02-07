import { Card, Badge, PnLDisplay, EmptyState } from '@/components/ui';
import { getStockDisplayName } from '@/lib/jp-stocks';
import { format, parseISO } from 'date-fns';
import { ja } from 'date-fns/locale';

interface Trade {
  id: string;
  strategy_mode: string;
  symbol: string;
  entry_date: string;
  entry_price: number;
  exit_date: string;
  exit_price: number;
  hold_days: number;
  pnl_pct: number;
  exit_reason: string;
}

interface TradeHistoryTableProps {
  trades: Trade[];
  isJapan: boolean;
}

export function TradeHistoryTable({ trades, isJapan }: TradeHistoryTableProps) {
  const costRate = isJapan ? '~0.8%' : '~0.1%';

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="section-title">トレード履歴（直近30日）</h3>
        <span className="text-xs text-gray-400">コスト: 往復{costRate}</span>
      </div>
      <Card className="!p-0 overflow-hidden">
        {trades.length === 0 ? (
          <EmptyState message="トレード履歴がありません" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50/50">
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">戦略</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">銘柄</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 hidden md:table-cell">エントリー</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 hidden md:table-cell">エグジット</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500">保有日数</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500">損益</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500">理由</th>
                </tr>
              </thead>
              <tbody>
                {trades.slice(0, 20).map((trade) => {
                  const fmtPrice = (p: number) =>
                    isJapan ? `¥${Math.round(p).toLocaleString()}` : `$${p.toFixed(2)}`;
                  return (
                    <tr key={trade.id} className="border-t border-gray-50 hover:bg-gray-50/50">
                      <td className="px-4 py-3">
                        <Badge variant="strategy" value={trade.strategy_mode} />
                      </td>
                      <td className="px-4 py-3 font-medium">{getStockDisplayName(trade.symbol)}</td>
                      <td className="px-4 py-3 text-gray-500 hidden md:table-cell">
                        {format(parseISO(trade.entry_date), 'MM/dd', { locale: ja })}
                        <span className="text-gray-400 ml-1">{fmtPrice(trade.entry_price)}</span>
                      </td>
                      <td className="px-4 py-3 text-gray-500 hidden md:table-cell">
                        {format(parseISO(trade.exit_date), 'MM/dd', { locale: ja })}
                        <span className="text-gray-400 ml-1">{fmtPrice(trade.exit_price)}</span>
                      </td>
                      <td className="px-4 py-3 text-right">{trade.hold_days}日</td>
                      <td className="px-4 py-3 text-right">
                        <PnLDisplay value={trade.pnl_pct} size="sm" showArrow={false} />
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Badge variant="exitReason" value={trade.exit_reason} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
