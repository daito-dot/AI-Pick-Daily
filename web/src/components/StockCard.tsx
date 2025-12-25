'use client';

import { useState } from 'react';

interface StockCardProps {
  symbol: string;
  compositeScore: number;
  percentileRank: number;
  trendScore: number;
  momentumScore: number;
  valueScore: number;
  sentimentScore: number;
  reasoning: string;
  priceAtTime: number;
  isJapan?: boolean;
}

function ScoreBar({ label, score, color }: { label: string; score: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-500 w-12">{label}</span>
      <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div
          className={`h-full ${color} transition-all duration-300`}
          style={{ width: `${score}%` }}
        />
      </div>
      <span className="text-xs font-medium w-8 text-right">{score}</span>
    </div>
  );
}

export function StockCard({
  symbol,
  compositeScore,
  percentileRank,
  trendScore,
  momentumScore,
  valueScore,
  sentimentScore,
  reasoning,
  priceAtTime,
  isJapan = false,
}: StockCardProps) {
  const [showDetails, setShowDetails] = useState(false);

  const getScoreClass = (score: number) => {
    if (score >= 70) return 'score-high';
    if (score >= 50) return 'score-medium';
    return 'score-low';
  };

  const scoreClass = getScoreClass(compositeScore);
  const currencySymbol = isJapan ? '¥' : '$';
  const formattedPrice = isJapan
    ? Math.round(priceAtTime).toLocaleString()
    : priceAtTime.toFixed(2);

  return (
    <div className="card hover:shadow-lg transition-shadow">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-xl font-bold text-gray-900">{symbol}</h3>
          <p className="text-sm text-gray-500">
            {currencySymbol}{formattedPrice}
          </p>
        </div>
        <div className="text-right">
          <div className={`score-badge ${scoreClass}`}>
            {compositeScore}点
          </div>
          <p className="text-xs text-gray-400 mt-1">
            上位{100 - percentileRank}%
          </p>
        </div>
      </div>

      {/* Score Breakdown */}
      <div className="space-y-2 mb-4">
        <ScoreBar label="Trend" score={trendScore} color="bg-blue-500" />
        <ScoreBar label="Mom" score={momentumScore} color="bg-purple-500" />
        <ScoreBar label="Value" score={valueScore} color="bg-green-500" />
        <ScoreBar label="Sent" score={sentimentScore} color="bg-orange-500" />
      </div>

      {/* Reasoning Toggle */}
      <button
        onClick={() => setShowDetails(!showDetails)}
        className="text-sm text-primary-600 hover:text-primary-800 font-medium"
      >
        {showDetails ? '詳細を隠す ▲' : '詳細を見る ▼'}
      </button>

      {/* Reasoning Details */}
      {showDetails && (
        <div className="mt-3 pt-3 border-t">
          <p className="text-sm text-gray-600 leading-relaxed">
            {reasoning || '詳細な推奨理由は生成されていません。'}
          </p>
        </div>
      )}
    </div>
  );
}
