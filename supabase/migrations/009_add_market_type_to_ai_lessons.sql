-- Add market_type column to ai_lessons table for JP/US distinction
-- This fixes the issue where save_ai_lesson_jp was trying to insert TEXT into DATE column

-- Add market_type column
ALTER TABLE ai_lessons
ADD COLUMN IF NOT EXISTS market_type TEXT DEFAULT 'us';

-- Drop the old unique constraint on lesson_date only
ALTER TABLE ai_lessons DROP CONSTRAINT IF EXISTS ai_lessons_lesson_date_key;

-- Add new unique constraint on (lesson_date, market_type) combination
ALTER TABLE ai_lessons
ADD CONSTRAINT ai_lessons_lesson_date_market_key UNIQUE (lesson_date, market_type);

-- Update existing records to have market_type = 'us'
UPDATE ai_lessons SET market_type = 'us' WHERE market_type IS NULL;

-- Create index for efficient queries
CREATE INDEX IF NOT EXISTS idx_ai_lessons_market_type ON ai_lessons(market_type);
