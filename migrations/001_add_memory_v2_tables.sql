-- Migration: Memory V2 Schema
-- Adds call summaries, caller profiles, and personality tracking
-- Phase 1: Call Summarization + Key Variables
-- Phase 2: Personality Tracking

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 1. Call Summaries Table
CREATE TABLE IF NOT EXISTS call_summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_id VARCHAR(255) UNIQUE NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    call_date TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Summary data
    summary TEXT NOT NULL,
    key_topics JSONB DEFAULT '[]'::jsonb,
    key_variables JSONB DEFAULT '{}'::jsonb,
    
    -- Metadata
    sentiment VARCHAR(50),
    duration_seconds INTEGER,
    resolution_status VARCHAR(50),
    
    -- Vector embedding for similarity search
    embedding vector(768),
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 2. Caller Profiles Table
CREATE TABLE IF NOT EXISTS caller_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) UNIQUE NOT NULL,
    
    -- Call history
    first_call_date TIMESTAMP NOT NULL,
    last_call_date TIMESTAMP NOT NULL,
    total_calls INTEGER DEFAULT 1,
    
    -- Personal preferences
    preferred_name VARCHAR(255),
    preferences JSONB DEFAULT '{}'::jsonb,
    context JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 3. Personality Metrics Table (per-call measurements)
CREATE TABLE IF NOT EXISTS personality_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    call_id VARCHAR(255) NOT NULL,
    measured_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Big 5 Personality Dimensions (0-100)
    openness FLOAT CHECK (openness >= 0 AND openness <= 100),
    conscientiousness FLOAT CHECK (conscientiousness >= 0 AND conscientiousness <= 100),
    extraversion FLOAT CHECK (extraversion >= 0 AND extraversion <= 100),
    agreeableness FLOAT CHECK (agreeableness >= 0 AND agreeableness <= 100),
    neuroticism FLOAT CHECK (neuroticism >= 0 AND neuroticism <= 100),
    
    -- Communication Style (0-100)
    formality FLOAT CHECK (formality >= 0 AND formality <= 100),
    directness FLOAT CHECK (directness >= 0 AND directness <= 100),
    detail_orientation FLOAT CHECK (detail_orientation >= 0 AND detail_orientation <= 100),
    patience FLOAT CHECK (patience >= 0 AND patience <= 100),
    technical_comfort FLOAT CHECK (technical_comfort >= 0 AND technical_comfort <= 100),
    
    -- Emotional State (0-100)
    frustration_level FLOAT CHECK (frustration_level >= 0 AND frustration_level <= 100),
    satisfaction_level FLOAT CHECK (satisfaction_level >= 0 AND satisfaction_level <= 100),
    urgency_level FLOAT CHECK (urgency_level >= 0 AND urgency_level <= 100),
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 4. Personality Averages Table (running calculations)
CREATE TABLE IF NOT EXISTS personality_averages (
    user_id VARCHAR(255) PRIMARY KEY,
    call_count INTEGER DEFAULT 0,
    last_updated TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Averaged personality traits
    avg_openness FLOAT,
    avg_conscientiousness FLOAT,
    avg_extraversion FLOAT,
    avg_agreeableness FLOAT,
    avg_neuroticism FLOAT,
    avg_formality FLOAT,
    avg_directness FLOAT,
    avg_detail_orientation FLOAT,
    avg_patience FLOAT,
    avg_technical_comfort FLOAT,
    
    -- Recent averages (last 3 calls)
    recent_frustration FLOAT,
    recent_satisfaction FLOAT,
    recent_urgency FLOAT,
    
    -- Trend indicators
    satisfaction_trend VARCHAR(20),
    frustration_trend VARCHAR(20)
);

-- Create indexes for fast lookup (AFTER tables are created)
CREATE INDEX IF NOT EXISTS idx_call_summaries_user_id ON call_summaries(user_id);
CREATE INDEX IF NOT EXISTS idx_call_summaries_call_date ON call_summaries(call_date DESC);

CREATE INDEX IF NOT EXISTS idx_caller_profiles_user_id ON caller_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_caller_profiles_last_call ON caller_profiles(last_call_date DESC);

CREATE INDEX IF NOT EXISTS idx_personality_metrics_user_id ON personality_metrics(user_id);
CREATE INDEX IF NOT EXISTS idx_personality_metrics_call_id ON personality_metrics(call_id);
CREATE INDEX IF NOT EXISTS idx_personality_metrics_measured_at ON personality_metrics(measured_at DESC);

CREATE INDEX IF NOT EXISTS idx_personality_averages_last_updated ON personality_averages(last_updated DESC);

-- Note: IVFFLAT index for vector similarity should be created AFTER data population
-- Uncomment and run this after you have some data:
-- CREATE INDEX idx_call_summaries_embedding ON call_summaries USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Functions to update personality averages

CREATE OR REPLACE FUNCTION update_personality_averages(p_user_id VARCHAR)
RETURNS VOID AS $$
BEGIN
    INSERT INTO personality_averages (
        user_id,
        call_count,
        last_updated,
        avg_openness,
        avg_conscientiousness,
        avg_extraversion,
        avg_agreeableness,
        avg_neuroticism,
        avg_formality,
        avg_directness,
        avg_detail_orientation,
        avg_patience,
        avg_technical_comfort,
        recent_frustration,
        recent_satisfaction,
        recent_urgency
    )
    SELECT 
        p_user_id,
        COUNT(*),
        NOW(),
        AVG(openness),
        AVG(conscientiousness),
        AVG(extraversion),
        AVG(agreeableness),
        AVG(neuroticism),
        AVG(formality),
        AVG(directness),
        AVG(detail_orientation),
        AVG(patience),
        AVG(technical_comfort),
        -- Last 3 calls for recent metrics
        (SELECT AVG(frustration_level) FROM (
            SELECT frustration_level FROM personality_metrics 
            WHERE user_id = p_user_id 
            ORDER BY measured_at DESC LIMIT 3
        ) sub),
        (SELECT AVG(satisfaction_level) FROM (
            SELECT satisfaction_level FROM personality_metrics 
            WHERE user_id = p_user_id 
            ORDER BY measured_at DESC LIMIT 3
        ) sub),
        (SELECT AVG(urgency_level) FROM (
            SELECT urgency_level FROM personality_metrics 
            WHERE user_id = p_user_id 
            ORDER BY measured_at DESC LIMIT 3
        ) sub)
    FROM personality_metrics
    WHERE user_id = p_user_id
    ON CONFLICT (user_id) DO UPDATE SET
        call_count = EXCLUDED.call_count,
        last_updated = EXCLUDED.last_updated,
        avg_openness = EXCLUDED.avg_openness,
        avg_conscientiousness = EXCLUDED.avg_conscientiousness,
        avg_extraversion = EXCLUDED.avg_extraversion,
        avg_agreeableness = EXCLUDED.avg_agreeableness,
        avg_neuroticism = EXCLUDED.avg_neuroticism,
        avg_formality = EXCLUDED.avg_formality,
        avg_directness = EXCLUDED.avg_directness,
        avg_detail_orientation = EXCLUDED.avg_detail_orientation,
        avg_patience = EXCLUDED.avg_patience,
        avg_technical_comfort = EXCLUDED.avg_technical_comfort,
        recent_frustration = EXCLUDED.recent_frustration,
        recent_satisfaction = EXCLUDED.recent_satisfaction,
        recent_urgency = EXCLUDED.recent_urgency;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update averages when new personality metrics are added
CREATE OR REPLACE FUNCTION trigger_update_personality_averages()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM update_personality_averages(NEW.user_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS personality_metrics_insert_trigger ON personality_metrics;
CREATE TRIGGER personality_metrics_insert_trigger
AFTER INSERT ON personality_metrics
FOR EACH ROW
EXECUTE FUNCTION trigger_update_personality_averages();

-- Comments for documentation
COMMENT ON TABLE call_summaries IS 'Stores AI-generated summaries of calls with key variables extracted';
COMMENT ON TABLE caller_profiles IS 'Maintains persistent caller information and preferences';
COMMENT ON TABLE personality_metrics IS 'Per-call personality and communication style measurements';
COMMENT ON TABLE personality_averages IS 'Running averages of personality traits per caller';
