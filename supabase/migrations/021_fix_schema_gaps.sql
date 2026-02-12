-- Migration 021: Fix schema gaps found during DB audit
-- Fixes:
--   1. Create research_logs (missing since 010 failed silently)
--   2. Rename stock_universe.is_active → enabled (backend uses "enabled")
--   3. Add scoring_config.factor_weights (015 didn't apply)
--   4. Add model_version to research_logs (019 skipped it)

-- ============================================
-- 1. CREATE RESEARCH_LOGS
-- Unified schema supporting both manual research (research_stock.py)
-- and automated weekly research (weekly_research.py)
-- ============================================

CREATE TABLE IF NOT EXISTS research_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Shared columns
    research_type VARCHAR(20) NOT NULL,
    market_type TEXT DEFAULT 'us',
    batch_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Weekly research columns (weekly_research.py)
    research_date DATE,
    title TEXT,
    content TEXT,
    symbols_mentioned JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    model_version VARCHAR(100),

    -- Manual research columns (research_stock.py / 010 schema)
    symbol VARCHAR(20),
    system_data JSONB,
    external_findings TEXT,
    news_sentiment VARCHAR(20),
    system_judgment VARCHAR(10),
    system_confidence DECIMAL(5, 4),
    sentiment_alignment VARCHAR(20),
    user_conclusion TEXT,
    override_decision VARCHAR(10),
    override_reason TEXT,
    researched_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_logs_date ON research_logs(research_date DESC);
CREATE INDEX IF NOT EXISTS idx_research_logs_type ON research_logs(research_type);
CREATE INDEX IF NOT EXISTS idx_research_logs_symbol ON research_logs(symbol) WHERE symbol IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_research_logs_batch ON research_logs(batch_date);
CREATE INDEX IF NOT EXISTS idx_research_logs_model ON research_logs(model_version) WHERE model_version IS NOT NULL;

ALTER TABLE research_logs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY "Service role full access" ON research_logs
        FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY "Anon read access" ON research_logs
        FOR SELECT TO anon USING (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- 2. FIX stock_universe COLUMN NAME
-- Backend (supabase_client.py) queries "enabled" but DB has "is_active"
-- ============================================

DO $$ BEGIN
    ALTER TABLE stock_universe RENAME COLUMN is_active TO enabled;
EXCEPTION WHEN undefined_column THEN
    -- Column "is_active" doesn't exist, check if "enabled" already exists
    NULL;
END $$;

-- Fix the partial index to use new column name
DROP INDEX IF EXISTS idx_stock_universe_active;
CREATE INDEX IF NOT EXISTS idx_stock_universe_enabled
    ON stock_universe(enabled, market_type);

-- ============================================
-- 3. ADD scoring_config.factor_weights
-- Migration 015 was recorded but column is missing
-- ============================================

ALTER TABLE scoring_config ADD COLUMN IF NOT EXISTS factor_weights JSONB DEFAULT NULL;

-- ============================================
-- 4. VIEWS (from 010, recreate safely)
-- ============================================

CREATE OR REPLACE VIEW v_judgment_overrides AS
SELECT
    rl.id,
    rl.symbol,
    rl.batch_date,
    rl.system_judgment,
    rl.system_confidence,
    rl.override_decision,
    rl.override_reason,
    rl.news_sentiment,
    rl.sentiment_alignment,
    rl.researched_at,
    CASE
        WHEN rl.override_decision IS NOT NULL
             AND rl.override_decision != 'no_change'
             AND rl.override_decision != LOWER(rl.system_judgment)
        THEN TRUE
        ELSE FALSE
    END as judgment_changed
FROM research_logs rl
WHERE rl.research_type = 'symbol'
  AND rl.override_decision IS NOT NULL
ORDER BY rl.researched_at DESC;

CREATE OR REPLACE VIEW v_research_stats AS
SELECT
    DATE(researched_at) as research_date,
    COUNT(*) as total_researches,
    COUNT(*) FILTER (WHERE research_type = 'symbol') as symbol_researches,
    COUNT(*) FILTER (WHERE research_type IN ('all', 'market', 'jp', 'us')) as overview_researches,
    COUNT(*) FILTER (WHERE override_decision IS NOT NULL AND override_decision != 'no_change') as overrides,
    COUNT(*) FILTER (WHERE sentiment_alignment = 'conflicting') as conflicting_signals
FROM research_logs
GROUP BY DATE(researched_at)
ORDER BY research_date DESC;
