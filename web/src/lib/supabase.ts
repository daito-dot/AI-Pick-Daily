import { createClient, SupabaseClient } from '@supabase/supabase-js';
import type {
  DailyPick,
  StockScore,
  MarketRegimeHistory,
  AILesson,
  PerformanceLog,
  StrategyModeType,
  JudgmentRecord,
  ReflectionRecord,
} from '@/types';

// Lazy initialization to handle build-time when env vars may not be set
let supabaseInstance: SupabaseClient | null = null;

function getSupabase(): SupabaseClient {
  if (supabaseInstance) {
    return supabaseInstance;
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    throw new Error('Supabase environment variables are not configured');
  }

  supabaseInstance = createClient(supabaseUrl, supabaseAnonKey);
  return supabaseInstance;
}

/**
 * Fetch today's picks with scores for both strategies
 */
export async function getTodayPicks(): Promise<{
  conservativePicks: DailyPick | null;
  aggressivePicks: DailyPick | null;
  conservativeScores: StockScore[];
  aggressiveScores: StockScore[];
  regime: MarketRegimeHistory | null;
  debugError?: string;
}> {
  try {
    const supabase = getSupabase();
    const today = new Date().toISOString().split('T')[0];

    // Get daily picks for both strategies
    const { data: allPicks, error: picksError } = await supabase
      .from('daily_picks')
      .select('*')
      .eq('batch_date', today);

    if (picksError) {
      console.error('[getTodayPicks] daily_picks error:', picksError);
      return {
        conservativePicks: null,
        aggressivePicks: null,
        conservativeScores: [],
        aggressiveScores: [],
        regime: null,
        debugError: `daily_picks: ${picksError.message}`,
      };
    }

    const conservativePicks = allPicks?.find(p => p.strategy_mode === 'conservative') || null;
    const aggressivePicks = allPicks?.find(p => p.strategy_mode === 'aggressive') || null;

    // Get stock scores for today (both strategies)
    const { data: allScores, error: scoresError } = await supabase
      .from('stock_scores')
      .select('*')
      .eq('batch_date', today)
      .order('composite_score', { ascending: false });

    if (scoresError) {
      console.error('[getTodayPicks] stock_scores error:', scoresError);
      return {
        conservativePicks,
        aggressivePicks,
        conservativeScores: [],
        aggressiveScores: [],
        regime: null,
        debugError: `stock_scores: ${scoresError.message}`,
      };
    }

    const conservativeScores = allScores?.filter(s => s.strategy_mode === 'conservative') || [];
    const aggressiveScores = allScores?.filter(s => s.strategy_mode === 'aggressive') || [];

    // Get market regime
    const { data: regime, error: regimeError } = await supabase
      .from('market_regime_history')
      .select('*')
      .eq('check_date', today)
      .single();

    // Note: single() returns error if no rows found, so we don't treat it as fatal
    if (regimeError && regimeError.code !== 'PGRST116') {
      console.error('[getTodayPicks] market_regime error:', regimeError);
    }

    return {
      conservativePicks,
      aggressivePicks,
      conservativeScores,
      aggressiveScores,
      regime: regime || null,
      debugError: undefined,
    };
  } catch (error) {
    console.error('getTodayPicks error:', error);
    return {
      conservativePicks: null,
      aggressivePicks: null,
      conservativeScores: [],
      aggressiveScores: [],
      regime: null,
      debugError: `Exception: ${error instanceof Error ? error.message : String(error)}`,
    };
  }
}

/**
 * Fetch today's picks for a specific strategy (legacy support)
 */
export async function getTodayPicksByStrategy(strategyMode: StrategyModeType): Promise<{
  picks: DailyPick | null;
  scores: StockScore[];
  regime: MarketRegimeHistory | null;
}> {
  try {
    const supabase = getSupabase();
    const today = new Date().toISOString().split('T')[0];

    const { data: picks } = await supabase
      .from('daily_picks')
      .select('*')
      .eq('batch_date', today)
      .eq('strategy_mode', strategyMode)
      .single();

    const { data: scores } = await supabase
      .from('stock_scores')
      .select('*')
      .eq('batch_date', today)
      .eq('strategy_mode', strategyMode)
      .order('composite_score', { ascending: false });

    const { data: regime } = await supabase
      .from('market_regime_history')
      .select('*')
      .eq('check_date', today)
      .single();

    return {
      picks: picks || null,
      scores: scores || [],
      regime: regime || null,
    };
  } catch (error) {
    console.error('getTodayPicksByStrategy error:', error);
    return { picks: null, scores: [], regime: null };
  }
}

/**
 * Fetch recent picks (last 7 days)
 */
export async function getRecentPicks(days: number = 7): Promise<DailyPick[]> {
  try {
    const supabase = getSupabase();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);

    const { data } = await supabase
      .from('daily_picks')
      .select('*')
      .gte('batch_date', startDate.toISOString().split('T')[0])
      .order('batch_date', { ascending: false });

    return data || [];
  } catch (error) {
    console.error('getRecentPicks error:', error);
    return [];
  }
}

/**
 * Fetch stock scores for a specific date
 */
export async function getScoresForDate(date: string): Promise<StockScore[]> {
  try {
    const supabase = getSupabase();
    const { data } = await supabase
      .from('stock_scores')
      .select('*')
      .eq('batch_date', date)
      .order('composite_score', { ascending: false });

    return data || [];
  } catch (error) {
    console.error('getScoresForDate error:', error);
    return [];
  }
}

/**
 * Fetch performance history
 */
export async function getPerformanceHistory(days: number = 30): Promise<PerformanceLog[]> {
  try {
    const supabase = getSupabase();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);

    const { data } = await supabase
      .from('performance_log')
      .select('*')
      .gte('pick_date', startDate.toISOString().split('T')[0])
      .order('pick_date', { ascending: false });

    return data || [];
  } catch (error) {
    console.error('getPerformanceHistory error:', error);
    return [];
  }
}

/**
 * Fetch AI lessons
 */
export async function getAILessons(limit: number = 10): Promise<AILesson[]> {
  try {
    const supabase = getSupabase();
    const { data } = await supabase
      .from('ai_lessons')
      .select('*')
      .order('lesson_date', { ascending: false })
      .limit(limit);

    return data || [];
  } catch (error) {
    console.error('getAILessons error:', error);
    return [];
  }
}

/**
 * Fetch market regime history
 */
export async function getMarketRegimeHistory(days: number = 30): Promise<MarketRegimeHistory[]> {
  try {
    const supabase = getSupabase();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);

    const { data } = await supabase
      .from('market_regime_history')
      .select('*')
      .gte('check_date', startDate.toISOString().split('T')[0])
      .order('check_date', { ascending: false });

    return data || [];
  } catch (error) {
    console.error('getMarketRegimeHistory error:', error);
    return [];
  }
}

/**
 * Fetch missed opportunities (stocks not picked but performed well)
 */
export async function getMissedOpportunities(days: number = 30, minReturn: number = 3.0): Promise<StockScore[]> {
  try {
    const supabase = getSupabase();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);

    const { data } = await supabase
      .from('stock_scores')
      .select('*')
      .gte('batch_date', startDate.toISOString().split('T')[0])
      .eq('was_picked', false)
      .gte('return_5d', minReturn)
      .order('return_5d', { ascending: false })
      .limit(20);

    return data || [];
  } catch (error) {
    console.error('getMissedOpportunities error:', error);
    return [];
  }
}

/**
 * Get performance comparison stats (picked vs not picked)
 */
export async function getPerformanceComparison(days: number = 30): Promise<{
  pickedCount: number;
  pickedAvgReturn: number;
  notPickedCount: number;
  notPickedAvgReturn: number;
  missedOpportunities: number;
}> {
  try {
    const supabase = getSupabase();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);

    const { data } = await supabase
      .from('stock_scores')
      .select('was_picked, return_5d')
      .gte('batch_date', startDate.toISOString().split('T')[0])
      .not('return_5d', 'is', null);

    if (!data || data.length === 0) {
      return {
        pickedCount: 0,
        pickedAvgReturn: 0,
        notPickedCount: 0,
        notPickedAvgReturn: 0,
        missedOpportunities: 0,
      };
    }

    const picked = data.filter(d => d.was_picked);
    const notPicked = data.filter(d => !d.was_picked);

    const avgReturn = (arr: typeof data) => {
      if (arr.length === 0) return 0;
      const sum = arr.reduce((acc, d) => acc + (d.return_5d || 0), 0);
      return sum / arr.length;
    };

    return {
      pickedCount: picked.length,
      pickedAvgReturn: avgReturn(picked),
      notPickedCount: notPicked.length,
      notPickedAvgReturn: avgReturn(notPicked),
      missedOpportunities: notPicked.filter(d => (d.return_5d || 0) >= 3).length,
    };
  } catch (error) {
    console.error('getPerformanceComparison error:', error);
    return {
      pickedCount: 0,
      pickedAvgReturn: 0,
      notPickedCount: 0,
      notPickedAvgReturn: 0,
      missedOpportunities: 0,
    };
  }
}

/**
 * Fetch portfolio snapshots for equity curve
 */
export async function getPortfolioSnapshots(strategyMode: string, days: number = 30): Promise<any[]> {
  try {
    const supabase = getSupabase();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);

    const { data } = await supabase
      .from('portfolio_daily_snapshot')
      .select('*')
      .eq('strategy_mode', strategyMode)
      .gte('snapshot_date', startDate.toISOString().split('T')[0])
      .order('snapshot_date', { ascending: true });

    return data || [];
  } catch (error) {
    console.error('getPortfolioSnapshots error:', error);
    return [];
  }
}

/**
 * Fetch open positions
 */
export async function getOpenPositions(strategyMode?: string): Promise<any[]> {
  try {
    const supabase = getSupabase();
    let query = supabase
      .from('virtual_portfolio')
      .select('*')
      .eq('status', 'open')
      .order('entry_date', { ascending: false });

    if (strategyMode) {
      query = query.eq('strategy_mode', strategyMode);
    }

    const { data } = await query;
    return data || [];
  } catch (error) {
    console.error('getOpenPositions error:', error);
    return [];
  }
}

/**
 * Fetch trade history
 */
export async function getTradeHistory(days: number = 30, strategyMode?: string): Promise<any[]> {
  try {
    const supabase = getSupabase();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);

    let query = supabase
      .from('trade_history')
      .select('*')
      .gte('exit_date', startDate.toISOString().split('T')[0])
      .order('exit_date', { ascending: false });

    if (strategyMode) {
      query = query.eq('strategy_mode', strategyMode);
    }

    const { data } = await query;
    return data || [];
  } catch (error) {
    console.error('getTradeHistory error:', error);
    return [];
  }
}

/**
 * Fetch scoring config (dynamic thresholds)
 */
export async function getScoringConfigs(): Promise<any[]> {
  try {
    const supabase = getSupabase();
    const { data } = await supabase
      .from('scoring_config')
      .select('*');

    return data || [];
  } catch (error) {
    console.error('getScoringConfigs error:', error);
    return [];
  }
}

/**
 * Fetch threshold history
 */
export async function getThresholdHistory(days: number = 30): Promise<any[]> {
  try {
    const supabase = getSupabase();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);

    const { data } = await supabase
      .from('threshold_history')
      .select('*')
      .gte('adjustment_date', startDate.toISOString().split('T')[0])
      .order('adjustment_date', { ascending: false });

    return data || [];
  } catch (error) {
    console.error('getThresholdHistory error:', error);
    return [];
  }
}

/**
 * Get portfolio summary stats
 */
export async function getPortfolioSummary(strategyMode: string): Promise<{
  totalValue: number;
  cashBalance: number;
  positionsValue: number;
  openPositions: number;
  cumulativePnlPct: number;
  alpha: number;
}> {
  try {
    const supabase = getSupabase();
    const { data } = await supabase
      .from('portfolio_daily_snapshot')
      .select('*')
      .eq('strategy_mode', strategyMode)
      .order('snapshot_date', { ascending: false })
      .limit(1)
      .single();

    if (!data) {
      return {
        totalValue: 100000,
        cashBalance: 100000,
        positionsValue: 0,
        openPositions: 0,
        cumulativePnlPct: 0,
        alpha: 0,
      };
    }

    return {
      totalValue: data.total_value || 100000,
      cashBalance: data.cash_balance || 100000,
      positionsValue: data.positions_value || 0,
      openPositions: data.open_positions || 0,
      cumulativePnlPct: data.cumulative_pnl_pct || 0,
      alpha: data.alpha || 0,
    };
  } catch (error) {
    console.error('getPortfolioSummary error:', error);
    return {
      totalValue: 100000,
      cashBalance: 100000,
      positionsValue: 0,
      openPositions: 0,
      cumulativePnlPct: 0,
      alpha: 0,
    };
  }
}

// ============================================
// LLM Judgment Layer (Layer 2) Functions
// ============================================

/**
 * Fetch today's LLM judgments for all stocks
 */
export async function getTodayJudgments(): Promise<JudgmentRecord[]> {
  try {
    const supabase = getSupabase();
    const today = new Date().toISOString().split('T')[0];

    const { data, error } = await supabase
      .from('judgment_records')
      .select('*')
      .eq('batch_date', today)
      .order('confidence', { ascending: false });

    if (error) {
      console.error('[getTodayJudgments] error:', error);
      return [];
    }

    return data || [];
  } catch (error) {
    console.error('getTodayJudgments error:', error);
    return [];
  }
}

/**
 * Fetch LLM judgments for a specific date
 */
export async function getJudgmentsForDate(date: string): Promise<JudgmentRecord[]> {
  try {
    const supabase = getSupabase();

    const { data, error } = await supabase
      .from('judgment_records')
      .select('*')
      .eq('batch_date', date)
      .order('confidence', { ascending: false });

    if (error) {
      console.error('[getJudgmentsForDate] error:', error);
      return [];
    }

    return data || [];
  } catch (error) {
    console.error('getJudgmentsForDate error:', error);
    return [];
  }
}

/**
 * Fetch judgment for a specific symbol and date
 */
export async function getJudgmentBySymbol(
  symbol: string,
  date?: string,
  strategyMode?: StrategyModeType
): Promise<JudgmentRecord | null> {
  try {
    const supabase = getSupabase();
    const targetDate = date || new Date().toISOString().split('T')[0];

    let query = supabase
      .from('judgment_records')
      .select('*')
      .eq('symbol', symbol)
      .eq('batch_date', targetDate);

    if (strategyMode) {
      query = query.eq('strategy_mode', strategyMode);
    }

    const { data, error } = await query.limit(1).single();

    if (error && error.code !== 'PGRST116') {
      console.error('[getJudgmentBySymbol] error:', error);
      return null;
    }

    return data || null;
  } catch (error) {
    console.error('getJudgmentBySymbol error:', error);
    return null;
  }
}

/**
 * Fetch recent judgments with their outcomes (for analysis)
 */
export async function getJudgmentHistory(days: number = 30): Promise<JudgmentRecord[]> {
  try {
    const supabase = getSupabase();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);

    const { data, error } = await supabase
      .from('judgment_records')
      .select('*')
      .gte('batch_date', startDate.toISOString().split('T')[0])
      .order('batch_date', { ascending: false })
      .order('confidence', { ascending: false });

    if (error) {
      console.error('[getJudgmentHistory] error:', error);
      return [];
    }

    return data || [];
  } catch (error) {
    console.error('getJudgmentHistory error:', error);
    return [];
  }
}

/**
 * Fetch judgment stats (accuracy, confidence distribution)
 */
export async function getJudgmentStats(days: number = 30): Promise<{
  totalJudgments: number;
  buyDecisions: number;
  holdDecisions: number;
  avoidDecisions: number;
  avgConfidence: number;
  highConfidenceCount: number;
}> {
  try {
    const supabase = getSupabase();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);

    const { data, error } = await supabase
      .from('judgment_records')
      .select('decision, confidence')
      .gte('batch_date', startDate.toISOString().split('T')[0]);

    if (error || !data) {
      return {
        totalJudgments: 0,
        buyDecisions: 0,
        holdDecisions: 0,
        avoidDecisions: 0,
        avgConfidence: 0,
        highConfidenceCount: 0,
      };
    }

    const buyCount = data.filter(d => d.decision === 'buy').length;
    const holdCount = data.filter(d => d.decision === 'hold').length;
    const avoidCount = data.filter(d => d.decision === 'avoid').length;
    const avgConf = data.length > 0
      ? data.reduce((sum, d) => sum + (d.confidence || 0), 0) / data.length
      : 0;
    const highConf = data.filter(d => d.confidence >= 0.7).length;

    return {
      totalJudgments: data.length,
      buyDecisions: buyCount,
      holdDecisions: holdCount,
      avoidDecisions: avoidCount,
      avgConfidence: avgConf,
      highConfidenceCount: highConf,
    };
  } catch (error) {
    console.error('getJudgmentStats error:', error);
    return {
      totalJudgments: 0,
      buyDecisions: 0,
      holdDecisions: 0,
      avoidDecisions: 0,
      avgConfidence: 0,
      highConfidenceCount: 0,
    };
  }
}

// ============================================
// Reflection Layer (Layer 3) Functions
// ============================================

/**
 * Fetch recent reflections
 */
export async function getReflections(limit: number = 5): Promise<ReflectionRecord[]> {
  try {
    const supabase = getSupabase();

    const { data, error } = await supabase
      .from('reflection_records')
      .select('*')
      .order('reflection_date', { ascending: false })
      .limit(limit);

    if (error) {
      console.error('[getReflections] error:', error);
      return [];
    }

    return data || [];
  } catch (error) {
    console.error('getReflections error:', error);
    return [];
  }
}

/**
 * Fetch latest reflection for a strategy
 */
export async function getLatestReflection(
  strategyMode: StrategyModeType
): Promise<ReflectionRecord | null> {
  try {
    const supabase = getSupabase();

    const { data, error } = await supabase
      .from('reflection_records')
      .select('*')
      .eq('strategy_mode', strategyMode)
      .order('reflection_date', { ascending: false })
      .limit(1)
      .single();

    if (error && error.code !== 'PGRST116') {
      console.error('[getLatestReflection] error:', error);
      return null;
    }

    return data || null;
  } catch (error) {
    console.error('getLatestReflection error:', error);
    return null;
  }
}

// ============================================
// System Status (Batch Execution Logs)
// ============================================

import type { BatchExecutionLog, SystemStatus, BatchType } from '@/types';

/**
 * Fetch today's batch execution status
 */
export async function getTodayBatchStatus(): Promise<SystemStatus> {
  try {
    const supabase = getSupabase();
    const today = new Date().toISOString().split('T')[0];

    const { data, error } = await supabase
      .from('batch_execution_logs')
      .select('*')
      .eq('batch_date', today)
      .order('started_at', { ascending: false });

    if (error) {
      console.error('[getTodayBatchStatus] error:', error);
      return {
        morningScoring: null,
        llmJudgment: null,
        eveningReview: null,
        weeklyResearch: null,
      };
    }

    // Get latest of each type
    const logs = data || [];
    const findLatest = (type: BatchType): BatchExecutionLog | null => {
      return logs.find(log => log.batch_type === type) || null;
    };

    return {
      morningScoring: findLatest('morning_scoring'),
      llmJudgment: findLatest('llm_judgment'),
      eveningReview: findLatest('evening_review'),
      weeklyResearch: findLatest('weekly_research'),
    };
  } catch (error) {
    console.error('getTodayBatchStatus error:', error);
    return {
      morningScoring: null,
      llmJudgment: null,
      eveningReview: null,
      weeklyResearch: null,
    };
  }
}

/**
 * Fetch recent batch execution failures
 */
export async function getRecentBatchFailures(days: number = 7): Promise<BatchExecutionLog[]> {
  try {
    const supabase = getSupabase();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);

    const { data, error } = await supabase
      .from('batch_execution_logs')
      .select('*')
      .in('status', ['failed', 'partial_success'])
      .gte('batch_date', startDate.toISOString().split('T')[0])
      .order('started_at', { ascending: false })
      .limit(20);

    if (error) {
      console.error('[getRecentBatchFailures] error:', error);
      return [];
    }

    return data || [];
  } catch (error) {
    console.error('getRecentBatchFailures error:', error);
    return [];
  }
}
