-- Migration: Add Judgment Records for LLM-based Investment Judgment
-- This enables Layer 2 of the 4-layer architecture:
-- 1. Store full reasoning traces for transparency
-- 2. Track key factors that influenced decisions
-- 3. Enable later reflection and learning (Layer 3)

-- ============================================
-- 1. JUDGMENT RECORDS (Core judgment storage)
-- ============================================

CREATE TABLE IF NOT EXISTS judgment_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Basic identification
  symbol VARCHAR(10) NOT NULL,
  batch_date DATE NOT NULL,
  strategy_mode VARCHAR(20) NOT NULL,  -- 'conservative' | 'aggressive'

  -- Decision output
  decision VARCHAR(20) NOT NULL,  -- 'buy' | 'hold' | 'avoid'
  confidence DECIMAL(5, 4) NOT NULL,  -- 0.0-1.0
  score INTEGER NOT NULL,  -- 0-100 composite score

  -- Reasoning trace (JSON for flexibility)
  reasoning JSONB NOT NULL,
  /* reasoning structure:
  {
    "steps": ["Step 1...", "Step 2..."],
    "top_factors": ["Factor 1", "Factor 2", "Factor 3"],
    "decision_point": "The key insight that led to this decision",
    "uncertainties": ["Uncertainty 1", "Uncertainty 2"],
    "confidence_explanation": "Why this confidence level"
  }
  */

  -- Key factors (array of structured factors)
  key_factors JSONB NOT NULL DEFAULT '[]',
  /* key_factors structure:
  [
    {
      "factor_type": "fundamental|technical|sentiment|macro|catalyst",
      "description": "What this factor is",
      "source": "Where this came from",
      "impact": "positive|negative|neutral",
      "weight": 0.0-1.0,
      "verifiable": true|false,
      "raw_data": {...} -- optional raw data
    }
  ]
  */

  -- Identified risks
  identified_risks JSONB NOT NULL DEFAULT '[]',  -- Array of risk descriptions

  -- Context at judgment time
  market_regime VARCHAR(20) NOT NULL,
  input_summary TEXT,  -- Brief summary of input data

  -- Model metadata
  model_version VARCHAR(100) NOT NULL,
  prompt_version VARCHAR(20) NOT NULL,

  -- Raw response for debugging/audit
  raw_llm_response TEXT,

  -- Timestamps
  judged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW(),

  -- Constraints
  UNIQUE(symbol, batch_date, strategy_mode)
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_judgment_records_date
ON judgment_records (batch_date DESC, strategy_mode);

CREATE INDEX IF NOT EXISTS idx_judgment_records_symbol
ON judgment_records (symbol, batch_date DESC);

CREATE INDEX IF NOT EXISTS idx_judgment_records_decision
ON judgment_records (decision, batch_date DESC);

CREATE INDEX IF NOT EXISTS idx_judgment_records_confidence
ON judgment_records (confidence DESC, batch_date DESC);

-- GIN index for JSONB queries on key_factors
CREATE INDEX IF NOT EXISTS idx_judgment_records_factors
ON judgment_records USING GIN (key_factors);

COMMENT ON TABLE judgment_records IS 'LLM-generated investment judgments with full reasoning traces';
COMMENT ON COLUMN judgment_records.reasoning IS 'Chain-of-Thought reasoning trace in JSON format';
COMMENT ON COLUMN judgment_records.key_factors IS 'Array of key factors that influenced the decision';
COMMENT ON COLUMN judgment_records.confidence IS 'Model confidence in the decision (0.0-1.0)';


-- ============================================
-- 2. JUDGMENT OUTCOMES (For Reflection/Learning)
-- ============================================

CREATE TABLE IF NOT EXISTS judgment_outcomes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Link to original judgment
  judgment_id UUID NOT NULL REFERENCES judgment_records(id),

  -- Outcome data
  outcome_date DATE NOT NULL,
  actual_return_1d DECIMAL(8, 4),
  actual_return_5d DECIMAL(8, 4),
  actual_return_10d DECIMAL(8, 4),

  -- Was the judgment correct?
  outcome_aligned BOOLEAN,  -- Did reality match prediction?

  -- Post-hoc analysis
  key_factors_validated JSONB,  -- Which factors proved correct?
  missed_factors JSONB,  -- What factors were missed?

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(judgment_id, outcome_date)
);

CREATE INDEX IF NOT EXISTS idx_judgment_outcomes_judgment
ON judgment_outcomes (judgment_id);

CREATE INDEX IF NOT EXISTS idx_judgment_outcomes_aligned
ON judgment_outcomes (outcome_aligned, outcome_date DESC);

COMMENT ON TABLE judgment_outcomes IS 'Actual outcomes for judgments, used for reflection and learning';


-- ============================================
-- 3. REFLECTION RECORDS (Layer 3 support)
-- ============================================

CREATE TABLE IF NOT EXISTS reflection_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Reflection scope
  reflection_date DATE NOT NULL,
  strategy_mode VARCHAR(20) NOT NULL,
  reflection_type VARCHAR(50) NOT NULL,  -- 'weekly' | 'monthly' | 'post_trade'

  -- Analysis period
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,

  -- Performance summary
  total_judgments INTEGER NOT NULL,
  correct_judgments INTEGER NOT NULL,
  accuracy_rate DECIMAL(5, 4),

  -- Pattern analysis (JSON)
  patterns_identified JSONB,
  /* patterns structure:
  {
    "successful_patterns": [...],
    "failure_patterns": [...],
    "factor_reliability": {...},
    "regime_performance": {...}
  }
  */

  -- Improvement suggestions
  improvement_suggestions JSONB,

  -- Model metadata
  model_version VARCHAR(100) NOT NULL,

  -- Raw response for audit
  raw_llm_response TEXT,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(reflection_date, strategy_mode, reflection_type)
);

CREATE INDEX IF NOT EXISTS idx_reflection_records_date
ON reflection_records (reflection_date DESC, strategy_mode);

COMMENT ON TABLE reflection_records IS 'LLM reflection analysis for continuous improvement';
