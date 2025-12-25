-- Migration: 009_fix_rls_security.sql
-- Description: Fix RLS security issues reported by Supabase linter
-- Issues addressed:
--   1. Enable RLS on all public tables
--   2. Fix SECURITY DEFINER views
--   3. Add appropriate RLS policies

-- ============================================================================
-- STEP 1: Enable RLS on all tables that don't have it enabled
-- ============================================================================

-- Tables without RLS
ALTER TABLE public.indicators_weights ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_performance_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_lessons ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.news_archive ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.judgment_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.performance_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.judgment_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reflection_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scoring_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.threshold_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolio_daily_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.virtual_portfolio ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trade_history ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- STEP 2: Create RLS policies for read access (public read, authenticated write)
-- ============================================================================

-- indicators_weights: Public read, service role write
CREATE POLICY "Public read indicators_weights"
    ON public.indicators_weights FOR SELECT
    USING (true);

CREATE POLICY "Service role write indicators_weights"
    ON public.indicators_weights FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- agent_performance_daily: Public read, service role write
CREATE POLICY "Public read agent_performance_daily"
    ON public.agent_performance_daily FOR SELECT
    USING (true);

CREATE POLICY "Service role write agent_performance_daily"
    ON public.agent_performance_daily FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- news_archive: Public read, service role write
CREATE POLICY "Public read news_archive"
    ON public.news_archive FOR SELECT
    USING (true);

CREATE POLICY "Service role write news_archive"
    ON public.news_archive FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- judgment_records: Public read, service role write
CREATE POLICY "Public read judgment_records"
    ON public.judgment_records FOR SELECT
    USING (true);

CREATE POLICY "Service role write judgment_records"
    ON public.judgment_records FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- judgment_outcomes: Public read, service role write
CREATE POLICY "Public read judgment_outcomes"
    ON public.judgment_outcomes FOR SELECT
    USING (true);

CREATE POLICY "Service role write judgment_outcomes"
    ON public.judgment_outcomes FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- reflection_records: Public read, service role write
CREATE POLICY "Public read reflection_records"
    ON public.reflection_records FOR SELECT
    USING (true);

CREATE POLICY "Service role write reflection_records"
    ON public.reflection_records FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- scoring_config: Public read, service role write
CREATE POLICY "Public read scoring_config"
    ON public.scoring_config FOR SELECT
    USING (true);

CREATE POLICY "Service role write scoring_config"
    ON public.scoring_config FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- threshold_history: Public read, service role write
CREATE POLICY "Public read threshold_history"
    ON public.threshold_history FOR SELECT
    USING (true);

CREATE POLICY "Service role write threshold_history"
    ON public.threshold_history FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- portfolio_daily_snapshot: Public read, service role write
CREATE POLICY "Public read portfolio_daily_snapshot"
    ON public.portfolio_daily_snapshot FOR SELECT
    USING (true);

CREATE POLICY "Service role write portfolio_daily_snapshot"
    ON public.portfolio_daily_snapshot FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- virtual_portfolio: Public read, service role write
CREATE POLICY "Public read virtual_portfolio"
    ON public.virtual_portfolio FOR SELECT
    USING (true);

CREATE POLICY "Service role write virtual_portfolio"
    ON public.virtual_portfolio FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- trade_history: Public read, service role write
CREATE POLICY "Public read trade_history"
    ON public.trade_history FOR SELECT
    USING (true);

CREATE POLICY "Service role write trade_history"
    ON public.trade_history FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ============================================================================
-- STEP 3: Fix views with SECURITY DEFINER (recreate as SECURITY INVOKER)
-- ============================================================================

-- Drop and recreate cumulative_performance view
DROP VIEW IF EXISTS public.cumulative_performance;

CREATE VIEW public.cumulative_performance
WITH (security_invoker = true)
AS
SELECT
    p.recorded_date,
    p.strategy_mode,
    p.symbol,
    p.entry_price,
    p.target_return,
    p.actual_return,
    p.is_successful,
    SUM(COALESCE(p.actual_return, 0)) OVER (
        PARTITION BY p.strategy_mode
        ORDER BY p.recorded_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_return,
    COUNT(*) OVER (
        PARTITION BY p.strategy_mode
        ORDER BY p.recorded_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS total_picks,
    SUM(CASE WHEN p.is_successful THEN 1 ELSE 0 END) OVER (
        PARTITION BY p.strategy_mode
        ORDER BY p.recorded_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS successful_picks
FROM public.performance_log p
WHERE p.actual_return IS NOT NULL;

-- Drop and recreate strategy_comparison view
DROP VIEW IF EXISTS public.strategy_comparison;

CREATE VIEW public.strategy_comparison
WITH (security_invoker = true)
AS
SELECT
    strategy_mode,
    COUNT(*) AS total_picks,
    COUNT(CASE WHEN actual_return IS NOT NULL THEN 1 END) AS evaluated_picks,
    ROUND(AVG(CASE WHEN actual_return IS NOT NULL THEN actual_return END)::numeric, 4) AS avg_return,
    ROUND(
        (SUM(CASE WHEN is_successful THEN 1 ELSE 0 END)::numeric /
         NULLIF(COUNT(CASE WHEN actual_return IS NOT NULL THEN 1 END), 0) * 100)::numeric,
        2
    ) AS success_rate,
    ROUND(SUM(COALESCE(actual_return, 0))::numeric, 4) AS total_return,
    MIN(recorded_date) AS first_pick_date,
    MAX(recorded_date) AS last_pick_date
FROM public.performance_log
GROUP BY strategy_mode;

-- Grant SELECT on views
GRANT SELECT ON public.cumulative_performance TO anon, authenticated;
GRANT SELECT ON public.strategy_comparison TO anon, authenticated;

-- ============================================================================
-- STEP 4: Add comments for documentation
-- ============================================================================

COMMENT ON POLICY "Public read indicators_weights" ON public.indicators_weights IS 'Allow public read access to indicator weights';
COMMENT ON POLICY "Public read agent_performance_daily" ON public.agent_performance_daily IS 'Allow public read access to agent performance data';
COMMENT ON POLICY "Public read news_archive" ON public.news_archive IS 'Allow public read access to news archive';
COMMENT ON POLICY "Public read judgment_records" ON public.judgment_records IS 'Allow public read access to judgment records';
COMMENT ON POLICY "Public read judgment_outcomes" ON public.judgment_outcomes IS 'Allow public read access to judgment outcomes';
COMMENT ON POLICY "Public read reflection_records" ON public.reflection_records IS 'Allow public read access to reflection records';
COMMENT ON POLICY "Public read scoring_config" ON public.scoring_config IS 'Allow public read access to scoring config';
COMMENT ON POLICY "Public read threshold_history" ON public.threshold_history IS 'Allow public read access to threshold history';
COMMENT ON POLICY "Public read portfolio_daily_snapshot" ON public.portfolio_daily_snapshot IS 'Allow public read access to portfolio snapshots';
COMMENT ON POLICY "Public read virtual_portfolio" ON public.virtual_portfolio IS 'Allow public read access to virtual portfolio';
COMMENT ON POLICY "Public read trade_history" ON public.trade_history IS 'Allow public read access to trade history';
