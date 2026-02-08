// Database types matching Supabase schema

export type MarketRegimeType = 'normal' | 'adjustment' | 'crisis';
export type RiskToleranceType = 'conservative' | 'balanced' | 'aggressive';
export type PickStatusType = 'generated' | 'published';
export type PerformanceStatusType = 'win' | 'loss' | 'flat' | 'pending';
export type AgentNameType = 'trend' | 'momentum' | 'value' | 'sentiment';
export type StrategyModeType = 'conservative' | 'aggressive' | 'jp_conservative' | 'jp_aggressive';

export interface DailyPick {
  id: string;
  batch_date: string;
  symbols: string[];
  pick_count: number;
  market_regime: MarketRegimeType;
  strategy_mode: StrategyModeType;
  status: PickStatusType;
  created_at: string;
}

export interface StockScore {
  id: string;
  batch_date: string;
  symbol: string;
  strategy_mode: StrategyModeType;

  // V1 scores
  trend_score: number;
  momentum_score: number;
  value_score: number;
  sentiment_score: number;

  // V2 scores
  momentum_12_1_score: number | null;
  breakout_score: number | null;
  catalyst_score: number | null;
  risk_adjusted_score: number | null;

  composite_score: number;
  percentile_rank: number;
  reasoning: string;
  price_at_time: number;
  market_regime_at_time: MarketRegimeType;
  created_at: string;

  // Return tracking (filled by daily_review)
  return_1d: number | null;
  return_5d: number | null;
  price_1d: number | null;
  price_5d: number | null;
  was_picked: boolean;
  reviewed_at: string | null;
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

// AILesson is deprecated (replaced by PerformanceStats)

// Portfolio-level AI judgment types
export type AllocationHint = 'high' | 'normal' | 'low';

export interface StockAllocation {
  symbol: string;
  action: 'buy' | 'skip';
  conviction: number;
  allocation_hint: AllocationHint;
  reasoning: string;
}

// Performance stats (replaces AI Lessons)
export interface PerformanceStats {
  buy_count: number;
  buy_win_count: number;
  buy_win_rate: number;
  buy_avg_return: number;
  avoid_count: number;
  avoid_correct_count: number;
  avoid_accuracy: number;
}

// Factor weights from scoring_config
export interface FactorWeights {
  [key: string]: number;
}

// Extended portfolio summary with risk metrics
export interface PortfolioSummaryWithRisk {
  totalValue: number;
  cashBalance: number;
  positionsValue: number;
  openPositions: number;
  cumulativePnlPct: number;
  alpha: number;
  maxDrawdown: number | null;
  sharpeRatio: number | null;
  winRate: number | null;
}

// LLM Judgment types (Layer 2)
export type JudgmentDecision = 'buy' | 'hold' | 'avoid';
export type FactorType = 'fundamental' | 'technical' | 'sentiment' | 'macro' | 'catalyst';
export type FactorImpact = 'positive' | 'negative' | 'neutral';

export interface KeyFactor {
  factor_type: FactorType;
  description: string;
  source: string;
  impact: FactorImpact;
  weight: number;
  verifiable: boolean;
  raw_data?: Record<string, unknown>;
}

export interface ReasoningTrace {
  steps: string[];
  top_factors: string[];
  decision_point: string;
  uncertainties: string[];
  confidence_explanation: string;
}

export interface JudgmentRecord {
  id: string;
  symbol: string;
  batch_date: string;
  strategy_mode: StrategyModeType;
  decision: JudgmentDecision;
  confidence: number;
  score: number;
  reasoning: ReasoningTrace;
  key_factors: KeyFactor[];
  identified_risks: string[];
  market_regime: MarketRegimeType;
  input_summary: string | null;
  model_version: string;
  prompt_version: string;
  raw_llm_response: string | null;
  judged_at: string;
  created_at: string;
}

export interface JudgmentOutcome {
  id: string;
  judgment_id: string;
  outcome_date: string;
  actual_return_1d: number | null;
  actual_return_5d: number | null;
  actual_return_10d: number | null;
  outcome_aligned: boolean | null;
  key_factors_validated: Record<string, boolean> | null;
  missed_factors: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface ReflectionRecord {
  id: string;
  reflection_date: string;
  strategy_mode: StrategyModeType;
  reflection_type: 'weekly' | 'monthly' | 'post_trade';
  period_start: string;
  period_end: string;
  total_judgments: number;
  correct_judgments: number;
  accuracy_rate: number;
  patterns_identified: {
    successful_patterns: string[];
    failure_patterns: string[];
    factor_reliability: Record<string, number>;
    regime_performance: Record<string, number>;
  } | null;
  improvement_suggestions: string[] | null;
  model_version: string;
  raw_llm_response: string | null;
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

// Batch execution status types
export type BatchType =
  | 'morning_scoring'
  | 'evening_review'
  | 'weekly_research'
  | 'llm_judgment'
  | 'reflection';

export type ExecutionStatus = 'running' | 'success' | 'partial_success' | 'failed';

export interface BatchExecutionLog {
  id: string;
  batch_date: string;
  batch_type: BatchType;
  status: ExecutionStatus;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  total_items: number;
  successful_items: number;
  failed_items: number;
  error_message: string | null;
  error_details: { errors: Array<{ error: string; item_id?: string }> } | null;
  model_used: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface SystemStatus {
  morningScoring: BatchExecutionLog | null;
  llmJudgment: BatchExecutionLog | null;
  eveningReview: BatchExecutionLog | null;
  weeklyResearch: BatchExecutionLog | null;
}

// Meta-Monitor types
export interface MetaIntervention {
  id: number;
  strategy_mode: string;
  intervention_date: string;
  trigger_type: string;
  diagnosis: Record<string, unknown>;
  actions_taken: Array<Record<string, unknown>>;
  pre_metrics: Record<string, number>;
  post_metrics: Record<string, number> | null;
  effectiveness_score: number | null;
  rolled_back: boolean;
  cooldown_until: string | null;
  created_at: string;
}

export interface PromptOverride {
  id: number;
  strategy_mode: string;
  override_text: string;
  reason: string;
  active: boolean;
  expires_at: string;
  created_at: string;
}

export interface JudgmentOutcomeStats {
  strategy_mode: string;
  decision: string;
  total: number;
  correct: number;
  accuracy_pct: number;
  avg_return_1d: number | null;
  avg_return_5d: number | null;
}

export interface OutcomeTrend {
  batch_date: string;
  strategy_mode: string;
  total: number;
  aligned: number;
  accuracy: number;
  avg_return: number;
}

export interface RollingMetrics {
  strategy_mode: string;
  metric_date: string;
  win_rate_7d: number | null;
  win_rate_30d: number | null;
  avg_return_7d: number | null;
  avg_return_30d: number | null;
  missed_rate_7d: number | null;
  total_judgments_7d: number | null;
  total_judgments_30d: number | null;
}

export interface ConfidenceCalibrationBucket {
  bucket: string;
  bucketMin: number;
  bucketMax: number;
  total: number;
  correct: number;
  accuracy: number;
  avgReturn: number;
}

export interface ParameterChangeRecord {
  id: number;
  strategy_mode: string;
  param_name: string;
  old_value: number | null;
  new_value: number;
  changed_by: string;
  reason: string | null;
  intervention_id: number | null;
  created_at: string;
}

export interface ExitReasonCount {
  exit_reason: string;
  count: number;
}
