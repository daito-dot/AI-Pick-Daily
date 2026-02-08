-- Strategy parameters: DB-managed tunable constants for meta-agent adjustment
-- Replaces hardcoded Python constants with DB-backed parameters

-- 1. Strategy parameters table (key-value per strategy)
CREATE TABLE IF NOT EXISTS strategy_parameters (
  id bigserial PRIMARY KEY,
  strategy_mode text NOT NULL,
  param_name text NOT NULL,
  current_value numeric NOT NULL,
  min_value numeric NOT NULL,
  max_value numeric NOT NULL,
  step numeric NOT NULL DEFAULT 1.0,
  description text,
  updated_at timestamptz DEFAULT now(),
  UNIQUE(strategy_mode, param_name)
);

-- 2. Parameter change log (audit trail for all changes)
CREATE TABLE IF NOT EXISTS parameter_change_log (
  id bigserial PRIMARY KEY,
  strategy_mode text NOT NULL,
  param_name text NOT NULL,
  old_value numeric,
  new_value numeric NOT NULL,
  changed_by text NOT NULL,
  reason text,
  intervention_id bigint REFERENCES meta_interventions(id),
  created_at timestamptz DEFAULT now()
);

-- 3. Add confidence drift columns to rolling metrics
ALTER TABLE performance_rolling_metrics
  ADD COLUMN IF NOT EXISTS avg_confidence_7d numeric,
  ADD COLUMN IF NOT EXISTS avg_confidence_30d numeric;

-- RLS
ALTER TABLE strategy_parameters ENABLE ROW LEVEL SECURITY;
ALTER TABLE parameter_change_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow service role full access on strategy_parameters"
  ON strategy_parameters FOR ALL
  USING (true) WITH CHECK (true);

CREATE POLICY "Allow service role full access on parameter_change_log"
  ON parameter_change_log FOR ALL
  USING (true) WITH CHECK (true);

-- Indexes
CREATE INDEX idx_strategy_parameters_mode
  ON strategy_parameters(strategy_mode);

CREATE INDEX idx_parameter_change_log_mode_date
  ON parameter_change_log(strategy_mode, created_at DESC);

-- Seed: 15 parameters × 4 strategies = 60 rows
-- Helper function for bulk insert
DO $$
DECLARE
  strategies text[] := ARRAY['conservative', 'aggressive', 'jp_conservative', 'jp_aggressive'];
  s text;
BEGIN
  FOREACH s IN ARRAY strategies
  LOOP
    INSERT INTO strategy_parameters (strategy_mode, param_name, current_value, min_value, max_value, step, description) VALUES
      (s, 'take_profit_pct',            8.0,   3.0,  20.0,  2.0,  '利確閾値(%)'),
      (s, 'stop_loss_pct',             -7.0, -15.0,  -3.0,  2.0,  '損切閾値(%)'),
      (s, 'max_hold_days',             10,     5,    20,    2,     'ソフト最大保有日数'),
      (s, 'absolute_max_hold_days',    15,    10,    30,    3,     'ハード最大保有日数'),
      (s, 'max_positions',             10,     3,    20,    2,     '最大同時保有数'),
      (s, 'mdd_warning_pct',          -10.0, -20.0,  -5.0,  2.0,  'MDD警告閾値(%)'),
      (s, 'mdd_stop_new_pct',         -15.0, -25.0,  -8.0,  2.0,  'MDD新規停止閾値(%)'),
      (s, 'win_rate_drop_ratio',        0.7,   0.5,   0.9,  0.05, '勝率低下検知比率'),
      (s, 'return_decline_threshold',  -1.0,  -3.0,   0.0,  0.5,  'リターン悪化閾値(%)'),
      (s, 'missed_spike_threshold',     0.30,  0.15,  0.50, 0.05, '見逃し率閾値'),
      (s, 'cooldown_days',              3,     1,     7,    1,     '介入間クールダウン(日)'),
      (s, 'prompt_expiry_days',         14,    7,    30,    3,     'Override有効期間(日)'),
      (s, 'max_threshold_change',       10,    3,    15,    2,     '閾値変更上限'),
      (s, 'max_weight_change',          0.1,   0.03,  0.2,  0.02, '重み変更上限'),
      (s, 'confidence_drift_threshold', 0.05,  0.02,  0.15, 0.01, '信頼度ドリフト閾値')
    ON CONFLICT (strategy_mode, param_name) DO NOTHING;
  END LOOP;
END $$;
