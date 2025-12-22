-- Migration: Add Risk-Adjusted Metrics to Portfolio Snapshot
-- This enables tracking of:
-- 1. Maximum Drawdown (MDD) - worst peak-to-trough decline
-- 2. Sharpe Ratio - risk-adjusted return (30-day rolling)
-- 3. Win Rate - percentage of profitable trades

-- Add risk metric columns to portfolio_daily_snapshot
ALTER TABLE portfolio_daily_snapshot
ADD COLUMN IF NOT EXISTS max_drawdown DECIMAL(8, 4),
ADD COLUMN IF NOT EXISTS sharpe_ratio DECIMAL(8, 4),
ADD COLUMN IF NOT EXISTS win_rate DECIMAL(5, 2);

COMMENT ON COLUMN portfolio_daily_snapshot.max_drawdown IS 'Maximum drawdown percentage from peak (negative value)';
COMMENT ON COLUMN portfolio_daily_snapshot.sharpe_ratio IS '30-day rolling Sharpe ratio (assumes 2% risk-free rate)';
COMMENT ON COLUMN portfolio_daily_snapshot.win_rate IS 'Win rate percentage based on closed trades';

-- Create a function to calculate Sharpe ratio from daily returns
-- Note: This is for reference - actual calculation done in Python
CREATE OR REPLACE FUNCTION calculate_sharpe_ratio(
    daily_returns DECIMAL[],
    risk_free_rate DECIMAL DEFAULT 0.02
)
RETURNS DECIMAL AS $$
DECLARE
    mean_return DECIMAL;
    std_dev DECIMAL;
    daily_rf DECIMAL;
    n INTEGER;
BEGIN
    n := array_length(daily_returns, 1);
    IF n < 2 THEN
        RETURN NULL;
    END IF;

    -- Calculate mean return
    SELECT AVG(r) INTO mean_return FROM unnest(daily_returns) AS r;

    -- Calculate standard deviation
    SELECT SQRT(AVG((r - mean_return) * (r - mean_return))) INTO std_dev
    FROM unnest(daily_returns) AS r;

    IF std_dev = 0 THEN
        RETURN NULL;
    END IF;

    -- Annualize: daily returns * 252, daily std * sqrt(252)
    -- Daily risk-free rate
    daily_rf := risk_free_rate / 252;

    -- Sharpe = (mean - rf) / std * sqrt(252)
    RETURN ((mean_return - daily_rf) / std_dev) * SQRT(252);
END;
$$ LANGUAGE plpgsql;
