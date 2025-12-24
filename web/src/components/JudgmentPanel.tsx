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

interface JudgmentPanelProps {
  judgments: JudgmentRecord[];
  title?: string;
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

function ReasoningSection({ reasoning }: { reasoning: JudgmentRecord['reasoning'] }) {
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

function JudgmentCard({ judgment }: { judgment: JudgmentRecord }) {
  const [showDetails, setShowDetails] = useState(false);

  // Parse JSON fields that might be stored as strings (legacy data)
  const keyFactors = parseKeyFactors(judgment.key_factors);
  const identifiedRisks = parseRisks(judgment.identified_risks);
  const reasoning = parseReasoning(judgment.reasoning);

  return (
    <div className="bg-white rounded-lg border p-4 shadow-sm hover:shadow-md transition-shadow">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold">{judgment.symbol}</span>
          <span className={`text-xs px-2 py-0.5 rounded ${
            (judgment.strategy_mode === 'conservative' || judgment.strategy_mode === 'jp_conservative')
              ? 'bg-blue-100 text-blue-700'
              : 'bg-orange-100 text-orange-700'
          }`}>
            {(judgment.strategy_mode === 'conservative' || judgment.strategy_mode === 'jp_conservative') ? 'V1' : 'V2'}
          </span>
        </div>
        <DecisionBadge decision={judgment.decision} confidence={judgment.confidence} />
      </div>

      {/* Confidence Bar */}
      <div className="mb-3">
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>信頼度</span>
          <span>{(judgment.confidence * 100).toFixed(0)}%</span>
        </div>
        <ConfidenceBar confidence={judgment.confidence} />
      </div>

      {/* Score */}
      <div className="flex items-center justify-between text-sm mb-3">
        <span className="text-gray-600">スコア</span>
        <span className={`font-bold ${
          judgment.score >= 75 ? 'text-green-600' :
          judgment.score >= 60 ? 'text-yellow-600' : 'text-red-600'
        }`}>
          {judgment.score}点
        </span>
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
  );
}

export function JudgmentPanel({ judgments, title = 'LLM判断 (Layer 2)' }: JudgmentPanelProps) {
  const [filter, setFilter] = useState<'all' | 'buy' | 'hold' | 'avoid'>('all');
  const [sortBy, setSortBy] = useState<'confidence' | 'score'>('confidence');

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

  // Filter and sort
  const filteredJudgments = judgments
    .filter(j => filter === 'all' || j.decision === filter)
    .sort((a, b) => {
      if (sortBy === 'confidence') return b.confidence - a.confidence;
      return b.score - a.score;
    });

  // Stats
  const stats = {
    total: judgments.length,
    buy: judgments.filter(j => j.decision === 'buy').length,
    hold: judgments.filter(j => j.decision === 'hold').length,
    avoid: judgments.filter(j => j.decision === 'avoid').length,
    avgConfidence: judgments.reduce((sum, j) => sum + j.confidence, 0) / judgments.length,
  };

  return (
    <div className="space-y-4">
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">{title}</h3>

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
          <JudgmentCard key={judgment.id} judgment={judgment} />
        ))}
      </div>
    </div>
  );
}

export default JudgmentPanel;
