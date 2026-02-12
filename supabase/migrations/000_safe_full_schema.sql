-- AI Pick Daily - Safe Full Schema
-- Handles partial state: creates only missing objects
-- Run this in Supabase SQL Editor for fresh installs
--
-- NOTE: This file must stay in sync with migrations 001-020.
-- It produces the same final schema as running all incremental migrations.

-- ============================================
-- ENUMS (skip if exists)
-- ============================================

DO $$ BEGIN
    CREATE TYPE market_regime_type AS ENUM ('normal', 'adjustment', 'crisis');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE risk_tolerance_type AS ENUM ('conservative', 'balanced', 'aggressive');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE pick_status_type AS ENUM ('generated', 'published');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE performance_status_type AS ENUM ('win', 'loss', 'flat', 'pending');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE earnings_time_type AS ENUM ('bmo', 'amc', 'dmh', 'unknown');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE agent_name_type AS ENUM ('trend', 'momentum', 'value', 'sentiment');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE user_action_type AS ENUM ('viewed', 'liked', 'disliked');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE strategy_mode_type AS ENUM ('conservative', 'aggressive', 'jp_conservative', 'jp_aggressive');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- USERS
-- ============================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    timezone TEXT DEFAULT 'UTC',
    risk_tolerance risk_tolerance_type DEFAULT 'balanced',
    notification_enabled BOOLEAN DEFAULT TRUE,
    notification_time TIME DEFAULT '07:00'
);

-- ============================================
-- MARKET REGIME HISTORY
-- ============================================

CREATE TABLE IF NOT EXISTS market_regime_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    check_date DATE UNIQUE NOT NULL,
    vix_level DECIMAL(10,2),
    market_regime market_regime_type NOT NULL,
    sp500_sma20_deviation_pct DECIMAL(10,2),
    nyse_advance_decline_ratio DECIMAL(10,4),
    volatility_cluster_flag BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_regime_date ON market_regime_history(check_date DESC);

-- ============================================
-- DAILY PICKS
-- ============================================

CREATE TABLE IF NOT EXISTS daily_picks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_date DATE NOT NULL,
    symbols JSONB NOT NULL DEFAULT '[]',
    pick_count INTEGER DEFAULT 0,
    market_regime market_regime_type,
    status pick_status_type DEFAULT 'generated',
    strategy_mode strategy_mode_type DEFAULT 'conservative',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    UNIQUE(batch_date, strategy_mode)
);

CREATE INDEX IF NOT EXISTS idx_daily_picks_date ON daily_picks(batch_date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_picks_strategy ON daily_picks(strategy_mode);
CREATE INDEX IF NOT EXISTS idx_daily_picks_unreviewed ON daily_picks(strategy_mode, batch_date DESC) WHERE reviewed_at IS NULL AND status = 'published';

-- ============================================
-- STOCK SCORES
-- ============================================

CREATE TABLE IF NOT EXISTS stock_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_date DATE NOT NULL,
    symbol TEXT NOT NULL,
    strategy_mode strategy_mode_type DEFAULT 'conservative',

    -- Agent scores
    trend_score INTEGER CHECK (trend_score >= 0 AND trend_score <= 100),
    momentum_score INTEGER CHECK (momentum_score >= 0 AND momentum_score <= 100),
    value_score INTEGER CHECK (value_score >= 0 AND value_score <= 100),
    sentiment_score INTEGER CHECK (sentiment_score >= 0 AND sentiment_score <= 100),

    -- Composite
    composite_score INTEGER CHECK (composite_score >= 0 AND composite_score <= 100),
    percentile_rank INTEGER CHECK (percentile_rank >= 1 AND percentile_rank <= 100),

    -- Details
    reasoning TEXT,
    price_at_time DECIMAL(12,4),

    -- Earnings info
    earnings_date DATE,
    earnings_timezone TEXT,
    earnings_time_of_day earnings_time_type,
    earnings_timestamp_utc TIMESTAMPTZ,

    -- Market context
    market_regime_at_time market_regime_type,

    -- Audit trail
    cutoff_timestamp TIMESTAMPTZ,
    input_data_asof JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(batch_date, symbol, strategy_mode)
);

CREATE INDEX IF NOT EXISTS idx_stock_scores_date ON stock_scores(batch_date DESC);
CREATE INDEX IF NOT EXISTS idx_stock_scores_symbol ON stock_scores(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_scores_composite ON stock_scores(composite_score DESC);
CREATE INDEX IF NOT EXISTS idx_stock_scores_strategy ON stock_scores(strategy_mode);

-- ============================================
-- INDICATORS WEIGHTS
-- ============================================

CREATE TABLE IF NOT EXISTS indicators_weights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    updated_date DATE NOT NULL,
    strategy_mode strategy_mode_type DEFAULT 'conservative',
    trend_weight DECIMAL(5,4) DEFAULT 0.35,
    momentum_weight DECIMAL(5,4) DEFAULT 0.35,
    value_weight DECIMAL(5,4) DEFAULT 0.20,
    sentiment_weight DECIMAL(5,4) DEFAULT 0.10,
    version INTEGER DEFAULT 1,
    change_reason TEXT,
    previous_weights JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(updated_date, strategy_mode)
);

-- ============================================
-- PERFORMANCE LOG
-- ============================================

CREATE TABLE IF NOT EXISTS performance_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pick_date DATE NOT NULL,
    symbol TEXT NOT NULL,
    strategy_mode strategy_mode_type DEFAULT 'conservative',
    recommendation_open_price DECIMAL(12,4),
    recommendation_score INTEGER,
    recommendation_percentile INTEGER,
    market_regime_at_time market_regime_type,
    earnings_date DATE,
    cutoff_timestamp TIMESTAMPTZ,

    -- Entry tracking
    entry_date DATE,
    entry_price DECIMAL(12,4),

    -- Exit tracking
    exit_date DATE,
    exit_price DECIMAL(12,4),
    exit_reason TEXT,

    -- 1-day performance
    check_date_1d DATE,
    price_1d DECIMAL(12,4),
    return_pct_1d DECIMAL(8,4),
    status_1d performance_status_type DEFAULT 'pending',

    -- 5-day performance
    check_date_5d DATE,
    price_5d DECIMAL(12,4),
    return_pct_5d DECIMAL(8,4),
    status_5d performance_status_type DEFAULT 'pending',

    -- Analysis
    which_agent_was_right TEXT,
    which_agent_was_wrong TEXT,
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(pick_date, symbol, strategy_mode)
);

CREATE INDEX IF NOT EXISTS idx_performance_date ON performance_log(pick_date DESC);
CREATE INDEX IF NOT EXISTS idx_performance_symbol ON performance_log(symbol);
CREATE INDEX IF NOT EXISTS idx_performance_strategy ON performance_log(strategy_mode);

-- ============================================
-- AGENT PERFORMANCE DAILY
-- ============================================

CREATE TABLE IF NOT EXISTS agent_performance_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_date DATE NOT NULL,
    agent_name agent_name_type NOT NULL,
    strategy_mode strategy_mode_type DEFAULT 'conservative',
    win_rate_30d DECIMAL(5,4),
    alpha_vs_sp500_30d DECIMAL(8,4),
    recommendation_count_30d INTEGER,
    avg_return_when_correct DECIMAL(8,4),
    avg_loss_when_wrong DECIMAL(8,4),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(analysis_date, agent_name, strategy_mode)
);

-- ============================================
-- USER INTERACTIONS
-- ============================================

CREATE TABLE IF NOT EXISTS user_interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    stock_score_id UUID REFERENCES stock_scores(id) ON DELETE CASCADE,
    action user_action_type NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_interactions_user ON user_interactions(user_id);

-- ============================================
-- AI LESSONS
-- ============================================

CREATE TABLE IF NOT EXISTS ai_lessons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lesson_date DATE NOT NULL,
    market_type TEXT DEFAULT 'us',
    lesson_text TEXT,
    biggest_miss_symbols JSONB,
    miss_analysis TEXT,
    weight_changes JSONB,
    model_version VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(lesson_date, market_type)
);

CREATE INDEX IF NOT EXISTS idx_ai_lessons_date ON ai_lessons(lesson_date DESC);

-- ============================================
-- NEWS ARCHIVE
-- ============================================

CREATE TABLE IF NOT EXISTS news_archive (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finnhub_news_id TEXT UNIQUE,
    symbol TEXT NOT NULL,
    news_title TEXT,
    news_url TEXT,
    source TEXT,
    published_date TIMESTAMPTZ,
    article_summary TEXT,
    sentiment_score DECIMAL(5,4),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    archived_date DATE DEFAULT CURRENT_DATE
);

CREATE INDEX IF NOT EXISTS idx_news_symbol ON news_archive(symbol);
CREATE INDEX IF NOT EXISTS idx_news_date ON news_archive(published_date DESC);

-- ============================================
-- SCORING CONFIG (Dynamic Threshold Management)
-- From migration 004
-- ============================================

CREATE TABLE IF NOT EXISTS scoring_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_mode VARCHAR(20) NOT NULL UNIQUE,
    threshold DECIMAL(5, 2) NOT NULL,
    min_threshold DECIMAL(5, 2) NOT NULL DEFAULT 40,
    max_threshold DECIMAL(5, 2) NOT NULL DEFAULT 90,
    last_adjustment_date DATE,
    last_adjustment_reason TEXT,
    factor_weights JSONB DEFAULT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- THRESHOLD HISTORY (Walk-Forward Validation)
-- From migration 004
-- ============================================

CREATE TABLE IF NOT EXISTS threshold_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_mode VARCHAR(20) NOT NULL,
    old_threshold DECIMAL(5, 2) NOT NULL,
    new_threshold DECIMAL(5, 2) NOT NULL,
    adjustment_date DATE NOT NULL,
    reason TEXT NOT NULL,
    missed_opportunities_count INTEGER,
    missed_avg_return DECIMAL(8, 4),
    missed_avg_score DECIMAL(5, 2),
    picked_count INTEGER,
    picked_avg_return DECIMAL(8, 4),
    not_picked_count INTEGER,
    not_picked_avg_return DECIMAL(8, 4),
    wfe_score DECIMAL(5, 2),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_threshold_history_date
ON threshold_history (strategy_mode, adjustment_date DESC);

-- ============================================
-- VIRTUAL PORTFOLIO (Paper Trading Positions)
-- From migration 004
-- ============================================

CREATE TABLE IF NOT EXISTS virtual_portfolio (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_mode VARCHAR(20) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    entry_date DATE NOT NULL,
    entry_price DECIMAL(12, 4) NOT NULL,
    shares DECIMAL(12, 4) NOT NULL,
    position_value DECIMAL(14, 2) NOT NULL,
    entry_score INTEGER,
    status VARCHAR(20) DEFAULT 'open',
    exit_date DATE,
    exit_price DECIMAL(12, 4),
    exit_reason VARCHAR(50),
    realized_pnl DECIMAL(14, 2),
    realized_pnl_pct DECIMAL(8, 4),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(strategy_mode, symbol, entry_date)
);

CREATE INDEX IF NOT EXISTS idx_virtual_portfolio_open
ON virtual_portfolio (strategy_mode, status) WHERE status = 'open';

CREATE INDEX IF NOT EXISTS idx_virtual_portfolio_closed
ON virtual_portfolio (strategy_mode, exit_date DESC) WHERE status = 'closed';

-- ============================================
-- PORTFOLIO DAILY SNAPSHOT
-- From migration 004 (backend uses this name, NOT portfolio_snapshots)
-- ============================================

CREATE TABLE IF NOT EXISTS portfolio_daily_snapshot (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_date DATE NOT NULL,
    strategy_mode VARCHAR(20) NOT NULL,
    total_value DECIMAL(14, 2) NOT NULL,
    cash_balance DECIMAL(14, 2) NOT NULL,
    positions_value DECIMAL(14, 2) NOT NULL,
    daily_pnl DECIMAL(14, 2),
    daily_pnl_pct DECIMAL(8, 4),
    cumulative_pnl DECIMAL(14, 2),
    cumulative_pnl_pct DECIMAL(8, 4),
    sp500_daily_pct DECIMAL(8, 4),
    sp500_cumulative_pct DECIMAL(8, 4),
    alpha DECIMAL(8, 4),
    open_positions INTEGER,
    closed_today INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(snapshot_date, strategy_mode)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_snapshot_date
ON portfolio_daily_snapshot (strategy_mode, snapshot_date DESC);

-- ============================================
-- TRADE HISTORY
-- From migration 004
-- ============================================

CREATE TABLE IF NOT EXISTS trade_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_mode VARCHAR(20) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    entry_date DATE NOT NULL,
    entry_price DECIMAL(12, 4) NOT NULL,
    entry_score INTEGER,
    exit_date DATE NOT NULL,
    exit_price DECIMAL(12, 4) NOT NULL,
    shares DECIMAL(12, 4) NOT NULL,
    hold_days INTEGER NOT NULL,
    pnl DECIMAL(14, 2) NOT NULL,
    pnl_pct DECIMAL(8, 4) NOT NULL,
    exit_reason VARCHAR(50) NOT NULL,
    market_regime_at_entry VARCHAR(20),
    market_regime_at_exit VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trade_history_date
ON trade_history (strategy_mode, exit_date DESC);

CREATE INDEX IF NOT EXISTS idx_trade_history_symbol
ON trade_history (symbol, exit_date DESC);

-- ============================================
-- JUDGMENT RECORDS
-- From migration 006, with shadow model support (018) and market_type
-- ============================================

CREATE TABLE IF NOT EXISTS judgment_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL,
    batch_date DATE NOT NULL,
    strategy_mode VARCHAR(20) NOT NULL,
    decision VARCHAR(20) NOT NULL,
    confidence DECIMAL(5, 4) NOT NULL,
    score INTEGER NOT NULL,
    reasoning JSONB NOT NULL,
    key_factors JSONB NOT NULL DEFAULT '[]',
    identified_risks JSONB DEFAULT '[]',
    market_regime VARCHAR(20),
    composite_score INTEGER,
    input_summary TEXT,
    model_version VARCHAR(100),
    prompt_version VARCHAR(20),
    raw_llm_response TEXT,
    is_primary BOOLEAN DEFAULT TRUE,
    market_type VARCHAR(2) DEFAULT 'us',
    judged_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_judgment_batch_date ON judgment_records(batch_date DESC);
CREATE INDEX IF NOT EXISTS idx_judgment_strategy ON judgment_records(strategy_mode);
CREATE INDEX IF NOT EXISTS idx_judgment_records_model ON judgment_records(model_version, batch_date DESC);
CREATE INDEX IF NOT EXISTS idx_judgment_records_primary ON judgment_records(is_primary, batch_date DESC) WHERE is_primary = TRUE;
CREATE INDEX IF NOT EXISTS idx_judgment_records_factors ON judgment_records USING GIN (key_factors);

-- ============================================
-- JUDGMENT OUTCOMES (For Reflection/Learning)
-- From migration 006
-- ============================================

CREATE TABLE IF NOT EXISTS judgment_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    judgment_id UUID NOT NULL REFERENCES judgment_records(id),
    outcome_date DATE NOT NULL,
    actual_return_1d DECIMAL(8, 4),
    actual_return_5d DECIMAL(8, 4),
    actual_return_10d DECIMAL(8, 4),
    outcome_aligned BOOLEAN,
    key_factors_validated JSONB,
    missed_factors JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(judgment_id, outcome_date)
);

CREATE INDEX IF NOT EXISTS idx_judgment_outcomes_judgment ON judgment_outcomes(judgment_id);
CREATE INDEX IF NOT EXISTS idx_judgment_outcomes_aligned ON judgment_outcomes(outcome_aligned, outcome_date DESC);

-- ============================================
-- REFLECTION RECORDS (Layer 3)
-- From migration 006
-- ============================================

CREATE TABLE IF NOT EXISTS reflection_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reflection_date DATE NOT NULL,
    strategy_mode VARCHAR(20) NOT NULL,
    reflection_type VARCHAR(50) NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    total_judgments INTEGER NOT NULL,
    correct_judgments INTEGER NOT NULL,
    accuracy_rate DECIMAL(5, 4),
    patterns_identified JSONB,
    improvement_suggestions JSONB,
    model_version VARCHAR(100) NOT NULL,
    raw_llm_response TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(reflection_date, strategy_mode, reflection_type)
);

CREATE INDEX IF NOT EXISTS idx_reflection_records_date
ON reflection_records (reflection_date DESC, strategy_mode);

-- ============================================
-- BATCH EXECUTION LOGS
-- From migration 007, with model tracking (019)
-- ============================================

CREATE TABLE IF NOT EXISTS batch_execution_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_date DATE NOT NULL,
    batch_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    strategy_mode strategy_mode_type,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    total_items INTEGER DEFAULT 0,
    successful_items INTEGER DEFAULT 0,
    failed_items INTEGER DEFAULT 0,
    error_message TEXT,
    error_details JSONB,
    model_used TEXT,
    analysis_model VARCHAR(100),
    reflection_model VARCHAR(100),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_batch_logs_date ON batch_execution_logs(batch_date DESC);
CREATE INDEX IF NOT EXISTS idx_batch_logs_type ON batch_execution_logs(batch_type);
CREATE INDEX IF NOT EXISTS idx_batch_logs_status ON batch_execution_logs(status);
CREATE INDEX IF NOT EXISTS idx_batch_logs_date_type ON batch_execution_logs(batch_date DESC, batch_type);

-- ============================================
-- STOCK UNIVERSE
-- From migration 008 (backend uses "enabled", NOT "is_active")
-- ============================================

CREATE TABLE IF NOT EXISTS stock_universe (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    market_type VARCHAR(10) NOT NULL CHECK (market_type IN ('us', 'jp')),
    company_name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(100),
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT stock_universe_symbol_market_unique UNIQUE (symbol, market_type)
);

CREATE INDEX IF NOT EXISTS idx_stock_universe_market_type ON stock_universe(market_type);
CREATE INDEX IF NOT EXISTS idx_stock_universe_enabled ON stock_universe(enabled, market_type);
CREATE INDEX IF NOT EXISTS idx_stock_universe_symbol ON stock_universe(symbol);

-- Updated-at trigger for stock_universe
CREATE OR REPLACE FUNCTION update_stock_universe_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_stock_universe_updated_at ON stock_universe;
CREATE TRIGGER trigger_stock_universe_updated_at
    BEFORE UPDATE ON stock_universe
    FOR EACH ROW
    EXECUTE FUNCTION update_stock_universe_updated_at();

-- ============================================
-- RESEARCH LOGS
-- From migration 010, with model tracking (019)
-- ============================================

CREATE TABLE IF NOT EXISTS research_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_date DATE NOT NULL,
    market_type TEXT NOT NULL DEFAULT 'us',
    research_type TEXT NOT NULL,
    title TEXT,
    content TEXT,
    symbols_mentioned JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    model_version VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_logs_date ON research_logs(research_date DESC);
CREATE INDEX IF NOT EXISTS idx_research_logs_type ON research_logs(research_type);
CREATE INDEX IF NOT EXISTS idx_research_logs_model ON research_logs(model_version) WHERE model_version IS NOT NULL;

-- ============================================
-- META-MONITOR TABLES
-- From migration 016, with confidence columns (017)
-- ============================================

CREATE TABLE IF NOT EXISTS performance_rolling_metrics (
    id bigserial PRIMARY KEY,
    strategy_mode text NOT NULL,
    metric_date date NOT NULL DEFAULT CURRENT_DATE,
    win_rate_7d numeric,
    win_rate_30d numeric,
    avg_return_7d numeric,
    avg_return_30d numeric,
    missed_rate_7d numeric,
    total_judgments_7d integer,
    total_judgments_30d integer,
    avg_confidence_7d numeric,
    avg_confidence_30d numeric,
    created_at timestamptz DEFAULT now(),
    UNIQUE(strategy_mode, metric_date)
);

CREATE TABLE IF NOT EXISTS meta_interventions (
    id bigserial PRIMARY KEY,
    strategy_mode text NOT NULL,
    intervention_date timestamptz DEFAULT now(),
    trigger_type text NOT NULL,
    diagnosis jsonb NOT NULL,
    actions_taken jsonb NOT NULL,
    pre_metrics jsonb NOT NULL,
    post_metrics jsonb,
    effectiveness_score numeric,
    rolled_back boolean DEFAULT false,
    rollback_date timestamptz,
    cooldown_until timestamptz,
    created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prompt_overrides (
    id bigserial PRIMARY KEY,
    strategy_mode text NOT NULL,
    override_text text NOT NULL,
    reason text NOT NULL,
    intervention_id bigint REFERENCES meta_interventions(id),
    active boolean DEFAULT true,
    expires_at timestamptz NOT NULL,
    created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rolling_metrics_strategy_date
    ON performance_rolling_metrics(strategy_mode, metric_date DESC);

CREATE INDEX IF NOT EXISTS idx_meta_interventions_strategy_date
    ON meta_interventions(strategy_mode, intervention_date DESC);

CREATE INDEX IF NOT EXISTS idx_prompt_overrides_strategy_active
    ON prompt_overrides(strategy_mode, active) WHERE active = true;

-- ============================================
-- STRATEGY PARAMETERS
-- From migration 017
-- ============================================

CREATE TABLE IF NOT EXISTS strategy_parameters (
    id bigserial PRIMARY KEY,
    strategy_mode text NOT NULL,
    param_name text NOT NULL,
    current_value numeric NOT NULL,
    min_value numeric NOT NULL,
    max_value numeric NOT NULL,
    step numeric NOT NULL DEFAULT 1.0,
    description text,
    updated_at timestamptz DEFAULT now(),
    UNIQUE(strategy_mode, param_name)
);

CREATE TABLE IF NOT EXISTS parameter_change_log (
    id bigserial PRIMARY KEY,
    strategy_mode text NOT NULL,
    param_name text NOT NULL,
    old_value numeric,
    new_value numeric NOT NULL,
    changed_by text NOT NULL,
    reason text,
    intervention_id bigint REFERENCES meta_interventions(id),
    created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_strategy_parameters_mode
    ON strategy_parameters(strategy_mode);

CREATE INDEX IF NOT EXISTS idx_parameter_change_log_mode_date
    ON parameter_change_log(strategy_mode, created_at DESC);

-- ============================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_picks ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_regime_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_lessons ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_daily_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE judgment_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE judgment_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE reflection_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE batch_execution_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_universe ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_rolling_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_interventions ENABLE ROW LEVEL SECURITY;
ALTER TABLE prompt_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE strategy_parameters ENABLE ROW LEVEL SECURITY;
ALTER TABLE parameter_change_log ENABLE ROW LEVEL SECURITY;

-- Drop existing policies first (ignore errors if they don't exist)
DO $$ BEGIN DROP POLICY IF EXISTS "Users can view own profile" ON users; EXCEPTION WHEN undefined_object THEN NULL; END $$;
DO $$ BEGIN DROP POLICY IF EXISTS "Users can update own profile" ON users; EXCEPTION WHEN undefined_object THEN NULL; END $$;
DO $$ BEGIN DROP POLICY IF EXISTS "Users can view own interactions" ON user_interactions; EXCEPTION WHEN undefined_object THEN NULL; END $$;
DO $$ BEGIN DROP POLICY IF EXISTS "Users can insert own interactions" ON user_interactions; EXCEPTION WHEN undefined_object THEN NULL; END $$;
DO $$ BEGIN DROP POLICY IF EXISTS "Public read access" ON daily_picks; EXCEPTION WHEN undefined_object THEN NULL; END $$;
DO $$ BEGIN DROP POLICY IF EXISTS "Public read access" ON stock_scores; EXCEPTION WHEN undefined_object THEN NULL; END $$;
DO $$ BEGIN DROP POLICY IF EXISTS "Public read access" ON market_regime_history; EXCEPTION WHEN undefined_object THEN NULL; END $$;
DO $$ BEGIN DROP POLICY IF EXISTS "Public read access" ON ai_lessons; EXCEPTION WHEN undefined_object THEN NULL; END $$;

-- User policies
CREATE POLICY "Users can view own profile" ON users FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON users FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Users can view own interactions" ON user_interactions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own interactions" ON user_interactions FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Service role full access for batch jobs
CREATE POLICY "Service role full access" ON daily_picks FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON stock_scores FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON market_regime_history FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON ai_lessons FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON portfolio_daily_snapshot FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON performance_log FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON judgment_records FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON judgment_outcomes FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON reflection_records FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON batch_execution_logs FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON stock_universe FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON research_logs FOR ALL USING (auth.role() = 'service_role');

-- Anon read access for public data
CREATE POLICY "Anon read access" ON daily_picks FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON stock_scores FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON market_regime_history FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON ai_lessons FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON portfolio_daily_snapshot FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON performance_log FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON judgment_records FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON judgment_outcomes FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON stock_universe FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON research_logs FOR SELECT TO anon USING (true);

-- Meta-monitor and strategy tables: read public, write service_role (matching 020)
DO $$ BEGIN
    CREATE POLICY "Anon read access on performance_rolling_metrics"
        ON performance_rolling_metrics FOR SELECT TO anon, authenticated USING (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY "Service role write access on performance_rolling_metrics"
        ON performance_rolling_metrics FOR ALL TO service_role USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY "Anon read access on meta_interventions"
        ON meta_interventions FOR SELECT TO anon, authenticated USING (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY "Service role write access on meta_interventions"
        ON meta_interventions FOR ALL TO service_role USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY "Anon read access on prompt_overrides"
        ON prompt_overrides FOR SELECT TO anon, authenticated USING (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY "Service role write access on prompt_overrides"
        ON prompt_overrides FOR ALL TO service_role USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY "Anon read access on strategy_parameters"
        ON strategy_parameters FOR SELECT TO anon, authenticated USING (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY "Service role write access on strategy_parameters"
        ON strategy_parameters FOR ALL TO service_role USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY "Anon read access on parameter_change_log"
        ON parameter_change_log FOR SELECT TO anon, authenticated USING (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY "Service role write access on parameter_change_log"
        ON parameter_change_log FOR ALL TO service_role USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

CREATE OR REPLACE FUNCTION get_unreviewed_batch(
    p_strategy_mode TEXT,
    p_market_type TEXT DEFAULT 'us'
)
RETURNS TABLE (
    batch_id UUID,
    batch_date DATE,
    symbols JSONB,
    pick_count INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        dp.id,
        dp.batch_date,
        dp.symbols,
        dp.pick_count
    FROM daily_picks dp
    WHERE dp.strategy_mode = p_strategy_mode::strategy_mode_type
      AND dp.status = 'published'
      AND dp.reviewed_at IS NULL
      AND (p_market_type = 'us' AND dp.strategy_mode IN ('conservative', 'aggressive')
           OR p_market_type = 'jp' AND dp.strategy_mode IN ('jp_conservative', 'jp_aggressive'))
    ORDER BY dp.batch_date DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- INITIAL DATA
-- ============================================

-- Default indicator weights
INSERT INTO indicators_weights (updated_date, strategy_mode, trend_weight, momentum_weight, value_weight, sentiment_weight, version, change_reason)
VALUES
    (CURRENT_DATE, 'conservative', 0.35, 0.35, 0.20, 0.10, 1, 'Initial weights'),
    (CURRENT_DATE, 'aggressive', 0.35, 0.35, 0.20, 0.10, 1, 'Initial weights')
ON CONFLICT (updated_date, strategy_mode) DO NOTHING;

-- Scoring config with correct thresholds (V1=60, V2=45)
INSERT INTO scoring_config (strategy_mode, threshold, min_threshold, max_threshold) VALUES
    ('conservative', 60, 40, 80),
    ('aggressive', 45, 30, 90)
ON CONFLICT (strategy_mode) DO NOTHING;

-- Initial portfolio snapshots with $100,000 starting capital
INSERT INTO portfolio_daily_snapshot (
    snapshot_date, strategy_mode, total_value, cash_balance, positions_value,
    daily_pnl, daily_pnl_pct, cumulative_pnl, cumulative_pnl_pct,
    sp500_cumulative_pct, alpha, open_positions
) VALUES
    (CURRENT_DATE, 'conservative', 100000.00, 100000.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0),
    (CURRENT_DATE, 'aggressive', 100000.00, 100000.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0)
ON CONFLICT (snapshot_date, strategy_mode) DO NOTHING;

-- Strategy parameters seed data (15 params × 4 strategies)
DO $$
DECLARE
    strategies text[] := ARRAY['conservative', 'aggressive', 'jp_conservative', 'jp_aggressive'];
    s text;
BEGIN
    FOREACH s IN ARRAY strategies
    LOOP
        INSERT INTO strategy_parameters (strategy_mode, param_name, current_value, min_value, max_value, step, description) VALUES
            (s, 'take_profit_pct',            8.0,   3.0,  20.0,  2.0,  '利確閾値(%)'),
            (s, 'stop_loss_pct',             -7.0, -15.0,  -3.0,  2.0,  '損切閾値(%)'),
            (s, 'max_hold_days',             10,     5,    20,    2,     'ソフト最大保有日数'),
            (s, 'absolute_max_hold_days',    15,    10,    30,    3,     'ハード最大保有日数'),
            (s, 'max_positions',             10,     3,    20,    2,     '最大同時保有数'),
            (s, 'mdd_warning_pct',          -10.0, -20.0,  -5.0,  2.0,  'MDD警告閾値(%)'),
            (s, 'mdd_stop_new_pct',         -15.0, -25.0,  -8.0,  2.0,  'MDD新規停止閾値(%)'),
            (s, 'win_rate_drop_ratio',        0.7,   0.5,   0.9,  0.05, '勝率低下検知比率'),
            (s, 'return_decline_threshold',  -1.0,  -3.0,   0.0,  0.5,  'リターン悪化閾値(%)'),
            (s, 'missed_spike_threshold',     0.30,  0.15,  0.50, 0.05, '見逃し率閾値'),
            (s, 'cooldown_days',              3,     1,     7,    1,     '介入間クールダウン(日)'),
            (s, 'prompt_expiry_days',         14,    7,    30,    3,     'Override有効期間(日)'),
            (s, 'max_threshold_change',       10,    3,    15,    2,     '閾値変更上限'),
            (s, 'max_weight_change',          0.1,   0.03,  0.2,  0.02, '重み変更上限'),
            (s, 'confidence_drift_threshold', 0.05,  0.02,  0.15, 0.01, '信頼度ドリフト閾値')
        ON CONFLICT (strategy_mode, param_name) DO NOTHING;
    END LOOP;
END $$;
