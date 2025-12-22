-- Migration: Add Feedback Loop and Portfolio Management
-- This enables:
-- 1. Dynamic threshold management (scoring_config)
-- 2. Threshold change history for Walk-Forward validation
-- 3. Paper trading simulation tables

-- ============================================
-- 1. SCORING CONFIG (Dynamic Threshold Management)
-- ============================================

CREATE TABLE IF NOT EXISTS scoring_config (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  strategy_mode VARCHAR(20) NOT NULL UNIQUE,  -- 'conservative' | 'aggressive'
  threshold DECIMAL(5, 2) NOT NULL,  -- Current threshold (initial: conservative=60, aggressive=75)
  min_threshold DECIMAL(5, 2) NOT NULL DEFAULT 40,  -- Lower bound
  max_threshold DECIMAL(5, 2) NOT NULL DEFAULT 90,  -- Upper bound
  last_adjustment_date DATE,
  last_adjustment_reason TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Initial configuration
INSERT INTO scoring_config (strategy_mode, threshold, min_threshold, max_threshold) VALUES
  ('conservative', 60, 40, 80),
  ('aggressive', 75, 50, 90)
ON CONFLICT (strategy_mode) DO NOTHING;

COMMENT ON TABLE scoring_config IS 'Dynamic scoring thresholds - updated by feedback loop';
COMMENT ON COLUMN scoring_config.threshold IS 'Current score threshold for picking stocks';

-- ============================================
-- 2. THRESHOLD HISTORY (Walk-Forward Validation)
-- ============================================

CREATE TABLE IF NOT EXISTS threshold_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  strategy_mode VARCHAR(20) NOT NULL,
  old_threshold DECIMAL(5, 2) NOT NULL,
  new_threshold DECIMAL(5, 2) NOT NULL,
  adjustment_date DATE NOT NULL,
  reason TEXT NOT NULL,
  -- Evidence data for the change
  missed_opportunities_count INTEGER,
  missed_avg_return DECIMAL(8, 4),
  missed_avg_score DECIMAL(5, 2),
  picked_count INTEGER,
  picked_avg_return DECIMAL(8, 4),
  not_picked_count INTEGER,
  not_picked_avg_return DECIMAL(8, 4),
  -- Walk-Forward Efficiency score
  wfe_score DECIMAL(5, 2),  -- Expected efficiency (>50% is valid)
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_threshold_history_date
ON threshold_history (strategy_mode, adjustment_date DESC);

COMMENT ON TABLE threshold_history IS 'History of threshold adjustments for audit and rollback';

-- ============================================
-- 3. VIRTUAL PORTFOLIO (Paper Trading Positions)
-- ============================================

CREATE TABLE IF NOT EXISTS virtual_portfolio (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  strategy_mode VARCHAR(20) NOT NULL,  -- 'conservative' | 'aggressive'
  symbol VARCHAR(10) NOT NULL,
  entry_date DATE NOT NULL,
  entry_price DECIMAL(12, 4) NOT NULL,
  shares DECIMAL(12, 4) NOT NULL,
  position_value DECIMAL(14, 2) NOT NULL,
  entry_score INTEGER,  -- Score at entry
  status VARCHAR(20) DEFAULT 'open',  -- 'open' | 'closed'
  exit_date DATE,
  exit_price DECIMAL(12, 4),
  exit_reason VARCHAR(50),  -- 'score_drop' | 'stop_loss' | 'take_profit' | 'max_hold' | 'regime_change'
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

COMMENT ON TABLE virtual_portfolio IS 'Paper trading positions for simulation';
COMMENT ON COLUMN virtual_portfolio.exit_reason IS 'Why position was closed: score_drop, stop_loss, take_profit, max_hold, regime_change';

-- ============================================
-- 4. PORTFOLIO DAILY SNAPSHOT
-- ============================================

CREATE TABLE IF NOT EXISTS portfolio_daily_snapshot (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  snapshot_date DATE NOT NULL,
  strategy_mode VARCHAR(20) NOT NULL,
  -- Portfolio values
  total_value DECIMAL(14, 2) NOT NULL,
  cash_balance DECIMAL(14, 2) NOT NULL,
  positions_value DECIMAL(14, 2) NOT NULL,
  -- Daily P&L
  daily_pnl DECIMAL(14, 2),
  daily_pnl_pct DECIMAL(8, 4),
  -- Cumulative P&L
  cumulative_pnl DECIMAL(14, 2),
  cumulative_pnl_pct DECIMAL(8, 4),
  -- Benchmark comparison
  sp500_daily_pct DECIMAL(8, 4),
  sp500_cumulative_pct DECIMAL(8, 4),
  alpha DECIMAL(8, 4),  -- cumulative_pnl_pct - sp500_cumulative_pct
  -- Position counts
  open_positions INTEGER,
  closed_today INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(snapshot_date, strategy_mode)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_snapshot_date
ON portfolio_daily_snapshot (strategy_mode, snapshot_date DESC);

COMMENT ON TABLE portfolio_daily_snapshot IS 'Daily snapshot of portfolio values for equity curve';

-- ============================================
-- 5. TRADE HISTORY (Closed Positions)
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

COMMENT ON TABLE trade_history IS 'Complete history of closed trades for performance analysis';

-- ============================================
-- 6. INITIAL PORTFOLIO SETUP
-- ============================================

-- Insert initial portfolio snapshots with ¥100,000 starting capital
INSERT INTO portfolio_daily_snapshot (
  snapshot_date,
  strategy_mode,
  total_value,
  cash_balance,
  positions_value,
  daily_pnl,
  daily_pnl_pct,
  cumulative_pnl,
  cumulative_pnl_pct,
  sp500_cumulative_pct,
  alpha,
  open_positions
) VALUES
  (CURRENT_DATE, 'conservative', 100000.00, 100000.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0),
  (CURRENT_DATE, 'aggressive', 100000.00, 100000.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0)
ON CONFLICT (snapshot_date, strategy_mode) DO NOTHING;
