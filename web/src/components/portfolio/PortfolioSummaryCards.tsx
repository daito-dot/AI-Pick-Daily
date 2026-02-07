import { Card, PnLDisplay, Badge } from '@/components/ui';
import type { PortfolioSummaryWithRisk } from '@/types';

interface PortfolioSummaryCardsProps {
  v1Summary: PortfolioSummaryWithRisk;
  v2Summary: PortfolioSummaryWithRisk;
  isJapan: boolean;
  v1Strategy: string;
  v2Strategy: string;
}

function SummaryCard({
  title,
  strategy,
  summary,
  isJapan,
  accentColor,
}: {
  title: string;
  strategy: string;
  summary: PortfolioSummaryWithRisk;
  isJapan: boolean;
  accentColor: string;
}) {
  const fmt = (v: number) =>
    isJapan
      ? `¥${Math.round(v).toLocaleString()}`
      : `$${Math.round(v).toLocaleString()}`;

  const benchmarkName = isJapan ? '日経225' : 'S&P500';

  return (
    <Card className={`border-t-4 ${accentColor}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-800">{title}</h3>
        <Badge variant="strategy" value={strategy} />
      </div>
      <div className="space-y-2.5 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-500">総資産</span>
          <span className="font-bold">{fmt(summary.totalValue)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">現金</span>
          <span>{fmt(summary.cashBalance)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">ポジション</span>
          <span>{fmt(summary.positionsValue)} ({summary.openPositions}件)</span>
        </div>
        <hr className="border-gray-100" />
        <div className="flex justify-between">
          <span className="text-gray-500">累積リターン</span>
          <PnLDisplay value={summary.cumulativePnlPct} size="sm" />
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Alpha (vs {benchmarkName})</span>
          <PnLDisplay value={summary.alpha} size="sm" />
        </div>
        {summary.maxDrawdown !== null && (
          <div className="flex justify-between">
            <span className="text-gray-500">最大ドローダウン</span>
            <span className="text-sm font-medium text-loss-dark">{summary.maxDrawdown.toFixed(1)}%</span>
          </div>
        )}
        {summary.sharpeRatio !== null && (
          <div className="flex justify-between">
            <span className="text-gray-500">Sharpe比率</span>
            <span className="text-sm font-medium">{summary.sharpeRatio.toFixed(2)}</span>
          </div>
        )}
        {summary.winRate !== null && (
          <div className="flex justify-between">
            <span className="text-gray-500">勝率</span>
            <span className="text-sm font-medium">{summary.winRate.toFixed(1)}%</span>
          </div>
        )}
      </div>
    </Card>
  );
}

export function PortfolioSummaryCards({
  v1Summary,
  v2Summary,
  isJapan,
  v1Strategy,
  v2Strategy,
}: PortfolioSummaryCardsProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <SummaryCard
        title="V1 Conservative"
        strategy={v1Strategy}
        summary={v1Summary}
        isJapan={isJapan}
        accentColor="border-t-blue-500"
      />
      <SummaryCard
        title="V2 Aggressive"
        strategy={v2Strategy}
        summary={v2Summary}
        isJapan={isJapan}
        accentColor="border-t-orange-500"
      />
    </div>
  );
}
