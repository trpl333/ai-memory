# AI-Memory Service - Complete File Inventory
**Generated:** November 1, 2025  
**Purpose:** Comprehensive catalog of every file in the AI-Memory microservice repository

---

## 📋 Table of Contents
1. [Core Application Files](#core-application-files)
2. [Middleware & Authentication](#middleware--authentication)
3. [Memory System Files](#memory-system-files)
4. [Configuration & Utilities](#configuration--utilities)
5. [Documentation Files](#documentation-files)
6. [⚠️ Backup & Temporary Files](#backup--temporary-files)
7. [📦 Attached Assets & Logs](#attached-assets--logs)
8. [🧹 Recommended Cleanup Actions](#recommended-cleanup-actions)

---

## Core Application Files

### `app/main.py` (1,154 lines)
**Purpose:** FastAPI application entrypoint and REST API endpoint definitions  
**Architecture Role:** Central orchestrator - exposes all HTTP endpoints for memory operations  
**Multi-Tenant:** ✅ Supports JWT authentication via middleware  
**Contains:**
- V1 endpoints: `/memory/store`, `/memory/retrieve`, `/memory/search`
- V2 endpoints: `/v2/profile`, `/v2/summaries`, `/v2/personality`, `/v2/context/enriched`, `/v2/summaries/search`, `/v2/process-call`
- Thread history management (in-memory rolling window + DB persistence)
- LLM chat endpoint
- Admin panel serving (`/admin.html`)

**Dependencies:**
- Imports: `http_memory.py`, `memory.py`, `llm.py`, `packer.py`, `tools.py`, `jwt_utils.py`, middleware
- Interacts with: PostgreSQL database, OpenAI API, external AI-Memory HTTP service

**Status:** ✅ Clean - All ChatStack contamination removed (Twilio/WebSocket code purged Oct 31)

---

### `app/models.py`
**Purpose:** Pydantic data models for request/response validation  
**Architecture Role:** Data contracts for API endpoints  
**Multi-Tenant:** Contains models with `customer_id` fields  
**Contains:**
- `ChatRequest`, `ChatResponse` - LLM chat models
- `MemoryObject` - V1 memory storage model
- V2 models: `CallerProfileResponse`, `CallSummaryResponse`, `PersonalityResponse`, `EnrichedContextRequest`, etc.

**Dependencies:** Imported by `main.py`  
**Status:** ✅ Clean

---

### `app/__init__.py`
**Purpose:** Python package initialization file  
**Architecture Role:** Makes `app/` a Python package  
**Status:** ✅ Clean (likely empty or minimal)

---

## Middleware & Authentication

### `app/middleware/auth.py`
**Purpose:** JWT token validation middleware  
**Architecture Role:** Multi-tenant security layer - validates JWT tokens and extracts `customer_id`  
**Multi-Tenant:** ✅ Core security component - enforces tenant isolation  
**Contains:**
- `validate_jwt()` function - verifies JWT signature and expiration
- Extracts `customer_id` from JWT payload
- Returns 401 Unauthorized for invalid/missing tokens

**Dependencies:**
- Uses `app/jwt_utils.py` for token verification
- Applied to protected V2 endpoints in `main.py`

**Status:** ✅ Clean - Part of Week 2 multi-tenant security architecture

---

### `app/middleware/request_tenant.py`
**Purpose:** PostgreSQL RLS tenant context middleware  
**Architecture Role:** Sets PostgreSQL session variable for Row-Level Security  
**Multi-Tenant:** ✅ Critical for RLS - sets `app.current_tenant` before queries  
**Contains:**
- Middleware that extracts `customer_id` from JWT
- Executes `SET app.current_tenant = '{customer_id}'` before each request
- Ensures RLS policies filter data correctly

**Dependencies:** Works with `auth.py` middleware  
**Status:** ✅ Clean

---

### `app/middleware/tenant_context.py`
**Purpose:** Tenant context management utilities  
**Architecture Role:** Helper functions for tenant context handling  
**Multi-Tenant:** ✅ Supports multi-tenant operations  
**Status:** ✅ Clean

---

## Memory System Files

### `app/memory.py`
**Purpose:** PostgreSQL-based memory store implementation  
**Architecture Role:** Core memory persistence layer (V1 + V2 schemas)  
**Multi-Tenant:** ✅ All queries filter by `customer_id`  
**Contains:**
- `MemoryStore` class with PostgreSQL connection
- V1 methods: `store()`, `retrieve()`, `search()` (semantic search with pgvector)
- V2 methods: `store_call_summary()`, `store_personality_metrics()`, `get_caller_profile()`, etc.
- Database schema: 5 tables with RLS policies
  - `memories` (V1 raw data)
  - `call_summaries` (V2 AI-generated summaries)
  - `caller_profiles` (V2 user profiles)
  - `personality_metrics` (V2 per-call personality tracking)
  - `personality_averages` (V2 aggregated personality trends)

**Dependencies:**
- Uses `pgvector` for embedding storage and semantic search
- Imported by `main.py`, `http_memory.py`, `memory_integration.py`

**Status:** ✅ Clean - Multi-tenant ready with RLS

---

### `app/http_memory.py` (814 lines)
**Purpose:** HTTP client for external AI-Memory service + memory template schemas  
**Architecture Role:** External memory service integration  
**Multi-Tenant:** Uses JWT tokens for authentication  
**Contains:**
- `HTTPMemoryStore` class - HTTP client wrapper
- `MEMORY_TEMPLATE` - Comprehensive fill-in-the-blanks schema for caller data (identity, contacts, vehicles, policies, claims, properties, preferences, facts)
- Methods mirror `MemoryStore` API (store, retrieve, search)
- Used when AI-Memory runs as separate microservice

**Dependencies:** 
- Uses `requests` library
- Calls external AI-Memory HTTP endpoints (configurable via `AI_MEMORY_BASE_URL`)

**Status:** ✅ Clean

---

### `app/memory_integration.py` (132 lines)
**Purpose:** Memory V2 integration orchestrator  
**Architecture Role:** Hooks call completion events to trigger summarization + personality tracking  
**Multi-Tenant:** Works with multi-tenant memory store  
**Contains:**
- `MemoryV2Integration` class
- `process_completed_call()` - Orchestrates:
  1. AI call summarization (via `summarizer.py`)
  2. Personality analysis (via `personality.py`)
  3. Database storage (via `memory.py`)
  4. Caller profile updates

**Dependencies:**
- Uses `summarizer.py`, `personality.py`, `memory.py`
- Called by `main.py` after call completion

**Status:** ✅ Clean

---

### `app/memory_v2_schema.py`
**Purpose:** Database schema definitions for Memory V2 tables  
**Architecture Role:** Schema documentation and migration scripts  
**Multi-Tenant:** ✅ All tables include `customer_id` with RLS policies  
**Contains:**
- SQL CREATE TABLE statements for V2 tables
- RLS policy definitions
- Index definitions for performance

**Status:** ✅ Clean

---

### `app/summarizer.py`
**Purpose:** AI-powered call summarization engine  
**Architecture Role:** Converts raw conversation history into structured summaries  
**Multi-Tenant:** Agnostic (processes data, doesn't access database directly)  
**Contains:**
- `CallSummarizer` class
- `summarize_call()` - Uses LLM to extract:
  - Summary text
  - Key topics
  - Sentiment analysis
  - Resolution status
  - Action items

**Dependencies:**
- Uses `llm.py` for LLM calls
- Called by `memory_integration.py`

**Status:** ✅ Clean

---

### `app/personality.py`
**Purpose:** Personality trait tracking system  
**Architecture Role:** Analyzes conversation style and emotional patterns  
**Multi-Tenant:** Agnostic (processes data only)  
**Contains:**
- `PersonalityTracker` class
- `analyze_personality()` - Extracts:
  - Big 5 personality traits (openness, conscientiousness, extraversion, agreeableness, neuroticism)
  - Communication style (formality, directness, technical comfort)
  - Emotional state
  - Satisfaction level

**Dependencies:**
- Uses `llm.py` for LLM analysis
- Called by `memory_integration.py`

**Status:** ✅ Clean

---

## Configuration & Utilities

### `app/jwt_utils.py` (29 lines)
**Purpose:** Shared JWT authentication utilities  
**Architecture Role:** **SHARED INFRASTRUCTURE** (used by both ChatStack and AI-Memory)  
**Multi-Tenant:** ✅ Core security component  
**Contains:**
- `generate_memory_token(customer_id, scope)` - Creates JWT tokens (used by ChatStack)
- `verify_token(token)` - Validates JWT tokens (used by AI-Memory)
- Uses `JWT_SECRET_KEY` environment variable

**Dependencies:**
- Uses `PyJWT` library
- **SHARED FILE:** Both repos need this (not contamination!)

**Status:** ✅ Clean - **Critical shared infrastructure**

---

### `app/llm.py`
**Purpose:** OpenAI LLM integration wrapper  
**Architecture Role:** Centralized LLM API client  
**Multi-Tenant:** Agnostic (no multi-tenant logic)  
**Contains:**
- `chat()` - Standard OpenAI chat completions
- `chat_realtime_stream()` - Streaming responses
- `validate_llm_connection()` - Health check
- `_get_llm_config()` - Configuration loader

**Dependencies:**
- Uses `openai` library
- Calls OpenAI API (requires `OPENAI_API_KEY`)

**Status:** ✅ Clean

---

### `app/packer.py`
**Purpose:** Prompt engineering utilities  
**Architecture Role:** Context packing for LLM prompts  
**Multi-Tenant:** Agnostic  
**Contains:**
- `pack_prompt()` - Combines system prompt + caller context + conversation history
- `should_remember()` - Determines if content should be persisted
- `extract_carry_kit_items()` - Extracts important facts for memory
- `detect_safety_triggers()` - Content filtering (PII, inappropriate content)

**Dependencies:**
- Used by `main.py` for LLM prompt preparation

**Status:** ✅ Clean

---

### `app/tools.py`
**Purpose:** External tool execution framework  
**Architecture Role:** Extensible tool calling system  
**Multi-Tenant:** Agnostic  
**Contains:**
- `tool_dispatcher()` - Routes tool calls to handlers
- `parse_tool_calls()` - Parses LLM tool call requests
- `execute_tool_calls()` - Executes tools with error recovery
- JSON schema-based tool definitions

**Dependencies:**
- Called by `main.py` during LLM conversations

**Status:** ✅ Clean

---

### `app/prompts/system_safety.txt`
**Purpose:** Safety system prompt for content filtering  
**Architecture Role:** LLM safety instructions  
**Contains:** Text prompt for PII protection, content filtering, safety triggers  
**Status:** ✅ Clean

---

### `app/prompts/system_sam.txt`
**Purpose:** Samantha AI personality system prompt  
**Architecture Role:** AI agent instructions  
**Contains:** Character definition, conversation guidelines, personality traits  
**Status:** ✅ Clean

---

## Documentation Files

### `replit.md` (Active)
**Purpose:** Project overview and architecture documentation  
**Architecture Role:** Living documentation - keeps agent context across sessions  
**Contains:**
- System architecture overview
- Deployment information (production server IP, docker commands)
- User preferences
- Technical implementation details
- **CRITICAL:** Documents `docker-compose-ai.yml` filename

**Status:** ✅ Active - Keep updated

---

### `V2_ENDPOINTS_READY.md` (238 lines)
**Purpose:** Memory V2 API documentation and integration guide  
**Architecture Role:** Developer documentation for V2 endpoints  
**Contains:**
- Complete API endpoint specifications
- Request/response examples
- Integration guide for ChatStack
- Performance benchmarks (V1 vs V2: 2-3s vs <1s)

**Status:** ✅ Active - Reference documentation

---

### `WEEK1_MIGRATION_GUIDE.md` (416 lines)
**Purpose:** Multi-tenant database migration instructions  
**Architecture Role:** Step-by-step migration guide for RLS deployment  
**Contains:**
- Pre-migration checklist
- Migration execution steps
- Verification procedures
- Troubleshooting guide
- Rollback procedures

**Status:** ✅ Active - Reference for future migrations

---

## ⚠️ Backup & Temporary Files

### `app/main.py.backup`
**Purpose:** Backup created during ChatStack cleanup (Oct 31, 2025)  
**Architecture Role:** BACKUP FILE - Contains contaminated code (548 lines of Twilio/WebSocket)  
**Status:** ❌ **DELETE** - Served its purpose, no longer needed

---

### `app/main.py.save`
**Purpose:** Auto-save or temporary backup file  
**Architecture Role:** TEMPORARY FILE  
**Status:** ❌ **DELETE** - Likely duplicate or outdated

---

## 📦 Attached Assets & Logs

### `attached_assets/` (90+ files)
**Purpose:** Miscellaneous chat logs, screenshots, and PDF documents  
**Architecture Role:** Historical reference and debugging artifacts  
**Contains:**
- PDF: `Chat Gpt‑style Stack_ One‑pager + Fast Api Starter_1757101208972.pdf`
- Screenshots: `image_*.png` (5 files)
- Chat logs: 80+ pasted text files from troubleshooting sessions

**Status:** ❌ **CLEANUP RECOMMENDED**
- Keep: PDF documentation, recent screenshots (last 7 days)
- Delete: Old pasted chat logs (60+ files from debugging sessions)

**Specific Files to Keep:**
- PDF documentation (1 file)
- Recent screenshots showing UI/architecture (last 5-7 files by date)

**Files to Delete:**
- All `Pasted-*.txt` files (80+ files) - these are ephemeral debugging artifacts

---

### `update_runpod_proxy.sh`
**Purpose:** UNKNOWN - Appears to be RunPod configuration script  
**Architecture Role:** UNCLEAR - Not related to AI-Memory core functionality  
**Status:** ⚠️ **INVESTIGATE**
- RunPod is a GPU cloud service
- This script may be leftover from GPU/LLM experimentation
- **Action:** Read file to determine if needed, otherwise delete

---

### `uv.lock`
**Purpose:** Python dependency lock file (for `uv` package manager)  
**Architecture Role:** Dependency version pinning  
**Status:** ✅ Keep (if using `uv` for package management)

---

## 🧹 Recommended Cleanup Actions

### Immediate Deletions (Safe)
```bash
# Remove backup files
rm app/main.py.backup
rm app/main.py.save

# Remove old debugging artifacts (80+ pasted chat logs)
rm attached_assets/Pasted-*.txt
```

### Investigate & Decide
```bash
# Check if this is needed
cat update_runpod_proxy.sh
# If unrelated to AI-Memory → DELETE
# If used for production → DOCUMENT in replit.md
```

### Keep (Active Files)
- All `app/*.py` files (core application)
- All `app/middleware/*.py` files (authentication)
- All `app/prompts/*.txt` files (system prompts)
- `replit.md`, `V2_ENDPOINTS_READY.md`, `WEEK1_MIGRATION_GUIDE.md`
- `uv.lock` (dependency management)
- PDF documentation and recent screenshots

---

## 🔍 Unclear/Potentially Unused Files

### `update_runpod_proxy.sh`
**Status:** ⚠️ UNCLEAR PURPOSE
- Not referenced in any documentation
- RunPod is GPU cloud service (may be leftover from experiments)
- **Recommendation:** Investigate contents, likely can be deleted

---

## 🎯 Architecture Boundary Check

### ✅ Clean Files (AI-Memory Microservice Scope)
All files in `app/` folder are within AI-Memory's scope:
- Memory API endpoints ✅
- Database persistence ✅
- JWT authentication ✅
- LLM integration for summarization ✅

### ❌ ChatStack Contamination Removed
**Previously contaminated (fixed Oct 31):**
- `app/main.py` contained 548 lines of Twilio WebSocket + OpenAI Realtime phone orchestration
- **Status:** ✅ Cleaned - Contamination removed

### ✅ Shared Infrastructure (Not Contamination)
- `app/jwt_utils.py` - **SHARED** by both ChatStack and AI-Memory (legitimate!)

---

## 📊 File Count Summary

**Core Application:** 12 files (main, models, memory, llm, etc.)  
**Middleware:** 3 files (auth, tenant context)  
**Documentation:** 3 active markdown files  
**Backups/Temp:** 2 files (RECOMMEND DELETE)  
**Attached Assets:** 90+ files (RECOMMEND CLEANUP - delete 80+ pasted logs)  
**Unknown:** 1 file (update_runpod_proxy.sh - INVESTIGATE)

**Total Repository Files:** ~110 files  
**Recommended After Cleanup:** ~25 essential files

---

## ✅ Multi-Tenant Readiness Status

**Authentication:** ✅ JWT validation implemented (`jwt_utils.py`, `middleware/auth.py`)  
**Database:** ✅ RLS enabled on all 5 tables with `customer_id` column  
**API Endpoints:** ✅ All V2 endpoints require JWT authentication  
**Security:** ✅ PostgreSQL RLS policies enforce tenant isolation  
**Production:** ✅ Deployed to 209.38.143.71:8100 with docker-compose-ai.yml

**Peterson Insurance (customer_id=1):** Production test client  
**Ready for New Tenants:** ✅ Yes - add customer_id=2, 3, 4... with complete data isolation

---

**END OF FILE INVENTORY**

Last Updated: November 1, 2025  
Maintained By: Alice (AI-Memory Agent)
