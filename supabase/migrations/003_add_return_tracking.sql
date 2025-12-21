-- Add return tracking columns to stock_scores table
-- This enables tracking performance of ALL scored stocks, not just picked ones

-- Add return columns
ALTER TABLE stock_scores
ADD COLUMN IF NOT EXISTS return_1d DECIMAL(8, 4) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS return_5d DECIMAL(8, 4) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS was_picked BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS price_1d DECIMAL(12, 4) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS price_5d DECIMAL(12, 4) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ DEFAULT NULL;

-- Add index for performance queries
CREATE INDEX IF NOT EXISTS idx_stock_scores_return_tracking
ON stock_scores (batch_date, strategy_mode, was_picked, return_5d);

-- Add index for finding missed opportunities (high score, not picked, positive return)
CREATE INDEX IF NOT EXISTS idx_stock_scores_missed_opportunities
ON stock_scores (batch_date, strategy_mode, composite_score DESC, return_5d DESC)
WHERE was_picked = FALSE AND return_5d IS NOT NULL;

-- Comment explaining the columns
COMMENT ON COLUMN stock_scores.return_1d IS 'Price return after 1 trading day (percentage)';
COMMENT ON COLUMN stock_scores.return_5d IS 'Price return after 5 trading days (percentage)';
COMMENT ON COLUMN stock_scores.was_picked IS 'Whether this stock was in the daily_picks for this date/strategy';
COMMENT ON COLUMN stock_scores.price_1d IS 'Price at 1-day review';
COMMENT ON COLUMN stock_scores.price_5d IS 'Price at 5-day review';
COMMENT ON COLUMN stock_scores.reviewed_at IS 'When the return was last calculated';
