import { getPerformanceHistory, getAILessons } from '@/lib/supabase';
import { format, parseISO } from 'date-fns';
import { ja } from 'date-fns/locale';

export const revalidate = 300;

function StatusBadge({ status }: { status: string }) {
  const config = {
    win: { label: '勝ち', className: 'bg-green-100 text-green-800' },
    loss: { label: '負け', className: 'bg-red-100 text-red-800' },
    flat: { label: 'フラット', className: 'bg-gray-100 text-gray-800' },
    pending: { label: '判定中', className: 'bg-yellow-100 text-yellow-800' },
  };
  const c = config[status as keyof typeof config] || config.pending;

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${c.className}`}>
      {c.label}
    </span>
  );
}

export default async function PerformancePage() {
  const [performance, lessons] = await Promise.all([
    getPerformanceHistory(30),
    getAILessons(5),
  ]);

  // Calculate stats
  const completedTrades = performance.filter(p => p.status_5d !== 'pending');
  const wins = completedTrades.filter(p => p.status_5d === 'win').length;
  const winRate = completedTrades.length > 0
    ? ((wins / completedTrades.length) * 100).toFixed(1)
    : '---';
  const avgReturn = completedTrades.length > 0
    ? (completedTrades.reduce((sum, p) => sum + (p.return_pct_5d || 0), 0) / completedTrades.length).toFixed(2)
    : '---';

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold text-gray-900">パフォーマンス</h2>
        <p className="text-gray-500 mt-1">推奨銘柄の実績と学習内容</p>
      </div>

      {/* Stats Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="card text-center">
          <p className="text-gray-500 text-sm">勝率（5日）</p>
          <p className="text-4xl font-bold text-primary-600">{winRate}%</p>
        </div>
        <div className="card text-center">
          <p className="text-gray-500 text-sm">平均リターン</p>
          <p className={`text-4xl font-bold ${
            Number(avgReturn) >= 0 ? 'text-green-600' : 'text-red-600'
          }`}>
            {avgReturn !== '---' ? `${avgReturn}%` : avgReturn}
          </p>
        </div>
        <div className="card text-center">
          <p className="text-gray-500 text-sm">取引数</p>
          <p className="text-4xl font-bold text-gray-700">{completedTrades.length}</p>
        </div>
      </div>

      {/* Recent Performance */}
      <div className="card overflow-x-auto">
        <h3 className="text-lg font-semibold mb-4">直近のパフォーマンス</h3>
        {performance.length > 0 ? (
          <table className="w-full">
            <thead>
              <tr className="border-b text-left text-sm text-gray-500">
                <th className="pb-3">日付</th>
                <th className="pb-3">銘柄</th>
                <th className="pb-3 text-right">スコア</th>
                <th className="pb-3 text-right">1日</th>
                <th className="pb-3 text-right">5日</th>
                <th className="pb-3 text-center">結果</th>
              </tr>
            </thead>
            <tbody>
              {performance.slice(0, 20).map((p) => (
                <tr key={p.id} className="border-b last:border-0">
                  <td className="py-3 text-sm text-gray-600">
                    {format(parseISO(p.pick_date), 'MM/dd', { locale: ja })}
                  </td>
                  <td className="py-3 font-medium">{p.symbol}</td>
                  <td className="py-3 text-right">{p.recommendation_score}</td>
                  <td className={`py-3 text-right ${
                    (p.return_pct_1d || 0) >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {p.return_pct_1d !== null ? `${p.return_pct_1d.toFixed(2)}%` : '-'}
                  </td>
                  <td className={`py-3 text-right ${
                    (p.return_pct_5d || 0) >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {p.return_pct_5d !== null ? `${p.return_pct_5d.toFixed(2)}%` : '-'}
                  </td>
                  <td className="py-3 text-center">
                    <StatusBadge status={p.status_5d} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-gray-500 text-center py-8">
            パフォーマンスデータがありません
          </p>
        )}
      </div>

      {/* AI Lessons */}
      <div>
        <h3 className="text-xl font-semibold mb-4">AIの反省と学習</h3>
        {lessons.length > 0 ? (
          <div className="space-y-4">
            {lessons.map((lesson) => (
              <div key={lesson.id} className="card">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-gray-500">
                    {format(parseISO(lesson.lesson_date), 'yyyy年MM月dd日', { locale: ja })}
                  </span>
                </div>
                <p className="text-gray-700 whitespace-pre-wrap">
                  {lesson.lesson_text}
                </p>
                {lesson.biggest_miss_symbols?.length > 0 && (
                  <div className="mt-3 pt-3 border-t">
                    <p className="text-sm text-gray-500">
                      分析対象: {lesson.biggest_miss_symbols.join(', ')}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="card text-center py-8">
            <p className="text-gray-500">
              学習データがありません
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
