import { Card, PnLDisplay } from '@/components/ui';

interface PerformanceComparisonProps {
  comparison: {
    pickedCount: number;
    pickedAvgReturn: number;
    notPickedCount: number;
    notPickedAvgReturn: number;
    missedOpportunities: number;
  };
}

export function PerformanceComparison({ comparison }: PerformanceComparisonProps) {
  if (comparison.pickedCount === 0 && comparison.notPickedCount === 0) {
    return null;
  }

  const pickedBetter = comparison.pickedAvgReturn >= comparison.notPickedAvgReturn;

  return (
    <div>
      <h3 className="section-title mb-3">推奨 vs 非推奨 パフォーマンス</h3>
      <Card>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-4 bg-blue-50/50 rounded-lg">
            <h4 className="text-sm font-medium text-blue-800 mb-2">推奨した銘柄</h4>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">件数</span>
                <span className="font-bold">{comparison.pickedCount}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">平均リターン</span>
                <PnLDisplay value={comparison.pickedAvgReturn} size="sm" />
              </div>
            </div>
          </div>
          <div className="p-4 bg-gray-50/50 rounded-lg">
            <h4 className="text-sm font-medium text-gray-700 mb-2">推奨しなかった銘柄</h4>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">件数</span>
                <span className="font-bold">{comparison.notPickedCount}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">平均リターン</span>
                <PnLDisplay value={comparison.notPickedAvgReturn} size="sm" />
              </div>
            </div>
          </div>
        </div>

        {!pickedBetter && (
          <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
            <p className="text-yellow-800 text-xs">
              推奨しなかった銘柄の方が平均リターンが高い状況です。スコアリングロジックの見直しが必要かもしれません。
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}
