'use client';

import { useState } from 'react';
import { Card, Badge, EmptyState } from '@/components/ui';
import type { ReflectionRecord } from '@/types';

interface ReflectionPanelProps {
  reflections: ReflectionRecord[];
  isJapan: boolean;
}

export function ReflectionPanel({ reflections, isJapan }: ReflectionPanelProps) {
  const v1Strategy = isJapan ? 'jp_conservative' : 'conservative';
  const v2Strategy = isJapan ? 'jp_aggressive' : 'aggressive';

  const filtered = reflections.filter(
    (r) => r.strategy_mode === v1Strategy || r.strategy_mode === v2Strategy
  );

  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (filtered.length === 0) {
    return (
      <Card>
        <h3 className="section-title mb-3">リフレクション（自己振り返り）</h3>
        <EmptyState message="リフレクションデータがまだありません" icon="🪞" />
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <h3 className="section-title">リフレクション（自己振り返り）</h3>

      {filtered.map((ref) => {
        const patterns = ref.patterns_identified;
        const suggestions = ref.improvement_suggestions;
        const isExpanded = expandedId === ref.id;

        return (
          <Card key={ref.id}>
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <Badge variant="strategy" value={ref.strategy_mode} />
                <span className="text-xs text-gray-500">
                  {ref.reflection_type === 'weekly' ? '週次' : ref.reflection_type === 'monthly' ? '月次' : 'トレード後'}
                </span>
              </div>
              <span className="text-xs text-gray-400">
                {ref.period_start} ~ {ref.period_end}
              </span>
            </div>

            {/* Summary Stats */}
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="text-center">
                <p className="text-xs text-gray-500">判断数</p>
                <p className="text-lg font-bold text-gray-800">{ref.total_judgments}</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-gray-500">正答数</p>
                <p className="text-lg font-bold text-gray-800">{ref.correct_judgments}</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-gray-500">精度</p>
                <p className={`text-lg font-bold ${ref.accuracy_rate >= 55 ? 'text-green-600' : ref.accuracy_rate < 45 ? 'text-red-600' : 'text-gray-800'}`}>
                  {ref.accuracy_rate.toFixed(1)}%
                </p>
              </div>
            </div>

            {/* Expand/Collapse Button */}
            <button
              onClick={() => setExpandedId(isExpanded ? null : ref.id)}
              className="text-sm text-primary-600 hover:text-primary-800 font-medium"
            >
              {isExpanded ? '詳細を閉じる' : '詳細を表示'}
            </button>

            {isExpanded && (
              <div className="mt-4 space-y-4">
                {/* Failure Patterns */}
                {patterns?.failure_patterns && patterns.failure_patterns.length > 0 && (
                  <div>
                    <h5 className="text-xs font-semibold text-red-600 uppercase tracking-wide mb-2">失敗パターン</h5>
                    <ul className="space-y-1">
                      {patterns.failure_patterns.map((p, i) => (
                        <li key={i} className="text-sm text-gray-700 flex items-start gap-2">
                          <span className="text-red-400 mt-0.5 flex-shrink-0">-</span>
                          <span>{typeof p === 'string' ? p : JSON.stringify(p)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Successful Patterns */}
                {patterns?.successful_patterns && patterns.successful_patterns.length > 0 && (
                  <div>
                    <h5 className="text-xs font-semibold text-green-600 uppercase tracking-wide mb-2">成功パターン</h5>
                    <ul className="space-y-1">
                      {patterns.successful_patterns.map((p, i) => (
                        <li key={i} className="text-sm text-gray-700 flex items-start gap-2">
                          <span className="text-green-400 mt-0.5 flex-shrink-0">+</span>
                          <span>{typeof p === 'string' ? p : JSON.stringify(p)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Factor Reliability */}
                {patterns?.factor_reliability && Object.keys(patterns.factor_reliability).length > 0 && (
                  <div>
                    <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">ファクター信頼度</h5>
                    <div className="space-y-2">
                      {Object.entries(patterns.factor_reliability)
                        .sort(([, a], [, b]) => b - a)
                        .map(([factor, score]) => (
                          <div key={factor} className="flex items-center gap-3">
                            <span className="text-xs text-gray-600 w-28 truncate">{factor}</span>
                            <div className="flex-1 bg-gray-100 rounded-full h-2">
                              <div
                                className={`h-2 rounded-full ${score >= 0.6 ? 'bg-green-500' : score >= 0.4 ? 'bg-yellow-400' : 'bg-red-400'}`}
                                style={{ width: `${Math.min(score * 100, 100)}%` }}
                              />
                            </div>
                            <span className="text-xs text-gray-500 font-mono w-12 text-right">
                              {(score * 100).toFixed(0)}%
                            </span>
                          </div>
                        ))}
                    </div>
                  </div>
                )}

                {/* Regime Performance */}
                {patterns?.regime_performance && Object.keys(patterns.regime_performance).length > 0 && (
                  <div>
                    <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">市場レジーム別精度</h5>
                    <div className="flex gap-4">
                      {Object.entries(patterns.regime_performance).map(([regime, perf]) => (
                        <div key={regime} className="text-center">
                          <Badge variant="regime" value={regime} />
                          <p className="text-sm font-mono font-semibold mt-1">
                            {(perf * 100).toFixed(1)}%
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Improvement Suggestions */}
                {suggestions && suggestions.length > 0 && (
                  <div>
                    <h5 className="text-xs font-semibold text-blue-600 uppercase tracking-wide mb-2">改善提案</h5>
                    <ul className="space-y-1">
                      {suggestions.map((s, i) => (
                        <li key={i} className="text-sm text-gray-700 flex items-start gap-2">
                          <span className="text-blue-400 mt-0.5 flex-shrink-0">{i + 1}.</span>
                          <span>{typeof s === 'string' ? s : JSON.stringify(s)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
