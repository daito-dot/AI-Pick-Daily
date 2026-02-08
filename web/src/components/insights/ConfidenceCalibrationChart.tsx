'use client';

import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
} from 'recharts';
import { Card, EmptyState } from '@/components/ui';
import type { ConfidenceCalibrationBucket } from '@/types';

interface ConfidenceCalibrationChartProps {
  buckets: ConfidenceCalibrationBucket[];
}

function shortenModel(name: string): string {
  return name
    .replace('models/', '')
    .replace('-preview', '')
    .replace('-instruct', '');
}

const MODEL_COLORS = [
  '#3B82F6', '#F97316', '#8B5CF6', '#10B981', '#EF4444',
  '#EC4899', '#06B6D4', '#F59E0B', '#6366F1', '#14B8A6',
];

export function ConfidenceCalibrationChart({ buckets }: ConfidenceCalibrationChartProps) {
  const models = useMemo(() => {
    const set = new Set(buckets.map((b) => b.model_version));
    return Array.from(set).sort();
  }, [buckets]);

  const hasMultipleModels = models.length > 1;

  // Build grouped chart data: one entry per bucket, with accuracy per model
  const chartData = useMemo(() => {
    const bucketLabels = Array.from(new Set(buckets.map((b) => b.bucket))).sort();
    return bucketLabels.map((label) => {
      const point: Record<string, string | number | null> = { bucket: label };
      const bucketItem = buckets.find((b) => b.bucket === label);
      if (bucketItem) {
        point.expected = Math.round(((bucketItem.bucketMin + bucketItem.bucketMax) / 2) * 100);
      }
      for (const model of models) {
        const item = buckets.find((b) => b.bucket === label && b.model_version === model);
        point[model] = item ? item.accuracy : null;
      }
      return point;
    });
  }, [buckets, models]);

  if (buckets.length === 0) {
    return (
      <Card>
        <h3 className="section-title mb-3">信頼度キャリブレーション</h3>
        <EmptyState message="キャリブレーションデータがまだありません" icon="🎯" />
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="section-title">信頼度キャリブレーション</h3>
      <Card>
        <p className="text-xs text-gray-500 mb-3">
          AIの自信度レベルごとの実際の正答率。理想は対角線（自信50% → 正答50%）。
        </p>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
            <YAxis
              domain={[0, 100]}
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => `${v}%`}
            />
            <Tooltip
              content={({ active, payload, label }) => {
                if (!active || !payload || payload.length === 0) return null;
                const data = payload[0]?.payload;
                return (
                  <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-sm">
                    <p className="font-medium text-gray-800">{label}</p>
                    <p className="text-gray-500 text-xs">期待: {data?.expected}%</p>
                    {payload.map((entry) => (
                      <p key={String(entry.name)} style={{ color: entry.color }}>
                        {shortenModel(String(entry.name ?? ''))}: {typeof entry.value === 'number' ? `${Number(entry.value).toFixed(1)}%` : '---'}
                      </p>
                    ))}
                  </div>
                );
              }}
            />
            <ReferenceLine y={50} stroke="#9ca3af" strokeDasharray="3 3" />
            {hasMultipleModels && <Legend formatter={(value: string) => shortenModel(value)} />}
            {models.map((model, i) => (
              <Bar
                key={model}
                dataKey={model}
                name={model}
                fill={MODEL_COLORS[i % MODEL_COLORS.length]}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>

        {/* Legend for single model */}
        {!hasMultipleModels && (
          <div className="flex items-center justify-center gap-4 mt-2 text-xs text-gray-500">
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded inline-block" style={{ backgroundColor: MODEL_COLORS[0] }} /> 実際の正答率
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-gray-300 inline-block" /> 対角線 = 理想
            </span>
          </div>
        )}

        {/* Summary Table — model-aware */}
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                {hasMultipleModels && (
                  <th className="text-left py-1.5 px-2 text-gray-500 font-medium text-xs">モデル</th>
                )}
                <th className="text-left py-1.5 px-2 text-gray-500 font-medium text-xs">信頼度帯</th>
                <th className="text-right py-1.5 px-2 text-gray-500 font-medium text-xs">件数</th>
                <th className="text-right py-1.5 px-2 text-gray-500 font-medium text-xs">正答率</th>
                <th className="text-right py-1.5 px-2 text-gray-500 font-medium text-xs">平均リターン</th>
              </tr>
            </thead>
            <tbody>
              {models.map((model, mi) => {
                const modelBuckets = buckets.filter((b) => b.model_version === model);
                return modelBuckets.map((b, bi) => (
                  <tr
                    key={`${model}-${b.bucket}`}
                    className={`border-b ${bi === modelBuckets.length - 1 && mi < models.length - 1 ? 'border-gray-200' : 'border-gray-50'} hover:bg-gray-50`}
                  >
                    {hasMultipleModels && bi === 0 && (
                      <td
                        className="py-1.5 px-2 font-mono text-xs text-gray-600 max-w-[140px] truncate"
                        rowSpan={modelBuckets.length}
                        title={model}
                        style={{ borderLeft: `3px solid ${MODEL_COLORS[mi % MODEL_COLORS.length]}` }}
                      >
                        {shortenModel(model)}
                      </td>
                    )}
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
                ));
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
