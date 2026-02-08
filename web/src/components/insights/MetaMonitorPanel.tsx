'use client';

import { Card, Badge, StatCard, EmptyState } from '@/components/ui';
import type { MetaIntervention, PromptOverride } from '@/types';

interface MetaMonitorPanelProps {
  interventions: MetaIntervention[];
  overrides: PromptOverride[];
  isJapan: boolean;
}

const TRIGGER_STYLES: Record<string, { label: string; className: string }> = {
  win_rate_drop: { label: '勝率低下', className: 'bg-red-100 text-red-800' },
  return_decline: { label: 'リターン悪化', className: 'bg-orange-100 text-orange-800' },
  missed_spike: { label: '急騰見逃し', className: 'bg-yellow-100 text-yellow-800' },
  confidence_drift: { label: '確信度ドリフト', className: 'bg-purple-100 text-purple-800' },
};

function TriggerBadge({ type }: { type: string }) {
  const style = TRIGGER_STYLES[type] || { label: type, className: 'bg-gray-100 text-gray-800' };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${style.className}`}>
      {style.label}
    </span>
  );
}

export function MetaMonitorPanel({ interventions, overrides, isJapan }: MetaMonitorPanelProps) {
  const hasData = interventions.length > 0 || overrides.length > 0;

  const latestIntervention = interventions[0] ?? null;
  const cooldownActive = latestIntervention?.cooldown_until
    ? new Date(latestIntervention.cooldown_until) > new Date()
    : false;

  return (
    <div className="space-y-6">
      <h3 className="section-title">メタ監視エージェント</h3>

      {/* Status Summary */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <StatCard
          label="アクティブ Override"
          value={overrides.length}
          sub={overrides.length > 0 ? '適用中' : 'なし'}
        />
        <StatCard
          label="直近介入"
          value={latestIntervention ? latestIntervention.intervention_date.slice(5) : '---'}
          sub={latestIntervention ? latestIntervention.trigger_type : '未実施'}
        />
        <StatCard
          label="クールダウン"
          value={cooldownActive ? 'ON' : 'OFF'}
          variant={cooldownActive ? 'highlighted' : 'default'}
          sub={cooldownActive && latestIntervention?.cooldown_until
            ? `~${latestIntervention.cooldown_until.slice(0, 10)}`
            : undefined}
        />
      </div>

      {!hasData && (
        <Card>
          <EmptyState
            message="メタ監視エージェントはまだ稼働していません。週明けから自動で監視を開始します。"
            icon="🤖"
          />
        </Card>
      )}

      {/* Active Prompt Overrides */}
      {overrides.length > 0 && (
        <Card>
          <h4 className="text-sm font-semibold text-gray-700 mb-3">アクティブなプロンプト Override</h4>
          <div className="space-y-3">
            {overrides.map((o) => (
              <div key={o.id} className="border border-amber-200 bg-amber-50 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <Badge variant="strategy" value={o.strategy_mode} />
                  <span className="text-xs text-gray-400">
                    期限: {o.expires_at.slice(0, 10)}
                  </span>
                </div>
                <p className="text-sm text-gray-800 mt-2">{o.override_text}</p>
                <p className="text-xs text-gray-500 mt-1">理由: {o.reason}</p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Intervention History */}
      {interventions.length > 0 && (
        <Card>
          <h4 className="text-sm font-semibold text-gray-700 mb-3">介入履歴</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-2 px-3 text-gray-500 font-medium">日付</th>
                  <th className="text-left py-2 px-3 text-gray-500 font-medium">戦略</th>
                  <th className="text-left py-2 px-3 text-gray-500 font-medium">トリガー</th>
                  <th className="text-left py-2 px-3 text-gray-500 font-medium">診断</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium">効果</th>
                  <th className="text-center py-2 px-3 text-gray-500 font-medium">ロールバック</th>
                </tr>
              </thead>
              <tbody>
                {interventions.map((row) => {
                  const diagSummary = row.diagnosis && typeof row.diagnosis === 'object'
                    ? (row.diagnosis as Record<string, unknown>).root_cause as string || JSON.stringify(row.diagnosis).slice(0, 80)
                    : '---';

                  return (
                    <tr key={row.id} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className="py-2 px-3 text-gray-600 whitespace-nowrap">
                        {row.intervention_date.slice(5)}
                      </td>
                      <td className="py-2 px-3">
                        <Badge variant="strategy" value={row.strategy_mode} />
                      </td>
                      <td className="py-2 px-3">
                        <TriggerBadge type={row.trigger_type} />
                      </td>
                      <td className="py-2 px-3 text-gray-600 max-w-xs truncate" title={diagSummary}>
                        {diagSummary}
                      </td>
                      <td className="text-right py-2 px-3 font-mono">
                        {row.effectiveness_score != null
                          ? <span className={row.effectiveness_score >= 0.5 ? 'text-green-600' : 'text-red-600'}>
                              {(row.effectiveness_score * 100).toFixed(0)}%
                            </span>
                          : <span className="text-gray-400">---</span>}
                      </td>
                      <td className="text-center py-2 px-3">
                        {row.rolled_back
                          ? <span className="text-red-500 text-xs font-medium">Yes</span>
                          : <span className="text-gray-400 text-xs">No</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
