import { Card } from './Card';

interface StatCardProps {
  label: string;
  value: string | number;
  suffix?: string;
  sub?: string;
  trend?: 'up' | 'down' | number | null;
  variant?: 'default' | 'highlighted' | 'danger';
  className?: string;
}

export function StatCard({ label, value, suffix = '', sub, trend, variant = 'default', className = '' }: StatCardProps) {
  const isNumericTrend = typeof trend === 'number';
  const isStringTrend = trend === 'up' || trend === 'down';
  const trendUp = isNumericTrend ? trend >= 0 : trend === 'up';
  const trendColor = (isNumericTrend || isStringTrend) ? (trendUp ? 'text-profit-dark' : 'text-loss-dark') : '';
  const trendArrow = (isNumericTrend || isStringTrend) ? (trendUp ? '↑' : '↓') : '';

  return (
    <Card variant={variant} className={`text-center ${className}`}>
      <p className="stat-label">{label}</p>
      <p className="stat-value mt-1">
        {value}{suffix}
      </p>
      {isNumericTrend && (
        <p className={`text-sm mt-1 font-medium ${trendColor}`}>
          {trendArrow} {trend >= 0 ? '+' : ''}{trend.toFixed(2)}%
        </p>
      )}
      {isStringTrend && (
        <p className={`text-sm mt-1 font-medium ${trendColor}`}>
          {trendArrow}
        </p>
      )}
      {sub && (
        <p className="text-xs text-gray-400 mt-1">{sub}</p>
      )}
    </Card>
  );
}
