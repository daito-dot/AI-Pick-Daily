-- Migration: Fix V2 aggressive threshold from 75 to 45
-- The threshold was incorrectly set to 75, causing 0 V2 candidates to pass
-- Config default is 45, which is the intended value

UPDATE scoring_config
SET threshold = 45,
    updated_at = NOW()
WHERE strategy_mode = 'aggressive'
  AND threshold = 75;

-- Also ensure conservative threshold is correct (60)
UPDATE scoring_config
SET threshold = 60,
    updated_at = NOW()
WHERE strategy_mode = 'conservative'
  AND threshold != 60;

-- Log the change
COMMENT ON TABLE scoring_config IS 'Dynamic scoring thresholds - V1=60, V2=45 (updated 2026-01-16)';
