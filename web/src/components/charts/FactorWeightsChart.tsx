'use client';

import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Legend, ResponsiveContainer } from 'recharts';
import type { FactorWeights } from '@/types';

const FACTOR_LABELS: Record<string, string> = {
  trend: 'トレンド',
  momentum: 'モメンタム',
  value: 'バリュー',
  sentiment: 'センチメント',
  momentum_12_1: 'Mom 12-1',
  breakout: 'ブレイクアウト',
  catalyst: 'カタリスト',
  risk_adjusted: 'リスク調整',
};

const V1_DEFAULTS: FactorWeights = { trend: 0.35, momentum: 0.35, value: 0.20, sentiment: 0.10 };
const V2_DEFAULTS: FactorWeights = { momentum_12_1: 0.40, breakout: 0.25, catalyst: 0.20, risk_adjusted: 0.15 };

interface FactorWeightsChartProps {
  v1Weights: FactorWeights | null;
  v2Weights: FactorWeights | null;
}

export function FactorWeightsChart({ v1Weights, v2Weights }: FactorWeightsChartProps) {
  const v1 = v1Weights || V1_DEFAULTS;
  const v2 = v2Weights || V2_DEFAULTS;

  // Combine all factors into one radar
  const allFactors = new Set([...Object.keys(v1), ...Object.keys(v2)]);
  const data = Array.from(allFactors).map((key) => ({
    factor: FACTOR_LABELS[key] || key,
    V1: Math.round((v1[key] || 0) * 100),
    V2: Math.round((v2[key] || 0) * 100),
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <RadarChart data={data}>
        <PolarGrid stroke="#e5e7eb" />
        <PolarAngleAxis dataKey="factor" tick={{ fontSize: 12, fill: '#6b7280' }} />
        <PolarRadiusAxis angle={90} domain={[0, 60]} tick={{ fontSize: 10, fill: '#9ca3af' }} />
        <Radar name="V1" dataKey="V1" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.15} />
        <Radar name="V2" dataKey="V2" stroke="#f97316" fill="#f97316" fillOpacity={0.15} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
