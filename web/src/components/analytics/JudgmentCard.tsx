'use client';

import { useState, memo } from 'react';
import { Badge, ConfidenceBar } from '@/components/ui';
import { parseKeyFactors, parseRisks, parseReasoning } from '@/lib/parsers';
import { JudgmentDetailModal } from './JudgmentDetailModal';
import type { JudgmentRecord } from '@/types';

interface RuleBasedScore {
  symbol: string;
  composite_score: number;
  percentile_rank: number;
  price_at_time?: number;
  return_1d?: number | null;
  return_5d?: number | null;
}

interface JudgmentCardProps {
  judgment: JudgmentRecord;
  isFinalPick?: boolean;
  confidenceThreshold?: number;
  ruleBasedScore?: RuleBasedScore;
  scoreThreshold?: number;
  ruleBasedRank?: number;
  isJapan?: boolean;
}

function TrendIndicator({ return1d, return5d }: { return1d?: number | null; return5d?: number | null }) {
  const getArrow = (ret: number, threshold: number) => {
    if (ret > threshold * 2) return { arrow: '↑↑', color: 'text-profit' };
    if (ret > threshold) return { arrow: '↑', color: 'text-profit-dark' };
    if (ret < -threshold * 2) return { arrow: '↓↓', color: 'text-loss' };
    if (ret < -threshold) return { arrow: '↓', color: 'text-loss-dark' };
    return { arrow: '→', color: 'text-gray-400' };
  };

  if (return1d == null && return5d == null) return null;

  return (
    <div className="flex items-center gap-1.5 text-sm">
      {return1d != null && (() => {
        const s = getArrow(return1d, 1);
        return (
          <span className={`${s.color} font-bold`} title={`1D: ${return1d >= 0 ? '+' : ''}${return1d.toFixed(1)}%`}>
            {s.arrow}
          </span>
        );
      })()}
      {return5d != null && (() => {
        const m = getArrow(return5d, 2);
        return (
          <span className={`${m.color} font-bold`} title={`5D: ${return5d >= 0 ? '+' : ''}${return5d.toFixed(1)}%`}>
            {m.arrow}
          </span>
        );
      })()}
    </div>
  );
}

export const JudgmentCard = memo(function JudgmentCard({
  judgment,
  isFinalPick,
  confidenceThreshold,
  ruleBasedScore,
  scoreThreshold,
  ruleBasedRank,
  isJapan = false,
}: JudgmentCardProps) {
  const [showModal, setShowModal] = useState(false);

  const keyFactors = parseKeyFactors(judgment.key_factors);
  const identifiedRisks = parseRisks(judgment.identified_risks);
  const reasoning = parseReasoning(judgment.reasoning);

  const isV1 = judgment.strategy_mode === 'conservative' || judgment.strategy_mode === 'jp_conservative';
  const confThreshold = confidenceThreshold ?? (isV1 ? 0.6 : 0.5);
  const ruleScore = ruleBasedScore?.composite_score ?? 0;
  const scoreThresh = scoreThreshold ?? (isV1 ? 60 : 75);
  const passedScoreThreshold = ruleScore >= scoreThresh;
  const passedLLM = judgment.decision === 'buy';
  const passedConfidence = judgment.confidence >= confThreshold;

  const getFilterStatus = () => {
    if (isFinalPick) return { text: '最終ピック採用', color: 'text-profit', icon: '✓' };
    if (!passedScoreThreshold) return { text: `リスクフィルター (${scoreThresh}点未満)`, color: 'text-orange-500', icon: '!' };
    if (!passedLLM) return { text: `LLM: ${judgment.decision.toUpperCase()}`, color: 'text-gray-400', icon: '−' };
    if (!passedConfidence) return { text: `信頼度不足`, color: 'text-orange-500', icon: '!' };
    return { text: '採用枠外', color: 'text-gray-400', icon: '−' };
  };
  const filterStatus = getFilterStatus();

  const decisionConfig: Record<string, { label: string; bg: string; text: string; border: string }> = {
    buy: { label: 'BUY', bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-200' },
    hold: { label: 'HOLD', bg: 'bg-yellow-100', text: 'text-yellow-800', border: 'border-yellow-200' },
    avoid: { label: 'AVOID', bg: 'bg-red-100', text: 'text-red-800', border: 'border-red-200' },
  };
  const dc = decisionConfig[judgment.decision] || decisionConfig.hold;

  return (
    <>
      <div
        className={`bg-white rounded-xl border p-4 shadow-card hover:shadow-card-hover transition-shadow cursor-pointer ${
          isFinalPick ? 'ring-2 ring-profit' : ''
        }`}
        onClick={() => setShowModal(true)}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="font-bold text-gray-900">{judgment.symbol}</span>
            <Badge variant="strategy" value={judgment.strategy_mode} />
            <TrendIndicator return1d={ruleBasedScore?.return_1d} return5d={ruleBasedScore?.return_5d} />
          </div>
          <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg ${dc.bg} border ${dc.border}`}>
            <span className={`text-xs font-bold ${dc.text}`}>{dc.label}</span>
            <span className={`text-xs ${dc.text}`}>{(judgment.confidence * 100).toFixed(0)}%</span>
          </div>
        </div>

        {/* Filter Status */}
        <p className={`text-xs mb-2 ${filterStatus.color}`}>
          {filterStatus.icon} {filterStatus.text}
        </p>

        {/* Confidence Bar */}
        <div className="mb-3">
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>確信度</span>
            <span>{(judgment.confidence * 100).toFixed(0)}%</span>
          </div>
          <ConfidenceBar value={judgment.confidence} showLabel={false} />
        </div>

        {/* Scores */}
        <div className="bg-gray-50 rounded-lg p-2">
          <div className="grid grid-cols-2 gap-2 text-center text-sm">
            <div>
              <p className="text-xs text-gray-400 mb-0.5">総合スコア</p>
              <span className={`font-bold ${ruleScore >= scoreThresh ? 'text-profit' : 'text-orange-500'}`}>
                {ruleScore > 0 ? `${ruleScore}点` : '-'}
              </span>
              {ruleBasedRank !== undefined && (
                <span className="text-xs text-gray-400 ml-1">({ruleBasedRank}位)</span>
              )}
            </div>
            <div>
              <p className="text-xs text-gray-400 mb-0.5">LLMスコア</p>
              <span className={`font-bold ${
                judgment.score >= 75 ? 'text-profit' : judgment.score >= 60 ? 'text-yellow-600' : 'text-loss'
              }`}>
                {judgment.score}点
              </span>
            </div>
          </div>
        </div>
      </div>

      <JudgmentDetailModal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        symbol={judgment.symbol}
        judgment={judgment}
        ruleBasedScore={ruleBasedScore}
        keyFactors={keyFactors}
        identifiedRisks={identifiedRisks}
        reasoning={reasoning}
        isJapan={isJapan}
      />
    </>
  );
});
