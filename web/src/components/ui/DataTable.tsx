'use client';

import { useState, useMemo } from 'react';
import { EmptyState } from './EmptyState';

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  sortable?: boolean;
  sortValue?: (row: T) => number | string;
  align?: 'left' | 'center' | 'right';
  hideOnMobile?: boolean;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (row: T) => string;
  defaultSortKey?: string;
  defaultSortDesc?: boolean;
  emptyMessage?: string;
  maxRows?: number;
}

export function DataTable<T>({
  columns,
  data,
  keyExtractor,
  defaultSortKey,
  defaultSortDesc = true,
  emptyMessage = 'データがありません',
  maxRows,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | undefined>(defaultSortKey);
  const [sortDesc, setSortDesc] = useState(defaultSortDesc);

  const sortedData = useMemo(() => {
    if (!sortKey) return data;
    const col = columns.find((c) => c.key === sortKey);
    if (!col?.sortValue) return data;

    return [...data].sort((a, b) => {
      const aVal = col.sortValue!(a);
      const bVal = col.sortValue!(b);
      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortDesc ? bVal - aVal : aVal - bVal;
      }
      const comp = String(aVal).localeCompare(String(bVal));
      return sortDesc ? -comp : comp;
    });
  }, [data, sortKey, sortDesc, columns]);

  const displayData = maxRows ? sortedData.slice(0, maxRows) : sortedData;

  if (data.length === 0) {
    return <EmptyState message={emptyMessage} />;
  }

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDesc(!sortDesc);
    } else {
      setSortKey(key);
      setSortDesc(true);
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-100">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`pb-3 text-sm font-medium text-gray-500 ${
                  col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'
                } ${col.hideOnMobile ? 'hidden md:table-cell' : ''} ${
                  col.sortable ? 'cursor-pointer hover:text-gray-700 select-none' : ''
                }`}
                onClick={() => col.sortable && handleSort(col.key)}
              >
                {col.header}
                {col.sortable && sortKey === col.key && (
                  <span className="ml-1">{sortDesc ? '↓' : '↑'}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayData.map((row) => (
            <tr key={keyExtractor(row)} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50">
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`py-3 ${
                    col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'
                  } ${col.hideOnMobile ? 'hidden md:table-cell' : ''}`}
                >
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
