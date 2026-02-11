-- Migration: Fix RLS policies on meta-monitor and strategy-parameter tables
-- Description: The original policies in 016/017 used FOR ALL USING(true) WITH CHECK(true)
--   without a TO clause, granting anonymous users full write access.
--   This migration drops those policies and replaces them with:
--     - SELECT open to anon + authenticated
--     - ALL (write) restricted to service_role only

-- ============================================================================
-- STEP 1: Drop overly-permissive policies from migration 016
-- ============================================================================

DROP POLICY IF EXISTS "Allow service role full access on performance_rolling_metrics"
  ON performance_rolling_metrics;

DROP POLICY IF EXISTS "Allow service role full access on meta_interventions"
  ON meta_interventions;

DROP POLICY IF EXISTS "Allow service role full access on prompt_overrides"
  ON prompt_overrides;

-- ============================================================================
-- STEP 2: Drop overly-permissive policies from migration 017
-- ============================================================================

DROP POLICY IF EXISTS "Allow service role full access on strategy_parameters"
  ON strategy_parameters;

DROP POLICY IF EXISTS "Allow service role full access on parameter_change_log"
  ON parameter_change_log;

-- ============================================================================
-- STEP 3: Create properly scoped policies — read public, write service_role
-- ============================================================================

-- performance_rolling_metrics
CREATE POLICY IF NOT EXISTS "Anon read access on performance_rolling_metrics"
  ON performance_rolling_metrics FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY IF NOT EXISTS "Service role write access on performance_rolling_metrics"
  ON performance_rolling_metrics FOR ALL
  TO service_role
  USING (true) WITH CHECK (true);

-- meta_interventions
CREATE POLICY IF NOT EXISTS "Anon read access on meta_interventions"
  ON meta_interventions FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY IF NOT EXISTS "Service role write access on meta_interventions"
  ON meta_interventions FOR ALL
  TO service_role
  USING (true) WITH CHECK (true);

-- prompt_overrides
CREATE POLICY IF NOT EXISTS "Anon read access on prompt_overrides"
  ON prompt_overrides FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY IF NOT EXISTS "Service role write access on prompt_overrides"
  ON prompt_overrides FOR ALL
  TO service_role
  USING (true) WITH CHECK (true);

-- strategy_parameters
CREATE POLICY IF NOT EXISTS "Anon read access on strategy_parameters"
  ON strategy_parameters FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY IF NOT EXISTS "Service role write access on strategy_parameters"
  ON strategy_parameters FOR ALL
  TO service_role
  USING (true) WITH CHECK (true);

-- parameter_change_log
CREATE POLICY IF NOT EXISTS "Anon read access on parameter_change_log"
  ON parameter_change_log FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY IF NOT EXISTS "Service role write access on parameter_change_log"
  ON parameter_change_log FOR ALL
  TO service_role
  USING (true) WITH CHECK (true);
