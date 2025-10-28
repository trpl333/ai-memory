-- Migration: Multi-Tenant Transformation
-- Adds customer_id to all tables for tenant isolation
-- Enables PostgreSQL Row-Level Security (RLS)
-- Phase 1 of NeuroSphere AI Multi-Tenant SaaS Architecture
-- Date: October 28, 2025

-- =============================================================================
-- STEP 1: Add customer_id columns with DEFAULT 1 (safe transition)
-- =============================================================================
-- IMPORTANT: Using DEFAULT 1 allows existing write code to continue working
-- This prevents breaking production during the migration window
-- DEFAULT will be removed in Step 3 after all code is updated

-- memories table (V1)
ALTER TABLE memories 
ADD COLUMN IF NOT EXISTS customer_id INTEGER DEFAULT 1;

-- call_summaries table (V2)
ALTER TABLE call_summaries 
ADD COLUMN IF NOT EXISTS customer_id INTEGER DEFAULT 1;

-- caller_profiles table (V2)
ALTER TABLE caller_profiles 
ADD COLUMN IF NOT EXISTS customer_id INTEGER DEFAULT 1;

-- personality_metrics table (V2)
ALTER TABLE personality_metrics 
ADD COLUMN IF NOT EXISTS customer_id INTEGER DEFAULT 1;

-- personality_averages table (V2)
ALTER TABLE personality_averages 
ADD COLUMN IF NOT EXISTS customer_id INTEGER DEFAULT 1;

-- =============================================================================
-- STEP 2: Migrate existing data to customer_id=1 (Peterson Insurance)
-- =============================================================================

-- All existing data belongs to Peterson Insurance (Test Client #1)
UPDATE memories SET customer_id = 1 WHERE customer_id IS NULL;
UPDATE call_summaries SET customer_id = 1 WHERE customer_id IS NULL;
UPDATE caller_profiles SET customer_id = 1 WHERE customer_id IS NULL;
UPDATE personality_metrics SET customer_id = 1 WHERE customer_id IS NULL;
UPDATE personality_averages SET customer_id = 1 WHERE customer_id IS NULL;

-- =============================================================================
-- STEP 3: Make customer_id NOT NULL + Remove DEFAULT (after code deployed)
-- =============================================================================
-- NOTE: Step 3 should ONLY be run AFTER Week 2 API changes are deployed
-- This ensures backward compatibility during the transition period

ALTER TABLE memories 
ALTER COLUMN customer_id SET NOT NULL,
ALTER COLUMN customer_id DROP DEFAULT;

ALTER TABLE call_summaries 
ALTER COLUMN customer_id SET NOT NULL,
ALTER COLUMN customer_id DROP DEFAULT;

ALTER TABLE caller_profiles 
ALTER COLUMN customer_id SET NOT NULL,
ALTER COLUMN customer_id DROP DEFAULT;

ALTER TABLE personality_metrics 
ALTER COLUMN customer_id SET NOT NULL,
ALTER COLUMN customer_id DROP DEFAULT;

ALTER TABLE personality_averages 
ALTER COLUMN customer_id SET NOT NULL,
ALTER COLUMN customer_id DROP DEFAULT;

-- =============================================================================
-- STEP 4: Add composite indexes for performance (customer_id + user_id)
-- =============================================================================

-- memories: Fast lookup by tenant + user
CREATE INDEX IF NOT EXISTS idx_memories_customer_user 
ON memories(customer_id, user_id);

-- call_summaries: Fast lookup by tenant + user + date
CREATE INDEX IF NOT EXISTS idx_call_summaries_customer_user 
ON call_summaries(customer_id, user_id);

CREATE INDEX IF NOT EXISTS idx_call_summaries_customer_date 
ON call_summaries(customer_id, call_date DESC);

-- caller_profiles: Fast lookup by tenant + user (unique per tenant)
CREATE INDEX IF NOT EXISTS idx_caller_profiles_customer_user 
ON caller_profiles(customer_id, user_id);

-- personality_metrics: Fast lookup by tenant + user
CREATE INDEX IF NOT EXISTS idx_personality_metrics_customer_user 
ON personality_metrics(customer_id, user_id);

-- personality_averages: Fast lookup by tenant + user
CREATE INDEX IF NOT EXISTS idx_personality_averages_customer_user 
ON personality_averages(customer_id, user_id);

-- =============================================================================
-- STEP 5: Update UNIQUE constraints for multi-tenancy
-- =============================================================================

-- caller_profiles: user_id must be unique PER TENANT (not globally)
-- Drop old constraint, create new composite unique constraint
ALTER TABLE caller_profiles 
DROP CONSTRAINT IF EXISTS caller_profiles_user_id_key;

ALTER TABLE caller_profiles 
ADD CONSTRAINT caller_profiles_customer_user_unique 
UNIQUE (customer_id, user_id);

-- personality_averages: user_id must be unique PER TENANT
-- Drop old primary key, create new composite primary key
ALTER TABLE personality_averages 
DROP CONSTRAINT IF EXISTS personality_averages_pkey;

ALTER TABLE personality_averages 
ADD CONSTRAINT personality_averages_pkey 
PRIMARY KEY (customer_id, user_id);

-- =============================================================================
-- STEP 6: Enable PostgreSQL Row-Level Security (RLS)
-- =============================================================================
-- RLS automatically enforces tenant isolation at database level
-- Even if developer forgets WHERE customer_id filter, PostgreSQL blocks it

-- Enable RLS on all tables
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE caller_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE personality_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE personality_averages ENABLE ROW LEVEL SECURITY;

-- CRITICAL: Force RLS even for table owner (prevents bypass)
-- Without this, the database owner role bypasses RLS policies!
ALTER TABLE memories FORCE ROW LEVEL SECURITY;
ALTER TABLE call_summaries FORCE ROW LEVEL SECURITY;
ALTER TABLE caller_profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE personality_metrics FORCE ROW LEVEL SECURITY;
ALTER TABLE personality_averages FORCE ROW LEVEL SECURITY;

-- =============================================================================
-- STEP 7: Create RLS Policies for Tenant Isolation
-- =============================================================================
-- Policy: Only return rows where customer_id matches session variable

-- memories table policy
DROP POLICY IF EXISTS tenant_isolation_memories ON memories;
CREATE POLICY tenant_isolation_memories ON memories
  USING (customer_id = current_setting('app.current_tenant')::int);

-- call_summaries table policy
DROP POLICY IF EXISTS tenant_isolation_call_summaries ON call_summaries;
CREATE POLICY tenant_isolation_call_summaries ON call_summaries
  USING (customer_id = current_setting('app.current_tenant')::int);

-- caller_profiles table policy
DROP POLICY IF EXISTS tenant_isolation_caller_profiles ON caller_profiles;
CREATE POLICY tenant_isolation_caller_profiles ON caller_profiles
  USING (customer_id = current_setting('app.current_tenant')::int);

-- personality_metrics table policy
DROP POLICY IF EXISTS tenant_isolation_personality_metrics ON personality_metrics;
CREATE POLICY tenant_isolation_personality_metrics ON personality_metrics
  USING (customer_id = current_setting('app.current_tenant')::int);

-- personality_averages table policy
DROP POLICY IF EXISTS tenant_isolation_personality_averages ON personality_averages;
CREATE POLICY tenant_isolation_personality_averages ON personality_averages
  USING (customer_id = current_setting('app.current_tenant')::int);

-- =============================================================================
-- STEP 8: Update personality_averages function for multi-tenancy
-- =============================================================================
-- The auto-update function needs to respect customer_id

DROP FUNCTION IF EXISTS update_personality_averages(VARCHAR);

CREATE OR REPLACE FUNCTION update_personality_averages(
    p_customer_id INTEGER,
    p_user_id VARCHAR
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO personality_averages (
        customer_id,
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
        p_customer_id,
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
            WHERE customer_id = p_customer_id AND user_id = p_user_id 
            ORDER BY measured_at DESC LIMIT 3
        ) sub),
        (SELECT AVG(satisfaction_level) FROM (
            SELECT satisfaction_level FROM personality_metrics 
            WHERE customer_id = p_customer_id AND user_id = p_user_id 
            ORDER BY measured_at DESC LIMIT 3
        ) sub),
        (SELECT AVG(urgency_level) FROM (
            SELECT urgency_level FROM personality_metrics 
            WHERE customer_id = p_customer_id AND user_id = p_user_id 
            ORDER BY measured_at DESC LIMIT 3
        ) sub)
    FROM personality_metrics
    WHERE customer_id = p_customer_id AND user_id = p_user_id
    ON CONFLICT (customer_id, user_id) DO UPDATE SET
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

-- Update trigger to pass customer_id
DROP TRIGGER IF EXISTS personality_metrics_insert_trigger ON personality_metrics;

CREATE OR REPLACE FUNCTION trigger_update_personality_averages()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM update_personality_averages(NEW.customer_id, NEW.user_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER personality_metrics_insert_trigger
AFTER INSERT ON personality_metrics
FOR EACH ROW
EXECUTE FUNCTION trigger_update_personality_averages();

-- =============================================================================
-- VERIFICATION QUERIES (Run these to verify migration success)
-- =============================================================================

-- Check all tables have customer_id
-- SELECT COUNT(*) FROM memories WHERE customer_id IS NULL;
-- SELECT COUNT(*) FROM call_summaries WHERE customer_id IS NULL;
-- SELECT COUNT(*) FROM caller_profiles WHERE customer_id IS NULL;
-- SELECT COUNT(*) FROM personality_metrics WHERE customer_id IS NULL;
-- SELECT COUNT(*) FROM personality_averages WHERE customer_id IS NULL;
-- All should return 0

-- Check RLS is enabled
-- SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public';
-- All tables should show rowsecurity = true

-- Check policies exist
-- SELECT tablename, policyname FROM pg_policies WHERE schemaname = 'public';
-- Should show 5 tenant_isolation_* policies

-- =============================================================================
-- COMMENTS FOR DOCUMENTATION
-- =============================================================================

COMMENT ON COLUMN memories.customer_id IS 'Tenant isolation: Links memory to specific customer account';
COMMENT ON COLUMN call_summaries.customer_id IS 'Tenant isolation: Links call summary to specific customer account';
COMMENT ON COLUMN caller_profiles.customer_id IS 'Tenant isolation: Links caller profile to specific customer account';
COMMENT ON COLUMN personality_metrics.customer_id IS 'Tenant isolation: Links personality data to specific customer account';
COMMENT ON COLUMN personality_averages.customer_id IS 'Tenant isolation: Links personality averages to specific customer account';

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================
-- All tables now have customer_id for tenant isolation
-- Row-Level Security (RLS) policies automatically enforce isolation
-- Existing data assigned to customer_id = 1 (Peterson Insurance)
-- Ready for multi-tenant operations
-- =============================================================================
