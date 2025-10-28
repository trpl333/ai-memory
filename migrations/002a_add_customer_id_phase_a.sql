-- Migration Phase A: Multi-Tenant Foundation (SAFE - Backward Compatible)
-- Adds customer_id with DEFAULT 1 to allow existing code to continue working
-- Enables PostgreSQL Row-Level Security (RLS) with FORCE
-- Phase 1 of NeuroSphere AI Multi-Tenant SaaS Architecture
-- Date: October 28, 2025
-- Run Timing: Week 1 - Immediately (no code changes required)

-- =============================================================================
-- STEP 1: Add customer_id columns with DEFAULT 1 (backward compatible)
-- =============================================================================
-- IMPORTANT: DEFAULT 1 allows existing write code to continue working
-- This prevents breaking production during the migration window

ALTER TABLE memories 
ADD COLUMN IF NOT EXISTS customer_id INTEGER DEFAULT 1;

ALTER TABLE call_summaries 
ADD COLUMN IF NOT EXISTS customer_id INTEGER DEFAULT 1;

ALTER TABLE caller_profiles 
ADD COLUMN IF NOT EXISTS customer_id INTEGER DEFAULT 1;

ALTER TABLE personality_metrics 
ADD COLUMN IF NOT EXISTS customer_id INTEGER DEFAULT 1;

ALTER TABLE personality_averages 
ADD COLUMN IF NOT EXISTS customer_id INTEGER DEFAULT 1;

-- =============================================================================
-- STEP 2: Migrate existing data to customer_id=1 (Peterson Insurance)
-- =============================================================================

UPDATE memories SET customer_id = 1 WHERE customer_id IS NULL;
UPDATE call_summaries SET customer_id = 1 WHERE customer_id IS NULL;
UPDATE caller_profiles SET customer_id = 1 WHERE customer_id IS NULL;
UPDATE personality_metrics SET customer_id = 1 WHERE customer_id IS NULL;
UPDATE personality_averages SET customer_id = 1 WHERE customer_id IS NULL;

-- =============================================================================
-- STEP 3: Add composite indexes for performance (customer_id + user_id)
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_memories_customer_user 
ON memories(customer_id, user_id);

CREATE INDEX IF NOT EXISTS idx_call_summaries_customer_user 
ON call_summaries(customer_id, user_id);

CREATE INDEX IF NOT EXISTS idx_call_summaries_customer_date 
ON call_summaries(customer_id, call_date DESC);

CREATE INDEX IF NOT EXISTS idx_caller_profiles_customer_user 
ON caller_profiles(customer_id, user_id);

CREATE INDEX IF NOT EXISTS idx_personality_metrics_customer_user 
ON personality_metrics(customer_id, user_id);

CREATE INDEX IF NOT EXISTS idx_personality_averages_customer_user 
ON personality_averages(customer_id, user_id);

-- =============================================================================
-- STEP 4: Update UNIQUE constraints for multi-tenancy
-- =============================================================================

-- caller_profiles: user_id must be unique PER TENANT (not globally)
ALTER TABLE caller_profiles 
DROP CONSTRAINT IF EXISTS caller_profiles_user_id_key;

ALTER TABLE caller_profiles 
ADD CONSTRAINT caller_profiles_customer_user_unique 
UNIQUE (customer_id, user_id);

-- personality_averages: user_id must be unique PER TENANT
ALTER TABLE personality_averages 
DROP CONSTRAINT IF EXISTS personality_averages_pkey;

ALTER TABLE personality_averages 
ADD CONSTRAINT personality_averages_pkey 
PRIMARY KEY (customer_id, user_id);

-- =============================================================================
-- STEP 5: Enable PostgreSQL Row-Level Security (RLS)
-- =============================================================================

-- Enable RLS on all tables
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE caller_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE personality_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE personality_averages ENABLE ROW LEVEL SECURITY;

-- CRITICAL: Force RLS even for table owner (prevents bypass)
ALTER TABLE memories FORCE ROW LEVEL SECURITY;
ALTER TABLE call_summaries FORCE ROW LEVEL SECURITY;
ALTER TABLE caller_profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE personality_metrics FORCE ROW LEVEL SECURITY;
ALTER TABLE personality_averages FORCE ROW LEVEL SECURITY;

-- =============================================================================
-- STEP 6: Create TRANSITIONAL RLS Policies (Backward Compatible for Phase A)
-- =============================================================================
-- IMPORTANT: These policies allow legacy traffic to customer_id=1 (Peterson)
-- This ensures backward compatibility until Week 2 JWT code is deployed
-- Phase B will replace these with strict policies requiring session variable
--
-- Policy Logic:
--   customer_id = 1  OR  customer_id = session_variable
--
-- This allows:
--   - Old code (no JWT): Can access customer_id=1 (Peterson) ✅
--   - New code (with JWT): Can access their assigned customer_id ✅

-- memories table policy (transitional)
DROP POLICY IF EXISTS tenant_isolation_memories ON memories;
CREATE POLICY tenant_isolation_memories ON memories
  USING (
    customer_id = 1  -- Allow legacy traffic to Peterson (customer_id=1)
    OR customer_id = current_setting('app.current_tenant', true)::int
  )
  WITH CHECK (
    customer_id = 1
    OR customer_id = current_setting('app.current_tenant', true)::int
  );

-- call_summaries table policy (transitional)
DROP POLICY IF EXISTS tenant_isolation_call_summaries ON call_summaries;
CREATE POLICY tenant_isolation_call_summaries ON call_summaries
  USING (
    customer_id = 1
    OR customer_id = current_setting('app.current_tenant', true)::int
  )
  WITH CHECK (
    customer_id = 1
    OR customer_id = current_setting('app.current_tenant', true)::int
  );

-- caller_profiles table policy (transitional)
DROP POLICY IF EXISTS tenant_isolation_caller_profiles ON caller_profiles;
CREATE POLICY tenant_isolation_caller_profiles ON caller_profiles
  USING (
    customer_id = 1
    OR customer_id = current_setting('app.current_tenant', true)::int
  )
  WITH CHECK (
    customer_id = 1
    OR customer_id = current_setting('app.current_tenant', true)::int
  );

-- personality_metrics table policy (transitional)
DROP POLICY IF EXISTS tenant_isolation_personality_metrics ON personality_metrics;
CREATE POLICY tenant_isolation_personality_metrics ON personality_metrics
  USING (
    customer_id = 1
    OR customer_id = current_setting('app.current_tenant', true)::int
  )
  WITH CHECK (
    customer_id = 1
    OR customer_id = current_setting('app.current_tenant', true)::int
  );

-- personality_averages table policy (transitional)
DROP POLICY IF EXISTS tenant_isolation_personality_averages ON personality_averages;
CREATE POLICY tenant_isolation_personality_averages ON personality_averages
  USING (
    customer_id = 1
    OR customer_id = current_setting('app.current_tenant', true)::int
  )
  WITH CHECK (
    customer_id = 1
    OR customer_id = current_setting('app.current_tenant', true)::int
  );

-- =============================================================================
-- STEP 7: Update personality_averages function for multi-tenancy
-- =============================================================================

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

-- Update trigger
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
-- COMMENTS FOR DOCUMENTATION
-- =============================================================================

COMMENT ON COLUMN memories.customer_id IS 'Tenant isolation: Links memory to specific customer account (DEFAULT 1 for backward compatibility)';
COMMENT ON COLUMN call_summaries.customer_id IS 'Tenant isolation: Links call summary to specific customer account (DEFAULT 1 for backward compatibility)';
COMMENT ON COLUMN caller_profiles.customer_id IS 'Tenant isolation: Links caller profile to specific customer account (DEFAULT 1 for backward compatibility)';
COMMENT ON COLUMN personality_metrics.customer_id IS 'Tenant isolation: Links personality data to specific customer account (DEFAULT 1 for backward compatibility)';
COMMENT ON COLUMN personality_averages.customer_id IS 'Tenant isolation: Links personality averages to specific customer account (DEFAULT 1 for backward compatibility)';

-- =============================================================================
-- PHASE A COMPLETE
-- =============================================================================
-- ✅ customer_id columns added with DEFAULT 1
-- ✅ Existing data migrated to customer_id=1
-- ✅ RLS enabled and FORCED for all roles
-- ✅ RLS policies with USING + WITH CHECK clauses
-- ✅ Backward compatible: Old code continues working
--
-- NEXT STEP: Deploy Week 2 JWT code, then run Phase B
-- =============================================================================
