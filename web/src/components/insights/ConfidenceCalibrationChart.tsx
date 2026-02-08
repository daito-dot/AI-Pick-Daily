'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
} from 'recharts';
import { Card, EmptyState } from '@/components/ui';
import type { ConfidenceCalibrationBucket } from '@/types';

interface ConfidenceCalibrationChartProps {
  buckets: ConfidenceCalibrationBucket[];
}

export function ConfidenceCalibrationChart({ buckets }: ConfidenceCalibrationChartProps) {
  if (buckets.length === 0) {
    return (
      <Card>
        <h3 className="section-title mb-3">信頼度キャリブレーション</h3>
        <EmptyState message="キャリブレーションデータがまだありません" icon="🎯" />
      </Card>
    );
  }

  // Chart data: expected confidence (midpoint) vs actual accuracy
  const chartData = buckets.map((b) => ({
    bucket: b.bucket,
    expected: Math.round(((b.bucketMin + b.bucketMax) / 2) * 100),
    actual: b.accuracy,
    total: b.total,
    avgReturn: b.avgReturn,
  }));

  const isCalibrated = (expected: number, actual: number) =>
    Math.abs(expected - actual) <= 10;

  return (
    <div className="space-y-4">
      <h3 className="section-title">信頼度キャリブレーション</h3>
      <Card>
        <p className="text-xs text-gray-500 mb-3">
          AIの自信度レベルごとの実際の正答率。理想は対角線（自信50% → 正答50%）。
        </p>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
            <YAxis
              domain={[0, 100]}
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => `${v}%`}
            />
            <Tooltip
              formatter={(value: number, name: string) => {
                if (name === 'actual') return [`${value.toFixed(1)}%`, '実際の正答率'];
                if (name === 'expected') return [`${value}%`, '期待正答率'];
                return [value, name];
              }}
              content={({ active, payload, label }) => {
                if (!active || !payload || payload.length === 0) return null;
                const data = payload[0]?.payload;
                return (
                  <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-sm">
                    <p className="font-medium text-gray-800">{label}</p>
                    <p className="text-gray-600">件数: {data?.total}</p>
                    <p className="text-blue-600">期待: {data?.expected}%</p>
                    <p className={data?.actual >= data?.expected ? 'text-green-600' : 'text-red-600'}>
                      実際: {data?.actual?.toFixed(1)}%
                    </p>
                    <p className={data?.avgReturn >= 0 ? 'text-green-600' : 'text-red-600'}>
                      平均リターン: {data?.avgReturn >= 0 ? '+' : ''}{data?.avgReturn?.toFixed(3)}%
                    </p>
                  </div>
                );
              }}
            />
            <ReferenceLine y={50} stroke="#9ca3af" strokeDasharray="3 3" label="" />
            <Bar dataKey="actual" name="actual" radius={[4, 4, 0, 0]}>
              {chartData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={
                    isCalibrated(entry.expected, entry.actual)
                      ? '#22c55e'
                      : entry.actual > entry.expected
                        ? '#3b82f6'
                        : '#ef4444'
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        {/* Legend */}
        <div className="flex items-center justify-center gap-4 mt-2 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded bg-green-500 inline-block" /> 適正
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded bg-blue-500 inline-block" /> 過小評価（実際の方が高い）
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded bg-red-500 inline-block" /> 過信（自信ほど当たらない）
          </span>
        </div>

        {/* Summary Table */}
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left py-1.5 px-2 text-gray-500 font-medium text-xs">信頼度帯</th>
                <th className="text-right py-1.5 px-2 text-gray-500 font-medium text-xs">件数</th>
                <th className="text-right py-1.5 px-2 text-gray-500 font-medium text-xs">正答率</th>
                <th className="text-right py-1.5 px-2 text-gray-500 font-medium text-xs">平均リターン</th>
              </tr>
            </thead>
            <tbody>
              {buckets.map((b) => (
                <tr key={b.bucket} className="border-b border-gray-50">
                  <td className="py-1.5 px-2 text-gray-700">{b.bucket}</td>
                  <td className="text-right py-1.5 px-2 font-mono text-gray-600">{b.total}</td>
                  <td className="text-right py-1.5 px-2 font-mono">
                    <span className={b.accuracy >= 55 ? 'text-green-600' : b.accuracy < 45 ? 'text-red-600' : 'text-gray-700'}>
                      {b.accuracy.toFixed(1)}%
                    </span>
                  </td>
                  <td className="text-right py-1.5 px-2 font-mono">
                    <span className={b.avgReturn >= 0 ? 'text-green-600' : 'text-red-600'}>
                      {b.avgReturn >= 0 ? '+' : ''}{b.avgReturn.toFixed(3)}%
                    </span>
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
