-- Add factor_weights column to scoring_config
-- NULL = use default weights from config.py
-- Example: {"trend": 0.30, "momentum": 0.40, "value": 0.20, "sentiment": 0.10}
ALTER TABLE scoring_config ADD COLUMN IF NOT EXISTS factor_weights JSONB DEFAULT NULL;
