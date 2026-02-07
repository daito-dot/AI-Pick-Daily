import { Card, Badge } from '@/components/ui';

interface ThresholdsDisplayProps {
  v1Config: any;
  v2Config: any;
  thresholdHistory: any[];
}

export function ThresholdsDisplay({ v1Config, v2Config, thresholdHistory }: ThresholdsDisplayProps) {
  return (
    <div>
      <h3 className="section-title mb-3">動的閾値（フィードバックループ）</h3>
      <Card>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-4 bg-blue-50/50 rounded-lg">
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-blue-800">V1 Conservative</span>
              <span className="text-xl font-bold text-blue-900">{v1Config?.threshold ?? 60}点</span>
            </div>
            <p className="text-xs text-blue-600">
              範囲: {v1Config?.min_threshold ?? 40} - {v1Config?.max_threshold ?? 80}
            </p>
            {v1Config?.last_adjustment_date && (
              <p className="text-xs text-blue-400 mt-1">最終調整: {v1Config.last_adjustment_date}</p>
            )}
          </div>
          <div className="p-4 bg-orange-50/50 rounded-lg">
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-orange-800">V2 Aggressive</span>
              <span className="text-xl font-bold text-orange-900">{v2Config?.threshold ?? 75}点</span>
            </div>
            <p className="text-xs text-orange-600">
              範囲: {v2Config?.min_threshold ?? 50} - {v2Config?.max_threshold ?? 90}
            </p>
            {v2Config?.last_adjustment_date && (
              <p className="text-xs text-orange-400 mt-1">最終調整: {v2Config.last_adjustment_date}</p>
            )}
          </div>
        </div>

        {thresholdHistory.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <h4 className="text-sm font-medium text-gray-600 mb-2">変更履歴</h4>
            <div className="space-y-1.5">
              {thresholdHistory.slice(0, 5).map((h: any, i: number) => (
                <div key={i} className="flex items-center justify-between text-sm p-2 bg-gray-50 rounded">
                  <div className="flex items-center gap-2">
                    <Badge variant="strategy" value={h.strategy_mode} />
                    <span className="text-gray-600">{h.old_threshold} → {h.new_threshold}</span>
                  </div>
                  <span className="text-xs text-gray-400">{h.adjustment_date}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
