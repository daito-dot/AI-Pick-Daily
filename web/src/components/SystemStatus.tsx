'use client';

import type { SystemStatus, BatchExecutionLog, ExecutionStatus } from '@/types';
import { format } from 'date-fns';
import { ja } from 'date-fns/locale';

interface SystemStatusPanelProps {
  status: SystemStatus;
}

function StatusIcon({ status }: { status: ExecutionStatus | null }) {
  if (!status) {
    return <span className="text-gray-400">-</span>;
  }

  switch (status) {
    case 'success':
      return <span className="text-green-500">&#x2713;</span>;
    case 'partial_success':
      return <span className="text-yellow-500">&#x26A0;</span>;
    case 'failed':
      return <span className="text-red-500">&#x2717;</span>;
    case 'running':
      return <span className="text-blue-500 animate-pulse">&#x25CF;</span>;
    default:
      return <span className="text-gray-400">-</span>;
  }
}

function StatusBadge({ status }: { status: ExecutionStatus | null }) {
  if (!status) {
    return (
      <span className="px-2 py-0.5 text-xs rounded bg-gray-100 text-gray-500">
        未実行
      </span>
    );
  }

  const config = {
    success: { bg: 'bg-green-100', text: 'text-green-700', label: '成功' },
    partial_success: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: '一部失敗' },
    failed: { bg: 'bg-red-100', text: 'text-red-700', label: '失敗' },
    running: { bg: 'bg-blue-100', text: 'text-blue-700', label: '実行中' },
  };

  const c = config[status];

  return (
    <span className={`px-2 py-0.5 text-xs rounded ${c.bg} ${c.text}`}>
      {c.label}
    </span>
  );
}

function BatchStatusRow({
  label,
  log,
}: {
  label: string;
  log: BatchExecutionLog | null;
}) {
  const formatTime = (isoString: string | null) => {
    if (!isoString) return '-';
    try {
      return format(new Date(isoString), 'HH:mm', { locale: ja });
    } catch {
      return '-';
    }
  };

  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
      <div className="flex items-center gap-2">
        <StatusIcon status={log?.status || null} />
        <span className="text-sm font-medium text-gray-700">{label}</span>
      </div>

      <div className="flex items-center gap-3">
        {log?.status && log.status !== 'running' && (
          <span className="text-xs text-gray-500">
            {log.successful_items}/{log.total_items}
          </span>
        )}
        <span className="text-xs text-gray-400">
          {formatTime(log?.started_at || null)}
        </span>
        <StatusBadge status={log?.status || null} />
      </div>
    </div>
  );
}

function ErrorDetails({ log }: { log: BatchExecutionLog }) {
  if (!log.error_message && !log.error_details) {
    return null;
  }

  return (
    <div className="mt-2 p-2 bg-red-50 rounded text-xs">
      {log.error_message && (
        <p className="text-red-700 font-medium">{log.error_message}</p>
      )}
      {log.error_details?.errors && log.error_details.errors.length > 0 && (
        <ul className="mt-1 text-red-600 list-disc list-inside">
          {log.error_details.errors.slice(0, 3).map((err, idx) => (
            <li key={idx}>
              {err.item_id ? `${err.item_id}: ` : ''}{err.error}
            </li>
          ))}
          {log.error_details.errors.length > 3 && (
            <li className="text-gray-500">
              ...他 {log.error_details.errors.length - 3} 件
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

export function SystemStatusPanel({ status }: SystemStatusPanelProps) {
  // Check if any batch has errors
  const hasErrors = [
    status.morningScoring,
    status.llmJudgment,
    status.eveningReview,
  ].some(log => log?.status === 'failed' || log?.status === 'partial_success');

  // Find the log with error for details
  const errorLog = [
    status.morningScoring,
    status.llmJudgment,
    status.eveningReview,
  ].find(log => log?.status === 'failed' || log?.status === 'partial_success');

  return (
    <div className={`rounded-lg border p-4 ${
      hasErrors ? 'bg-red-50 border-red-200' : 'bg-gray-50 border-gray-200'
    }`}>
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-gray-700">
          システムステータス
        </h4>
        {hasErrors && (
          <span className="text-xs text-red-600 font-medium">
            要確認
          </span>
        )}
      </div>

      <div className="space-y-1">
        <BatchStatusRow label="朝バッチ" log={status.morningScoring} />
        <BatchStatusRow label="LLM判断" log={status.llmJudgment} />
        <BatchStatusRow label="夕バッチ" log={status.eveningReview} />
      </div>

      {errorLog && <ErrorDetails log={errorLog} />}
    </div>
  );
}

// Compact version for header
export function SystemStatusCompact({ status }: SystemStatusPanelProps) {
  const getOverallStatus = (): 'ok' | 'warning' | 'error' | 'pending' => {
    const logs = [status.morningScoring, status.llmJudgment];

    if (logs.some(l => l?.status === 'failed')) return 'error';
    if (logs.some(l => l?.status === 'partial_success')) return 'warning';
    if (logs.some(l => l?.status === 'running')) return 'pending';
    if (logs.some(l => l?.status === 'success')) return 'ok';
    return 'pending';
  };

  const overall = getOverallStatus();

  const config = {
    ok: { bg: 'bg-green-100', text: 'text-green-700', icon: '&#x2713;', label: '正常' },
    warning: { bg: 'bg-yellow-100', text: 'text-yellow-700', icon: '&#x26A0;', label: '警告' },
    error: { bg: 'bg-red-100', text: 'text-red-700', icon: '&#x2717;', label: 'エラー' },
    pending: { bg: 'bg-gray-100', text: 'text-gray-500', icon: '-', label: '待機中' },
  };

  const c = config[overall];

  return (
    <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded ${c.bg}`}>
      <span className={c.text} dangerouslySetInnerHTML={{ __html: c.icon }} />
      <span className={`text-xs font-medium ${c.text}`}>{c.label}</span>
    </div>
  );
}

export default SystemStatusPanel;
