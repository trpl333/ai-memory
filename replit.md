# AI-Memory Service (NeuroSphere Ecosystem)

## Overview
AI-Memory is a shared microservice providing persistent memory storage, call summarization, and personality tracking for the NeuroSphere ecosystem (ChatStack, LeadFlowTracker, NeuroSphere Send Text). Built on FastAPI with PostgreSQL and pgvector, it implements a Memory V2 system that delivers 10x faster retrieval (<1 second vs 2-3 seconds) through AI-generated call summaries instead of raw conversation data. The service offers REST API endpoints for memory storage, retrieval, and intelligent context enrichment.

## Recent Changes

### October 28, 2025 - Phase 1 Week 1: Multi-Tenant Database Architecture (IN PROGRESS) 🚀
**Goal:** Transform AI-Memory from single-tenant to multi-tenant SaaS with PostgreSQL Row-Level Security

**Completed:**
- ✅ Multi-tenant migration SQL created (`migrations/002_add_customer_id_for_multi_tenant.sql`)
  - Adds `customer_id INTEGER NOT NULL` to all 5 tables (memories, call_summaries, caller_profiles, personality_metrics, personality_averages)
  - Migrates existing data to customer_id=1 (Peterson Insurance)
  - Enables PostgreSQL Row-Level Security (RLS) on all tables
  - Creates RLS policies for automatic tenant isolation
  - Updates indexes, constraints, and functions for multi-tenancy
- ✅ Python migration runner created (`run_migration.py`)
  - Dry-run mode for safe preview
  - Execute mode with verification
  - Comprehensive error handling
- ✅ Migration documentation (`WEEK1_MIGRATION_GUIDE.md`)
  - Step-by-step execution guide for production server
  - Pre-flight checklist and testing procedures
  - Rollback procedures and troubleshooting
- ✅ PyJWT library installed for JWT authentication
- ✅ RLS middleware created (`app/middleware/tenant_context.py`)
  - Sets PostgreSQL session variable for RLS enforcement
  - Automatic tenant isolation at database level
- ✅ JWT auth middleware created (`app/middleware/auth.py`)
  - Validates JWT tokens from ChatStack
  - Extracts customer_id from signed tokens
  - Prevents tenant spoofing attacks

**Next Steps (Week 1):**
- ⏳ Execute migration on production database (209.38.143.71)
- ⏳ Verify RLS policies block cross-tenant queries
- ⏳ Test migration with production data

**Architecture:** ChatGPT-5 validated as "80% production-ready" → targeting 100% with RLS + JWT + tests

**Documentation:**
- `NEUROSPHERE_MULTI_TENANT_ARCHITECTURE.md` - Full architectural design
- `IMPLEMENTATION_PLAN_PHASE1.md` - 4-week execution plan
- `WEEK1_MIGRATION_GUIDE.md` - Production migration guide

---

### October 28, 2025 - Backward Compatibility Shims Deployed ✅
**Issue:** ChatStack was calling legacy `/memory/store` and `/memory/retrieve` endpoints that no longer existed after API evolution to `/v1/*` and `/v2/*`.

**Solution:** Added backward compatibility shims in production:
- `POST /memory/store` → forwards to V1 memory storage (`mem_store.write()`)
- `POST /memory/retrieve` → forwards to V1 memory retrieval (`mem_store.get_user_memories()`)

**Impact:** ChatStack now works with zero code changes. Migration guide created for future V2 upgrade (10x performance).

**Documentation:**
- `CHATSTACK_MIGRATION_GUIDE.md` - Step-by-step V2 migration path
- `MULTI_PROJECT_ARCHITECTURE.md` v1.3.3 - Updated endpoint mapping
- Production: http://209.38.143.71:8100 (verified working)

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture
The system operates as a true microservices architecture with complete separation of concerns:

1.  **Phone System (ChatStack)**: A Flask orchestrator (`main.py`) handles Twilio webhooks.
2.  **AI Engine**: A FastAPI backend (`app/main.py`) manages LLM integration and conversation flow.
3.  **AI-Memory Service**: An external HTTP service (http://209.38.143.71:8100) manages all persistent memory and admin configuration.

All admin settings (greetings, voice settings, AI instructions) are stored in the AI-Memory service for dynamic configuration without code deployment.

### UI/UX Decisions
-   **Admin Panel**: A web interface at `/admin.html` provides full control over greeting messages, voice settings, AI personality, and system configuration via the AI-Memory service.
-   **Voice-First Design**: Seamless voice interaction is achieved with ElevenLabs TTS integration.
-   **Real-time Updates**: Admin changes take effect immediately without requiring code deployment.

### Technical Implementations
-   **LLM Integration**: Fully migrated to OpenAI Realtime API (gpt-realtime) for AI responses.
-   **Memory System**: An advanced four-tier Memory V2 system optimized for speed and intelligence, featuring:
    -   **Call Summaries**: AI-generated summaries for faster retrieval.
    -   **Caller Profiles**: Persistent caller information.
    -   **Personality Tracking**: Big 5 traits, communication style, and emotional state.
    -   **Summary-First Retrieval**: AI reads summaries and personality profiles for sub-second retrieval.
    -   A three-tier system for unlimited conversation memory, including rolling thread history, LLM-powered automatic memory consolidation, and permanent durable storage in the AI-Memory Service.
-   **Prompt Engineering**: Uses file-based system prompts for AI personalities, intelligent context packing, and safety triggers.
-   **Tool System**: An extensible, JSON schema-based architecture for external tool execution with a central dispatcher and error recovery.
-   **Data Models**: Pydantic for type-safe validation of request/response models.
-   **Safety & Security**: Multi-tier content filtering, PII protection, rate limiting, and input validation.
-   **Python Frameworks**: Flask and FastAPI.
-   **Database**: PostgreSQL with `pgvector` for vector embeddings and `pgcrypto` for UUIDs.
-   **Containerization**: Docker for deployment using `docker-compose.yml`.
-   **Web Server**: Nginx for HTTPS termination and proxying.
-   **Deployment**: Primarily on DigitalOcean Droplets.

## External Dependencies

### Services
-   **Twilio**: For voice call management and incoming call webhooks.
-   **OpenAI API**: Primary LLM service using GPT Realtime model (`https://api.openai.com/v1/chat/completions`).
-   **ElevenLabs**: For natural voice synthesis and text-to-speech conversion.
-   **AI-Memory Service**: An external HTTP service for conversation memory persistence (`http://209.38.143.71:8100`).

### Databases
-   **PostgreSQL**: Used with `pgvector` extension for conversation memory and semantic search.

### Libraries (Key Examples)
-   **FastAPI** & **Uvicorn**: Web framework and ASGI server.
-   **Pydantic**: Data validation.
-   **NumPy**: Vector operations.
-   **Requests**: HTTP client.
-   **psycopg2**: PostgreSQL adapter.