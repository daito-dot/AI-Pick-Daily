-- Migration: Add missing objects to existing database
-- Only adds stock_universe table and reviewed_at column

-- ============================================
-- 1. ADD STOCK_UNIVERSE TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS stock_universe (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    market_type TEXT NOT NULL DEFAULT 'us',
    company_name TEXT,
    sector TEXT,
    industry TEXT,
    market_cap DECIMAL(20,2),
    is_active BOOLEAN DEFAULT TRUE,
    added_date DATE DEFAULT CURRENT_DATE,
    removed_date DATE,
    removal_reason TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, market_type)
);

CREATE INDEX IF NOT EXISTS idx_stock_universe_symbol ON stock_universe(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_universe_market ON stock_universe(market_type);
CREATE INDEX IF NOT EXISTS idx_stock_universe_active ON stock_universe(is_active) WHERE is_active = TRUE;

-- RLS for stock_universe
ALTER TABLE stock_universe ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access" ON stock_universe;
CREATE POLICY "Service role full access" ON stock_universe
    FOR ALL USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "Anon read access" ON stock_universe;
CREATE POLICY "Anon read access" ON stock_universe
    FOR SELECT TO anon USING (true);

-- ============================================
-- 2. ADD REVIEWED_AT TO DAILY_PICKS
-- ============================================

ALTER TABLE daily_picks
ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;

-- Index for efficient lookup of unreviewed batches
CREATE INDEX IF NOT EXISTS idx_daily_picks_unreviewed
ON daily_picks(strategy_mode, batch_date DESC)
WHERE reviewed_at IS NULL AND status = 'published';

COMMENT ON COLUMN daily_picks.reviewed_at IS
'Timestamp when this batch was reviewed by Pre-Market Review. NULL means pending review.';

-- ============================================
-- 3. HELPER FUNCTION FOR UNREVIEWED BATCH
-- ============================================

CREATE OR REPLACE FUNCTION get_unreviewed_batch(
    p_strategy_mode TEXT,
    p_market_type TEXT DEFAULT 'us'
)
RETURNS TABLE (
    batch_id UUID,
    batch_date DATE,
    symbols JSONB,
    pick_count INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        dp.id,
        dp.batch_date,
        dp.symbols,
        dp.pick_count
    FROM daily_picks dp
    WHERE dp.strategy_mode = p_strategy_mode::strategy_mode_type
      AND dp.status = 'published'
      AND dp.reviewed_at IS NULL
      AND (p_market_type = 'us' AND dp.strategy_mode IN ('conservative', 'aggressive')
           OR p_market_type = 'jp' AND dp.strategy_mode IN ('jp_conservative', 'jp_aggressive'))
    ORDER BY dp.batch_date DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;
