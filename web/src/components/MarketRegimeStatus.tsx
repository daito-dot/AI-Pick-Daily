import type { MarketRegimeType } from '@/types';

interface MarketRegimeStatusProps {
  regime: MarketRegimeType;
  vixLevel: number;
  notes: string;
}

const regimeConfig = {
  normal: {
    label: '通常相場',
    className: 'regime-normal',
    icon: '✅',
    description: '市場は安定しています',
  },
  adjustment: {
    label: '調整相場',
    className: 'regime-adjustment',
    icon: '⚠️',
    description: 'ボラティリティが上昇中',
  },
  crisis: {
    label: 'クライシス',
    className: 'regime-crisis',
    icon: '🚨',
    description: '高リスク環境',
  },
};

export function MarketRegimeStatus({ regime, vixLevel, notes }: MarketRegimeStatusProps) {
  const config = regimeConfig[regime];

  return (
    <div className="flex items-center gap-4">
      <div className={`px-4 py-2 rounded-lg ${config.className}`}>
        <div className="flex items-center gap-2">
          <span>{config.icon}</span>
          <span className="font-semibold">{config.label}</span>
        </div>
      </div>
      <div className="text-right">
        <p className="text-sm text-gray-500">VIX</p>
        <p className="text-lg font-bold text-gray-900">{vixLevel.toFixed(1)}</p>
      </div>
    </div>
  );
}
