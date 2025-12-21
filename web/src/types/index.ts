// Database types matching Supabase schema

export type MarketRegimeType = 'normal' | 'adjustment' | 'crisis';
export type RiskToleranceType = 'conservative' | 'balanced' | 'aggressive';
export type PickStatusType = 'generated' | 'published';
export type PerformanceStatusType = 'win' | 'loss' | 'flat' | 'pending';
export type AgentNameType = 'trend' | 'momentum' | 'value' | 'sentiment';

export interface DailyPick {
  id: string;
  batch_date: string;
  symbols: string[];
  pick_count: number;
  market_regime: MarketRegimeType;
  status: PickStatusType;
  created_at: string;
}

export interface StockScore {
  id: string;
  batch_date: string;
  symbol: string;
  trend_score: number;
  momentum_score: number;
  value_score: number;
  sentiment_score: number;
  composite_score: number;
  percentile_rank: number;
  reasoning: string;
  price_at_time: number;
  market_regime_at_time: MarketRegimeType;
  created_at: string;
}

export interface MarketRegimeHistory {
  id: string;
  check_date: string;
  vix_level: number;
  market_regime: MarketRegimeType;
  sp500_sma20_deviation_pct: number;
  volatility_cluster_flag: boolean;
  notes: string;
  created_at: string;
}

export interface PerformanceLog {
  id: string;
  pick_date: string;
  symbol: string;
  recommendation_open_price: number;
  recommendation_score: number;
  recommendation_percentile: number;
  market_regime_at_time: MarketRegimeType;
  return_pct_1d: number | null;
  status_1d: PerformanceStatusType;
  return_pct_5d: number | null;
  status_5d: PerformanceStatusType;
  created_at: string;
}

export interface AILesson {
  id: string;
  lesson_date: string;
  lesson_text: string;
  biggest_miss_symbols: string[];
  miss_analysis: string;
  created_at: string;
}

// UI display types
export interface StockCardData {
  symbol: string;
  compositeScore: number;
  percentileRank: number;
  trendScore: number;
  momentumScore: number;
  valueScore: number;
  sentimentScore: number;
  reasoning: string;
  priceAtTime: number;
}

export interface DashboardData {
  todayPicks: StockCardData[];
  marketRegime: MarketRegimeType;
  regimeNotes: string;
  vixLevel: number;
  lastUpdated: string;
}
