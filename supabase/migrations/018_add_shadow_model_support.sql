-- Migration: Add shadow model support for multi-model judgment comparison
-- Enables multiple LLM models to judge the same stocks independently

-- Step 1: Backfill empty model_version to avoid null conflicts
UPDATE judgment_records SET model_version = 'unknown' WHERE model_version IS NULL OR model_version = '';

-- Step 2: Drop old unique constraint (symbol, batch_date, strategy_mode)
ALTER TABLE judgment_records
  DROP CONSTRAINT IF EXISTS judgment_records_symbol_batch_date_strategy_mode_key;

-- Step 3: Add new unique constraint including model_version
ALTER TABLE judgment_records
  ADD CONSTRAINT judgment_records_symbol_date_strategy_model_key
  UNIQUE (symbol, batch_date, strategy_mode, model_version);

-- Step 4: Add is_primary flag to distinguish primary vs shadow judgments
ALTER TABLE judgment_records
  ADD COLUMN IF NOT EXISTS is_primary BOOLEAN DEFAULT TRUE;

-- Step 5: Index for model-based queries (used by Insights UI)
CREATE INDEX IF NOT EXISTS idx_judgment_records_model
  ON judgment_records (model_version, batch_date DESC);

CREATE INDEX IF NOT EXISTS idx_judgment_records_primary
  ON judgment_records (is_primary, batch_date DESC) WHERE is_primary = TRUE;
