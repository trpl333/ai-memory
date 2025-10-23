"""
Memory V2 Schema Design
=======================

Phase 1: Call Summarization + Key Variables
Phase 2: Personality Tracking
Phase 3: Backfill Historical Data

NEW DATABASE TABLES:
-------------------

1. call_summaries
   - id (UUID, primary key)
   - call_id (VARCHAR, unique) - links to original conversation
   - user_id (VARCHAR) - caller identifier
   - call_date (TIMESTAMP)
   - summary (TEXT) - AI-generated summary of the call
   - key_topics (JSONB) - extracted topics ["billing", "technical_support"]
   - key_variables (JSONB) - extracted variables {account_id: "12345", issue_type: "billing"}
   - sentiment (VARCHAR) - overall sentiment (positive, neutral, negative, frustrated, satisfied)
   - duration_seconds (INTEGER)
   - resolution_status (VARCHAR) - resolved, pending, escalated
   - embedding (VECTOR) - for similarity search on summaries
   - created_at (TIMESTAMP)
   
2. caller_profiles
   - id (UUID, primary key)
   - user_id (VARCHAR, unique) - caller identifier (phone number, etc)
   - first_call_date (TIMESTAMP)
   - last_call_date (TIMESTAMP)
   - total_calls (INTEGER)
   - preferred_name (VARCHAR) - how they like to be addressed
   - preferences (JSONB) - {"communication_style": "brief", "technical_level": "advanced"}
   - context (JSONB) - persistent context {"company": "Acme Inc", "role": "IT Manager"}
   - created_at (TIMESTAMP)
   - updated_at (TIMESTAMP)

3. personality_metrics
   - id (UUID, primary key)
   - user_id (VARCHAR) - links to caller
   - call_id (VARCHAR) - which call this is from
   - measured_at (TIMESTAMP)
   
   # The "Big 5" Personality Dimensions (0-100 scale)
   - openness (FLOAT) - curiosity, creativity
   - conscientiousness (FLOAT) - organization, dependability
   - extraversion (FLOAT) - sociability, assertiveness
   - agreeableness (FLOAT) - cooperation, empathy
   - neuroticism (FLOAT) - emotional stability (inverse)
   
   # Communication Style Metrics (0-100 scale)
   - formality (FLOAT) - formal vs casual
   - directness (FLOAT) - direct vs indirect
   - detail_orientation (FLOAT) - high-level vs detailed
   - patience (FLOAT) - patient vs impatient
   - technical_comfort (FLOAT) - technical vs non-technical
   
   # Emotional State (detected during this call)
   - frustration_level (FLOAT) - 0-100
   - satisfaction_level (FLOAT) - 0-100
   - urgency_level (FLOAT) - 0-100
   
   created_at (TIMESTAMP)

4. personality_averages (materialized view / running calculation)
   - user_id (VARCHAR, primary key)
   - call_count (INTEGER)
   - last_updated (TIMESTAMP)
   
   # Averaged personality traits (rolling average)
   - avg_openness (FLOAT)
   - avg_conscientiousness (FLOAT)
   - avg_extraversion (FLOAT)
   - avg_agreeableness (FLOAT)
   - avg_neuroticism (FLOAT)
   - avg_formality (FLOAT)
   - avg_directness (FLOAT)
   - avg_detail_orientation (FLOAT)
   - avg_patience (FLOAT)
   - avg_technical_comfort (FLOAT)
   
   # Trend indicators (last 3 calls vs previous average)
   - satisfaction_trend (VARCHAR) - "improving", "stable", "declining"
   - frustration_trend (VARCHAR)

RETRIEVAL STRATEGY:
------------------

OLD WAY (slow):
1. Search raw memories
2. LLM reads all raw data
3. LLM extracts insights on-the-fly
4. Total: 2-3 seconds

NEW WAY (fast):
1. Look up caller_profile by user_id (instant)
2. Get personality_averages for user (instant)
3. Search call_summaries (not raw data) for context (fast)
4. LLM reads: profile + personality + summaries (< 1 second)
5. Fall back to raw memories only if needed

BENEFITS:
---------
- 10x faster retrieval (no raw data processing)
- Smarter personality adaptation
- Better context retention
- Scalable to millions of calls
"""
