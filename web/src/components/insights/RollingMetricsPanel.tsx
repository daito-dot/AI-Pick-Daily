'use client';

import { Card, StatCard, EmptyState, Badge } from '@/components/ui';
import type { RollingMetrics } from '@/types';

interface RollingMetricsPanelProps {
  metrics: RollingMetrics[];
  isJapan: boolean;
}

export function RollingMetricsPanel({ metrics, isJapan }: RollingMetricsPanelProps) {
  if (metrics.length === 0) {
    return (
      <Card>
        <h3 className="section-title mb-3">ローリング指標（7日 / 30日）</h3>
        <EmptyState message="ローリング指標データがまだありません" icon="📉" />
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <h3 className="section-title">ローリング指標（7日 / 30日）</h3>

      {metrics.map((m) => (
        <Card key={m.strategy_mode}>
          <div className="flex items-center gap-3 mb-4">
            <Badge variant="strategy" value={m.strategy_mode} size="md" />
            <span className="text-xs text-gray-400">
              {m.metric_date}時点
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <p className="text-xs text-gray-500 mb-1">勝率 7d</p>
              <p className={`text-xl font-bold ${
                (m.win_rate_7d ?? 0) >= 55 ? 'text-green-600' :
                (m.win_rate_7d ?? 0) < 45 ? 'text-red-600' : 'text-gray-800'
              }`}>
                {m.win_rate_7d != null ? `${m.win_rate_7d.toFixed(1)}%` : '---'}
              </p>
              <p className="text-xs text-gray-400">
                30d: {m.win_rate_30d != null ? `${m.win_rate_30d.toFixed(1)}%` : '---'}
              </p>
            </div>

            <div className="text-center">
              <p className="text-xs text-gray-500 mb-1">平均リターン 7d</p>
              <p className={`text-xl font-bold ${
                (m.avg_return_7d ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
              }`}>
                {m.avg_return_7d != null
                  ? `${m.avg_return_7d >= 0 ? '+' : ''}${m.avg_return_7d.toFixed(2)}%`
                  : '---'}
              </p>
              <p className="text-xs text-gray-400">
                30d: {m.avg_return_30d != null
                  ? `${m.avg_return_30d >= 0 ? '+' : ''}${m.avg_return_30d.toFixed(2)}%`
                  : '---'}
              </p>
            </div>

            <div className="text-center">
              <p className="text-xs text-gray-500 mb-1">判断数 7d</p>
              <p className="text-xl font-bold text-gray-800">
                {m.total_judgments_7d ?? '---'}
              </p>
              <p className="text-xs text-gray-400">
                30d: {m.total_judgments_30d ?? '---'}
              </p>
            </div>

            <div className="text-center">
              <p className="text-xs text-gray-500 mb-1">見逃し率 7d</p>
              <p className={`text-xl font-bold ${
                (m.missed_rate_7d ?? 0) > 20 ? 'text-red-600' :
                (m.missed_rate_7d ?? 0) > 10 ? 'text-yellow-600' : 'text-green-600'
              }`}>
                {m.missed_rate_7d != null ? `${m.missed_rate_7d.toFixed(1)}%` : '---'}
              </p>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}
