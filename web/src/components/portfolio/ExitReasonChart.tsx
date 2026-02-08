'use client';

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { Card, EmptyState } from '@/components/ui';
import type { ExitReasonCount } from '@/types';

interface ExitReasonChartProps {
  data: ExitReasonCount[];
}

const EXIT_REASON_CONFIG: Record<string, { label: string; color: string }> = {
  take_profit: { label: '利確', color: '#22c55e' },
  stop_loss: { label: '損切', color: '#ef4444' },
  score_drop: { label: 'スコア低下', color: '#eab308' },
  max_hold: { label: '保有期限', color: '#6b7280' },
  absolute_max_hold: { label: '最大保有期限', color: '#9ca3af' },
  regime_change: { label: '相場変化', color: '#8b5cf6' },
};

function getConfig(reason: string) {
  return EXIT_REASON_CONFIG[reason] || { label: reason, color: '#d1d5db' };
}

export function ExitReasonChart({ data }: ExitReasonChartProps) {
  if (data.length === 0) {
    return (
      <Card>
        <h4 className="text-sm font-semibold text-gray-700 mb-3">決済理由の分布</h4>
        <EmptyState message="決済データがありません" icon="📊" />
      </Card>
    );
  }

  const total = data.reduce((sum, d) => sum + d.count, 0);
  const chartData = data.map((d) => ({
    name: getConfig(d.exit_reason).label,
    value: d.count,
    pct: ((d.count / total) * 100).toFixed(1),
    color: getConfig(d.exit_reason).color,
  }));

  return (
    <Card>
      <h4 className="text-sm font-semibold text-gray-700 mb-3">
        決済理由の分布
        <span className="text-xs text-gray-400 font-normal ml-2">直近90日 / {total}件</span>
      </h4>

      <div className="flex flex-col md:flex-row items-center gap-4">
        <div className="w-full md:w-1/2">
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={chartData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={80}
                innerRadius={40}
                paddingAngle={2}
              >
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value: number, name: string) => [`${value}件`, name]}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="w-full md:w-1/2 space-y-2">
          {chartData.map((d) => (
            <div key={d.name} className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <span
                  className="w-3 h-3 rounded-full inline-block flex-shrink-0"
                  style={{ backgroundColor: d.color }}
                />
                <span className="text-gray-700">{d.name}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-gray-600">{d.value}件</span>
                <span className="font-mono text-gray-400 text-xs w-12 text-right">{d.pct}%</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
