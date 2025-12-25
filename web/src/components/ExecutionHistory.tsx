'use client';

import { useEffect, useState } from 'react';
import type { BatchExecutionLog } from '@/types';
import { getBatchExecutionHistory } from '@/lib/supabase';
import { format, formatDistanceToNow } from 'date-fns';
import { ja } from 'date-fns/locale';
import { StatusBadge } from './shared';

interface ExecutionHistoryProps {
  initialData?: BatchExecutionLog[];
}

function BatchTypeLabel({ batchType }: { batchType: string }) {
  const labels: Record<string, { label: string; market: string }> = {
    'morning_scoring': { label: 'Post-Market Scoring', market: '🇺🇸 米国株' },
    'evening_review': { label: 'Pre-Market Review', market: '🇺🇸 米国株' },
    'llm_judgment': { label: 'LLM Judgment', market: '' },
    'weekly_research': { label: 'Weekly Research', market: '' },
    'morning_scoring_jp': { label: 'Post-Market Scoring', market: '🇯🇵 日本株' },
    'evening_review_jp': { label: 'Pre-Market Review', market: '🇯🇵 日本株' },
  };

  const info = labels[batchType] || { label: batchType, market: '' };

  return (
    <div className="flex items-center gap-2">
      {info.market && (
        <span className={`text-xs px-1.5 py-0.5 rounded ${
          info.market.includes('日本株') ? 'bg-red-50 text-red-600' : 'bg-blue-50 text-blue-600'
        }`}>
          {info.market}
        </span>
      )}
      <span className="text-sm font-medium text-gray-700">{info.label}</span>
    </div>
  );
}

function ExecutionRow({ log }: { log: BatchExecutionLog }) {
  const formatTime = (isoString: string | null) => {
    if (!isoString) return '-';
    try {
      const date = new Date(isoString);
      return format(date, 'M月d日 HH:mm', { locale: ja });
    } catch {
      return '-';
    }
  };

  const formatDuration = (start: string | null, end: string | null) => {
    if (!start || !end) return '-';
    try {
      const startDate = new Date(start);
      const endDate = new Date(end);
      const diffMs = endDate.getTime() - startDate.getTime();
      const diffSec = Math.floor(diffMs / 1000);
      const minutes = Math.floor(diffSec / 60);
      const seconds = diffSec % 60;
      if (minutes > 0) {
        return `${minutes}m ${seconds}s`;
      }
      return `${seconds}s`;
    } catch {
      return '-';
    }
  };

  const formatRelativeTime = (isoString: string | null) => {
    if (!isoString) return '';
    try {
      return formatDistanceToNow(new Date(isoString), { addSuffix: true, locale: ja });
    } catch {
      return '';
    }
  };

  return (
    <div className="flex items-center justify-between py-3 border-b border-gray-100 last:border-0 hover:bg-gray-50 px-2 -mx-2 rounded">
      <div className="flex items-center gap-3 min-w-0">
        <BatchTypeLabel batchType={log.batch_type} />
      </div>

      <div className="flex items-center gap-4 text-sm">
        {log.total_items > 0 && (
          <span className="text-gray-500">
            {log.successful_items}/{log.total_items}
          </span>
        )}
        <span className="text-gray-400 text-xs w-20 text-right">
          {formatDuration(log.started_at, log.completed_at)}
        </span>
        <span className="text-gray-400 text-xs w-28 text-right" title={log.started_at || ''}>
          {formatTime(log.started_at)}
        </span>
        <StatusBadge status={log.status} />
      </div>
    </div>
  );
}

function ScheduleTable() {
  const schedules = [
    { market: '🇺🇸 米国株', type: 'Post-Market Scoring', time: '07:00 JST', utc: '22:00 UTC' },
    { market: '🇺🇸 米国株', type: 'Pre-Market Review', time: '06:00 JST', utc: '21:00 UTC' },
    { market: '🇯🇵 日本株', type: 'Post-Market Scoring', time: '16:00 JST', utc: '07:00 UTC' },
    { market: '🇯🇵 日本株', type: 'Pre-Market Review', time: '08:00 JST', utc: '23:00 UTC' },
  ];

  return (
    <div className="mt-4 pt-4 border-t border-gray-200">
      <p className="text-xs text-gray-500 mb-2 font-medium">実行スケジュール (月〜金)</p>
      <div className="grid grid-cols-2 gap-2 text-xs">
        {schedules.map((s, i) => (
          <div key={i} className="flex items-center justify-between bg-white rounded p-2">
            <span className="text-gray-600">{s.market} {s.type}</span>
            <span className="font-medium text-gray-800">{s.time}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ExecutionHistory({ initialData }: ExecutionHistoryProps) {
  const [logs, setLogs] = useState<BatchExecutionLog[]>(initialData || []);
  const [loading, setLoading] = useState(!initialData);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!initialData) {
      loadHistory();
    }
  }, [initialData]);

  const loadHistory = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getBatchExecutionHistory(7);
      setLogs(data);
    } catch (err) {
      setError('履歴の取得に失敗しました');
      console.error('Failed to load execution history:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="rounded-lg border bg-gray-50 border-gray-200 p-4">
        <h4 className="text-sm font-semibold text-gray-700 mb-3">実行履歴</h4>
        <div className="animate-pulse space-y-2">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-8 bg-gray-200 rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border bg-red-50 border-red-200 p-4">
        <h4 className="text-sm font-semibold text-red-700 mb-2">実行履歴</h4>
        <p className="text-sm text-red-600">{error}</p>
        <button
          onClick={loadHistory}
          className="mt-2 text-xs text-red-700 underline hover:no-underline"
        >
          再試行
        </button>
      </div>
    );
  }

  // Group by date
  const groupedLogs = logs.reduce((acc, log) => {
    const date = log.batch_date;
    if (!acc[date]) {
      acc[date] = [];
    }
    acc[date].push(log);
    return acc;
  }, {} as Record<string, BatchExecutionLog[]>);

  const sortedDates = Object.keys(groupedLogs).sort((a, b) => b.localeCompare(a));

  return (
    <div className="rounded-lg border bg-gray-50 border-gray-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-gray-700">実行履歴 (7日間)</h4>
        <button
          onClick={loadHistory}
          className="text-xs text-blue-600 hover:text-blue-800"
          title="更新"
        >
          ↻ 更新
        </button>
      </div>

      {logs.length === 0 ? (
        <p className="text-sm text-gray-500 text-center py-4">
          実行履歴がありません
        </p>
      ) : (
        <div className="space-y-4 max-h-96 overflow-y-auto">
          {sortedDates.map(date => (
            <div key={date}>
              <p className="text-xs font-medium text-gray-500 mb-1 sticky top-0 bg-gray-50 py-1">
                {format(new Date(date), 'M月d日 (E)', { locale: ja })}
              </p>
              <div className="space-y-0">
                {groupedLogs[date].map(log => (
                  <ExecutionRow key={log.id} log={log} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <ScheduleTable />
    </div>
  );
}

export default ExecutionHistory;
