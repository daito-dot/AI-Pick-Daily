import { Card, Badge, ConfidenceBar } from '@/components/ui';
import { getStockDisplayName } from '@/lib/jp-stocks';
import type { StockScore, StrategyModeType, JudgmentRecord } from '@/types';

interface PickCardProps {
  score: StockScore;
  judgment?: JudgmentRecord;
  isJapan: boolean;
}

export function PickCard({ score, judgment, isJapan }: PickCardProps) {
  const isAggressive = score.strategy_mode === 'aggressive' || score.strategy_mode === 'jp_aggressive';
  const accentColor = isAggressive ? 'border-l-orange-400' : 'border-l-blue-400';
  const currencySymbol = isJapan ? '¥' : '$';

  const scoreBadgeClass =
    score.composite_score >= 75 ? 'bg-green-100 text-green-800' :
    score.composite_score >= 60 ? 'bg-yellow-100 text-yellow-800' :
    'bg-red-100 text-red-800';

  // Extract conviction from judgment (portfolio-level judgment stores it as confidence)
  const conviction = judgment?.confidence;
  const allocationHint = judgment?.input_summary?.includes('high') ? 'high'
    : judgment?.input_summary?.includes('low') ? 'low' : 'normal';

  return (
    <Card className={`border-l-4 ${accentColor} !p-4`}>
      <div className="flex items-start justify-between mb-2">
        <div>
          <span className="font-bold text-base">{getStockDisplayName(score.symbol)}</span>
          {score.price_at_time && (
            <span className="text-xs text-gray-400 ml-2">
              {currencySymbol}{isJapan ? Math.round(score.price_at_time).toLocaleString() : score.price_at_time.toFixed(2)}
            </span>
          )}
        </div>
        <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${scoreBadgeClass}`}>
          {score.composite_score}点
        </span>
      </div>

      {/* Factor scores */}
      <div className="grid grid-cols-4 gap-2 text-xs text-center mb-3">
        {isAggressive ? (
          <>
            <div><div className="text-gray-400">Mom12-1</div><div className="font-medium">{score.momentum_12_1_score ?? '-'}</div></div>
            <div><div className="text-gray-400">Break</div><div className="font-medium">{score.breakout_score ?? '-'}</div></div>
            <div><div className="text-gray-400">Catalyst</div><div className="font-medium">{score.catalyst_score ?? '-'}</div></div>
            <div><div className="text-gray-400">Risk</div><div className="font-medium">{score.risk_adjusted_score ?? '-'}</div></div>
          </>
        ) : (
          <>
            <div><div className="text-gray-400">Trend</div><div className="font-medium">{score.trend_score}</div></div>
            <div><div className="text-gray-400">Mom</div><div className="font-medium">{score.momentum_score}</div></div>
            <div><div className="text-gray-400">Value</div><div className="font-medium">{score.value_score}</div></div>
            <div><div className="text-gray-400">Sent</div><div className="font-medium">{score.sentiment_score}</div></div>
          </>
        )}
      </div>

      {/* AI conviction */}
      {conviction !== undefined && (
        <div className="mt-2">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-gray-500">AI確信度</span>
            {allocationHint !== 'normal' && (
              <span className={`text-xs font-medium ${
                allocationHint === 'high' ? 'text-profit-dark' : 'text-gray-500'
              }`}>
                {allocationHint === 'high' ? '高配分' : '低配分'}
              </span>
            )}
          </div>
          <ConfidenceBar value={conviction} size="sm" />
        </div>
      )}

      {/* Reasoning */}
      {score.reasoning && (
        <p className="mt-2 text-xs text-gray-500 line-clamp-2">{score.reasoning}</p>
      )}
    </Card>
  );
}
