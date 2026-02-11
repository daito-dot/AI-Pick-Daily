-- Migration: Add model tracking to remaining tables
-- Ensures ALL LLM-generated data records which model produced the output

-- 1. research_logs: track which model generated research
ALTER TABLE research_logs ADD COLUMN IF NOT EXISTS model_version VARCHAR(100);

-- 2. ai_lessons: track which model generated lessons
ALTER TABLE ai_lessons ADD COLUMN IF NOT EXISTS model_version VARCHAR(100);

-- 3. batch_execution_logs: track analysis and reflection models (scoring model already tracked as model_used)
ALTER TABLE batch_execution_logs
  ADD COLUMN IF NOT EXISTS analysis_model VARCHAR(100),
  ADD COLUMN IF NOT EXISTS reflection_model VARCHAR(100);

-- 4. Index for model-based queries on research_logs
CREATE INDEX IF NOT EXISTS idx_research_logs_model
  ON research_logs(model_version) WHERE model_version IS NOT NULL;
