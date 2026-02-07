type BadgeVariant = 'strategy' | 'status' | 'exitReason' | 'decision' | 'regime' | 'market';

interface BadgeProps {
  variant: BadgeVariant;
  value: string;
  size?: 'sm' | 'md';
}

const STRATEGY_STYLES: Record<string, { label: string; className: string }> = {
  conservative: { label: 'V1 Conservative', className: 'bg-blue-100 text-blue-800' },
  aggressive: { label: 'V2 Aggressive', className: 'bg-orange-100 text-orange-800' },
  jp_conservative: { label: 'V1 Conservative', className: 'bg-blue-100 text-blue-800' },
  jp_aggressive: { label: 'V2 Aggressive', className: 'bg-orange-100 text-orange-800' },
};

const STATUS_STYLES: Record<string, { label: string; className: string }> = {
  win: { label: '勝ち', className: 'bg-green-100 text-green-800' },
  loss: { label: '負け', className: 'bg-red-100 text-red-800' },
  flat: { label: 'フラット', className: 'bg-gray-100 text-gray-800' },
  pending: { label: '判定中', className: 'bg-yellow-100 text-yellow-800' },
  success: { label: '成功', className: 'bg-green-100 text-green-800' },
  failed: { label: '失敗', className: 'bg-red-100 text-red-800' },
  partial_success: { label: '部分成功', className: 'bg-yellow-100 text-yellow-800' },
  running: { label: '実行中', className: 'bg-blue-100 text-blue-800' },
};

const EXIT_REASON_STYLES: Record<string, { label: string; className: string }> = {
  take_profit: { label: '利確', className: 'bg-green-100 text-green-800' },
  stop_loss: { label: '損切', className: 'bg-red-100 text-red-800' },
  score_drop: { label: 'スコア低下', className: 'bg-yellow-100 text-yellow-800' },
  max_hold: { label: '保有期限', className: 'bg-gray-100 text-gray-800' },
  absolute_max_hold: { label: '最大保有期限', className: 'bg-gray-100 text-gray-800' },
  regime_change: { label: '相場変化', className: 'bg-purple-100 text-purple-800' },
};

const DECISION_STYLES: Record<string, { label: string; className: string }> = {
  buy: { label: 'BUY', className: 'bg-green-100 text-green-800' },
  hold: { label: 'HOLD', className: 'bg-yellow-100 text-yellow-800' },
  avoid: { label: 'AVOID', className: 'bg-red-100 text-red-800' },
};

const REGIME_STYLES: Record<string, { label: string; className: string }> = {
  normal: { label: '通常', className: 'bg-green-100 text-green-800' },
  adjustment: { label: '調整', className: 'bg-yellow-100 text-yellow-800' },
  crisis: { label: 'クライシス', className: 'bg-red-100 text-red-800' },
};

const MARKET_STYLES: Record<string, { label: string; className: string }> = {
  us: { label: '🇺🇸 米国株', className: 'bg-indigo-100 text-indigo-800' },
  jp: { label: '🇯🇵 日本株', className: 'bg-red-100 text-red-800' },
};

function getStyle(variant: BadgeVariant, value: string): { label: string; className: string } {
  const map: Record<BadgeVariant, Record<string, { label: string; className: string }>> = {
    strategy: STRATEGY_STYLES,
    status: STATUS_STYLES,
    exitReason: EXIT_REASON_STYLES,
    decision: DECISION_STYLES,
    regime: REGIME_STYLES,
    market: MARKET_STYLES,
  };
  return map[variant]?.[value] || { label: value, className: 'bg-gray-100 text-gray-800' };
}

export function Badge({ variant, value, size = 'sm' }: BadgeProps) {
  const style = getStyle(variant, value);
  const sizeClass = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm';

  return (
    <span className={`inline-flex items-center rounded-full font-medium ${sizeClass} ${style.className}`}>
      {style.label}
    </span>
  );
}
