'use client';

import { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { Card, StatCard, Badge, EmptyState } from '@/components/ui';
import type { JudgmentOutcomeStats, OutcomeTrend } from '@/types';

interface JudgmentOutcomesPanelProps {
  stats: JudgmentOutcomeStats[];
  trends: OutcomeTrend[];
  isJapan: boolean;
}

function shortenModel(name: string): string {
  return name
    .replace('models/', '')
    .replace('-preview', '')
    .replace('-instruct', '');
}

// Distinct colors for model lines
const MODEL_COLORS = [
  '#3B82F6', '#F97316', '#8B5CF6', '#10B981', '#EF4444',
  '#EC4899', '#06B6D4', '#F59E0B', '#6366F1', '#14B8A6',
];

export function JudgmentOutcomesPanel({ stats, trends, isJapan }: JudgmentOutcomesPanelProps) {
  // Detect unique models
  const models = useMemo(() => {
    const set = new Set(stats.map((s) => s.model_version));
    return Array.from(set).sort();
  }, [stats]);

  const hasMultipleModels = models.length > 1;

  const summary = useMemo(() => {
    const byDecision = (decision: string) => {
      const items = stats.filter((s) => s.decision === decision);
      const total = items.reduce((a, b) => a + b.total, 0);
      const correct = items.reduce((a, b) => a + b.correct, 0);
      return { total, correct, pct: total > 0 ? (correct / total) * 100 : 0 };
    };
    const all = stats.reduce((a, b) => ({ total: a.total + b.total, correct: a.correct + b.correct }), { total: 0, correct: 0 });

    return {
      buy: byDecision('buy'),
      hold: byDecision('hold'),
      avoid: byDecision('avoid'),
      overall: { ...all, pct: all.total > 0 ? (all.correct / all.total) * 100 : 0 },
    };
  }, [stats]);

  // Build chart data: one line per model (aggregating strategies)
  const chartData = useMemo(() => {
    const trendModels = Array.from(new Set(trends.map((t) => t.model_version))).sort();
    const dates = Array.from(new Set(trends.map((t) => t.batch_date))).sort();

    return dates.map((date) => {
      const point: Record<string, string | number | null> = { date: date.slice(5) };
      for (const model of trendModels) {
        const items = trends.filter((t) => t.batch_date === date && t.model_version === model);
        if (items.length > 0) {
          const totalAll = items.reduce((a, b) => a + b.total, 0);
          const alignedAll = items.reduce((a, b) => a + b.aligned, 0);
          point[model] = totalAll > 0 ? Math.round((alignedAll / totalAll) * 1000) / 10 : null;
        } else {
          point[model] = null;
        }
      }
      return point;
    });
  }, [trends]);

  const trendModels = useMemo(() =>
    Array.from(new Set(trends.map((t) => t.model_version))).sort(),
  [trends]);

  if (stats.length === 0) {
    return (
      <Card>
        <h3 className="section-title mb-3">判断精度（Judgment Outcomes）</h3>
        <EmptyState message="判断結果データがまだありません" icon="📊" />
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <h3 className="section-title">判断精度（Judgment Outcomes）</h3>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Buy精度"
          value={`${summary.buy.pct.toFixed(1)}%`}
          trend={summary.buy.pct >= 55 ? 'up' : summary.buy.pct < 45 ? 'down' : undefined}
          sub={`${summary.buy.correct}/${summary.buy.total}`}
        />
        <StatCard
          label="Hold精度"
          value={summary.hold.total > 0 ? `${summary.hold.pct.toFixed(1)}%` : '---'}
          sub={summary.hold.total > 0 ? `${summary.hold.correct}/${summary.hold.total}` : undefined}
        />
        <StatCard
          label="Avoid精度"
          value={`${summary.avoid.pct.toFixed(1)}%`}
          trend={summary.avoid.pct >= 55 ? 'up' : summary.avoid.pct < 45 ? 'down' : undefined}
          sub={`${summary.avoid.correct}/${summary.avoid.total}`}
        />
        <StatCard
          label="全体精度"
          value={`${summary.overall.pct.toFixed(1)}%`}
          trend={summary.overall.pct >= 55 ? 'up' : summary.overall.pct < 45 ? 'down' : undefined}
          sub={`${summary.overall.correct}/${summary.overall.total}件`}
        />
      </div>

      {/* Detail Table — now includes model column */}
      <Card>
        <h4 className="text-sm font-semibold text-gray-700 mb-3">
          {hasMultipleModels ? 'モデル x 戦略 x 判断 詳細' : '戦略 x 判断 詳細'}
        </h4>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                {hasMultipleModels && (
                  <th className="text-left py-2 px-3 text-gray-500 font-medium">モデル</th>
                )}
                <th className="text-left py-2 px-3 text-gray-500 font-medium">戦略</th>
                <th className="text-left py-2 px-3 text-gray-500 font-medium">判断</th>
                <th className="text-right py-2 px-3 text-gray-500 font-medium">件数</th>
                <th className="text-right py-2 px-3 text-gray-500 font-medium">正解</th>
                <th className="text-right py-2 px-3 text-gray-500 font-medium">精度</th>
                <th className="text-right py-2 px-3 text-gray-500 font-medium">平均1dリターン</th>
                <th className="text-right py-2 px-3 text-gray-500 font-medium">平均5dリターン</th>
              </tr>
            </thead>
            <tbody>
              {stats.map((row) => (
                <tr key={`${row.model_version}-${row.strategy_mode}-${row.decision}`} className="border-b border-gray-50 hover:bg-gray-50">
                  {hasMultipleModels && (
                    <td className="py-2 px-3 font-mono text-xs text-gray-600 max-w-[140px] truncate" title={row.model_version}>
                      {shortenModel(row.model_version)}
                    </td>
                  )}
                  <td className="py-2 px-3">
                    <Badge variant="strategy" value={row.strategy_mode} />
                  </td>
                  <td className="py-2 px-3">
                    <Badge variant="decision" value={row.decision} />
                  </td>
                  <td className="text-right py-2 px-3 font-mono">{row.total}</td>
                  <td className="text-right py-2 px-3 font-mono">{row.correct}</td>
                  <td className="text-right py-2 px-3 font-mono font-semibold">
                    <span className={row.accuracy_pct >= 55 ? 'text-green-600' : row.accuracy_pct < 45 ? 'text-red-600' : 'text-gray-700'}>
                      {row.accuracy_pct.toFixed(1)}%
                    </span>
                  </td>
                  <td className="text-right py-2 px-3 font-mono">
                    {row.avg_return_1d != null ? (
                      <span className={row.avg_return_1d >= 0 ? 'text-green-600' : 'text-red-600'}>
                        {row.avg_return_1d >= 0 ? '+' : ''}{row.avg_return_1d.toFixed(3)}%
                      </span>
                    ) : '---'}
                  </td>
                  <td className="text-right py-2 px-3 font-mono">
                    {row.avg_return_5d != null ? (
                      <span className={row.avg_return_5d >= 0 ? 'text-green-600' : 'text-red-600'}>
                        {row.avg_return_5d >= 0 ? '+' : ''}{row.avg_return_5d.toFixed(3)}%
                      </span>
                    ) : '---'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Trend Chart — one line per model */}
      {chartData.length > 1 && (
        <Card>
          <h4 className="text-sm font-semibold text-gray-700 mb-3">精度推移（直近30日）</h4>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
              <Tooltip formatter={(value: number) => [`${value.toFixed(1)}%`, '']} />
              <Legend />
              {trendModels.map((model, i) => (
                <Line
                  key={model}
                  type="monotone"
                  dataKey={model}
                  name={shortenModel(model)}
                  stroke={MODEL_COLORS[i % MODEL_COLORS.length]}
                  strokeWidth={2}
                  dot={{ r: 2 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}
    </div>
  );
}
