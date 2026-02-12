'use client';

import type { JudgmentRecord } from '@/types';
import ModelOutputCard from './ModelOutputCard';

interface Props {
  outputs: JudgmentRecord[];
  symbol: string;
}

export default function ModelComparisonPanel({ outputs, symbol }: Props) {
  // Sort: primary first, then by model name
  const sorted = [...outputs].sort((a, b) => {
    if (a.is_primary !== false && b.is_primary === false) return -1;
    if (a.is_primary === false && b.is_primary !== false) return 1;
    return (a.model_version || '').localeCompare(b.model_version || '');
  });

  // Consensus metrics
  const buyCount = outputs.filter((o) => o.decision === 'buy').length;
  const skipCount = outputs.length - buyCount;
  const riskScores = outputs
    .map((o) => {
      const r = (o.reasoning as unknown as Record<string, unknown>)?.risk_score;
      return typeof r === 'number' ? r : null;
    })
    .filter((r): r is number => r !== null);
  const avgRisk = riskScores.length > 0
    ? riskScores.reduce((a, b) => a + b, 0) / riskScores.length
    : 0;
  const minRisk = riskScores.length > 0 ? Math.min(...riskScores) : 0;
  const maxRisk = riskScores.length > 0 ? Math.max(...riskScores) : 0;

  return (
    <div>
      {/* Consensus summary */}
      <div className="card mb-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="section-title">{symbol}</h3>
          <span className="text-sm text-gray-500">{outputs.length} models</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="text-center">
            <div className="text-lg font-bold text-emerald-600">{buyCount}</div>
            <div className="text-xs text-gray-500">BUY</div>
          </div>
          <div className="text-center">
            <div className="text-lg font-bold text-gray-500">{skipCount}</div>
            <div className="text-xs text-gray-500">SKIP</div>
          </div>
          <div className="text-center">
            <div className="text-lg font-bold text-gray-800">{avgRisk.toFixed(1)}</div>
            <div className="text-xs text-gray-500">Avg Risk</div>
          </div>
          <div className="text-center">
            <div className="text-lg font-bold text-gray-800">{minRisk}-{maxRisk}</div>
            <div className="text-xs text-gray-500">Risk Range</div>
          </div>
        </div>
      </div>

      {/* Model cards grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {sorted.map((output) => (
          <ModelOutputCard key={output.id} output={output} />
        ))}
      </div>
    </div>
  );
}
