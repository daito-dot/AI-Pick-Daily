-- Migration: Add research logs and judgment overrides
-- Tracks manual research sessions and any resulting judgment changes

-- Research logs table
CREATE TABLE IF NOT EXISTS research_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Research context
    research_type VARCHAR(20) NOT NULL CHECK (research_type IN ('symbol', 'all', 'market', 'jp', 'us')),
    symbol VARCHAR(20),  -- NULL for non-symbol research (all, market, jp, us)

    -- Research results (from DB query)
    system_data JSONB,  -- Data fetched from our DB at research time

    -- External research (news, etc.)
    external_findings TEXT,  -- Summary of web search findings
    news_sentiment VARCHAR(20) CHECK (news_sentiment IN ('positive', 'negative', 'neutral', 'mixed')),

    -- Comparison with system judgment
    system_judgment VARCHAR(10),  -- BUY/HOLD/AVOID at research time
    system_confidence DECIMAL(5, 4),
    sentiment_alignment VARCHAR(20) CHECK (sentiment_alignment IN ('aligned', 'conflicting', 'partial', 'unknown')),

    -- User's conclusion after research
    user_conclusion TEXT,  -- User's notes/conclusion
    override_decision VARCHAR(10) CHECK (override_decision IN ('buy', 'hold', 'avoid', 'no_change')),
    override_reason TEXT,

    -- Metadata
    researched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    batch_date DATE,  -- Which batch this research relates to

    -- Indexes
    CONSTRAINT symbol_required_for_symbol_type CHECK (
        research_type != 'symbol' OR symbol IS NOT NULL
    )
);

-- Indexes for efficient querying
CREATE INDEX idx_research_logs_symbol ON research_logs(symbol) WHERE symbol IS NOT NULL;
CREATE INDEX idx_research_logs_type ON research_logs(research_type);
CREATE INDEX idx_research_logs_date ON research_logs(researched_at DESC);
CREATE INDEX idx_research_logs_batch ON research_logs(batch_date);
CREATE INDEX idx_research_logs_override ON research_logs(override_decision) WHERE override_decision IS NOT NULL AND override_decision != 'no_change';

-- Judgment overrides view (for easy tracking of when research changed decisions)
CREATE OR REPLACE VIEW v_judgment_overrides AS
SELECT
    rl.id,
    rl.symbol,
    rl.batch_date,
    rl.system_judgment,
    rl.system_confidence,
    rl.override_decision,
    rl.override_reason,
    rl.news_sentiment,
    rl.sentiment_alignment,
    rl.researched_at,
    -- Calculate if this was actually a change
    CASE
        WHEN rl.override_decision IS NOT NULL
             AND rl.override_decision != 'no_change'
             AND rl.override_decision != LOWER(rl.system_judgment)
        THEN TRUE
        ELSE FALSE
    END as judgment_changed
FROM research_logs rl
WHERE rl.research_type = 'symbol'
  AND rl.override_decision IS NOT NULL
ORDER BY rl.researched_at DESC;

-- Research stats view
CREATE OR REPLACE VIEW v_research_stats AS
SELECT
    DATE(researched_at) as research_date,
    COUNT(*) as total_researches,
    COUNT(*) FILTER (WHERE research_type = 'symbol') as symbol_researches,
    COUNT(*) FILTER (WHERE research_type IN ('all', 'market', 'jp', 'us')) as overview_researches,
    COUNT(*) FILTER (WHERE override_decision IS NOT NULL AND override_decision != 'no_change') as overrides,
    COUNT(*) FILTER (WHERE sentiment_alignment = 'conflicting') as conflicting_signals
FROM research_logs
GROUP BY DATE(researched_at)
ORDER BY research_date DESC;

-- Enable RLS
ALTER TABLE research_logs ENABLE ROW LEVEL SECURITY;

-- Allow public read (for dashboard)
CREATE POLICY "Allow public read on research_logs"
    ON research_logs FOR SELECT
    USING (true);

-- Allow authenticated insert/update
CREATE POLICY "Allow authenticated insert on research_logs"
    ON research_logs FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Allow authenticated update on research_logs"
    ON research_logs FOR UPDATE
    USING (true);

COMMENT ON TABLE research_logs IS 'Tracks manual research sessions and judgment overrides';
COMMENT ON COLUMN research_logs.research_type IS 'Type of research: symbol (individual stock), all, market, jp, us';
COMMENT ON COLUMN research_logs.system_data IS 'Snapshot of system data at research time (judgment, scores, etc.)';
COMMENT ON COLUMN research_logs.external_findings IS 'Summary of external research (news, analyst reports)';
COMMENT ON COLUMN research_logs.override_decision IS 'User decision after research: buy/hold/avoid/no_change';
COMMENT ON VIEW v_judgment_overrides IS 'Tracks cases where research led to a different decision than the system';
