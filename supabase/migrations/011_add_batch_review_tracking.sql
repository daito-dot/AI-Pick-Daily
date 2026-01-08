-- Migration: Add batch review tracking
-- Links Pre-Market Review to the correct Post-Market Scoring batch
-- instead of using date-based matching

-- ============================================
-- ADD REVIEWED_AT TO DAILY_PICKS
-- ============================================

-- Add reviewed_at column to track when a batch was reviewed by Pre-Market
ALTER TABLE daily_picks
ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;

-- Index for efficient lookup of unreviewed batches
CREATE INDEX IF NOT EXISTS idx_daily_picks_unreviewed
ON daily_picks(strategy_mode, batch_date DESC)
WHERE reviewed_at IS NULL AND status = 'published';

-- ============================================
-- HELPER FUNCTION
-- ============================================

-- Function to get the latest unreviewed batch for Pre-Market Review
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

-- ============================================
-- COMMENTS
-- ============================================

COMMENT ON COLUMN daily_picks.reviewed_at IS
'Timestamp when this batch was reviewed by Pre-Market Review. NULL means pending review.';

COMMENT ON FUNCTION get_unreviewed_batch IS
'Returns the latest Post-Market batch that has not been reviewed by Pre-Market yet.';
