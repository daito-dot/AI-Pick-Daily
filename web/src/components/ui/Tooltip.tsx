const DEFINITIONS: Record<string, string> = {
  confidence: 'AIがこの判断にどれだけ自信を持っているか（0-100%）',
  composite_score: '複数の評価指標を組み合わせた総合スコア',
  momentum: '株価の勢い・トレンドの強さ',
  breakout: '過去の高値を突破する可能性',
  catalyst: '決算発表など株価を動かす材料の有無',
  trend: '株価が上昇傾向か下降傾向か',
  value: '株価が割安かどうか',
  sentiment: '市場参加者の心理・ニュースの雰囲気',
  risk: 'リターンに対するリスクの度合い',
  percentile: '全銘柄の中での順位（上位何%か）',
  conviction: 'AIポートフォリオ判断での確信度',
  alpha: 'ベンチマークに対する超過リターン',
  sharpe: 'リスクあたりのリターン効率（高いほど良い）',
  drawdown: '最高値からの最大下落率',
};

interface TooltipProps {
  term: string;
  children: React.ReactNode;
}

export function Tooltip({ term, children }: TooltipProps) {
  return (
    <span className="relative group cursor-help underline decoration-dotted decoration-gray-400">
      {children}
      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-800 text-white text-xs rounded-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-50 pointer-events-none shadow-lg">
        {DEFINITIONS[term] || term}
      </span>
    </span>
  );
}
