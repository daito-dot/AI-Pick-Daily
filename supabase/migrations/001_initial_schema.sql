-- AI Pick Daily - Database Schema
-- Run this in Supabase SQL Editor

-- ============================================
-- ENUMS
-- ============================================

CREATE TYPE market_regime_type AS ENUM ('normal', 'adjustment', 'crisis');
CREATE TYPE risk_tolerance_type AS ENUM ('conservative', 'balanced', 'aggressive');
CREATE TYPE pick_status_type AS ENUM ('generated', 'published');
CREATE TYPE performance_status_type AS ENUM ('win', 'loss', 'flat', 'pending');
CREATE TYPE earnings_time_type AS ENUM ('bmo', 'amc', 'dmh', 'unknown');
CREATE TYPE agent_name_type AS ENUM ('trend', 'momentum', 'value', 'sentiment');
CREATE TYPE user_action_type AS ENUM ('viewed', 'liked', 'disliked');

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
    nyse_advance_decline_ratio DECIMAL(10,4),  -- Phase 2
    volatility_cluster_flag BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_market_regime_date ON market_regime_history(check_date DESC);

-- ============================================
-- DAILY PICKS
-- ============================================

CREATE TABLE IF NOT EXISTS daily_picks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_date DATE UNIQUE NOT NULL,
    symbols JSONB NOT NULL DEFAULT '[]',
    pick_count INTEGER DEFAULT 0,
    market_regime market_regime_type,
    status pick_status_type DEFAULT 'generated',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_daily_picks_date ON daily_picks(batch_date DESC);

-- ============================================
-- STOCK SCORES
-- ============================================

CREATE TABLE IF NOT EXISTS stock_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_date DATE NOT NULL,
    symbol TEXT NOT NULL,

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
    price_at_time DECIMAL(12,4),  -- Open price on recommendation day

    -- Earnings info
    earnings_date DATE,
    earnings_timezone TEXT,
    earnings_time_of_day earnings_time_type,
    earnings_timestamp_utc TIMESTAMPTZ,

    -- Market context
    market_regime_at_time market_regime_type,

    -- Audit trail (Lookahead Bias prevention)
    cutoff_timestamp TIMESTAMPTZ,
    input_data_asof JSONB,  -- {prices_asof, news_asof, fundamentals_asof, earnings_asof}

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(batch_date, symbol)
);

CREATE INDEX idx_stock_scores_date ON stock_scores(batch_date DESC);
CREATE INDEX idx_stock_scores_symbol ON stock_scores(symbol);
CREATE INDEX idx_stock_scores_composite ON stock_scores(composite_score DESC);

-- ============================================
-- INDICATORS WEIGHTS
-- ============================================

CREATE TABLE IF NOT EXISTS indicators_weights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    updated_date DATE UNIQUE NOT NULL,
    trend_weight DECIMAL(5,4) DEFAULT 0.35 CHECK (trend_weight >= 0.20 AND trend_weight <= 0.45),
    momentum_weight DECIMAL(5,4) DEFAULT 0.35 CHECK (momentum_weight >= 0.20 AND momentum_weight <= 0.45),
    value_weight DECIMAL(5,4) DEFAULT 0.20 CHECK (value_weight >= 0.10 AND value_weight <= 0.30),
    sentiment_weight DECIMAL(5,4) DEFAULT 0.10 CHECK (sentiment_weight >= 0.05 AND sentiment_weight <= 0.20),
    version INTEGER DEFAULT 1,
    change_reason TEXT,
    previous_weights JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- PERFORMANCE LOG
-- ============================================

CREATE TABLE IF NOT EXISTS performance_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pick_date DATE NOT NULL,
    symbol TEXT NOT NULL,
    recommendation_open_price DECIMAL(12,4),
    recommendation_score INTEGER,
    recommendation_percentile INTEGER,
    market_regime_at_time market_regime_type,
    earnings_date DATE,
    cutoff_timestamp TIMESTAMPTZ,

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

    UNIQUE(pick_date, symbol)
);

CREATE INDEX idx_performance_date ON performance_log(pick_date DESC);
CREATE INDEX idx_performance_symbol ON performance_log(symbol);

-- ============================================
-- AGENT PERFORMANCE DAILY
-- ============================================

CREATE TABLE IF NOT EXISTS agent_performance_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_date DATE NOT NULL,
    agent_name agent_name_type NOT NULL,
    win_rate_30d DECIMAL(5,4),
    alpha_vs_sp500_30d DECIMAL(8,4),
    recommendation_count_30d INTEGER,
    avg_return_when_correct DECIMAL(8,4),
    avg_loss_when_wrong DECIMAL(8,4),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(analysis_date, agent_name)
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

CREATE INDEX idx_user_interactions_user ON user_interactions(user_id);

-- ============================================
-- AI LESSONS
-- ============================================

CREATE TABLE IF NOT EXISTS ai_lessons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lesson_date DATE UNIQUE NOT NULL,
    lesson_text TEXT,
    biggest_miss_symbols JSONB,
    miss_analysis TEXT,
    weight_changes JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ai_lessons_date ON ai_lessons(lesson_date DESC);

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

CREATE INDEX idx_news_symbol ON news_archive(symbol);
CREATE INDEX idx_news_date ON news_archive(published_date DESC);

-- ============================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================

-- Enable RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_interactions ENABLE ROW LEVEL SECURITY;

-- Users can only see their own data
CREATE POLICY "Users can view own profile" ON users
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON users
    FOR UPDATE USING (auth.uid() = id);

-- User interactions are private
CREATE POLICY "Users can view own interactions" ON user_interactions
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own interactions" ON user_interactions
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Public read access for market data
CREATE POLICY "Public read access" ON daily_picks
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Public read access" ON stock_scores
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Public read access" ON market_regime_history
    FOR SELECT TO authenticated USING (true);

CREATE POLICY "Public read access" ON ai_lessons
    FOR SELECT TO authenticated USING (true);

-- ============================================
-- INITIAL DATA
-- ============================================

-- Insert default weights
INSERT INTO indicators_weights (updated_date, trend_weight, momentum_weight, value_weight, sentiment_weight, version, change_reason)
VALUES (CURRENT_DATE, 0.35, 0.35, 0.20, 0.10, 1, 'Initial weights')
ON CONFLICT (updated_date) DO NOTHING;
