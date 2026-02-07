import { StatCard } from '@/components/ui';
import type { PerformanceStats } from '@/types';

interface JudgmentAccuracyStatsProps {
  stats: PerformanceStats | null;
}

export function JudgmentAccuracyStats({ stats }: JudgmentAccuracyStatsProps) {
  if (!stats) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Buy勝率" value="---" />
        <StatCard label="平均リターン" value="---" />
        <StatCard label="Avoid精度" value="---" />
        <StatCard label="判断総数" value="---" />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <StatCard
        label="Buy勝率"
        value={`${stats.buy_win_rate.toFixed(1)}%`}
        trend={stats.buy_win_rate >= 55 ? 'up' : stats.buy_win_rate >= 45 ? undefined : 'down'}
        sub={`${stats.buy_win_count}/${stats.buy_count}`}
      />
      <StatCard
        label="平均リターン"
        value={`${stats.buy_avg_return >= 0 ? '+' : ''}${stats.buy_avg_return.toFixed(2)}%`}
        trend={stats.buy_avg_return >= 0 ? 'up' : 'down'}
      />
      <StatCard
        label="Avoid精度"
        value={`${stats.avoid_accuracy.toFixed(1)}%`}
        trend={stats.avoid_accuracy >= 55 ? 'up' : stats.avoid_accuracy >= 45 ? undefined : 'down'}
        sub={`${stats.avoid_correct_count}/${stats.avoid_count}`}
      />
      <StatCard
        label="判断総数"
        value={`${stats.buy_count + stats.avoid_count}`}
        sub={`Buy: ${stats.buy_count} / Avoid: ${stats.avoid_count}`}
      />
    </div>
  );
}
