'use client';

import { useState, useMemo, useCallback } from 'react';
import { Card, EmptyState } from '@/components/ui';
import { JudgmentCard } from './JudgmentCard';
import type { JudgmentRecord } from '@/types';

interface RuleBasedScore {
  symbol: string;
  composite_score: number;
  percentile_rank: number;
  price_at_time?: number;
  return_1d?: number | null;
  return_5d?: number | null;
}

interface JudgmentDetailPanelProps {
  judgments: JudgmentRecord[];
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

export function JudgmentDetailPanel({
  judgments,
  finalPicks,
  confidenceThreshold = { conservative: 0.6, aggressive: 0.5 },
  ruleBasedScores,
  scoreThreshold = { conservative: 60, aggressive: 75 },
  isJapan = false,
}: JudgmentDetailPanelProps) {
  const [filter, setFilter] = useState<'all' | 'buy' | 'hold' | 'avoid'>('all');
  const [sortBy, setSortBy] = useState<'confidence' | 'score'>('confidence');

  const isV1 = useCallback((j: JudgmentRecord) =>
    j.strategy_mode === 'conservative' || j.strategy_mode === 'jp_conservative',
    []
  );

  const checkIsFinalPick = useCallback((j: JudgmentRecord) => {
    if (!finalPicks) return false;
    const picks = isV1(j) ? finalPicks.conservative : finalPicks.aggressive;
    return picks.includes(j.symbol);
  }, [finalPicks, isV1]);

  const getConfThreshold = useCallback((j: JudgmentRecord) =>
    isV1(j) ? confidenceThreshold.conservative : confidenceThreshold.aggressive,
    [confidenceThreshold, isV1]
  );

  const getRuleBasedScore = useCallback((j: JudgmentRecord) => {
    if (!ruleBasedScores) return undefined;
    const scores = isV1(j) ? ruleBasedScores.conservative : ruleBasedScores.aggressive;
    return scores.find(s => s.symbol === j.symbol);
  }, [ruleBasedScores, isV1]);

  const getRuleBasedRank = useCallback((j: JudgmentRecord) => {
    if (!ruleBasedScores) return undefined;
    const scores = isV1(j) ? ruleBasedScores.conservative : ruleBasedScores.aggressive;
    const sorted = [...scores].sort((a, b) => b.composite_score - a.composite_score);
    const idx = sorted.findIndex(s => s.symbol === j.symbol);
    return idx >= 0 ? idx + 1 : undefined;
  }, [ruleBasedScores, isV1]);

  const getScoreThreshold = useCallback((j: JudgmentRecord) =>
    isV1(j) ? scoreThreshold.conservative : scoreThreshold.aggressive,
    [scoreThreshold, isV1]
  );

  const filteredJudgments = useMemo(() =>
    judgments
      .filter(j => filter === 'all' || j.decision === filter)
      .sort((a, b) =>
        sortBy === 'confidence' ? b.confidence - a.confidence : b.score - a.score
      ),
    [judgments, filter, sortBy]
  );

  const stats = useMemo(() => ({
    total: judgments.length,
    buy: judgments.filter(j => j.decision === 'buy').length,
    hold: judgments.filter(j => j.decision === 'hold').length,
    avoid: judgments.filter(j => j.decision === 'avoid').length,
    avgConfidence: judgments.length > 0
      ? judgments.reduce((sum, j) => sum + j.confidence, 0) / judgments.length
      : 0,
    finalPicks: judgments.filter(j => checkIsFinalPick(j)).length,
  }), [judgments, checkIsFinalPick]);

  if (!judgments || judgments.length === 0) {
    return (
      <div>
        <h3 className="section-title mb-3">LLM判断詳細</h3>
        <Card>
          <EmptyState message="本日のLLM判断データがありません" />
        </Card>
      </div>
    );
  }

  return (
    <div>
      <h3 className="section-title mb-3">LLM判断詳細</h3>

      <Card className="mb-4">
        {/* Pipeline Flow */}
        <div className="bg-gray-50 rounded-xl p-4 mb-4">
          <p className="text-xs text-gray-500 mb-3">選択フロー（LLM信頼度優先）</p>
          <div className="flex items-center gap-2 flex-wrap text-sm">
            <div className="text-center px-3 py-1.5 bg-white rounded-lg shadow-sm">
              <p className="text-lg font-bold text-gray-700">{stats.total}</p>
              <p className="text-xs text-gray-400">閾値通過</p>
            </div>
            <span className="text-gray-300">→</span>
            <div className="text-center px-3 py-1.5 bg-white rounded-lg shadow-sm">
              <p className="text-lg font-bold text-profit">{stats.buy}</p>
              <p className="text-xs text-gray-400">LLM BUY</p>
            </div>
            <span className="text-gray-300">→</span>
            <div className="text-center px-3 py-1.5 bg-blue-50 rounded-lg shadow-sm border border-blue-100">
              <p className="text-lg font-bold text-blue-600">{stats.finalPicks}</p>
              <p className="text-xs text-blue-500">最終採用</p>
            </div>
          </div>
          <div className="mt-3 text-xs text-gray-400 space-y-0.5">
            <p>ルールスコア閾値: V1≥{scoreThreshold.conservative}点 / V2≥{scoreThreshold.aggressive}点</p>
            <p>信頼度閾値: V1≥{(confidenceThreshold.conservative * 100).toFixed(0)}% / V2≥{(confidenceThreshold.aggressive * 100).toFixed(0)}%</p>
          </div>
        </div>

        {/* Summary stats */}
        <div className="grid grid-cols-5 gap-3 mb-4">
          {[
            { label: '総判断', value: stats.total, color: 'text-gray-700' },
            { label: 'BUY', value: stats.buy, color: 'text-profit' },
            { label: 'HOLD', value: stats.hold, color: 'text-yellow-600' },
            { label: 'AVOID', value: stats.avoid, color: 'text-loss' },
            { label: '平均信頼度', value: `${(stats.avgConfidence * 100).toFixed(0)}%`, color: 'text-blue-600' },
          ].map((s) => (
            <div key={s.label} className="text-center">
              <p className={`text-xl font-bold ${s.color}`}>{s.value}</p>
              <p className="text-xs text-gray-400">{s.label}</p>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-1.5">
            {(['all', 'buy', 'hold', 'avoid'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1 text-xs rounded-full transition-colors ${
                  filter === f
                    ? 'bg-gray-800 text-white'
                    : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                }`}
              >
                {f === 'all' ? 'ALL' : f.toUpperCase()}
              </button>
            ))}
          </div>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="text-xs border border-gray-200 rounded-lg px-2 py-1 text-gray-500"
          >
            <option value="confidence">信頼度順</option>
            <option value="score">スコア順</option>
          </select>
        </div>
      </Card>

      {/* Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredJudgments.map((j) => (
          <JudgmentCard
            key={j.id}
            judgment={j}
            isFinalPick={checkIsFinalPick(j)}
            confidenceThreshold={getConfThreshold(j)}
            ruleBasedScore={getRuleBasedScore(j)}
            scoreThreshold={getScoreThreshold(j)}
            ruleBasedRank={getRuleBasedRank(j)}
            isJapan={isJapan}
          />
        ))}
      </div>
    </div>
  );
}
