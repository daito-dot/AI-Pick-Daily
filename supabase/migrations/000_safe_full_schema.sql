-- AI Pick Daily - Safe Full Schema
-- Handles partial state: creates only missing objects
-- Run this in Supabase SQL Editor

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
-- PORTFOLIO SNAPSHOTS
-- ============================================

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_date DATE NOT NULL,
    strategy_mode strategy_mode_type NOT NULL,
    holdings JSONB NOT NULL DEFAULT '[]',
    total_value DECIMAL(14,2),
    cash_balance DECIMAL(14,2),
    daily_return_pct DECIMAL(8,4),
    cumulative_return_pct DECIMAL(8,4),
    benchmark_return_pct DECIMAL(8,4),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(snapshot_date, strategy_mode)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_date ON portfolio_snapshots(snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_strategy ON portfolio_snapshots(strategy_mode);

-- ============================================
-- JUDGMENT RECORDS
-- ============================================

CREATE TABLE IF NOT EXISTS judgment_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    judgment_date DATE NOT NULL,
    strategy_mode strategy_mode_type NOT NULL,
    position_action TEXT,
    symbols_to_buy JSONB DEFAULT '[]',
    symbols_to_sell JSONB DEFAULT '[]',
    reasoning TEXT,
    market_context JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(judgment_date, strategy_mode)
);

CREATE INDEX IF NOT EXISTS idx_judgment_date ON judgment_records(judgment_date DESC);
CREATE INDEX IF NOT EXISTS idx_judgment_strategy ON judgment_records(strategy_mode);

-- ============================================
-- BATCH EXECUTION LOGS
-- ============================================

CREATE TABLE IF NOT EXISTS batch_execution_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_type TEXT NOT NULL,
    batch_date DATE NOT NULL,
    strategy_mode strategy_mode_type,
    status TEXT NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_batch_logs_date ON batch_execution_logs(batch_date DESC);
CREATE INDEX IF NOT EXISTS idx_batch_logs_type ON batch_execution_logs(batch_type);

-- ============================================
-- STOCK UNIVERSE
-- ============================================

CREATE TABLE IF NOT EXISTS stock_universe (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    market_type TEXT NOT NULL DEFAULT 'us',
    company_name TEXT,
    sector TEXT,
    industry TEXT,
    market_cap DECIMAL(20,2),
    is_active BOOLEAN DEFAULT TRUE,
    added_date DATE DEFAULT CURRENT_DATE,
    removed_date DATE,
    removal_reason TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, market_type)
);

CREATE INDEX IF NOT EXISTS idx_stock_universe_symbol ON stock_universe(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_universe_market ON stock_universe(market_type);
CREATE INDEX IF NOT EXISTS idx_stock_universe_active ON stock_universe(is_active) WHERE is_active = TRUE;

-- ============================================
-- RESEARCH LOGS
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
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_logs_date ON research_logs(research_date DESC);
CREATE INDEX IF NOT EXISTS idx_research_logs_type ON research_logs(research_type);

-- ============================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_picks ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_regime_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_lessons ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE judgment_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE batch_execution_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_universe ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_logs ENABLE ROW LEVEL SECURITY;

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
CREATE POLICY "Service role full access" ON portfolio_snapshots FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON performance_log FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON judgment_records FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON batch_execution_logs FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON stock_universe FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON research_logs FOR ALL USING (auth.role() = 'service_role');

-- Anon read access for public data
CREATE POLICY "Anon read access" ON daily_picks FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON stock_scores FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON market_regime_history FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON ai_lessons FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON portfolio_snapshots FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON performance_log FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON judgment_records FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON stock_universe FOR SELECT TO anon USING (true);
CREATE POLICY "Anon read access" ON research_logs FOR SELECT TO anon USING (true);

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Function to get the latest unreviewed batch for Pre-Market Review
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

INSERT INTO indicators_weights (updated_date, strategy_mode, trend_weight, momentum_weight, value_weight, sentiment_weight, version, change_reason)
VALUES
    (CURRENT_DATE, 'conservative', 0.35, 0.35, 0.20, 0.10, 1, 'Initial weights'),
    (CURRENT_DATE, 'aggressive', 0.35, 0.35, 0.20, 0.10, 1, 'Initial weights')
ON CONFLICT (updated_date, strategy_mode) DO NOTHING;
