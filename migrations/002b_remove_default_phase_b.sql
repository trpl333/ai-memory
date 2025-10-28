-- Migration Phase B: Remove DEFAULT and Enforce NOT NULL
-- CRITICAL: Only run AFTER Week 2 JWT code is deployed and tested!
-- This migration removes backward compatibility and requires explicit customer_id
-- Phase 1 of NeuroSphere AI Multi-Tenant SaaS Architecture
-- Date: October 28, 2025
-- Run Timing: Week 2 - AFTER JWT authentication deployed (24+ hours monitoring)

-- =============================================================================
-- PRE-FLIGHT CHECKS (Manual - Verify before executing)
-- =============================================================================
-- [ ] Week 2 JWT code deployed to production
-- [ ] All API endpoints updated to extract customer_id from JWT
-- [ ] Tested with Peterson Insurance (customer_id=1) successfully
-- [ ] Production logs show NO errors for 24+ hours
-- [ ] Test calls working correctly
-- [ ] Backup created: pg_dump -U postgres ai_memory > backup_before_phase_b.sql

-- =============================================================================
-- STEP 1: Remove DEFAULT from customer_id columns
-- =============================================================================
-- After this step, all writes MUST explicitly provide customer_id
-- Old code (without JWT) will start failing here

ALTER TABLE memories 
ALTER COLUMN customer_id DROP DEFAULT;

ALTER TABLE call_summaries 
ALTER COLUMN customer_id DROP DEFAULT;

ALTER TABLE caller_profiles 
ALTER COLUMN customer_id DROP DEFAULT;

ALTER TABLE personality_metrics 
ALTER COLUMN customer_id DROP DEFAULT;

ALTER TABLE personality_averages 
ALTER COLUMN customer_id DROP DEFAULT;

-- =============================================================================
-- STEP 2: Enforce NOT NULL on customer_id
-- =============================================================================
-- This ensures data integrity - no NULL customer_ids allowed

ALTER TABLE memories 
ALTER COLUMN customer_id SET NOT NULL;

ALTER TABLE call_summaries 
ALTER COLUMN customer_id SET NOT NULL;

ALTER TABLE caller_profiles 
ALTER COLUMN customer_id SET NOT NULL;

ALTER TABLE personality_metrics 
ALTER COLUMN customer_id SET NOT NULL;

ALTER TABLE personality_averages 
ALTER COLUMN customer_id SET NOT NULL;

-- =============================================================================
-- STEP 3: Replace Transitional RLS Policies with Strict Policies
-- =============================================================================
-- IMPORTANT: This replaces the permissive Phase A policies
-- New policies REQUIRE session variable - no legacy access to customer_id=1
-- All traffic must now use JWT authentication

-- memories table policy (strict)
DROP POLICY IF EXISTS tenant_isolation_memories ON memories;
CREATE POLICY tenant_isolation_memories ON memories
  USING (
    customer_id = current_setting('app.current_tenant', true)::int
  )
  WITH CHECK (
    customer_id = current_setting('app.current_tenant', true)::int
  );

-- call_summaries table policy (strict)
DROP POLICY IF EXISTS tenant_isolation_call_summaries ON call_summaries;
CREATE POLICY tenant_isolation_call_summaries ON call_summaries
  USING (
    customer_id = current_setting('app.current_tenant', true)::int
  )
  WITH CHECK (
    customer_id = current_setting('app.current_tenant', true)::int
  );

-- caller_profiles table policy (strict)
DROP POLICY IF EXISTS tenant_isolation_caller_profiles ON caller_profiles;
CREATE POLICY tenant_isolation_caller_profiles ON caller_profiles
  USING (
    customer_id = current_setting('app.current_tenant', true)::int
  )
  WITH CHECK (
    customer_id = current_setting('app.current_tenant', true)::int
  );

-- personality_metrics table policy (strict)
DROP POLICY IF EXISTS tenant_isolation_personality_metrics ON personality_metrics;
CREATE POLICY tenant_isolation_personality_metrics ON personality_metrics
  USING (
    customer_id = current_setting('app.current_tenant', true)::int
  )
  WITH CHECK (
    customer_id = current_setting('app.current_tenant', true)::int
  );

-- personality_averages table policy (strict)
DROP POLICY IF EXISTS tenant_isolation_personality_averages ON personality_averages;
CREATE POLICY tenant_isolation_personality_averages ON personality_averages
  USING (
    customer_id = current_setting('app.current_tenant', true)::int
  )
  WITH CHECK (
    customer_id = current_setting('app.current_tenant', true)::int
  );

-- =============================================================================
-- VERIFICATION QUERIES
-- =============================================================================

-- Check no NULLs exist (should all return 0)
-- SELECT COUNT(*) FROM memories WHERE customer_id IS NULL;
-- SELECT COUNT(*) FROM call_summaries WHERE customer_id IS NULL;
-- SELECT COUNT(*) FROM caller_profiles WHERE customer_id IS NULL;
-- SELECT COUNT(*) FROM personality_metrics WHERE customer_id IS NULL;
-- SELECT COUNT(*) FROM personality_averages WHERE customer_id IS NULL;

-- Check all columns are NOT NULL
-- \d+ memories
-- \d+ call_summaries
-- \d+ caller_profiles
-- \d+ personality_metrics
-- \d+ personality_averages

-- =============================================================================
-- UPDATE COLUMN COMMENTS
-- =============================================================================

COMMENT ON COLUMN memories.customer_id IS 'Tenant isolation: Links memory to specific customer account (NOT NULL - no default)';
COMMENT ON COLUMN call_summaries.customer_id IS 'Tenant isolation: Links call summary to specific customer account (NOT NULL - no default)';
COMMENT ON COLUMN caller_profiles.customer_id IS 'Tenant isolation: Links caller profile to specific customer account (NOT NULL - no default)';
COMMENT ON COLUMN personality_metrics.customer_id IS 'Tenant isolation: Links personality data to specific customer account (NOT NULL - no default)';
COMMENT ON COLUMN personality_averages.customer_id IS 'Tenant isolation: Links personality averages to specific customer account (NOT NULL - no default)';

-- =============================================================================
-- PHASE B COMPLETE
-- =============================================================================
-- ✅ DEFAULT removed - writes must provide customer_id explicitly
-- ✅ NOT NULL enforced - data integrity guaranteed
-- ✅ Multi-tenant architecture complete
--
-- NEXT STEP: Week 3 testing with multiple tenants
-- =============================================================================
