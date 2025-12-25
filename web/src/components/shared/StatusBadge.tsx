'use client';

import type { ExecutionStatus } from '@/types';

// Status configuration with Japanese labels
export const STATUS_CONFIG = {
  success: { bg: 'bg-green-100', text: 'text-green-700', label: '成功', icon: '\u2713' },
  partial_success: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: '一部失敗', icon: '\u26A0' },
  failed: { bg: 'bg-red-100', text: 'text-red-700', label: '失敗', icon: '\u2717' },
  running: { bg: 'bg-blue-100', text: 'text-blue-700', label: '実行中', icon: '\u25CF' },
} as const;

export const NULL_STATUS_CONFIG = {
  bg: 'bg-gray-100',
  text: 'text-gray-500',
  label: '未実行',
  icon: '-',
} as const;

interface StatusIconProps {
  status: ExecutionStatus | null;
}

export function StatusIcon({ status }: StatusIconProps) {
  if (!status) {
    return <span className="text-gray-400">{NULL_STATUS_CONFIG.icon}</span>;
  }

  const config = STATUS_CONFIG[status];
  const isRunning = status === 'running';

  return (
    <span className={`${config.text} ${isRunning ? 'animate-pulse' : ''}`}>
      {config.icon}
    </span>
  );
}

interface StatusBadgeProps {
  status: ExecutionStatus | null;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  if (!status) {
    return (
      <span className={`px-2 py-0.5 text-xs rounded ${NULL_STATUS_CONFIG.bg} ${NULL_STATUS_CONFIG.text}`}>
        {NULL_STATUS_CONFIG.label}
      </span>
    );
  }

  const config = STATUS_CONFIG[status];

  return (
    <span className={`px-2 py-0.5 text-xs rounded ${config.bg} ${config.text}`}>
      {config.label}
    </span>
  );
}

export default StatusBadge;
