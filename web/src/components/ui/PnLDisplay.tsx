interface PnLDisplayProps {
  value: number;
  size?: 'sm' | 'md' | 'lg';
  showArrow?: boolean;
}

export function PnLDisplay({ value, size = 'md', showArrow = true }: PnLDisplayProps) {
  const isPositive = value >= 0;
  const color = isPositive ? 'text-profit-dark' : 'text-loss-dark';
  const arrow = isPositive ? '↑' : '↓';
  const sizeClass = size === 'sm' ? 'text-sm' : size === 'lg' ? 'text-2xl' : 'text-base';

  return (
    <span className={`font-bold ${color} ${sizeClass}`}>
      {showArrow && <span className="mr-0.5">{arrow}</span>}
      {isPositive ? '+' : ''}{value.toFixed(2)}%
    </span>
  );
}
