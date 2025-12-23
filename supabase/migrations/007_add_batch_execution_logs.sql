-- Migration: Add batch execution logs for system status tracking
-- This table tracks the execution status of all batch jobs

-- Batch execution type enum
CREATE TYPE batch_type AS ENUM (
    'morning_scoring',    -- Daily scoring batch
    'evening_review',     -- Evening review batch
    'weekly_research',    -- Weekly deep research
    'llm_judgment',       -- LLM judgment processing
    'reflection'          -- Reflection analysis
);

-- Execution status enum
CREATE TYPE execution_status AS ENUM (
    'running',
    'success',
    'partial_success',    -- Some items failed but batch completed
    'failed'
);

-- Batch execution logs table
CREATE TABLE batch_execution_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_date DATE NOT NULL,
    batch_type batch_type NOT NULL,
    status execution_status NOT NULL DEFAULT 'running',

    -- Execution details
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_seconds INTEGER,

    -- Processing stats
    total_items INTEGER DEFAULT 0,
    successful_items INTEGER DEFAULT 0,
    failed_items INTEGER DEFAULT 0,

    -- Error tracking
    error_message TEXT,
    error_details JSONB,

    -- Model info
    model_used TEXT,

    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_batch_logs_date ON batch_execution_logs(batch_date DESC);
CREATE INDEX idx_batch_logs_type ON batch_execution_logs(batch_type);
CREATE INDEX idx_batch_logs_status ON batch_execution_logs(status);
CREATE INDEX idx_batch_logs_date_type ON batch_execution_logs(batch_date DESC, batch_type);

-- Unique constraint: one running batch per type per day
CREATE UNIQUE INDEX idx_batch_logs_running
ON batch_execution_logs(batch_date, batch_type)
WHERE status = 'running';

-- Function to get latest batch status for each type
CREATE OR REPLACE FUNCTION get_latest_batch_status(target_date DATE DEFAULT CURRENT_DATE)
RETURNS TABLE (
    batch_type batch_type,
    status execution_status,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    total_items INTEGER,
    successful_items INTEGER,
    failed_items INTEGER,
    error_message TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT ON (bel.batch_type)
        bel.batch_type,
        bel.status,
        bel.started_at,
        bel.completed_at,
        bel.total_items,
        bel.successful_items,
        bel.failed_items,
        bel.error_message
    FROM batch_execution_logs bel
    WHERE bel.batch_date = target_date
    ORDER BY bel.batch_type, bel.started_at DESC;
END;
$$ LANGUAGE plpgsql;

-- RLS policies
ALTER TABLE batch_execution_logs ENABLE ROW LEVEL SECURITY;

-- Allow read access for authenticated users
CREATE POLICY "Allow read access for batch logs"
ON batch_execution_logs FOR SELECT
TO authenticated, anon
USING (true);

-- Allow insert/update for service role only
CREATE POLICY "Allow service role to manage batch logs"
ON batch_execution_logs FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Comment
COMMENT ON TABLE batch_execution_logs IS 'Tracks execution status of all batch jobs for system monitoring';
