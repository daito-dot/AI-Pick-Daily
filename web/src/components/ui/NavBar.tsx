'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { SystemStatus } from '@/types';

const NAV_ITEMS = [
  { href: '/', label: 'Dashboard' },
  { href: '/portfolio', label: 'Portfolio' },
  { href: '/analytics', label: 'Analytics' },
];

interface NavBarProps {
  systemStatus?: SystemStatus | null;
}

function StatusDot({ status }: { status: SystemStatus | null | undefined }) {
  if (!status) return null;

  const allStatuses = [
    status.morningScoring?.status,
    status.llmJudgment?.status,
    status.eveningReview?.status,
  ].filter(Boolean);

  const hasFailed = allStatuses.some((s) => s === 'failed');
  const hasRunning = allStatuses.some((s) => s === 'running');
  const allSuccess = allStatuses.length > 0 && allStatuses.every((s) => s === 'success');

  const color = hasFailed
    ? 'bg-red-500'
    : hasRunning
    ? 'bg-yellow-400 animate-pulse'
    : allSuccess
    ? 'bg-green-500'
    : 'bg-gray-300';

  const label = hasFailed ? 'エラーあり' : hasRunning ? '実行中' : allSuccess ? '正常' : '未実行';

  return (
    <div className="flex items-center gap-1.5" title={`システム: ${label}`}>
      <span className={`w-2 h-2 rounded-full ${color}`} />
      <span className="text-xs text-gray-500 hidden lg:inline">{label}</span>
    </div>
  );
}

export function NavBar({ systemStatus }: NavBarProps) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="bg-white/80 backdrop-blur-md border-b border-gray-100 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
        <Link href="/" className="text-xl font-bold text-primary-700 tracking-tight">
          AI Pick Daily
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden md:flex items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const isActive = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                }`}
              >
                {item.label}
              </Link>
            );
          })}
          <div className="ml-4 pl-4 border-l border-gray-200">
            <StatusDot status={systemStatus} />
          </div>
        </nav>

        {/* Mobile hamburger */}
        <button
          className="md:hidden p-2 rounded-lg hover:bg-gray-100"
          onClick={() => setMobileOpen(!mobileOpen)}
        >
          <svg className="w-5 h-5 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            {mobileOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <nav className="md:hidden border-t border-gray-100 bg-white px-4 py-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={`block px-4 py-2.5 rounded-lg text-sm font-medium ${
                  isActive
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                {item.label}
              </Link>
            );
          })}
          <div className="px-4 pt-2">
            <StatusDot status={systemStatus} />
          </div>
        </nav>
      )}
    </header>
  );
}
