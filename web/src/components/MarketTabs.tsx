'use client';

import { useState } from 'react';
import type { MarketType } from '@/lib/supabase';

interface MarketTabsProps {
  usContent: React.ReactNode;
  jpContent: React.ReactNode;
}

export function MarketTabs({ usContent, jpContent }: MarketTabsProps) {
  const [market, setMarket] = useState<MarketType>('us');

  return (
    <div>
      {/* Tab Buttons */}
      <div className="flex gap-2 mb-6">
        <button
          onClick={() => setMarket('us')}
          className={`px-6 py-3 rounded-lg font-medium transition-all ${
            market === 'us'
              ? 'bg-blue-600 text-white shadow-lg'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          <span className="mr-2">🇺🇸</span>
          米国株
        </button>
        <button
          onClick={() => setMarket('jp')}
          className={`px-6 py-3 rounded-lg font-medium transition-all ${
            market === 'jp'
              ? 'bg-red-600 text-white shadow-lg'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          <span className="mr-2">🇯🇵</span>
          日本株
        </button>
      </div>

      {/* Content */}
      <div className={market === 'us' ? 'block' : 'hidden'}>
        {usContent}
      </div>
      <div className={market === 'jp' ? 'block' : 'hidden'}>
        {jpContent}
      </div>
    </div>
  );
}

export default MarketTabs;
