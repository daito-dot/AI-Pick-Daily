import { createClient, SupabaseClient } from '@supabase/supabase-js';
import type { DailyPick, StockScore, MarketRegimeHistory, AILesson, PerformanceLog, StrategyModeType } from '@/types';

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
}> {
  try {
    const supabase = getSupabase();
    const today = new Date().toISOString().split('T')[0];

    // Get daily picks for both strategies
    const { data: allPicks } = await supabase
      .from('daily_picks')
      .select('*')
      .eq('batch_date', today);

    const conservativePicks = allPicks?.find(p => p.strategy_mode === 'conservative') || null;
    const aggressivePicks = allPicks?.find(p => p.strategy_mode === 'aggressive') || null;

    // Get stock scores for today (both strategies)
    const { data: allScores } = await supabase
      .from('stock_scores')
      .select('*')
      .eq('batch_date', today)
      .order('composite_score', { ascending: false });

    const conservativeScores = allScores?.filter(s => s.strategy_mode === 'conservative') || [];
    const aggressiveScores = allScores?.filter(s => s.strategy_mode === 'aggressive') || [];

    // Get market regime
    const { data: regime } = await supabase
      .from('market_regime_history')
      .select('*')
      .eq('check_date', today)
      .single();

    return {
      conservativePicks,
      aggressivePicks,
      conservativeScores,
      aggressiveScores,
      regime: regime || null,
    };
  } catch (error) {
    console.error('getTodayPicks error:', error);
    return {
      conservativePicks: null,
      aggressivePicks: null,
      conservativeScores: [],
      aggressiveScores: [],
      regime: null,
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
