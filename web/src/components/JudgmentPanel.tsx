'use client';

import { useState } from 'react';
import type { JudgmentRecord, KeyFactor, FactorImpact } from '@/types';

// Helper to safely parse JSON fields that might be stored as strings (possibly double-encoded)
function safeParseJson<T>(value: T | string | null | undefined, fallback: T): T {
  if (value === null || value === undefined) return fallback;
  if (typeof value !== 'string') return value;

  let result = value;
  // Try parsing up to 2 times to handle double-encoded JSON
  for (let i = 0; i < 2; i++) {
    if (typeof result !== 'string') break;
    try {
      result = JSON.parse(result);
    } catch {
      break;
    }
  }

  // If we got a valid parsed result (not a string), return it
  if (typeof result !== 'string') {
    return result as T;
  }

  return fallback;
}

// Helper to parse key_factors
function parseKeyFactors(value: KeyFactor[] | string | null | undefined): KeyFactor[] {
  return safeParseJson(value, []);
}

// Helper to parse identified_risks
function parseRisks(value: string[] | string | null | undefined): string[] {
  return safeParseJson(value, []);
}

// Helper to parse reasoning
function parseReasoning(value: JudgmentRecord['reasoning'] | string | null | undefined): JudgmentRecord['reasoning'] | null {
  if (!value) return null;
  return safeParseJson(value, null);
}

interface RuleBasedScore {
  symbol: string;
  composite_score: number;
  percentile_rank: number;
  price_at_time?: number;
  return_1d?: number | null;
  return_5d?: number | null;
}

interface JudgmentPanelProps {
  judgments: JudgmentRecord[];
  title?: string;
  finalPicks?: {
    conservative: string[];
    aggressive: string[];
  };
  confidenceThreshold?: {
    conservative: number;
    aggressive: number;
  };
  ruleBasedScores?: {
    conservative: RuleBasedScore[];
    aggressive: RuleBasedScore[];
  };
  scoreThreshold?: {
    conservative: number;
    aggressive: number;
  };
  isJapan?: boolean;
}

function DecisionBadge({ decision, confidence }: { decision: string; confidence: number }) {
  const config = {
    buy: { label: 'BUY', bgColor: 'bg-green-100', textColor: 'text-green-800', borderColor: 'border-green-300' },
    hold: { label: 'HOLD', bgColor: 'bg-yellow-100', textColor: 'text-yellow-800', borderColor: 'border-yellow-300' },
    avoid: { label: 'AVOID', bgColor: 'bg-red-100', textColor: 'text-red-800', borderColor: 'border-red-300' },
  };
  const c = config[decision as keyof typeof config] || config.hold;

  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${c.bgColor} border ${c.borderColor}`}>
      <span className={`font-bold ${c.textColor}`}>{c.label}</span>
      <span className={`text-sm ${c.textColor}`}>
        {(confidence * 100).toFixed(0)}%
      </span>
    </div>
  );
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const percent = confidence * 100;
  const color = percent >= 70 ? 'bg-green-500' : percent >= 50 ? 'bg-yellow-500' : 'bg-red-500';

  return (
    <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
      <div
        className={`h-full ${color} transition-all duration-300`}
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}

function ImpactIcon({ impact }: { impact: FactorImpact }) {
  if (impact === 'positive') {
    return <span className="text-green-600">+</span>;
  } else if (impact === 'negative') {
    return <span className="text-red-600">-</span>;
  }
  return <span className="text-gray-400">=</span>;
}

// Stock Detail Modal
interface StockDetailModalProps {
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

function StockDetailModal({
  isOpen,
  onClose,
  symbol,
  judgment,
  ruleBasedScore,
  keyFactors,
  identifiedRisks,
  reasoning,
  isJapan = false,
}: StockDetailModalProps) {
  if (!isOpen) return null;

  const currencySymbol = isJapan ? '¥' : '$';
  const price = ruleBasedScore?.price_at_time;
  const return1d = ruleBasedScore?.return_1d;
  const return5d = ruleBasedScore?.return_5d;

  // Generate mini price chart data (simulated from returns)
  const generateChartPoints = () => {
    if (return5d === null || return5d === undefined || !price) {
      return null;
    }
    // Estimate 5-day price movement based on return
    const dailyReturn = return5d / 5;
    const points = [];
    let currentPrice = price / (1 + return5d / 100);
    for (let i = 0; i <= 5; i++) {
      points.push({
        day: i,
        price: currentPrice,
      });
      currentPrice *= (1 + dailyReturn / 100);
    }
    return points;
  };

  const chartPoints = generateChartPoints();
  const minPrice = chartPoints ? Math.min(...chartPoints.map(p => p.price)) : 0;
  const maxPrice = chartPoints ? Math.max(...chartPoints.map(p => p.price)) : 0;
  const priceRange = maxPrice - minPrice || 1;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold">{symbol}</h2>
            {price && (
              <p className="text-lg text-gray-600">
                {currencySymbol}{isJapan ? Math.round(price).toLocaleString() : price.toFixed(2)}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl"
          >
            ×
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Price Chart */}
          {chartPoints && (
            <div className="bg-gray-50 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-700 mb-3">価格推移（5日間）</h3>
              <div className="relative h-32">
                <svg className="w-full h-full" viewBox="0 0 100 50">
                  {/* Grid lines */}
                  <line x1="0" y1="25" x2="100" y2="25" stroke="#e5e7eb" strokeWidth="0.5" />

                  {/* Price line */}
                  <polyline
                    fill="none"
                    stroke={(return5d ?? 0) >= 0 ? '#22c55e' : '#ef4444'}
                    strokeWidth="2"
                    points={chartPoints.map((p, i) =>
                      `${(i / 5) * 100},${50 - ((p.price - minPrice) / priceRange) * 45}`
                    ).join(' ')}
                  />

                  {/* Points */}
                  {chartPoints.map((p, i) => (
                    <circle
                      key={i}
                      cx={(i / 5) * 100}
                      cy={50 - ((p.price - minPrice) / priceRange) * 45}
                      r="2"
                      fill={(return5d ?? 0) >= 0 ? '#22c55e' : '#ef4444'}
                    />
                  ))}
                </svg>
              </div>
              <div className="flex justify-between text-xs text-gray-500 mt-2">
                <span>5日前</span>
                <span>今日</span>
              </div>
            </div>
          )}

          {/* Returns */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-gray-50 rounded-lg p-4 text-center">
              <p className="text-sm text-gray-500 mb-1">1日リターン</p>
              <p className={`text-2xl font-bold ${
                (return1d ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
              }`}>
                {return1d !== null && return1d !== undefined
                  ? `${return1d >= 0 ? '+' : ''}${return1d.toFixed(2)}%`
                  : '-'}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-4 text-center">
              <p className="text-sm text-gray-500 mb-1">5日リターン</p>
              <p className={`text-2xl font-bold ${
                (return5d ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
              }`}>
                {return5d !== null && return5d !== undefined
                  ? `${return5d >= 0 ? '+' : ''}${return5d.toFixed(2)}%`
                  : '-'}
              </p>
            </div>
          </div>

          {/* Scores */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-blue-50 rounded-lg p-4 text-center">
              <p className="text-sm text-blue-600 mb-1">ルールベーススコア</p>
              <p className="text-2xl font-bold text-blue-800">
                {ruleBasedScore?.composite_score ?? '-'}点
              </p>
              {ruleBasedScore?.percentile_rank && (
                <p className="text-xs text-blue-500">
                  上位 {(100 - ruleBasedScore.percentile_rank).toFixed(0)}%
                </p>
              )}
            </div>
            <div className="bg-purple-50 rounded-lg p-4 text-center">
              <p className="text-sm text-purple-600 mb-1">LLMスコア</p>
              <p className="text-2xl font-bold text-purple-800">
                {judgment.score}点
              </p>
              <p className="text-xs text-purple-500">
                信頼度: {(judgment.confidence * 100).toFixed(0)}%
              </p>
            </div>
          </div>

          {/* Decision */}
          <div className={`rounded-lg p-4 ${
            judgment.decision === 'buy' ? 'bg-green-50' :
            judgment.decision === 'hold' ? 'bg-yellow-50' : 'bg-red-50'
          }`}>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">LLM判定</span>
              <span className={`text-xl font-bold ${
                judgment.decision === 'buy' ? 'text-green-700' :
                judgment.decision === 'hold' ? 'text-yellow-700' : 'text-red-700'
              }`}>
                {judgment.decision.toUpperCase()}
              </span>
            </div>
          </div>

          {/* Key Factors */}
          {keyFactors.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-gray-700 mb-3">重要ファクター</h3>
              <div className="space-y-2">
                {keyFactors.map((factor, idx) => (
                  <div
                    key={idx}
                    className={`p-3 rounded-lg ${
                      factor.impact === 'positive' ? 'bg-green-50' :
                      factor.impact === 'negative' ? 'bg-red-50' : 'bg-gray-50'
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <span className={`mt-0.5 ${
                        factor.impact === 'positive' ? 'text-green-600' :
                        factor.impact === 'negative' ? 'text-red-600' : 'text-gray-400'
                      }`}>
                        {factor.impact === 'positive' ? '▲' :
                         factor.impact === 'negative' ? '▼' : '■'}
                      </span>
                      <div className="flex-1">
                        <p className="text-sm">{factor.description}</p>
                        <p className="text-xs text-gray-500 mt-1">
                          {factor.source} • 重み: {(factor.weight * 100).toFixed(0)}%
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Risks */}
          {identifiedRisks.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-red-700 mb-3">識別されたリスク</h3>
              <ul className="space-y-2">
                {identifiedRisks.map((risk, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-sm text-red-600 bg-red-50 p-2 rounded">
                    <span>⚠</span>
                    <span>{risk}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Reasoning */}
          {reasoning && (
            <div>
              <h3 className="text-sm font-medium text-gray-700 mb-3">推論プロセス</h3>
              <div className="bg-gray-50 rounded-lg p-4 space-y-3 text-sm">
                {reasoning.decision_point && (
                  <div className="bg-blue-50 p-3 rounded">
                    <p className="font-medium text-blue-800">決定ポイント</p>
                    <p className="text-blue-700">{reasoning.decision_point}</p>
                  </div>
                )}
                {reasoning.top_factors && reasoning.top_factors.length > 0 && (
                  <div>
                    <p className="font-medium text-gray-700">主要因</p>
                    <ul className="list-disc list-inside text-gray-600 mt-1">
                      {reasoning.top_factors.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  </div>
                )}
                {reasoning.confidence_explanation && (
                  <div>
                    <p className="font-medium text-gray-700">信頼度の根拠</p>
                    <p className="text-gray-600">{reasoning.confidence_explanation}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Model Info */}
          <div className="text-xs text-gray-400 pt-4 border-t">
            <p>Model: {judgment.model_version} • Prompt: v{judgment.prompt_version}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// Trend Indicator showing price momentum
function TrendIndicator({ return1d, return5d }: { return1d?: number | null; return5d?: number | null }) {
  // Use 1-day return for short-term trend, 5-day for medium-term
  const shortTerm = return1d ?? 0;
  const mediumTerm = return5d ?? 0;

  // Determine arrow based on returns
  const getArrow = (ret: number, threshold: number = 0.5) => {
    if (ret > threshold * 2) return { arrow: '↑↑', color: 'text-green-600', label: '強い上昇' };
    if (ret > threshold) return { arrow: '↑', color: 'text-green-500', label: '上昇' };
    if (ret < -threshold * 2) return { arrow: '↓↓', color: 'text-red-600', label: '強い下落' };
    if (ret < -threshold) return { arrow: '↓', color: 'text-red-500', label: '下落' };
    return { arrow: '→', color: 'text-gray-400', label: '横ばい' };
  };

  const short = getArrow(shortTerm, 1);
  const medium = getArrow(mediumTerm, 2);

  if (return1d === null && return5d === null) {
    return null;
  }

  return (
    <div className="flex items-center gap-2 text-sm">
      {return1d !== null && return1d !== undefined && (
        <div className="flex items-center gap-1" title={`1日: ${shortTerm >= 0 ? '+' : ''}${shortTerm.toFixed(1)}%`}>
          <span className="text-xs text-gray-400">1D</span>
          <span className={`font-bold ${short.color}`}>{short.arrow}</span>
        </div>
      )}
      {return5d !== null && return5d !== undefined && (
        <div className="flex items-center gap-1" title={`5日: ${mediumTerm >= 0 ? '+' : ''}${mediumTerm.toFixed(1)}%`}>
          <span className="text-xs text-gray-400">5D</span>
          <span className={`font-bold ${medium.color}`}>{medium.arrow}</span>
        </div>
      )}
    </div>
  );
}

function FactorTypeIcon({ type }: { type: string }) {
  const icons: Record<string, string> = {
    fundamental: '📊',
    technical: '📈',
    sentiment: '💬',
    macro: '🌍',
    catalyst: '⚡',
  };
  return <span>{icons[type] || '📌'}</span>;
}

function KeyFactorsList({ factors }: { factors: KeyFactor[] }) {
  if (!factors || !Array.isArray(factors) || factors.length === 0) {
    return <p className="text-gray-400 text-sm italic">ファクターデータなし</p>;
  }

  return (
    <div className="space-y-2">
      {factors.slice(0, 5).map((factor, idx) => (
        <div
          key={idx}
          className={`flex items-start gap-2 p-2 rounded ${
            factor.impact === 'positive' ? 'bg-green-50' :
            factor.impact === 'negative' ? 'bg-red-50' : 'bg-gray-50'
          }`}
        >
          <FactorTypeIcon type={factor.factor_type} />
          <div className="flex-1">
            <div className="flex items-center gap-1">
              <ImpactIcon impact={factor.impact} />
              <span className="text-sm font-medium">{factor.description}</span>
            </div>
            <div className="text-xs text-gray-500 mt-0.5">
              {factor.source} • weight: {(factor.weight * 100).toFixed(0)}%
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ReasoningSection({ reasoning }: { reasoning: JudgmentRecord['reasoning'] | null }) {
  const [expanded, setExpanded] = useState(false);

  if (!reasoning) {
    return null;
  }

  // Check if we have any displayable content
  const hasDecisionPoint = !!reasoning.decision_point;
  const hasTopFactors = Array.isArray(reasoning.top_factors) && reasoning.top_factors.length > 0;
  const hasUncertainties = Array.isArray(reasoning.uncertainties) && reasoning.uncertainties.length > 0;
  const hasSteps = Array.isArray(reasoning.steps) && reasoning.steps.length > 0;
  const hasConfidenceExplanation = !!reasoning.confidence_explanation;
  const hasAnyContent = hasDecisionPoint || hasTopFactors || hasUncertainties || hasSteps || hasConfidenceExplanation;

  return (
    <div className="mt-3 pt-3 border-t border-gray-100">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
      >
        <span>{expanded ? '▼' : '▶'}</span>
        <span>推論プロセス</span>
      </button>

      {expanded && (
        <div className="mt-2 space-y-3 text-sm">
          {hasAnyContent ? (
            <>
              {/* Decision Point */}
              {hasDecisionPoint && (
                <div className="p-2 bg-blue-50 rounded">
                  <p className="font-medium text-blue-800">決定ポイント:</p>
                  <p className="text-blue-700">{reasoning.decision_point}</p>
                </div>
              )}

              {/* Top Factors */}
              {hasTopFactors && (
                <div>
                  <p className="font-medium text-gray-700">主要因:</p>
                  <ul className="list-disc list-inside text-gray-600 ml-2">
                    {reasoning.top_factors.map((factor, idx) => (
                      <li key={idx}>{factor}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Uncertainties */}
              {hasUncertainties && (
                <div>
                  <p className="font-medium text-orange-700">不確実性:</p>
                  <ul className="list-disc list-inside text-orange-600 ml-2">
                    {reasoning.uncertainties.map((u, idx) => (
                      <li key={idx}>{u}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Reasoning Steps */}
              {hasSteps && (
                <div>
                  <p className="font-medium text-gray-700">推論ステップ:</p>
                  <ol className="list-decimal list-inside text-gray-600 ml-2 space-y-1">
                    {reasoning.steps.map((step, idx) => (
                      <li key={idx} className="text-xs">{step}</li>
                    ))}
                  </ol>
                </div>
              )}

              {/* Confidence Explanation */}
              {hasConfidenceExplanation && (
                <div className="p-2 bg-gray-50 rounded">
                  <p className="font-medium text-gray-700">信頼度の根拠:</p>
                  <p className="text-gray-600">{reasoning.confidence_explanation}</p>
                </div>
              )}
            </>
          ) : (
            <p className="text-gray-400 text-sm italic">推論データを解析できませんでした</p>
          )}
        </div>
      )}
    </div>
  );
}

interface JudgmentCardProps {
  judgment: JudgmentRecord;
  isFinalPick?: boolean;
  confidenceThreshold?: number;
  ruleBasedScore?: RuleBasedScore;
  scoreThreshold?: number;
  ruleBasedRank?: number;
  maxPicks?: number;
  isJapan?: boolean;
}

function JudgmentCard({ judgment, isFinalPick, confidenceThreshold, ruleBasedScore, scoreThreshold, ruleBasedRank, maxPicks, isJapan = false }: JudgmentCardProps) {
  const [showDetails, setShowDetails] = useState(false);
  const [showModal, setShowModal] = useState(false);

  // Parse JSON fields that might be stored as strings (legacy data)
  const keyFactors = parseKeyFactors(judgment.key_factors);
  const identifiedRisks = parseRisks(judgment.identified_risks);
  const reasoning = parseReasoning(judgment.reasoning);

  // Determine filter status (NEW: LLM-first selection logic)
  const isV1 = judgment.strategy_mode === 'conservative' || judgment.strategy_mode === 'jp_conservative';
  const confThreshold = confidenceThreshold ?? (isV1 ? 0.6 : 0.5);
  const passedLLM = judgment.decision === 'buy';
  const passedConfidence = judgment.confidence >= confThreshold;
  const ruleScore = ruleBasedScore?.composite_score ?? 0;
  const scoreThresh = scoreThreshold ?? (isV1 ? 60 : 45);  // V2 uses lower threshold
  const passedScoreThreshold = ruleScore >= scoreThresh;

  // Get filter status message (reflects LLM-first selection)
  const getFilterStatus = () => {
    if (isFinalPick) return { text: '最終ピック採用', color: 'text-green-600', icon: '✓' };
    if (!passedScoreThreshold) return { text: `リスクフィルター (${scoreThresh}点未満)`, color: 'text-orange-500', icon: '!' };
    if (!passedLLM) return { text: `LLM: ${judgment.decision.toUpperCase()}`, color: 'text-gray-500', icon: '−' };
    if (!passedConfidence) return { text: `信頼度不足 (${(confThreshold * 100).toFixed(0)}%未満)`, color: 'text-orange-500', icon: '!' };
    // Passed all filters but not picked = max picks limit reached
    return { text: '採用枠外 (信頼度順で選定)', color: 'text-gray-400', icon: '−' };
  };
  const filterStatus = getFilterStatus();

  return (
    <>
    <div className={`bg-white rounded-lg border p-4 shadow-sm hover:shadow-md transition-shadow ${isFinalPick ? 'ring-2 ring-green-500' : ''}`}>
      {/* Header - Clickable to open modal */}
      <div
        className="flex items-center justify-between mb-3 cursor-pointer group"
        onClick={() => setShowModal(true)}
      >
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold group-hover:text-blue-600 transition-colors">{judgment.symbol}</span>
          <span className={`text-xs px-2 py-0.5 rounded ${
            isV1
              ? 'bg-blue-100 text-blue-700'
              : 'bg-orange-100 text-orange-700'
          }`}>
            {isV1 ? 'V1' : 'V2'}
          </span>
          {isFinalPick && (
            <span className="text-xs px-2 py-0.5 rounded bg-green-100 text-green-700 font-medium">
              採用
            </span>
          )}
          {/* Trend Indicator */}
          <TrendIndicator
            return1d={ruleBasedScore?.return_1d}
            return5d={ruleBasedScore?.return_5d}
          />
        </div>
        <div className="flex items-center gap-2">
          <DecisionBadge decision={judgment.decision} confidence={judgment.confidence} />
          <span className="text-gray-300 group-hover:text-blue-400 transition-colors text-lg">›</span>
        </div>
      </div>

      {/* Filter Status */}
      <div className={`text-xs mb-2 ${filterStatus.color}`}>
        <span className="mr-1">{filterStatus.icon}</span>
        {filterStatus.text}
      </div>

      {/* Confidence Bar */}
      <div className="mb-3">
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>信頼度</span>
          <span>{(judgment.confidence * 100).toFixed(0)}%</span>
        </div>
        <ConfidenceBar confidence={judgment.confidence} />
      </div>

      {/* Scores - Both Rule-based and LLM */}
      <div className="bg-gray-50 rounded p-2 mb-3">
        <div className="grid grid-cols-2 gap-2 text-sm">
          {/* Rule-based Score */}
          <div className="text-center">
            <div className="text-xs text-gray-500 mb-1">ルールスコア</div>
            <div className="flex items-center justify-center gap-1">
              <span className={`font-bold ${
                ruleScore >= scoreThresh ? 'text-green-600' : 'text-orange-500'
              }`}>
                {ruleScore > 0 ? `${ruleScore}点` : '-'}
              </span>
              {ruleBasedRank !== undefined && (
                <span className="text-xs text-gray-400">
                  ({ruleBasedRank}位)
                </span>
              )}
            </div>
            <div className="text-xs text-gray-400">
              閾値: {scoreThresh}点
            </div>
          </div>
          {/* LLM Score */}
          <div className="text-center">
            <div className="text-xs text-gray-500 mb-1">LLMスコア</div>
            <span className={`font-bold ${
              judgment.score >= 75 ? 'text-green-600' :
              judgment.score >= 60 ? 'text-yellow-600' : 'text-red-600'
            }`}>
              {judgment.score}点
            </span>
            <div className="text-xs text-gray-400">
              参考値
            </div>
          </div>
        </div>
      </div>

      {/* Key Factors (collapsed by default) */}
      <button
        onClick={() => setShowDetails(!showDetails)}
        className="w-full text-left text-sm text-gray-600 hover:text-gray-900 flex items-center gap-1"
      >
        <span>{showDetails ? '▼' : '▶'}</span>
        <span>詳細分析 ({keyFactors.length}ファクター)</span>
      </button>

      {showDetails && (
        <div className="mt-3 space-y-3">
          {/* Key Factors */}
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">重要ファクター:</p>
            <KeyFactorsList factors={keyFactors} />
          </div>

          {/* Identified Risks */}
          {identifiedRisks.length > 0 && (
            <div>
              <p className="text-sm font-medium text-red-700 mb-2">識別されたリスク:</p>
              <ul className="list-disc list-inside text-sm text-red-600 ml-2">
                {identifiedRisks.map((risk, idx) => (
                  <li key={idx}>{risk}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Reasoning */}
          <ReasoningSection reasoning={reasoning} />

          {/* Model Info */}
          <div className="pt-2 border-t border-gray-100 text-xs text-gray-400">
            <p>Model: {judgment.model_version}</p>
            <p>Prompt: v{judgment.prompt_version}</p>
          </div>
        </div>
      )}
    </div>

    {/* Stock Detail Modal */}
    <StockDetailModal
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
}

export function JudgmentPanel({
  judgments,
  title = 'LLM判断 (Layer 2)',
  finalPicks,
  confidenceThreshold = { conservative: 0.6, aggressive: 0.5 },
  ruleBasedScores,
  scoreThreshold = { conservative: 60, aggressive: 45 },  // V2: 75→45 (risk filter only)
  isJapan = false,
}: JudgmentPanelProps) {
  const [filter, setFilter] = useState<'all' | 'buy' | 'hold' | 'avoid'>('all');
  const [sortBy, setSortBy] = useState<'confidence' | 'score'>('confidence');

  // Default max picks (NORMAL regime) - V2: 3→5
  const maxPicks = { conservative: 5, aggressive: 5 };

  if (!judgments || judgments.length === 0) {
    return (
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">{title}</h3>
        <p className="text-gray-400 text-sm italic text-center py-8">
          本日のLLM判断データがありません
        </p>
      </div>
    );
  }

  // Helper to check if a judgment is a final pick
  const isFinalPick = (j: JudgmentRecord) => {
    if (!finalPicks) return false;
    const isV1 = j.strategy_mode === 'conservative' || j.strategy_mode === 'jp_conservative';
    const picks = isV1 ? finalPicks.conservative : finalPicks.aggressive;
    return picks.includes(j.symbol);
  };

  // Helper to get confidence threshold for a judgment
  const getConfThreshold = (j: JudgmentRecord) => {
    const isV1 = j.strategy_mode === 'conservative' || j.strategy_mode === 'jp_conservative';
    return isV1 ? confidenceThreshold.conservative : confidenceThreshold.aggressive;
  };

  // Helper to get rule-based score for a judgment
  const getRuleBasedScore = (j: JudgmentRecord): RuleBasedScore | undefined => {
    if (!ruleBasedScores) return undefined;
    const isV1 = j.strategy_mode === 'conservative' || j.strategy_mode === 'jp_conservative';
    const scores = isV1 ? ruleBasedScores.conservative : ruleBasedScores.aggressive;
    return scores.find(s => s.symbol === j.symbol);
  };

  // Helper to get rule-based rank for a judgment
  const getRuleBasedRank = (j: JudgmentRecord): number | undefined => {
    if (!ruleBasedScores) return undefined;
    const isV1 = j.strategy_mode === 'conservative' || j.strategy_mode === 'jp_conservative';
    const scores = isV1 ? ruleBasedScores.conservative : ruleBasedScores.aggressive;
    // Sort by composite_score descending
    const sorted = [...scores].sort((a, b) => b.composite_score - a.composite_score);
    const idx = sorted.findIndex(s => s.symbol === j.symbol);
    return idx >= 0 ? idx + 1 : undefined;
  };

  // Helper to get score threshold for a judgment
  const getScoreThreshold = (j: JudgmentRecord) => {
    const isV1 = j.strategy_mode === 'conservative' || j.strategy_mode === 'jp_conservative';
    return isV1 ? scoreThreshold.conservative : scoreThreshold.aggressive;
  };

  // Helper to get max picks for a judgment
  const getMaxPicks = (j: JudgmentRecord) => {
    const isV1 = j.strategy_mode === 'conservative' || j.strategy_mode === 'jp_conservative';
    return isV1 ? maxPicks.conservative : maxPicks.aggressive;
  };

  // Filter and sort
  const filteredJudgments = judgments
    .filter(j => filter === 'all' || j.decision === filter)
    .sort((a, b) => {
      if (sortBy === 'confidence') return b.confidence - a.confidence;
      return b.score - a.score;
    });

  // Stats
  const finalPickCount = judgments.filter(j => isFinalPick(j)).length;
  const stats = {
    total: judgments.length,
    buy: judgments.filter(j => j.decision === 'buy').length,
    hold: judgments.filter(j => j.decision === 'hold').length,
    avoid: judgments.filter(j => j.decision === 'avoid').length,
    avgConfidence: judgments.reduce((sum, j) => sum + j.confidence, 0) / judgments.length,
    finalPicks: finalPickCount,
  };

  return (
    <div className="space-y-4">
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">{title}</h3>

        {/* Pipeline Flow - New LLM-first selection logic */}
        <div className="bg-gray-50 rounded-lg p-4 mb-6">
          <p className="text-xs text-gray-500 mb-3">選択フロー（LLM信頼度優先）</p>
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-1 flex-wrap">
              <div className="text-center px-2 py-1 bg-white rounded shadow-sm">
                <p className="text-lg font-bold text-gray-700">{stats.total}</p>
                <p className="text-xs text-gray-500">閾値通過</p>
              </div>
              <span className="text-gray-400">→</span>
              <div className="text-center px-2 py-1 bg-white rounded shadow-sm">
                <p className="text-lg font-bold text-green-600">{stats.buy}</p>
                <p className="text-xs text-gray-500">LLM BUY</p>
              </div>
              <span className="text-gray-400">→</span>
              <div className="text-center px-2 py-1 bg-white rounded shadow-sm">
                <p className="text-lg font-bold text-purple-600">
                  {judgments.filter(j => j.decision === 'buy' && j.confidence >= (
                    (j.strategy_mode === 'conservative' || j.strategy_mode === 'jp_conservative')
                      ? confidenceThreshold.conservative
                      : confidenceThreshold.aggressive
                  )).length}
                </p>
                <p className="text-xs text-gray-500">信頼度OK</p>
              </div>
              <span className="text-gray-400">→</span>
              <div className="text-center px-2 py-1 bg-blue-50 rounded shadow-sm border border-blue-200">
                <p className="text-lg font-bold text-blue-600">{stats.finalPicks}</p>
                <p className="text-xs text-blue-600">最終採用</p>
              </div>
            </div>
          </div>
          <div className="mt-3 text-xs text-gray-500 space-y-1">
            <p>• ルールスコア閾値: V1≥{scoreThreshold.conservative}点 / V2≥{scoreThreshold.aggressive}点（リスクフィルター）</p>
            <p>• 信頼度閾値: V1≥{(confidenceThreshold.conservative * 100).toFixed(0)}% / V2≥{(confidenceThreshold.aggressive * 100).toFixed(0)}%</p>
            <p>• 採用順: LLM信頼度の高い順（ルールスコア順位ではない）</p>
          </div>
        </div>

        {/* Stats Summary */}
        <div className="grid grid-cols-5 gap-4 mb-6">
          <div className="text-center">
            <p className="text-2xl font-bold text-gray-800">{stats.total}</p>
            <p className="text-xs text-gray-500">総判断</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-green-600">{stats.buy}</p>
            <p className="text-xs text-gray-500">BUY</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-yellow-600">{stats.hold}</p>
            <p className="text-xs text-gray-500">HOLD</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-red-600">{stats.avoid}</p>
            <p className="text-xs text-gray-500">AVOID</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-blue-600">
              {(stats.avgConfidence * 100).toFixed(0)}%
            </p>
            <p className="text-xs text-gray-500">平均信頼度</p>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-4 mb-4">
          <div className="flex gap-2">
            {(['all', 'buy', 'hold', 'avoid'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1 text-sm rounded-full transition-colors ${
                  filter === f
                    ? 'bg-gray-800 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {f === 'all' ? 'ALL' : f.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <span>並び順:</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as 'confidence' | 'score')}
              className="border rounded px-2 py-1"
            >
              <option value="confidence">信頼度</option>
              <option value="score">スコア</option>
            </select>
          </div>
        </div>
      </div>

      {/* Judgment Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredJudgments.map((judgment) => (
          <JudgmentCard
            key={judgment.id}
            judgment={judgment}
            isFinalPick={isFinalPick(judgment)}
            confidenceThreshold={getConfThreshold(judgment)}
            ruleBasedScore={getRuleBasedScore(judgment)}
            scoreThreshold={getScoreThreshold(judgment)}
            ruleBasedRank={getRuleBasedRank(judgment)}
            maxPicks={getMaxPicks(judgment)}
            isJapan={isJapan}
          />
        ))}
      </div>
    </div>
  );
}

export default JudgmentPanel;
