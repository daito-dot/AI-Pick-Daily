'use client';

import { Card } from '@/components/ui';
import { FactorWeightsChart } from '@/components/charts';
import type { FactorWeights } from '@/types';

interface FactorWeightsSectionProps {
  v1Weights: FactorWeights | null;
  v2Weights: FactorWeights | null;
}

export function FactorWeightsSection({ v1Weights, v2Weights }: FactorWeightsSectionProps) {
  return (
    <div>
      <h3 className="section-title mb-3">ファクター重み配分</h3>
      <Card>
        <FactorWeightsChart v1Weights={v1Weights} v2Weights={v2Weights} />
        <p className="text-xs text-gray-400 text-center mt-2">
          DBに保存された重み（なければデフォルト値）。日次レビューで自動調整されます。
        </p>
      </Card>
    </div>
  );
}
