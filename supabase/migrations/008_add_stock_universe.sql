-- Migration: Add Stock Universe Table
-- Description: External stock symbol management for dynamic symbol lists
-- Date: 2024-12-24

-- =============================================================================
-- Stock Universe Table
-- =============================================================================
-- Stores the list of stock symbols to be processed by the scoring system.
-- Symbols can be loaded from this table as an alternative to YAML config.

CREATE TABLE IF NOT EXISTS stock_universe (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,

    -- Symbol identification
    symbol VARCHAR(20) NOT NULL,
    market_type VARCHAR(10) NOT NULL CHECK (market_type IN ('us', 'jp')),

    -- Symbol metadata
    company_name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(100),

    -- Status
    enabled BOOLEAN DEFAULT TRUE,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique constraint
    CONSTRAINT stock_universe_symbol_market_unique UNIQUE (symbol, market_type)
);

-- =============================================================================
-- Indexes
-- =============================================================================

-- Index for querying by market type
CREATE INDEX IF NOT EXISTS idx_stock_universe_market_type
ON stock_universe(market_type);

-- Index for enabled symbols (most common query)
CREATE INDEX IF NOT EXISTS idx_stock_universe_enabled
ON stock_universe(enabled, market_type);

-- Index for symbol lookup
CREATE INDEX IF NOT EXISTS idx_stock_universe_symbol
ON stock_universe(symbol);

-- =============================================================================
-- Updated At Trigger
-- =============================================================================

-- Create trigger function if not exists
CREATE OR REPLACE FUNCTION update_stock_universe_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger
DROP TRIGGER IF EXISTS trigger_stock_universe_updated_at ON stock_universe;
CREATE TRIGGER trigger_stock_universe_updated_at
    BEFORE UPDATE ON stock_universe
    FOR EACH ROW
    EXECUTE FUNCTION update_stock_universe_updated_at();

-- =============================================================================
-- Initial Data (US Stocks - S&P 500 Top Holdings)
-- =============================================================================

INSERT INTO stock_universe (symbol, market_type, company_name, sector, enabled) VALUES
    -- Technology Giants
    ('AAPL', 'us', 'Apple Inc.', 'Technology', TRUE),
    ('MSFT', 'us', 'Microsoft Corporation', 'Technology', TRUE),
    ('AMZN', 'us', 'Amazon.com Inc.', 'Consumer Cyclical', TRUE),
    ('NVDA', 'us', 'NVIDIA Corporation', 'Technology', TRUE),
    ('GOOGL', 'us', 'Alphabet Inc. Class A', 'Technology', TRUE),
    ('META', 'us', 'Meta Platforms Inc.', 'Technology', TRUE),
    ('TSLA', 'us', 'Tesla Inc.', 'Consumer Cyclical', TRUE),

    -- Financial
    ('BRK.B', 'us', 'Berkshire Hathaway Class B', 'Financial', TRUE),
    ('JPM', 'us', 'JPMorgan Chase & Co.', 'Financial', TRUE),
    ('V', 'us', 'Visa Inc.', 'Financial', TRUE),
    ('MA', 'us', 'Mastercard Inc.', 'Financial', TRUE),
    ('MS', 'us', 'Morgan Stanley', 'Financial', TRUE),

    -- Healthcare
    ('UNH', 'us', 'UnitedHealth Group Inc.', 'Healthcare', TRUE),
    ('JNJ', 'us', 'Johnson & Johnson', 'Healthcare', TRUE),
    ('MRK', 'us', 'Merck & Co. Inc.', 'Healthcare', TRUE),
    ('ABBV', 'us', 'AbbVie Inc.', 'Healthcare', TRUE),
    ('LLY', 'us', 'Eli Lilly and Company', 'Healthcare', TRUE),
    ('TMO', 'us', 'Thermo Fisher Scientific', 'Healthcare', TRUE),
    ('ABT', 'us', 'Abbott Laboratories', 'Healthcare', TRUE),
    ('DHR', 'us', 'Danaher Corporation', 'Healthcare', TRUE),

    -- Consumer
    ('PG', 'us', 'Procter & Gamble Co.', 'Consumer Defensive', TRUE),
    ('KO', 'us', 'Coca-Cola Company', 'Consumer Defensive', TRUE),
    ('PEP', 'us', 'PepsiCo Inc.', 'Consumer Defensive', TRUE),
    ('COST', 'us', 'Costco Wholesale Corporation', 'Consumer Defensive', TRUE),
    ('WMT', 'us', 'Walmart Inc.', 'Consumer Defensive', TRUE),
    ('MCD', 'us', 'McDonald''s Corporation', 'Consumer Cyclical', TRUE),
    ('NKE', 'us', 'Nike Inc.', 'Consumer Cyclical', TRUE),
    ('HD', 'us', 'Home Depot Inc.', 'Consumer Cyclical', TRUE),
    ('LOW', 'us', 'Lowe''s Companies Inc.', 'Consumer Cyclical', TRUE),

    -- Energy
    ('XOM', 'us', 'Exxon Mobil Corporation', 'Energy', TRUE),
    ('CVX', 'us', 'Chevron Corporation', 'Energy', TRUE),

    -- Technology & Semiconductors
    ('AVGO', 'us', 'Broadcom Inc.', 'Technology', TRUE),
    ('CRM', 'us', 'Salesforce Inc.', 'Technology', TRUE),
    ('ACN', 'us', 'Accenture plc', 'Technology', TRUE),
    ('ADBE', 'us', 'Adobe Inc.', 'Technology', TRUE),
    ('ORCL', 'us', 'Oracle Corporation', 'Technology', TRUE),
    ('TXN', 'us', 'Texas Instruments Inc.', 'Technology', TRUE),
    ('CSCO', 'us', 'Cisco Systems Inc.', 'Technology', TRUE),
    ('INTC', 'us', 'Intel Corporation', 'Technology', TRUE),
    ('QCOM', 'us', 'Qualcomm Inc.', 'Technology', TRUE),

    -- Industrial & Utilities
    ('LIN', 'us', 'Linde plc', 'Basic Materials', TRUE),
    ('NEE', 'us', 'NextEra Energy Inc.', 'Utilities', TRUE),
    ('HON', 'us', 'Honeywell International Inc.', 'Industrials', TRUE),
    ('RTX', 'us', 'RTX Corporation', 'Industrials', TRUE),
    ('BA', 'us', 'Boeing Company', 'Industrials', TRUE),
    ('UPS', 'us', 'United Parcel Service Inc.', 'Industrials', TRUE),

    -- Telecom & Others
    ('PM', 'us', 'Philip Morris International', 'Consumer Defensive', TRUE),
    ('VZ', 'us', 'Verizon Communications Inc.', 'Telecom', TRUE),
    ('CMCSA', 'us', 'Comcast Corporation', 'Telecom', TRUE),
    ('SPGI', 'us', 'S&P Global Inc.', 'Financial', TRUE)
ON CONFLICT (symbol, market_type) DO UPDATE SET
    company_name = EXCLUDED.company_name,
    sector = EXCLUDED.sector,
    updated_at = NOW();

-- =============================================================================
-- Initial Data (Japan Stocks - Nikkei 225 Selection)
-- =============================================================================

INSERT INTO stock_universe (symbol, market_type, company_name, sector, enabled) VALUES
    -- Automotive
    ('7203.T', 'jp', 'Toyota Motor Corporation', 'Automotive', TRUE),
    ('7267.T', 'jp', 'Honda Motor Co.', 'Automotive', TRUE),
    ('7269.T', 'jp', 'Suzuki Motor Corporation', 'Automotive', TRUE),
    ('7201.T', 'jp', 'Nissan Motor Co.', 'Automotive', TRUE),

    -- Electronics & Technology
    ('6758.T', 'jp', 'Sony Group Corporation', 'Technology', TRUE),
    ('6861.T', 'jp', 'Keyence Corporation', 'Technology', TRUE),
    ('6501.T', 'jp', 'Hitachi Ltd.', 'Technology', TRUE),
    ('6702.T', 'jp', 'Fujitsu Limited', 'Technology', TRUE),
    ('6503.T', 'jp', 'Mitsubishi Electric Corporation', 'Technology', TRUE),
    ('6752.T', 'jp', 'Panasonic Holdings Corporation', 'Technology', TRUE),
    ('6594.T', 'jp', 'Nidec Corporation', 'Technology', TRUE),

    -- Semiconductors
    ('6857.T', 'jp', 'Advantest Corporation', 'Technology', TRUE),
    ('8035.T', 'jp', 'Tokyo Electron Limited', 'Technology', TRUE),
    ('6723.T', 'jp', 'Renesas Electronics Corporation', 'Technology', TRUE),

    -- Trading Companies
    ('8058.T', 'jp', 'Mitsubishi Corporation', 'Trading', TRUE),
    ('8031.T', 'jp', 'Mitsui & Co. Ltd.', 'Trading', TRUE),
    ('8001.T', 'jp', 'ITOCHU Corporation', 'Trading', TRUE),
    ('8002.T', 'jp', 'Marubeni Corporation', 'Trading', TRUE),
    ('8053.T', 'jp', 'Sumitomo Corporation', 'Trading', TRUE),

    -- Banking & Finance
    ('8306.T', 'jp', 'Mitsubishi UFJ Financial Group', 'Financial', TRUE),
    ('8316.T', 'jp', 'Sumitomo Mitsui Financial Group', 'Financial', TRUE),
    ('8411.T', 'jp', 'Mizuho Financial Group', 'Financial', TRUE),
    ('8766.T', 'jp', 'Tokio Marine Holdings', 'Financial', TRUE),

    -- Pharmaceuticals
    ('4502.T', 'jp', 'Takeda Pharmaceutical Company', 'Healthcare', TRUE),
    ('4503.T', 'jp', 'Astellas Pharma Inc.', 'Healthcare', TRUE),
    ('4568.T', 'jp', 'Daiichi Sankyo Company', 'Healthcare', TRUE),
    ('4519.T', 'jp', 'Chugai Pharmaceutical Co.', 'Healthcare', TRUE),

    -- Consumer & Retail
    ('9983.T', 'jp', 'Fast Retailing Co.', 'Consumer Cyclical', TRUE),
    ('7974.T', 'jp', 'Nintendo Co.', 'Technology', TRUE),
    ('9984.T', 'jp', 'SoftBank Group Corp.', 'Technology', TRUE),
    ('4452.T', 'jp', 'Kao Corporation', 'Consumer Defensive', TRUE),

    -- Industrial
    ('6301.T', 'jp', 'Komatsu Ltd.', 'Industrials', TRUE),
    ('6367.T', 'jp', 'Daikin Industries', 'Industrials', TRUE),
    ('7751.T', 'jp', 'Canon Inc.', 'Technology', TRUE),
    ('7733.T', 'jp', 'Olympus Corporation', 'Healthcare', TRUE),

    -- Telecommunications
    ('9432.T', 'jp', 'Nippon Telegraph and Telephone', 'Telecom', TRUE),
    ('9433.T', 'jp', 'KDDI Corporation', 'Telecom', TRUE),
    ('9434.T', 'jp', 'SoftBank Corp.', 'Telecom', TRUE),

    -- Real Estate
    ('8801.T', 'jp', 'Mitsui Fudosan Co.', 'Real Estate', TRUE),
    ('8802.T', 'jp', 'Mitsubishi Estate Co.', 'Real Estate', TRUE)
ON CONFLICT (symbol, market_type) DO UPDATE SET
    company_name = EXCLUDED.company_name,
    sector = EXCLUDED.sector,
    updated_at = NOW();

-- =============================================================================
-- Row Level Security (RLS)
-- =============================================================================

-- Enable RLS
ALTER TABLE stock_universe ENABLE ROW LEVEL SECURITY;

-- Policy for service role (full access)
CREATE POLICY "Service role has full access to stock_universe"
ON stock_universe
FOR ALL
USING (auth.role() = 'service_role')
WITH CHECK (auth.role() = 'service_role');

-- Policy for authenticated users (read-only)
CREATE POLICY "Authenticated users can view stock_universe"
ON stock_universe
FOR SELECT
USING (auth.role() = 'authenticated');

-- =============================================================================
-- Comments
-- =============================================================================

COMMENT ON TABLE stock_universe IS 'Stock symbol universe for the AI-Pick-Daily scoring system';
COMMENT ON COLUMN stock_universe.symbol IS 'Stock ticker symbol (e.g., AAPL, 7203.T)';
COMMENT ON COLUMN stock_universe.market_type IS 'Market type: us (US market) or jp (Japan market)';
COMMENT ON COLUMN stock_universe.company_name IS 'Full company name';
COMMENT ON COLUMN stock_universe.sector IS 'Industry sector classification';
COMMENT ON COLUMN stock_universe.enabled IS 'Whether this symbol is active for scoring';
