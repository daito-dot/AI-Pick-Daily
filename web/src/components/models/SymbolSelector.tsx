'use client';

import type { JudgmentRecord } from '@/types';

interface Props {
  symbols: string[];
  selectedSymbol: string | null;
  outputsBySymbol: Map<string, JudgmentRecord[]>;
  onSelect: (symbol: string) => void;
}

export default function SymbolSelector({ symbols, selectedSymbol, outputsBySymbol, onSelect }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      {symbols.map((sym) => {
        const outputs = outputsBySymbol.get(sym) || [];
        const buyCount = outputs.filter((o) => o.decision === 'buy').length;
        const totalCount = outputs.length;
        const isSelected = sym === selectedSymbol;

        return (
          <button
            key={sym}
            onClick={() => onSelect(sym)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              isSelected
                ? 'bg-blue-600 text-white shadow-md'
                : 'bg-white border border-gray-200 text-gray-700 hover:bg-gray-50'
            }`}
          >
            <span>{sym}</span>
            <span className={`ml-1.5 text-xs ${isSelected ? 'text-blue-200' : 'text-gray-400'}`}>
              {buyCount}/{totalCount}
            </span>
          </button>
        );
      })}
    </div>
  );
}
