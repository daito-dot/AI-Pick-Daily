'use client';

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { format, parseISO } from 'date-fns';

interface SnapshotData {
  snapshot_date: string;
  cumulative_pnl_pct: number;
  sp500_cumulative_pct: number;
  alpha: number;
  total_value: number;
}

interface EquityCurveChartProps {
  v1Snapshots: SnapshotData[];
  v2Snapshots: SnapshotData[];
  benchmarkName: string;
  isJapan: boolean;
}

function mergeSnapshots(v1: SnapshotData[], v2: SnapshotData[]) {
  const dateMap = new Map<string, any>();

  for (const s of v1) {
    dateMap.set(s.snapshot_date, {
      date: s.snapshot_date,
      v1_pnl: Number(s.cumulative_pnl_pct) || 0,
      benchmark: Number(s.sp500_cumulative_pct) || 0,
    });
  }

  for (const s of v2) {
    const existing = dateMap.get(s.snapshot_date) || {
      date: s.snapshot_date,
      benchmark: Number(s.sp500_cumulative_pct) || 0,
    };
    existing.v2_pnl = Number(s.cumulative_pnl_pct) || 0;
    if (!existing.benchmark) {
      existing.benchmark = Number(s.sp500_cumulative_pct) || 0;
    }
    dateMap.set(s.snapshot_date, existing);
  }

  return Array.from(dateMap.values()).sort(
    (a, b) => a.date.localeCompare(b.date)
  );
}

function formatDateTick(dateStr: string) {
  try {
    return format(parseISO(dateStr), 'M/d');
  } catch {
    return dateStr;
  }
}

export function EquityCurveChart({
  v1Snapshots,
  v2Snapshots,
  benchmarkName,
  isJapan,
}: EquityCurveChartProps) {
  const data = mergeSnapshots(v1Snapshots, v2Snapshots);

  if (data.length < 2) {
    return (
      <div className="text-center text-gray-400 py-12">
        グラフ表示にはデータが2日分以上必要です
      </div>
    );
  }

  return (
    <div className="w-full h-80">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="date"
            tickFormatter={formatDateTick}
            tick={{ fontSize: 12, fill: '#6b7280' }}
            interval="preserveStartEnd"
          />
          <YAxis
            tickFormatter={(v: number) => `${v.toFixed(1)}%`}
            tick={{ fontSize: 12, fill: '#6b7280' }}
            width={55}
          />
          <Tooltip
            formatter={(value: number, name: string) => [
              `${value.toFixed(2)}%`,
              name,
            ]}
            labelFormatter={(label: string) => {
              try {
                return format(parseISO(label), 'yyyy/MM/dd');
              } catch {
                return label;
              }
            }}
            contentStyle={{
              borderRadius: '8px',
              border: '1px solid #e5e7eb',
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: '13px' }}
          />
          <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="3 3" />
          <Line
            type="monotone"
            dataKey="v1_pnl"
            name="V1 Conservative"
            stroke="#2563eb"
            strokeWidth={2}
            dot={false}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="v2_pnl"
            name="V2 Aggressive"
            stroke="#ea580c"
            strokeWidth={2}
            dot={false}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="benchmark"
            name={benchmarkName}
            stroke="#9ca3af"
            strokeWidth={1.5}
            strokeDasharray="5 5"
            dot={false}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default EquityCurveChart;
