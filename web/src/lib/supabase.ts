import { createClient, SupabaseClient } from '@supabase/supabase-js';
import type {
  DailyPick,
  StockScore,
  MarketRegimeHistory,
  PerformanceLog,
  StrategyModeType,
  JudgmentRecord,
  ReflectionRecord,
  PerformanceStats,
  FactorWeights,
  PortfolioSummaryWithRisk,
  JudgmentOutcomeStats,
  OutcomeTrend,
  MetaIntervention,
  PromptOverride,
  RollingMetrics,
  ConfidenceCalibrationBucket,
  ExitReasonCount,
  ParameterChangeRecord,
  ModelPerformanceStats,
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

// Market type for US vs Japan stocks
export type MarketType = 'us' | 'jp';

// Strategy mode mapping by market
const STRATEGY_MODES = {
  us: { conservative: 'conservative', aggressive: 'aggressive' },
  jp: { conservative: 'jp_conservative', aggressive: 'jp_aggressive' },
} as const;

/**
 * Get today's date in UTC as YYYY-MM-DD string.
 * This ensures consistency with backend batch jobs that run in UTC.
 */
function getUTCToday(): string {
  const now = new Date();
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, '0')}-${String(now.getUTCDate()).padStart(2, '0')}`;
}

/**
 * Get a date N days ago in UTC as YYYY-MM-DD string.
 * Uses UTC-based arithmetic to avoid timezone issues.
 */
function getUTCDateDaysAgo(days: number): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - days);
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`;
}

/**
 * Fetch today's picks with scores for both strategies
 */
export async function getTodayPicks(marketType: MarketType = 'us'): Promise<{
  conservativePicks: DailyPick | null;
  aggressivePicks: DailyPick | null;
  conservativeScores: StockScore[];
  aggressiveScores: StockScore[];
  regime: MarketRegimeHistory | null;
  hasError?: boolean;
}> {
  try {
    const supabase = getSupabase();
    const today = getUTCToday();
    const modes = STRATEGY_MODES[marketType];

    // First try today's date, then fallback to most recent
    let targetDate = today;

    // Check if today's picks exist
    const { data: todayCheck } = await supabase
      .from('daily_picks')
      .select('batch_date')
      .eq('batch_date', today)
      .in('strategy_mode', [modes.conservative, modes.aggressive])
      .limit(1);

    // If no data for today, get the most recent date
    if (!todayCheck || todayCheck.length === 0) {
      const { data: recentDate } = await supabase
        .from('daily_picks')
        .select('batch_date')
        .in('strategy_mode', [modes.conservative, modes.aggressive])
        .order('batch_date', { ascending: false })
        .limit(1);

      if (recentDate && recentDate.length > 0) {
        targetDate = recentDate[0].batch_date;
      }
    }

    // Get daily picks for both strategies
    const { data: allPicks, error: picksError } = await supabase
      .from('daily_picks')
      .select('*')
      .eq('batch_date', targetDate)
      .in('strategy_mode', [modes.conservative, modes.aggressive]);

    if (picksError) {
      console.error('[getTodayPicks] daily_picks error:', picksError);
      return {
        conservativePicks: null,
        aggressivePicks: null,
        conservativeScores: [],
        aggressiveScores: [],
        regime: null,
        hasError: true,
      };
    }

    const conservativePicks = allPicks?.find(p => p.strategy_mode === modes.conservative) || null;
    const aggressivePicks = allPicks?.find(p => p.strategy_mode === modes.aggressive) || null;

    // Get stock scores for target date (both strategies)
    const { data: allScores, error: scoresError } = await supabase
      .from('stock_scores')
      .select('*')
      .eq('batch_date', targetDate)
      .in('strategy_mode', [modes.conservative, modes.aggressive])
      .order('composite_score', { ascending: false });

    if (scoresError) {
      console.error('[getTodayPicks] stock_scores error:', scoresError);
      return {
        conservativePicks,
        aggressivePicks,
        conservativeScores: [],
        aggressiveScores: [],
        regime: null,
        hasError: true,
      };
    }

    const conservativeScores = allScores?.filter(s => s.strategy_mode === modes.conservative) || [];
    const aggressiveScores = allScores?.filter(s => s.strategy_mode === modes.aggressive) || [];

    // Get market regime
    const { data: regime, error: regimeError } = await supabase
      .from('market_regime_history')
      .select('*')
      .eq('check_date', targetDate)
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
      hasError: false,
    };
  } catch (error) {
    console.error('getTodayPicks error:', error);
    return {
      conservativePicks: null,
      aggressivePicks: null,
      conservativeScores: [],
      aggressiveScores: [],
      regime: null,
      hasError: true,
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
    const today = getUTCToday();

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

    const { data } = await supabase
      .from('daily_picks')
      .select('*')
      .gte('batch_date', getUTCDateDaysAgo(days))
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
 * Fetch performance history from stock_scores where was_picked = true
 */
export async function getPerformanceHistory(days: number = 30, marketType: MarketType = 'us'): Promise<PerformanceLog[]> {
  try {
    const supabase = getSupabase();
    const modes = STRATEGY_MODES[marketType];

    const { data, error } = await supabase
      .from('stock_scores')
      .select('*')
      .eq('was_picked', true)
      .in('strategy_mode', [modes.conservative, modes.aggressive])
      .gte('batch_date', getUTCDateDaysAgo(days))
      .not('return_5d', 'is', null)  // Filter out pending (consistent with getPerformanceComparison)
      .order('batch_date', { ascending: false });

    if (error) {
      console.error('getPerformanceHistory query error:', error);
      return [];
    }

    // Map stock_scores to PerformanceLog format
    return (data || []).map(score => {
      const return1d = score.return_1d;
      const return5d = score.return_5d;

      // Determine status based on return
      const getStatus = (ret: number | null): 'win' | 'loss' | 'flat' | 'pending' => {
        if (ret === null || ret === undefined) return 'pending';
        if (ret >= 1) return 'win';
        if (ret <= -1) return 'loss';
        return 'flat';
      };

      return {
        id: score.id,
        pick_date: score.batch_date,
        symbol: score.symbol,
        recommendation_open_price: score.price_at_time || 0,
        recommendation_score: score.composite_score || 0,
        recommendation_percentile: 0, // Not available in stock_scores
        market_regime_at_time: score.market_regime_at_time || 'normal',
        return_pct_1d: return1d,
        status_1d: getStatus(return1d),
        return_pct_5d: return5d,
        status_5d: getStatus(return5d),
        created_at: score.created_at || score.batch_date,
      };
    });
  } catch (error) {
    console.error('getPerformanceHistory error:', error);
    return [];
  }
}

/**
 * Fetch performance stats (replaces AI Lessons).
 * Mirrors build_performance_stats() from Python backend.
 */
export async function getPerformanceStats(marketType: MarketType = 'us'): Promise<PerformanceStats | null> {
  try {
    const supabase = getSupabase();
    const modes = STRATEGY_MODES[marketType];

    const { data, error } = await supabase
      .from('judgment_outcomes')
      .select('outcome_aligned, actual_return_5d, judgment_records!inner(decision, strategy_mode, is_primary)')
      .in('judgment_records.strategy_mode', [modes.conservative, modes.aggressive])
      .eq('judgment_records.is_primary', true)
      .gte('outcome_date', getUTCDateDaysAgo(30));

    if (error || !data || data.length < 5) {
      return null;
    }

    const buyOutcomes = data.filter((d: any) => d.judgment_records?.decision === 'buy');
    const avoidOutcomes = data.filter((d: any) =>
      d.judgment_records?.decision === 'avoid' || d.judgment_records?.decision === 'hold'
    );

    const buyWins = buyOutcomes.filter((d: any) => d.outcome_aligned === true);
    const avoidCorrect = avoidOutcomes.filter((d: any) => d.outcome_aligned === true);

    const buyReturns = buyOutcomes
      .map((d: any) => d.actual_return_5d)
      .filter((r: any) => r !== null) as number[];
    const buyAvgReturn = buyReturns.length > 0
      ? buyReturns.reduce((a: number, b: number) => a + b, 0) / buyReturns.length
      : 0;

    return {
      buy_count: buyOutcomes.length,
      buy_win_count: buyWins.length,
      buy_win_rate: buyOutcomes.length > 0 ? (buyWins.length / buyOutcomes.length) * 100 : 0,
      buy_avg_return: buyAvgReturn,
      avoid_count: avoidOutcomes.length,
      avoid_correct_count: avoidCorrect.length,
      avoid_accuracy: avoidOutcomes.length > 0 ? (avoidCorrect.length / avoidOutcomes.length) * 100 : 0,
    };
  } catch (error) {
    console.error('getPerformanceStats error:', error);
    return null;
  }
}

/**
 * Fetch factor weights from scoring_config
 */
export async function getFactorWeights(marketType: MarketType = 'us'): Promise<{
  v1: FactorWeights | null;
  v2: FactorWeights | null;
}> {
  try {
    const supabase = getSupabase();
    const modes = STRATEGY_MODES[marketType];

    const { data } = await supabase
      .from('scoring_config')
      .select('strategy_mode, factor_weights')
      .in('strategy_mode', [modes.conservative, modes.aggressive]);

    const v1Config = data?.find((d: any) => d.strategy_mode === modes.conservative);
    const v2Config = data?.find((d: any) => d.strategy_mode === modes.aggressive);

    return {
      v1: v1Config?.factor_weights || null,
      v2: v2Config?.factor_weights || null,
    };
  } catch (error) {
    console.error('getFactorWeights error:', error);
    return { v1: null, v2: null };
  }
}

/**
 * Fetch past picks with scores (for Analytics page, replaces getRecentPicks for detailed view)
 */
export async function getPastPicksDetailed(days: number = 30, marketType: MarketType = 'us'): Promise<{
  date: string;
  market: MarketType;
  regime: string;
  v1Picks: string[];
  v2Picks: string[];
  v1TopScores: Array<{ symbol: string; score: number; return_5d: number | null }>;
  v2TopScores: Array<{ symbol: string; score: number; return_5d: number | null }>;
}[]> {
  try {
    const supabase = getSupabase();
    const modes = STRATEGY_MODES[marketType];

    const [{ data: picks }, { data: scores }] = await Promise.all([
      supabase
        .from('daily_picks')
        .select('*')
        .in('strategy_mode', [modes.conservative, modes.aggressive])
        .gte('batch_date', getUTCDateDaysAgo(days))
        .order('batch_date', { ascending: false }),
      supabase
        .from('stock_scores')
        .select('symbol, batch_date, strategy_mode, composite_score, return_5d, was_picked')
        .in('strategy_mode', [modes.conservative, modes.aggressive])
        .gte('batch_date', getUTCDateDaysAgo(days))
        .eq('was_picked', true)
        .order('composite_score', { ascending: false }),
    ]);

    if (!picks) return [];

    const dateMap = new Map<string, any>();

    for (const pick of picks) {
      const key = pick.batch_date;
      if (!dateMap.has(key)) {
        dateMap.set(key, {
          date: pick.batch_date,
          market: marketType,
          regime: pick.market_regime || 'normal',
          v1Picks: [],
          v2Picks: [],
          v1TopScores: [],
          v2TopScores: [],
        });
      }
      const entry = dateMap.get(key)!;
      const isV1 = pick.strategy_mode === modes.conservative;
      if (isV1) {
        entry.v1Picks = pick.symbols || [];
      } else {
        entry.v2Picks = pick.symbols || [];
      }
    }

    if (scores) {
      for (const score of scores) {
        const entry = dateMap.get(score.batch_date);
        if (!entry) continue;
        const isV1 = score.strategy_mode === modes.conservative;
        const scoreEntry = {
          symbol: score.symbol,
          score: score.composite_score,
          return_5d: score.return_5d,
        };
        if (isV1) {
          entry.v1TopScores.push(scoreEntry);
        } else {
          entry.v2TopScores.push(scoreEntry);
        }
      }
    }

    return Array.from(dateMap.values());
  } catch (error) {
    console.error('getPastPicksDetailed error:', error);
    return [];
  }
}

/**
 * Fetch market regime history
 */
export async function getMarketRegimeHistory(days: number = 30): Promise<MarketRegimeHistory[]> {
  try {
    const supabase = getSupabase();

    const { data } = await supabase
      .from('market_regime_history')
      .select('*')
      .gte('check_date', getUTCDateDaysAgo(days))
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
export async function getMissedOpportunities(days: number = 30, minReturn: number = 3.0, marketType: MarketType = 'us'): Promise<StockScore[]> {
  try {
    const supabase = getSupabase();
    const modes = STRATEGY_MODES[marketType];

    const { data } = await supabase
      .from('stock_scores')
      .select('*')
      .in('strategy_mode', [modes.conservative, modes.aggressive])
      .gte('batch_date', getUTCDateDaysAgo(days))
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
export async function getPerformanceComparison(days: number = 30, marketType: MarketType = 'us'): Promise<{
  pickedCount: number;
  pickedAvgReturn: number;
  notPickedCount: number;
  notPickedAvgReturn: number;
  missedOpportunities: number;
}> {
  try {
    const supabase = getSupabase();
    const modes = STRATEGY_MODES[marketType];

    const { data } = await supabase
      .from('stock_scores')
      .select('was_picked, return_5d')
      .in('strategy_mode', [modes.conservative, modes.aggressive])
      .gte('batch_date', getUTCDateDaysAgo(days))
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

    const { data } = await supabase
      .from('portfolio_daily_snapshot')
      .select('*')
      .eq('strategy_mode', strategyMode)
      .gte('snapshot_date', getUTCDateDaysAgo(days))
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

    let query = supabase
      .from('trade_history')
      .select('*')
      .gte('exit_date', getUTCDateDaysAgo(days))
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

    const { data } = await supabase
      .from('threshold_history')
      .select('*')
      .gte('adjustment_date', getUTCDateDaysAgo(days))
      .order('adjustment_date', { ascending: false });

    return data || [];
  } catch (error) {
    console.error('getThresholdHistory error:', error);
    return [];
  }
}

/**
 * Get portfolio summary stats with risk metrics
 */
export async function getPortfolioSummary(strategyMode: string): Promise<PortfolioSummaryWithRisk> {
  const defaults: PortfolioSummaryWithRisk = {
    totalValue: 100000,
    cashBalance: 100000,
    positionsValue: 0,
    openPositions: 0,
    cumulativePnlPct: 0,
    alpha: 0,
    maxDrawdown: null,
    sharpeRatio: null,
    winRate: null,
  };

  try {
    const supabase = getSupabase();
    const { data } = await supabase
      .from('portfolio_daily_snapshot')
      .select('*')
      .eq('strategy_mode', strategyMode)
      .order('snapshot_date', { ascending: false })
      .limit(1)
      .single();

    if (!data) return defaults;

    return {
      totalValue: data.total_value || 100000,
      cashBalance: data.cash_balance || 100000,
      positionsValue: data.positions_value || 0,
      openPositions: data.open_positions || 0,
      cumulativePnlPct: data.cumulative_pnl_pct || 0,
      alpha: data.alpha || 0,
      maxDrawdown: data.max_drawdown ?? null,
      sharpeRatio: data.sharpe_ratio ?? null,
      winRate: data.win_rate ?? null,
    };
  } catch (error) {
    console.error('getPortfolioSummary error:', error);
    return defaults;
  }
}

// ============================================
// LLM Judgment Layer (Layer 2) Functions
// ============================================

/**
 * Fetch today's LLM judgments for all stocks
 */
export async function getTodayJudgments(marketType: MarketType = 'us'): Promise<JudgmentRecord[]> {
  try {
    const supabase = getSupabase();
    const today = getUTCToday();
    const modes = STRATEGY_MODES[marketType];

    // First try today's date, then fallback to most recent
    let targetDate = today;

    // Check if today's judgments exist (primary only)
    const { data: todayCheck } = await supabase
      .from('judgment_records')
      .select('batch_date')
      .eq('batch_date', today)
      .in('strategy_mode', [modes.conservative, modes.aggressive])
      .eq('is_primary', true)
      .limit(1);

    // If no data for today, get the most recent date
    if (!todayCheck || todayCheck.length === 0) {
      const { data: recentDate } = await supabase
        .from('judgment_records')
        .select('batch_date')
        .in('strategy_mode', [modes.conservative, modes.aggressive])
        .eq('is_primary', true)
        .order('batch_date', { ascending: false })
        .limit(1);

      if (recentDate && recentDate.length > 0) {
        targetDate = recentDate[0].batch_date;
      }
    }

    const { data, error } = await supabase
      .from('judgment_records')
      .select('*')
      .eq('batch_date', targetDate)
      .in('strategy_mode', [modes.conservative, modes.aggressive])
      .eq('is_primary', true)
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
      .eq('is_primary', true)
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
    const targetDate = date || getUTCToday();

    let query = supabase
      .from('judgment_records')
      .select('*')
      .eq('symbol', symbol)
      .eq('batch_date', targetDate)
      .eq('is_primary', true);

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

    const { data, error } = await supabase
      .from('judgment_records')
      .select('*')
      .gte('batch_date', getUTCDateDaysAgo(days))
      .eq('is_primary', true)
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

    const { data, error } = await supabase
      .from('judgment_records')
      .select('decision, confidence')
      .gte('batch_date', getUTCDateDaysAgo(days))
      .eq('is_primary', true);

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
    const today = getUTCToday();

    // First try today's date
    let { data, error } = await supabase
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

    // If no data for today, get the most recent date's logs
    if (!data || data.length === 0) {
      const { data: recentData, error: recentError } = await supabase
        .from('batch_execution_logs')
        .select('*')
        .order('batch_date', { ascending: false })
        .order('started_at', { ascending: false })
        .limit(10);

      if (!recentError && recentData && recentData.length > 0) {
        // Get the most recent batch_date
        const mostRecentDate = recentData[0].batch_date;
        // Filter to only that date's logs
        data = recentData.filter(log => log.batch_date === mostRecentDate);
      }
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

    const { data, error } = await supabase
      .from('batch_execution_logs')
      .select('*')
      .in('status', ['failed', 'partial_success'])
      .gte('batch_date', getUTCDateDaysAgo(days))
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

/**
 * Fetch batch execution history for display
 */
export async function getBatchExecutionHistory(days: number = 7): Promise<BatchExecutionLog[]> {
  try {
    const supabase = getSupabase();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);

    const { data, error } = await supabase
      .from('batch_execution_logs')
      .select('*')
      .gte('batch_date', startDate.toISOString().split('T')[0])
      .order('started_at', { ascending: false })
      .limit(50);

    if (error) {
      console.error('[getBatchExecutionHistory] error:', error);
      return [];
    }

    return data || [];
  } catch (error) {
    console.error('getBatchExecutionHistory error:', error);
    return [];
  }
}

// ============================================
// Insights Page Functions
// ============================================

/**
 * Fetch judgment outcome stats grouped by strategy × decision
 */
export async function getJudgmentOutcomeStats(
  marketType: MarketType = 'us'
): Promise<JudgmentOutcomeStats[]> {
  try {
    const supabase = getSupabase();
    const strategies = Object.values(STRATEGY_MODES[marketType]);

    const { data, error } = await supabase.rpc('get_judgment_outcome_stats', {
      strategy_modes: strategies,
    });

    if (error) {
      // Fallback: query directly if RPC doesn't exist
      console.warn('[getJudgmentOutcomeStats] RPC not available, using direct query');
      return await getJudgmentOutcomeStatsFallback(marketType);
    }

    return data || [];
  } catch {
    return await getJudgmentOutcomeStatsFallback(marketType);
  }
}

async function getJudgmentOutcomeStatsFallback(
  marketType: MarketType
): Promise<JudgmentOutcomeStats[]> {
  try {
    const supabase = getSupabase();
    const strategies = Object.values(STRATEGY_MODES[marketType]);

    // Fetch judgment_records with outcomes for these strategies
    const { data: judgments, error } = await supabase
      .from('judgment_records')
      .select('strategy_mode, decision, model_version, id, judgment_outcomes(outcome_aligned, actual_return_1d, actual_return_5d)')
      .in('strategy_mode', strategies);

    if (error || !judgments) {
      console.error('[getJudgmentOutcomeStatsFallback] error:', error);
      return [];
    }

    // Aggregate manually — group by strategy × decision × model
    const groups = new Map<string, { total: number; correct: number; returns1d: number[]; returns5d: number[] }>();

    for (const j of judgments) {
      const model = (j.model_version as string) || 'unknown';
      const key = `${j.strategy_mode}|${j.decision}|${model}`;
      if (!groups.has(key)) {
        groups.set(key, { total: 0, correct: 0, returns1d: [], returns5d: [] });
      }
      const g = groups.get(key)!;
      const outcomes = j.judgment_outcomes as Array<{ outcome_aligned: boolean | null; actual_return_1d: number | null; actual_return_5d: number | null }>;
      if (outcomes && outcomes.length > 0) {
        for (const o of outcomes) {
          g.total++;
          if (o.outcome_aligned) g.correct++;
          if (o.actual_return_1d != null) g.returns1d.push(o.actual_return_1d);
          if (o.actual_return_5d != null) g.returns5d.push(o.actual_return_5d);
        }
      }
    }

    const results: JudgmentOutcomeStats[] = [];
    Array.from(groups.entries()).forEach(([key, g]) => {
      if (g.total === 0) return;
      const [strategy_mode, decision, model_version] = key.split('|');
      results.push({
        strategy_mode,
        decision,
        model_version,
        total: g.total,
        correct: g.correct,
        accuracy_pct: Math.round((g.correct / g.total) * 1000) / 10,
        avg_return_1d: g.returns1d.length > 0
          ? Math.round(g.returns1d.reduce((a, b) => a + b, 0) / g.returns1d.length * 1000) / 1000
          : null,
        avg_return_5d: g.returns5d.length > 0
          ? Math.round(g.returns5d.reduce((a, b) => a + b, 0) / g.returns5d.length * 1000) / 1000
          : null,
      });
    });

    return results.sort((a, b) =>
      a.model_version.localeCompare(b.model_version) ||
      a.strategy_mode.localeCompare(b.strategy_mode) ||
      a.decision.localeCompare(b.decision)
    );
  } catch (error) {
    console.error('getJudgmentOutcomeStatsFallback error:', error);
    return [];
  }
}

/**
 * Fetch outcome accuracy trends over time
 */
export async function getOutcomeTrends(
  marketType: MarketType = 'us',
  days: number = 30
): Promise<OutcomeTrend[]> {
  try {
    const supabase = getSupabase();
    const strategies = Object.values(STRATEGY_MODES[marketType]);
    const startDate = getUTCDateDaysAgo(days);

    const { data: judgments, error } = await supabase
      .from('judgment_records')
      .select('batch_date, strategy_mode, model_version, judgment_outcomes(outcome_aligned, actual_return_1d)')
      .in('strategy_mode', strategies)
      .gte('batch_date', startDate)
      .order('batch_date', { ascending: true });

    if (error || !judgments) {
      console.error('[getOutcomeTrends] error:', error);
      return [];
    }

    // Group by date × strategy × model
    const groups = new Map<string, { total: number; aligned: number; returns: number[] }>();

    for (const j of judgments) {
      const outcomes = j.judgment_outcomes as Array<{ outcome_aligned: boolean | null; actual_return_1d: number | null }>;
      if (!outcomes || outcomes.length === 0) continue;

      const model = (j.model_version as string) || 'unknown';
      const key = `${j.batch_date}|${j.strategy_mode}|${model}`;
      if (!groups.has(key)) {
        groups.set(key, { total: 0, aligned: 0, returns: [] });
      }
      const g = groups.get(key)!;
      for (const o of outcomes) {
        g.total++;
        if (o.outcome_aligned) g.aligned++;
        if (o.actual_return_1d != null) g.returns.push(o.actual_return_1d);
      }
    }

    const results: OutcomeTrend[] = [];
    Array.from(groups.entries()).forEach(([key, g]) => {
      if (g.total === 0) return;
      const [batch_date, strategy_mode, model_version] = key.split('|');
      results.push({
        batch_date,
        strategy_mode,
        model_version,
        total: g.total,
        aligned: g.aligned,
        accuracy: Math.round((g.aligned / g.total) * 1000) / 10,
        avg_return: g.returns.length > 0
          ? Math.round(g.returns.reduce((a, b) => a + b, 0) / g.returns.length * 1000) / 1000
          : 0,
      });
    });

    return results.sort((a, b) => a.batch_date.localeCompare(b.batch_date));
  } catch (error) {
    console.error('getOutcomeTrends error:', error);
    return [];
  }
}

/**
 * Fetch meta-monitor interventions
 */
export async function getMetaInterventions(
  marketType: MarketType = 'us',
  limit: number = 20
): Promise<MetaIntervention[]> {
  try {
    const supabase = getSupabase();
    const strategies = Object.values(STRATEGY_MODES[marketType]);

    const { data, error } = await supabase
      .from('meta_interventions')
      .select('*')
      .in('strategy_mode', strategies)
      .order('intervention_date', { ascending: false })
      .limit(limit);

    if (error) {
      console.error('[getMetaInterventions] error:', error);
      return [];
    }

    return (data || []) as MetaIntervention[];
  } catch (error) {
    console.error('getMetaInterventions error:', error);
    return [];
  }
}

/**
 * Fetch active prompt overrides
 */
export async function getActivePromptOverrides(
  marketType: MarketType = 'us'
): Promise<PromptOverride[]> {
  try {
    const supabase = getSupabase();
    const strategies = Object.values(STRATEGY_MODES[marketType]);
    const now = new Date().toISOString();

    const { data, error } = await supabase
      .from('prompt_overrides')
      .select('*')
      .in('strategy_mode', strategies)
      .eq('active', true)
      .gte('expires_at', now)
      .order('created_at', { ascending: false });

    if (error) {
      console.error('[getActivePromptOverrides] error:', error);
      return [];
    }

    return (data || []) as PromptOverride[];
  } catch (error) {
    console.error('getActivePromptOverrides error:', error);
    return [];
  }
}

/**
 * Fetch latest rolling metrics per strategy
 */
export async function getRollingMetrics(
  marketType: MarketType = 'us'
): Promise<RollingMetrics[]> {
  try {
    const supabase = getSupabase();
    const strategies = Object.values(STRATEGY_MODES[marketType]);

    const results: RollingMetrics[] = [];
    for (const strategy of strategies) {
      const { data, error } = await supabase
        .from('performance_rolling_metrics')
        .select('*')
        .eq('strategy_mode', strategy)
        .order('metric_date', { ascending: false })
        .limit(1);

      if (!error && data && data.length > 0) {
        results.push(data[0] as RollingMetrics);
      }
    }

    return results;
  } catch (error) {
    console.error('getRollingMetrics error:', error);
    return [];
  }
}

/**
 * Compute confidence calibration from judgment_records + outcomes
 */
export async function getConfidenceCalibration(
  marketType: MarketType = 'us'
): Promise<ConfidenceCalibrationBucket[]> {
  try {
    const supabase = getSupabase();
    const strategies = Object.values(STRATEGY_MODES[marketType]);

    const { data: judgments, error } = await supabase
      .from('judgment_records')
      .select('confidence, decision, model_version, judgment_outcomes(outcome_aligned, actual_return_1d)')
      .in('strategy_mode', strategies);

    if (error || !judgments) {
      console.error('[getConfidenceCalibration] error:', error);
      return [];
    }

    // Bucket: 0.0-0.3, 0.3-0.5, 0.5-0.6, 0.6-0.7, 0.7-0.8, 0.8-0.9, 0.9-1.0
    const bucketDefs = [
      { label: '0-30%', min: 0, max: 0.3 },
      { label: '30-50%', min: 0.3, max: 0.5 },
      { label: '50-60%', min: 0.5, max: 0.6 },
      { label: '60-70%', min: 0.6, max: 0.7 },
      { label: '70-80%', min: 0.7, max: 0.8 },
      { label: '80-90%', min: 0.8, max: 0.9 },
      { label: '90-100%', min: 0.9, max: 1.01 },
    ];

    // Group by model × bucket
    const modelBuckets = new Map<string, Map<string, { total: number; correct: number; returns: number[]; min: number; max: number }>>();

    for (const j of judgments) {
      const outcomes = j.judgment_outcomes as Array<{
        outcome_aligned: boolean | null;
        actual_return_1d: number | null;
      }>;
      if (!outcomes || outcomes.length === 0) continue;

      const model = (j.model_version as string) || 'unknown';
      const conf = j.confidence;
      const bDef = bucketDefs.find((b) => conf >= b.min && conf < b.max);
      if (!bDef) continue;

      if (!modelBuckets.has(model)) {
        modelBuckets.set(model, new Map());
      }
      const mBuckets = modelBuckets.get(model)!;
      if (!mBuckets.has(bDef.label)) {
        mBuckets.set(bDef.label, { total: 0, correct: 0, returns: [], min: bDef.min, max: bDef.max });
      }
      const bucket = mBuckets.get(bDef.label)!;

      for (const o of outcomes) {
        bucket.total++;
        if (o.outcome_aligned) bucket.correct++;
        if (o.actual_return_1d != null) bucket.returns.push(o.actual_return_1d);
      }
    }

    const results: ConfidenceCalibrationBucket[] = [];
    for (const [model, mBuckets] of Array.from(modelBuckets.entries())) {
      for (const [label, b] of Array.from(mBuckets.entries())) {
        if (b.total === 0) continue;
        results.push({
          bucket: label,
          bucketMin: b.min,
          bucketMax: b.max,
          total: b.total,
          correct: b.correct,
          accuracy: Math.round((b.correct / b.total) * 1000) / 10,
          avgReturn: b.returns.length > 0
            ? Math.round(b.returns.reduce((a, c) => a + c, 0) / b.returns.length * 1000) / 1000
            : 0,
          model_version: model,
        });
      }
    }

    return results;
  } catch (error) {
    console.error('getConfidenceCalibration error:', error);
    return [];
  }
}

/**
 * Fetch exit reason distribution from trade history
 */
export async function getExitReasonDistribution(
  marketType: MarketType = 'us',
  days: number = 90
): Promise<ExitReasonCount[]> {
  try {
    const supabase = getSupabase();
    const strategies = Object.values(STRATEGY_MODES[marketType]);

    const { data, error } = await supabase
      .from('trade_history')
      .select('exit_reason')
      .in('strategy_mode', strategies)
      .gte('exit_date', getUTCDateDaysAgo(days));

    if (error || !data) {
      console.error('[getExitReasonDistribution] error:', error);
      return [];
    }

    const counts = new Map<string, number>();
    for (const row of data) {
      const reason = row.exit_reason || 'unknown';
      counts.set(reason, (counts.get(reason) || 0) + 1);
    }

    return Array.from(counts.entries())
      .map(([exit_reason, count]) => ({ exit_reason, count }))
      .sort((a, b) => b.count - a.count);
  } catch (error) {
    console.error('getExitReasonDistribution error:', error);
    return [];
  }
}

/**
 * Fetch parameter change log (audit trail for strategy parameter adjustments)
 */
export async function getParameterChangeLog(
  marketType: MarketType = 'us',
  limit: number = 30
): Promise<ParameterChangeRecord[]> {
  try {
    const supabase = getSupabase();
    const strategies = Object.values(STRATEGY_MODES[marketType]);

    const { data, error } = await supabase
      .from('parameter_change_log')
      .select('*')
      .in('strategy_mode', strategies)
      .order('created_at', { ascending: false })
      .limit(limit);

    if (error) {
      console.error('[getParameterChangeLog] error:', error);
      return [];
    }

    return (data || []) as ParameterChangeRecord[];
  } catch (error) {
    console.error('getParameterChangeLog error:', error);
    return [];
  }
}

/**
 * Fetch model-level performance statistics from judgment_records + judgment_outcomes.
 * Groups by model_version and computes win rate, avg return, etc.
 */
export async function getModelPerformanceStats(
  marketType: MarketType = 'us'
): Promise<ModelPerformanceStats[]> {
  try {
    const supabase = getSupabase();
    const strategies = Object.values(STRATEGY_MODES[marketType]);

    // Fetch judgment_records with their outcomes
    const { data, error } = await supabase
      .from('judgment_records')
      .select(`
        model_version,
        decision,
        confidence,
        batch_date,
        judgment_outcomes(actual_return_5d, outcome_aligned)
      `)
      .in('strategy_mode', strategies)
      .not('model_version', 'eq', 'fallback')
      .not('model_version', 'eq', '')
      .order('batch_date', { ascending: false });

    if (error) {
      console.error('[getModelPerformanceStats] error:', error);
      return [];
    }

    if (!data || data.length === 0) return [];

    // Group by model_version
    const modelMap = new Map<string, {
      total: number;
      buys: number;
      avoids: number;
      buyWins: number;
      returns5d: number[];
      confidences: number[];
      firstDate: string;
      lastDate: string;
    }>();

    for (const row of data) {
      const model = row.model_version || 'unknown';
      if (!modelMap.has(model)) {
        modelMap.set(model, {
          total: 0, buys: 0, avoids: 0, buyWins: 0,
          returns5d: [], confidences: [], firstDate: row.batch_date, lastDate: row.batch_date,
        });
      }
      const stats = modelMap.get(model)!;
      stats.total++;
      stats.confidences.push(row.confidence || 0);

      if (row.batch_date < stats.firstDate) stats.firstDate = row.batch_date;
      if (row.batch_date > stats.lastDate) stats.lastDate = row.batch_date;

      if (row.decision === 'buy') {
        stats.buys++;
        // Check outcome
        const outcomes = row.judgment_outcomes as Array<{
          actual_return_5d: number | null;
          outcome_aligned: boolean | null;
        }> | null;
        if (outcomes && outcomes.length > 0) {
          const o = outcomes[0];
          if (o.outcome_aligned === true) stats.buyWins++;
          if (o.actual_return_5d != null) stats.returns5d.push(o.actual_return_5d);
        }
      } else if (row.decision === 'avoid') {
        stats.avoids++;
      }
    }

    // Convert to array
    const result: ModelPerformanceStats[] = [];
    for (const [model, stats] of Array.from(modelMap.entries())) {
      const avgReturn = stats.returns5d.length > 0
        ? stats.returns5d.reduce((a, b) => a + b, 0) / stats.returns5d.length
        : null;
      const avgConf = stats.confidences.length > 0
        ? stats.confidences.reduce((a, b) => a + b, 0) / stats.confidences.length
        : 0;

      result.push({
        model_version: model,
        total_judgments: stats.total,
        buy_count: stats.buys,
        avoid_count: stats.avoids,
        buy_win_count: stats.buyWins,
        buy_win_rate: stats.buys > 0 ? (stats.buyWins / stats.buys) * 100 : 0,
        avg_return_5d: avgReturn,
        avg_confidence: avgConf,
        first_used: stats.firstDate,
        last_used: stats.lastDate,
      });
    }

    // Sort by total judgments desc
    result.sort((a, b) => b.total_judgments - a.total_judgments);
    return result;
  } catch (error) {
    console.error('getModelPerformanceStats error:', error);
    return [];
  }
}
