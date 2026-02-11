-- Meta-monitor tables for autonomous performance improvement
-- Detect → Diagnose → Act → Evaluate cycle

-- 1. Rolling metrics (daily cache)
CREATE TABLE IF NOT EXISTS performance_rolling_metrics (
  id bigserial PRIMARY KEY,
  strategy_mode text NOT NULL,
  metric_date date NOT NULL DEFAULT CURRENT_DATE,
  win_rate_7d numeric,
  win_rate_30d numeric,
  avg_return_7d numeric,
  avg_return_30d numeric,
  missed_rate_7d numeric,
  total_judgments_7d integer,
  total_judgments_30d integer,
  created_at timestamptz DEFAULT now(),
  UNIQUE(strategy_mode, metric_date)
);

-- 2. Meta intervention log
CREATE TABLE IF NOT EXISTS meta_interventions (
  id bigserial PRIMARY KEY,
  strategy_mode text NOT NULL,
  intervention_date timestamptz DEFAULT now(),
  trigger_type text NOT NULL,
  diagnosis jsonb NOT NULL,
  actions_taken jsonb NOT NULL,
  pre_metrics jsonb NOT NULL,
  post_metrics jsonb,
  effectiveness_score numeric,
  rolled_back boolean DEFAULT false,
  rollback_date timestamptz,
  cooldown_until timestamptz,
  created_at timestamptz DEFAULT now()
);

-- 3. Prompt overrides
CREATE TABLE IF NOT EXISTS prompt_overrides (
  id bigserial PRIMARY KEY,
  strategy_mode text NOT NULL,
  override_text text NOT NULL,
  reason text NOT NULL,
  intervention_id bigint REFERENCES meta_interventions(id),
  active boolean DEFAULT true,
  expires_at timestamptz NOT NULL,
  created_at timestamptz DEFAULT now()
);

-- Enable RLS
ALTER TABLE performance_rolling_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_interventions ENABLE ROW LEVEL SECURITY;
ALTER TABLE prompt_overrides ENABLE ROW LEVEL SECURITY;

-- RLS policies: read is public, write is service_role only

-- performance_rolling_metrics
CREATE POLICY "Anon read access on performance_rolling_metrics"
  ON performance_rolling_metrics FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Service role write access on performance_rolling_metrics"
  ON performance_rolling_metrics FOR ALL
  TO service_role
  USING (true) WITH CHECK (true);

-- meta_interventions
CREATE POLICY "Anon read access on meta_interventions"
  ON meta_interventions FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Service role write access on meta_interventions"
  ON meta_interventions FOR ALL
  TO service_role
  USING (true) WITH CHECK (true);

-- prompt_overrides
CREATE POLICY "Anon read access on prompt_overrides"
  ON prompt_overrides FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Service role write access on prompt_overrides"
  ON prompt_overrides FOR ALL
  TO service_role
  USING (true) WITH CHECK (true);

-- Index for common queries
CREATE INDEX idx_rolling_metrics_strategy_date
  ON performance_rolling_metrics(strategy_mode, metric_date DESC);

CREATE INDEX idx_meta_interventions_strategy_date
  ON meta_interventions(strategy_mode, intervention_date DESC);

CREATE INDEX idx_prompt_overrides_strategy_active
  ON prompt_overrides(strategy_mode, active) WHERE active = true;
