'use client';

import { useState, useMemo } from 'react';
import type { JudgmentRecord } from '@/types';
import DateSelector from './DateSelector';
import SymbolSelector from './SymbolSelector';
import ModelComparisonPanel from './ModelComparisonPanel';
import { getModelOutputs } from '@/lib/supabase';
import type { MarketType } from '@/lib/supabase';

interface Props {
  initialDates: string[];
  initialOutputs: JudgmentRecord[];
  marketType: MarketType;
}

export default function ModelOutputsContent({ initialDates, initialOutputs, marketType }: Props) {
  const [selectedDate, setSelectedDate] = useState(initialDates[0] || '');
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [outputs, setOutputs] = useState<JudgmentRecord[]>(initialOutputs);
  const [loading, setLoading] = useState(false);

  // Group by symbol
  const outputsBySymbol = useMemo(() => {
    const map = new Map<string, JudgmentRecord[]>();
    for (const o of outputs) {
      const list = map.get(o.symbol) || [];
      list.push(o);
      map.set(o.symbol, list);
    }
    return map;
  }, [outputs]);

  const symbols = useMemo(() => Array.from(outputsBySymbol.keys()).sort(), [outputsBySymbol]);

  // Auto-select first symbol when data changes
  useMemo(() => {
    if (symbols.length > 0 && (!selectedSymbol || !symbols.includes(selectedSymbol))) {
      setSelectedSymbol(symbols[0]);
    }
  }, [symbols, selectedSymbol]);

  const selectedOutputs = selectedSymbol ? outputsBySymbol.get(selectedSymbol) || [] : [];

  async function handleDateChange(date: string) {
    setSelectedDate(date);
    setLoading(true);
    try {
      const data = await getModelOutputs(date, marketType);
      setOutputs(data);
    } catch (e) {
      console.error('Failed to fetch model outputs:', e);
    } finally {
      setLoading(false);
    }
  }

  if (initialDates.length === 0) {
    return (
      <div className="card text-center py-12 text-gray-500">
        No judgment data available
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex items-center gap-4 flex-wrap">
        <DateSelector
          dates={initialDates}
          selectedDate={selectedDate}
          onChange={handleDateChange}
        />
        <span className="text-sm text-gray-500">
          {symbols.length} symbols / {outputs.length} records
        </span>
        {loading && (
          <span className="text-sm text-blue-600 animate-pulse">Loading...</span>
        )}
      </div>

      {/* Symbol selector */}
      <SymbolSelector
        symbols={symbols}
        selectedSymbol={selectedSymbol}
        outputsBySymbol={outputsBySymbol}
        onSelect={setSelectedSymbol}
      />

      {/* Comparison panel */}
      {selectedSymbol && selectedOutputs.length > 0 ? (
        <ModelComparisonPanel
          outputs={selectedOutputs}
          symbol={selectedSymbol}
        />
      ) : (
        <div className="card text-center py-12 text-gray-500">
          Select a symbol to compare model outputs
        </div>
      )}
    </div>
  );
}
