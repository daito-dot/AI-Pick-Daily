-- URGENT FIX: Add JP strategy modes to ENUM type
-- Run this IMMEDIATELY in Supabase SQL Editor

-- Add jp_conservative to strategy_mode_type enum
ALTER TYPE strategy_mode_type ADD VALUE IF NOT EXISTS 'jp_conservative';

-- Add jp_aggressive to strategy_mode_type enum
ALTER TYPE strategy_mode_type ADD VALUE IF NOT EXISTS 'jp_aggressive';

-- Verify the enum now has all values
SELECT enumlabel FROM pg_enum
WHERE enumtypid = 'strategy_mode_type'::regtype
ORDER BY enumsortorder;
