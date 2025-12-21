-- AI Pick Daily - Strategy Mode Migration
-- Adds support for dual strategy (V1 Conservative / V2 Aggressive)

-- ============================================
-- NEW ENUM FOR STRATEGY MODE
-- ============================================

CREATE TYPE strategy_mode_type AS ENUM ('conservative', 'aggressive');

-- ============================================
-- MODIFY DAILY PICKS
-- ============================================

-- Add strategy_mode column
ALTER TABLE daily_picks
ADD COLUMN strategy_mode strategy_mode_type NOT NULL DEFAULT 'conservative';

-- Remove unique constraint on batch_date (now need batch_date + strategy_mode)
ALTER TABLE daily_picks DROP CONSTRAINT IF EXISTS daily_picks_batch_date_key;

-- Add new composite unique constraint
ALTER TABLE daily_picks
ADD CONSTRAINT daily_picks_batch_date_strategy_key UNIQUE (batch_date, strategy_mode);

-- ============================================
-- MODIFY STOCK SCORES
-- ============================================

-- Add strategy_mode column
ALTER TABLE stock_scores
ADD COLUMN strategy_mode strategy_mode_type NOT NULL DEFAULT 'conservative';

-- Add V2-specific score columns
ALTER TABLE stock_scores
ADD COLUMN momentum_12_1_score INTEGER CHECK (momentum_12_1_score >= 0 AND momentum_12_1_score <= 100),
ADD COLUMN breakout_score INTEGER CHECK (breakout_score >= 0 AND breakout_score <= 100),
ADD COLUMN catalyst_score INTEGER CHECK (catalyst_score >= 0 AND catalyst_score <= 100),
ADD COLUMN risk_adjusted_score INTEGER CHECK (risk_adjusted_score >= 0 AND risk_adjusted_score <= 100);

-- Remove old unique constraint
ALTER TABLE stock_scores DROP CONSTRAINT IF EXISTS stock_scores_batch_date_symbol_key;

-- Add new composite unique constraint
ALTER TABLE stock_scores
ADD CONSTRAINT stock_scores_batch_date_symbol_strategy_key UNIQUE (batch_date, symbol, strategy_mode);

-- ============================================
-- MODIFY PERFORMANCE LOG
-- ============================================

-- Add strategy_mode column
ALTER TABLE performance_log
ADD COLUMN strategy_mode strategy_mode_type NOT NULL DEFAULT 'conservative';

-- Remove old unique constraint
ALTER TABLE performance_log DROP CONSTRAINT IF EXISTS performance_log_pick_date_symbol_key;

-- Add new composite unique constraint
ALTER TABLE performance_log
ADD CONSTRAINT performance_log_pick_date_symbol_strategy_key UNIQUE (pick_date, symbol, strategy_mode);

-- Add trailing stop tracking for V2
ALTER TABLE performance_log
ADD COLUMN trailing_stop_price DECIMAL(12,4),
ADD COLUMN trailing_stop_triggered BOOLEAN DEFAULT FALSE,
ADD COLUMN trailing_stop_date DATE;

-- ============================================
-- CREATE STRATEGY COMPARISON VIEW
-- ============================================

CREATE OR REPLACE VIEW strategy_comparison AS
SELECT
    pl.pick_date,
    pl.strategy_mode,
    COUNT(*) as pick_count,
    AVG(pl.return_pct_1d) as avg_return_1d,
    AVG(pl.return_pct_5d) as avg_return_5d,
    SUM(CASE WHEN pl.status_5d = 'win' THEN 1 ELSE 0 END)::FLOAT /
        NULLIF(SUM(CASE WHEN pl.status_5d != 'pending' THEN 1 ELSE 0 END), 0) * 100 as win_rate_5d
FROM performance_log pl
WHERE pl.status_5d != 'pending'
GROUP BY pl.pick_date, pl.strategy_mode
ORDER BY pl.pick_date DESC, pl.strategy_mode;

-- ============================================
-- CREATE CUMULATIVE PERFORMANCE VIEW
-- ============================================

CREATE OR REPLACE VIEW cumulative_performance AS
WITH daily_returns AS (
    SELECT
        pick_date,
        strategy_mode,
        AVG(return_pct_5d) as daily_return
    FROM performance_log
    WHERE status_5d != 'pending'
    GROUP BY pick_date, strategy_mode
)
SELECT
    strategy_mode,
    pick_date,
    daily_return,
    SUM(daily_return) OVER (
        PARTITION BY strategy_mode
        ORDER BY pick_date
    ) as cumulative_return
FROM daily_returns
ORDER BY strategy_mode, pick_date;

-- ============================================
-- ADD INDEXES
-- ============================================

CREATE INDEX idx_daily_picks_strategy ON daily_picks(strategy_mode);
CREATE INDEX idx_stock_scores_strategy ON stock_scores(strategy_mode);
CREATE INDEX idx_performance_log_strategy ON performance_log(strategy_mode);

-- ============================================
-- UPDATE RLS POLICIES
-- ============================================

-- Public read access for performance_log (drop existing if any, then create)
DROP POLICY IF EXISTS "Public read strategy comparison" ON performance_log;
CREATE POLICY "Public read strategy comparison" ON performance_log
    FOR SELECT TO authenticated USING (true);
