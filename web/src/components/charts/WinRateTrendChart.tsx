'use client';

import { LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip } from 'recharts';

interface DataPoint {
  date: string;
  winRate: number;
  avgReturn: number;
}

interface WinRateTrendChartProps {
  data: DataPoint[];
}

export function WinRateTrendChart({ data }: WinRateTrendChartProps) {
  if (data.length === 0) {
    return (
      <div className="h-[250px] flex items-center justify-center text-gray-400">
        データが不足しています
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={250}>
      <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11, fill: '#9ca3af' }}
          tickFormatter={(v) => v.slice(5)} // MM-DD
        />
        <YAxis
          tick={{ fontSize: 11, fill: '#9ca3af' }}
          domain={[0, 100]}
          tickFormatter={(v) => `${v}%`}
        />
        <Tooltip
          formatter={(value: number, name: string) => [
            `${value.toFixed(1)}%`,
            name === 'winRate' ? '勝率' : '平均リターン',
          ]}
          labelFormatter={(label) => `日付: ${label}`}
          contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}
        />
        <Line
          type="monotone"
          dataKey="winRate"
          stroke="#3b82f6"
          strokeWidth={2}
          dot={{ r: 3 }}
          name="winRate"
        />
        <Line
          type="monotone"
          dataKey="avgReturn"
          stroke="#22c55e"
          strokeWidth={2}
          dot={{ r: 3 }}
          name="avgReturn"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
