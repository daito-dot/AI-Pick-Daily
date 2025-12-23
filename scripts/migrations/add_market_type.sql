-- Migration: Add market_type column for Japan stocks support
-- Run this in Supabase SQL Editor

-- 1. Add market_type column to stock_scores
ALTER TABLE stock_scores
ADD COLUMN IF NOT EXISTS market_type TEXT DEFAULT 'us';

-- 2. Add market_type column to daily_picks
ALTER TABLE daily_picks
ADD COLUMN IF NOT EXISTS market_type TEXT DEFAULT 'us';

-- 3. Add market_type column to judgment_records
ALTER TABLE judgment_records
ADD COLUMN IF NOT EXISTS market_type TEXT DEFAULT 'us';

-- 4. Update existing data to have 'us' as market_type
UPDATE stock_scores SET market_type = 'us' WHERE market_type IS NULL;
UPDATE daily_picks SET market_type = 'us' WHERE market_type IS NULL;
UPDATE judgment_records SET market_type = 'us' WHERE market_type IS NULL;

-- 5. Add jp_conservative and jp_aggressive to strategy_mode constraint
-- First, check if the constraint exists and drop it
DO $$
BEGIN
    -- Try to drop existing constraint
    ALTER TABLE stock_scores DROP CONSTRAINT IF EXISTS stock_scores_strategy_mode_check;
    ALTER TABLE daily_picks DROP CONSTRAINT IF EXISTS daily_picks_strategy_mode_check;
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- Note: strategy_mode will now accept 'jp_conservative' and 'jp_aggressive'
-- The application handles validation

-- 6. Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_stock_scores_market_type
ON stock_scores (batch_date, market_type, strategy_mode);

CREATE INDEX IF NOT EXISTS idx_daily_picks_market_type
ON daily_picks (batch_date, market_type);

-- 7. Add market_type to portfolio tables
ALTER TABLE portfolio_daily_snapshot
ADD COLUMN IF NOT EXISTS market_type TEXT DEFAULT 'us';

ALTER TABLE virtual_portfolio
ADD COLUMN IF NOT EXISTS market_type TEXT DEFAULT 'us';

ALTER TABLE trade_history
ADD COLUMN IF NOT EXISTS market_type TEXT DEFAULT 'us';

-- Update existing portfolio data
UPDATE portfolio_daily_snapshot SET market_type = 'us' WHERE market_type IS NULL;
UPDATE virtual_portfolio SET market_type = 'us' WHERE market_type IS NULL;
UPDATE trade_history SET market_type = 'us' WHERE market_type IS NULL;

-- Done!
-- Verify with:
-- SELECT DISTINCT market_type FROM stock_scores;
-- SELECT DISTINCT market_type FROM daily_picks;
