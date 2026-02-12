import { StatCard } from '@/components/ui';
import type { PortfolioSummaryWithRisk } from '@/types';

interface QuickPortfolioSummaryProps {
  v1Summary: PortfolioSummaryWithRisk;
  v2Summary: PortfolioSummaryWithRisk;
  isJapan: boolean;
}

export function QuickPortfolioSummary({ v1Summary, v2Summary, isJapan }: QuickPortfolioSummaryProps) {
  const totalValue = v1Summary.totalValue + v2Summary.totalValue;
  const initialFund = 100000;  // Matches INITIAL_CAPITAL in portfolio/manager.py
  const totalPnlPct = ((totalValue - initialFund) / initialFund) * 100;
  const avgAlpha = (v1Summary.alpha + v2Summary.alpha) / 2;
  const worstDrawdown = Math.min(
    v1Summary.maxDrawdown ?? 0,
    v2Summary.maxDrawdown ?? 0,
  );

  const currency = isJapan ? '¥' : '$';
  const formattedValue = isJapan
    ? `${currency}${Math.round(totalValue).toLocaleString()}`
    : `${currency}${Math.round(totalValue).toLocaleString()}`;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <StatCard label="総資産" value={formattedValue} />
      <StatCard
        label="累積リターン"
        value={`${totalPnlPct >= 0 ? '+' : ''}${totalPnlPct.toFixed(1)}`}
        suffix="%"
        variant={totalPnlPct >= 0 ? 'default' : 'danger'}
      />
      <StatCard
        label="Alpha"
        value={`${avgAlpha >= 0 ? '+' : ''}${avgAlpha.toFixed(2)}`}
        suffix="%"
      />
      <StatCard
        label="最大DD"
        value={worstDrawdown !== 0 ? `${worstDrawdown.toFixed(1)}` : '---'}
        suffix={worstDrawdown !== 0 ? '%' : ''}
        variant={worstDrawdown < -5 ? 'danger' : 'default'}
      />
    </div>
  );
}
