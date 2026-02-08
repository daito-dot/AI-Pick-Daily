'use client';

import { Card, StatCard, EmptyState } from '@/components/ui';
import type { ModelPerformanceStats } from '@/types';

interface ModelPerformancePanelProps {
  models: ModelPerformanceStats[];
}

function shortenModelName(name: string): string {
  // Shorten common model prefixes for display
  return name
    .replace('models/', '')
    .replace('-preview', '')
    .replace('-instruct', '');
}

export function ModelPerformancePanel({ models }: ModelPerformancePanelProps) {
  if (models.length === 0) {
    return (
      <div className="space-y-4">
        <h3 className="section-title">モデル別成績比較</h3>
        <Card>
          <EmptyState
            message="モデル別の成績データがまだありません。判断実行後に表示されます。"
            icon="🤖"
          />
        </Card>
      </div>
    );
  }

  // Find best model by win rate (with minimum 5 buys)
  const eligibleModels = models.filter(m => m.buy_count >= 5);
  const bestModel = eligibleModels.length > 0
    ? eligibleModels.reduce((a, b) => a.buy_win_rate > b.buy_win_rate ? a : b)
    : null;

  return (
    <div className="space-y-6">
      <h3 className="section-title">モデル別成績比較</h3>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <StatCard
          label="使用モデル数"
          value={models.length}
          sub="テスト中"
        />
        <StatCard
          label="総判断数"
          value={models.reduce((sum, m) => sum + m.total_judgments, 0)}
          sub="全モデル合計"
        />
        {bestModel && (
          <StatCard
            label="最高勝率モデル"
            value={`${bestModel.buy_win_rate.toFixed(0)}%`}
            variant="highlighted"
            sub={shortenModelName(bestModel.model_version)}
          />
        )}
      </div>

      {/* Comparison table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left py-2 px-3 text-gray-500 font-medium">モデル</th>
                <th className="text-right py-2 px-3 text-gray-500 font-medium">判断数</th>
                <th className="text-right py-2 px-3 text-gray-500 font-medium">Buy</th>
                <th className="text-right py-2 px-3 text-gray-500 font-medium">勝率</th>
                <th className="text-right py-2 px-3 text-gray-500 font-medium">平均5dリターン</th>
                <th className="text-right py-2 px-3 text-gray-500 font-medium">平均確信度</th>
                <th className="text-left py-2 px-3 text-gray-500 font-medium">使用期間</th>
              </tr>
            </thead>
            <tbody>
              {models.map((row) => {
                const isBest = bestModel && row.model_version === bestModel.model_version;
                return (
                  <tr
                    key={row.model_version}
                    className={`border-b border-gray-50 hover:bg-gray-50 ${isBest ? 'bg-green-50' : ''}`}
                  >
                    <td className="py-2 px-3 font-mono text-xs text-gray-700 max-w-[200px] truncate" title={row.model_version}>
                      {shortenModelName(row.model_version)}
                      {isBest && <span className="ml-1 text-green-600 text-[10px]">BEST</span>}
                    </td>
                    <td className="text-right py-2 px-3 text-gray-600">
                      {row.total_judgments}
                    </td>
                    <td className="text-right py-2 px-3 text-gray-600">
                      {row.buy_count}
                    </td>
                    <td className="text-right py-2 px-3 font-mono">
                      {row.buy_count > 0 ? (
                        <span className={row.buy_win_rate >= 50 ? 'text-green-600' : 'text-red-600'}>
                          {row.buy_win_rate.toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-gray-400">---</span>
                      )}
                    </td>
                    <td className="text-right py-2 px-3 font-mono">
                      {row.avg_return_5d != null ? (
                        <span className={row.avg_return_5d >= 0 ? 'text-green-600' : 'text-red-600'}>
                          {row.avg_return_5d >= 0 ? '+' : ''}{row.avg_return_5d.toFixed(2)}%
                        </span>
                      ) : (
                        <span className="text-gray-400">---</span>
                      )}
                    </td>
                    <td className="text-right py-2 px-3 font-mono text-gray-600">
                      {(row.avg_confidence * 100).toFixed(0)}%
                    </td>
                    <td className="py-2 px-3 text-gray-500 text-xs whitespace-nowrap">
                      {row.first_used.slice(5)} ~ {row.last_used.slice(5)}
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
