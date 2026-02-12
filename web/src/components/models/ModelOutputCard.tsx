'use client';

import { useState } from 'react';
import type { JudgmentRecord } from '@/types';

interface Props {
  output: JudgmentRecord;
}

function riskColor(score: number): string {
  if (score <= 2) return 'bg-green-100 text-green-800';
  if (score <= 3) return 'bg-yellow-100 text-yellow-800';
  if (score <= 4) return 'bg-orange-100 text-orange-800';
  return 'bg-red-100 text-red-800';
}

function decisionColor(decision: string): string {
  if (decision === 'buy') return 'bg-emerald-100 text-emerald-800';
  return 'bg-gray-100 text-gray-600';
}

export default function ModelOutputCard({ output }: Props) {
  const [showRaw, setShowRaw] = useState(false);
  const reasoning = (output.reasoning as unknown as Record<string, unknown>) || {};
  const riskScore = (reasoning.risk_score as number) ?? 0;
  const catalysts = (reasoning.negative_catalysts as string[]) || [];
  const newsInterp = (reasoning.news_interpretation as string) || '';
  const decisionReason = (reasoning.decision_reason as string) || '';
  const marketRisks = (reasoning.market_level_risks as string) || '';
  const isPrimary = output.is_primary !== false;

  let rawJson = '';
  if (output.raw_llm_response) {
    try {
      rawJson = JSON.stringify(JSON.parse(output.raw_llm_response), null, 2);
    } catch {
      rawJson = output.raw_llm_response;
    }
  }

  return (
    <div className={`card ${isPrimary ? 'ring-2 ring-blue-500' : ''}`}>
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm text-gray-900 truncate">
              {output.model_version}
            </span>
            {isPrimary && (
              <span className="px-1.5 py-0.5 text-xs font-medium bg-blue-100 text-blue-700 rounded">
                PRIMARY
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 ml-2 flex-shrink-0">
          <span className={`px-2 py-0.5 text-xs font-bold rounded ${decisionColor(output.decision)}`}>
            {output.decision.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="text-center">
          <div className={`inline-block px-2 py-1 rounded text-sm font-bold ${riskColor(riskScore)}`}>
            R{riskScore}
          </div>
          <div className="text-xs text-gray-500 mt-0.5">Risk</div>
        </div>
        <div className="text-center">
          <div className="text-sm font-bold text-gray-800">
            {(output.confidence * 100).toFixed(0)}%
          </div>
          <div className="text-xs text-gray-500">Confidence</div>
        </div>
        <div className="text-center">
          <div className="text-sm font-bold text-gray-800">{output.score}</div>
          <div className="text-xs text-gray-500">Score</div>
        </div>
      </div>

      {/* Confidence bar */}
      <div className="w-full bg-gray-200 rounded-full h-1.5 mb-3">
        <div
          className="bg-blue-500 h-1.5 rounded-full"
          style={{ width: `${Math.min(output.confidence * 100, 100)}%` }}
        />
      </div>

      {/* Decision reason */}
      {decisionReason && (
        <p className="text-xs text-gray-600 mb-2">{decisionReason}</p>
      )}

      {/* Catalysts */}
      {catalysts.length > 0 && (
        <div className="mb-2">
          <div className="text-xs font-medium text-gray-500 mb-1">Negative Catalysts</div>
          <ul className="space-y-0.5">
            {catalysts.map((c, i) => (
              <li key={i} className="text-xs text-gray-700 flex items-start gap-1">
                <span className="text-red-400 mt-0.5">-</span>
                <span>{c}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* News interpretation */}
      {newsInterp && !newsInterp.startsWith('Fallback:') && (
        <div className="mb-2">
          <div className="text-xs font-medium text-gray-500 mb-1">News</div>
          <p className="text-xs text-gray-700 line-clamp-3">{newsInterp}</p>
        </div>
      )}

      {/* Market risks */}
      {marketRisks && !marketRisks.startsWith('Risk assessment unavailable') && (
        <div className="mb-2">
          <div className="text-xs font-medium text-gray-500 mb-1">Market Risks</div>
          <p className="text-xs text-gray-700 line-clamp-2">{marketRisks}</p>
        </div>
      )}

      {/* Raw LLM Response toggle */}
      {output.raw_llm_response && (
        <div className="mt-3 pt-2 border-t border-gray-100">
          <button
            onClick={() => setShowRaw(!showRaw)}
            className="text-xs text-blue-600 hover:text-blue-800 font-medium"
          >
            {showRaw ? 'Hide' : 'Show'} Raw Response ({output.raw_llm_response.length} chars)
          </button>
          {showRaw && (
            <pre className="mt-2 p-3 bg-gray-900 text-gray-100 text-xs rounded-lg overflow-x-auto max-h-80 overflow-y-auto">
              {rawJson}
            </pre>
          )}
        </div>
      )}

      {/* Fallback indicator */}
      {!output.raw_llm_response && (
        <div className="mt-2 text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded">
          LLM response unavailable (fallback used)
        </div>
      )}
    </div>
  );
}
