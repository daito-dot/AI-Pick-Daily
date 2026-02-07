interface ConfidenceBarProps {
  value: number; // 0.0-1.0
  showLabel?: boolean;
  size?: 'sm' | 'md';
}

export function ConfidenceBar({ value, showLabel = true, size = 'md' }: ConfidenceBarProps) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? 'bg-profit' : pct >= 50 ? 'bg-yellow-400' : 'bg-loss';
  const height = size === 'sm' ? 'h-1.5' : 'h-2.5';

  return (
    <div className="flex items-center gap-2">
      <div className={`flex-1 ${height} bg-gray-100 rounded-full overflow-hidden`}>
        <div
          className={`${height} ${color} rounded-full transition-all duration-300`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showLabel && (
        <span className="text-xs text-gray-500 font-medium w-8 text-right">{pct}%</span>
      )}
    </div>
  );
}
