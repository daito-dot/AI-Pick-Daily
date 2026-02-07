'use client';

import { useEffect } from 'react';
import { ConfidenceBar } from '@/components/ui';
import type { JudgmentRecord, KeyFactor, FactorImpact } from '@/types';

interface RuleBasedScore {
  symbol: string;
  composite_score: number;
  percentile_rank: number;
  price_at_time?: number;
  return_1d?: number | null;
  return_5d?: number | null;
}

interface JudgmentDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  symbol: string;
  judgment: JudgmentRecord;
  ruleBasedScore?: RuleBasedScore;
  keyFactors: KeyFactor[];
  identifiedRisks: string[];
  reasoning: JudgmentRecord['reasoning'] | null;
  isJapan?: boolean;
}

function FactorTypeIcon({ type }: { type: string }) {
  const icons: Record<string, string> = {
    fundamental: '📊', technical: '📈', sentiment: '💬', macro: '🌍', catalyst: '⚡',
  };
  return <span>{icons[type] || '📌'}</span>;
}

export function JudgmentDetailModal({
  isOpen,
  onClose,
  symbol,
  judgment,
  ruleBasedScore,
  keyFactors,
  identifiedRisks,
  reasoning,
  isJapan = false,
}: JudgmentDetailModalProps) {
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const currencySymbol = isJapan ? '¥' : '$';
  const price = ruleBasedScore?.price_at_time;
  const return1d = ruleBasedScore?.return_1d;
  const return5d = ruleBasedScore?.return_5d;

  const decisionColor =
    judgment.decision === 'buy' ? 'green' :
    judgment.decision === 'hold' ? 'yellow' : 'red';

  const hasDecisionPoint = !!reasoning?.decision_point;
  const hasTopFactors = Array.isArray(reasoning?.top_factors) && reasoning.top_factors.length > 0;
  const hasUncertainties = Array.isArray(reasoning?.uncertainties) && reasoning.uncertainties.length > 0;
  const hasSteps = Array.isArray(reasoning?.steps) && reasoning.steps.length > 0;
  const hasConfidenceExplanation = !!reasoning?.confidence_explanation;
  const hasAnyReasoningContent = hasDecisionPoint || hasTopFactors || hasUncertainties || hasSteps || hasConfidenceExplanation;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl max-w-3xl w-full max-h-[90vh] overflow-y-auto shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex items-center justify-between z-10 rounded-t-2xl">
          <div className="flex items-center gap-4">
            <div>
              <h2 className="text-2xl font-bold">{symbol}</h2>
              {price && (
                <p className="text-lg text-gray-500">
                  {currencySymbol}{isJapan ? Math.round(price).toLocaleString() : price.toFixed(2)}
                </p>
              )}
            </div>
            <div className={`px-4 py-2 rounded-xl bg-${decisionColor}-100 border border-${decisionColor}-200`}>
              <span className={`text-xl font-bold text-${decisionColor}-700`}>
                {judgment.decision.toUpperCase()}
              </span>
              <span className={`ml-2 text-sm text-${decisionColor}-600`}>
                {(judgment.confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-2xl p-1">×</button>
        </div>

        <div className="p-6 space-y-6">
          {/* Returns */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <p className="text-sm text-gray-500 mb-1">1日リターン</p>
              <p className={`text-2xl font-bold ${(return1d ?? 0) >= 0 ? 'text-profit' : 'text-loss'}`}>
                {return1d !== null && return1d !== undefined
                  ? `${return1d >= 0 ? '+' : ''}${return1d.toFixed(2)}%`
                  : '-'}
              </p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <p className="text-sm text-gray-500 mb-1">5日リターン</p>
              <p className={`text-2xl font-bold ${(return5d ?? 0) >= 0 ? 'text-profit' : 'text-loss'}`}>
                {return5d !== null && return5d !== undefined
                  ? `${return5d >= 0 ? '+' : ''}${return5d.toFixed(2)}%`
                  : '-'}
              </p>
            </div>
          </div>

          {/* Scores */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-blue-50 rounded-xl p-4 text-center">
              <p className="text-sm text-blue-600 mb-1">ルールベーススコア</p>
              <p className="text-2xl font-bold text-blue-800">
                {ruleBasedScore?.composite_score ?? '-'}点
              </p>
              {ruleBasedScore?.percentile_rank != null && (
                <p className="text-xs text-blue-500">上位 {(100 - ruleBasedScore.percentile_rank).toFixed(0)}%</p>
              )}
            </div>
            <div className="bg-purple-50 rounded-xl p-4 text-center">
              <p className="text-sm text-purple-600 mb-1">LLMスコア</p>
              <p className="text-2xl font-bold text-purple-800">{judgment.score}点</p>
              <p className="text-xs text-purple-500">信頼度: {(judgment.confidence * 100).toFixed(0)}%</p>
            </div>
          </div>

          {/* Key Factors */}
          <section>
            <h3 className="text-sm font-semibold text-gray-700 mb-3 pb-2 border-b">重要ファクター</h3>
            {keyFactors.length > 0 ? (
              <div className="space-y-2">
                {keyFactors.map((factor, idx) => (
                  <div
                    key={idx}
                    className={`p-3 rounded-lg ${
                      factor.impact === 'positive' ? 'bg-green-50 border border-green-200' :
                      factor.impact === 'negative' ? 'bg-red-50 border border-red-200' :
                      'bg-gray-50 border border-gray-200'
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <FactorTypeIcon type={factor.factor_type} />
                      <span className={`font-bold ${
                        factor.impact === 'positive' ? 'text-green-600' :
                        factor.impact === 'negative' ? 'text-red-600' : 'text-gray-400'
                      }`}>
                        {factor.impact === 'positive' ? '+' : factor.impact === 'negative' ? '-' : '='}
                      </span>
                      <div className="flex-1">
                        <p className="text-sm font-medium text-gray-800">{factor.description}</p>
                        <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                          <span>{factor.source}</span>
                          <span>重み: {(factor.weight * 100).toFixed(0)}%</span>
                          {factor.verifiable && <span className="text-green-600">検証可能</span>}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-400 text-sm italic">ファクターデータなし</p>
            )}
          </section>

          {/* Identified Risks */}
          {identifiedRisks.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-red-700 mb-3 pb-2 border-b border-red-200">識別されたリスク</h3>
              <ul className="space-y-2">
                {identifiedRisks.map((risk, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-sm bg-red-50 border border-red-200 p-3 rounded-lg">
                    <span className="text-red-500">!</span>
                    <span className="text-red-700">{risk}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Reasoning */}
          <section>
            <h3 className="text-sm font-semibold text-gray-700 mb-3 pb-2 border-b">推論プロセス</h3>
            {hasAnyReasoningContent ? (
              <div className="space-y-3">
                {hasDecisionPoint && (
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                    <h4 className="text-xs font-semibold text-blue-800 mb-1">決定ポイント</h4>
                    <p className="text-sm text-blue-700">{reasoning!.decision_point}</p>
                  </div>
                )}
                {hasTopFactors && (
                  <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                    <h4 className="text-xs font-semibold text-gray-800 mb-1">主要因</h4>
                    <ul className="list-disc list-inside text-sm text-gray-700 space-y-0.5">
                      {reasoning!.top_factors.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  </div>
                )}
                {hasUncertainties && (
                  <div className="bg-orange-50 border border-orange-200 rounded-lg p-3">
                    <h4 className="text-xs font-semibold text-orange-800 mb-1">不確実性</h4>
                    <ul className="list-disc list-inside text-sm text-orange-700 space-y-0.5">
                      {reasoning!.uncertainties.map((u, i) => <li key={i}>{u}</li>)}
                    </ul>
                  </div>
                )}
                {hasSteps && (
                  <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                    <h4 className="text-xs font-semibold text-gray-800 mb-1">推論ステップ</h4>
                    <ol className="list-decimal list-inside text-sm text-gray-700 space-y-1">
                      {reasoning!.steps.map((s, i) => <li key={i}>{s}</li>)}
                    </ol>
                  </div>
                )}
                {hasConfidenceExplanation && (
                  <div className="bg-purple-50 border border-purple-200 rounded-lg p-3">
                    <h4 className="text-xs font-semibold text-purple-800 mb-1">信頼度の根拠</h4>
                    <p className="text-sm text-purple-700">{reasoning!.confidence_explanation}</p>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-gray-400 text-sm italic">推論データなし</p>
            )}
          </section>

          {/* Model Info */}
          <section className="border-t pt-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500 mb-0.5">モデル</p>
                <p className="font-medium text-gray-800">{judgment.model_version}</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500 mb-0.5">プロンプト</p>
                <p className="font-medium text-gray-800">v{judgment.prompt_version}</p>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
