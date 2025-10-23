# AI-Memory Service - Technical Specification

## System Overview

**AI-Memory** is a persistent memory service for conversational AI systems. It runs as a standalone FastAPI microservice that manages conversation history, caller profiles, and intelligent memory retrieval for AI phone systems.

**Production URL:** `http://209.38.143.71:8100`  
**Framework:** FastAPI (Python 3.11)  
**Database:** PostgreSQL with pgvector extension  
**Deployment:** Docker container on DigitalOcean Droplet

---

## Architecture

### Microservices Stack

```
┌─────────────────────┐
│   ChatStack         │  Phone System (Flask)
│   Port: 5000        │  - Twilio webhook handler
│   (Separate Server) │  - Voice call orchestration
└──────────┬──────────┘
           │ HTTP Calls
           ↓
┌─────────────────────┐
│   AI-Memory         │  Memory Service (FastAPI)
│   Port: 8100        │  - Conversation storage
│   209.38.143.71     │  - Caller profiles
└──────────┬──────────┘  - Personality tracking
           │             - Summary generation
           ↓
┌─────────────────────┐
│   PostgreSQL        │  Database
│   pgvector enabled  │  - Raw memories
└─────────────────────┘  - Call summaries
                         - Personality metrics
```

### Service Communication

**ChatStack → AI-Memory:**
- Protocol: HTTP/REST
- Base URL: `http://209.38.143.71:8100`
- Authentication: None (internal network)
- Format: JSON

---

## Core Components

### 1. Memory Store (`app/memory.py`)
**Purpose:** Low-level database operations for memory CRUD

**Key Methods:**
```python
# Legacy V1 Methods
store_memory(user_id, role, content, metadata)
get_memories(user_id, limit, thread_id)
search_memories_semantic(user_id, query, limit)
delete_thread(thread_id)

# New V2 Methods (Oct 2025)
store_call_summary(user_id, thread_id, summary_data)
get_call_summaries(user_id, limit)
search_call_summaries(user_id, query, limit)
get_or_create_caller_profile(user_id)
store_personality_metrics(user_id, thread_id, metrics)
get_personality_averages(user_id)
get_caller_context_for_llm(user_id, num_summaries)
```

**Database Connection:**
- Uses environment variables from `.env` file
- Auto-reconnect on connection loss
- Connection pooling enabled

### 2. Call Summarizer (`app/summarizer.py`)
**Purpose:** Generate AI summaries of completed calls

**Process:**
1. Takes conversation history as input
2. Calls OpenAI API to extract:
   - 2-3 sentence summary
   - Key topics (billing, technical_support, etc.)
   - Key variables (account IDs, names, etc.)
   - Sentiment (frustrated, satisfied, neutral)
   - Resolution status (resolved, pending, escalated)
3. Falls back to rule-based extraction if LLM fails
4. Returns structured summary data

**LLM Configuration:**
- Model: Uses `LLMChat` class (configured in `app/llm.py`)
- Temperature: 0.3 (factual summaries)
- Max tokens: 500

### 3. Personality Tracker (`app/personality.py`)
**Purpose:** Analyze caller personality from conversation

**Metrics Tracked (0-100 scale):**

**Big 5 Personality:**
- Openness
- Conscientiousness
- Extraversion
- Agreeableness
- Neuroticism

**Communication Style:**
- Formality (casual → formal)
- Directness (indirect → direct)
- Detail orientation (high-level → detailed)
- Patience (impatient → patient)
- Technical comfort (non-technical → technical)

**Emotional State:**
- Frustration level
- Satisfaction level
- Urgency level

**Process:**
1. Analyzes conversation turns
2. Calls LLM for personality assessment
3. Falls back to rule-based if LLM fails
4. Stores metrics in database
5. Auto-updates running averages via DB triggers

### 4. Memory Integration (`app/memory_integration.py`)
**Purpose:** High-level orchestration layer

**Key Methods:**

```python
# After call completion
process_completed_call(
    conversation_history,  # List of (role, content) tuples
    user_id,              # Phone number: "+15551234567"
    thread_id             # Call ID: "call_12345"
)
# Returns: {summary, sentiment, summary_id, personality_id}

# Before new call
get_enriched_context_for_call(
    user_id,              # Phone number
    num_summaries=5       # How many recent calls to include
)
# Returns: Formatted string for LLM system prompt
```

---

## Database Schema

### Legacy V1 Tables

**`memories`** - Raw conversation data
```sql
CREATE TABLE memories (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    thread_id TEXT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    embedding vector(768),
    created_at TIMESTAMP DEFAULT NOW()
);
```

### New V2 Tables (Oct 2025)

**`call_summaries`** - AI-generated summaries
```sql
CREATE TABLE call_summaries (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    call_date TIMESTAMP DEFAULT NOW(),
    summary TEXT NOT NULL,
    key_topics TEXT[],
    key_variables JSONB,
    sentiment TEXT,
    resolution_status TEXT,
    summary_embedding vector(768),
    created_at TIMESTAMP DEFAULT NOW()
);
```

**`caller_profiles`** - Persistent caller info
```sql
CREATE TABLE caller_profiles (
    id UUID PRIMARY KEY,
    user_id TEXT UNIQUE NOT NULL,
    preferred_name TEXT,
    total_calls INTEGER DEFAULT 0,
    first_call_date TIMESTAMP,
    last_call_date TIMESTAMP,
    preferences JSONB,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**`personality_metrics`** - Per-call personality
```sql
CREATE TABLE personality_metrics (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    call_date TIMESTAMP DEFAULT NOW(),
    -- Big 5
    openness DECIMAL(5,2),
    conscientiousness DECIMAL(5,2),
    extraversion DECIMAL(5,2),
    agreeableness DECIMAL(5,2),
    neuroticism DECIMAL(5,2),
    -- Communication Style
    formality DECIMAL(5,2),
    directness DECIMAL(5,2),
    detail_orientation DECIMAL(5,2),
    patience DECIMAL(5,2),
    technical_comfort DECIMAL(5,2),
    -- Emotional State
    frustration_level DECIMAL(5,2),
    satisfaction_level DECIMAL(5,2),
    urgency_level DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT NOW()
);
```

**`personality_averages`** - Running averages (auto-updated)
```sql
CREATE TABLE personality_averages (
    id UUID PRIMARY KEY,
    user_id TEXT UNIQUE NOT NULL,
    call_count INTEGER DEFAULT 0,
    -- Averages of all metrics above
    avg_openness DECIMAL(5,2),
    avg_formality DECIMAL(5,2),
    -- ... (same fields as personality_metrics)
    -- Trends
    satisfaction_trend TEXT,  -- improving/stable/declining
    last_updated TIMESTAMP DEFAULT NOW()
);
```

---

## API Endpoints

### Memory Operations

**Store Memory**
```http
POST /api/memory/store
Content-Type: application/json

{
  "user_id": "+15551234567",
  "role": "user",
  "content": "Hello, I need help with billing",
  "metadata": {"thread_id": "call_12345"}
}
```

**Retrieve Memories**
```http
GET /api/memory/{user_id}?limit=50&thread_id=call_12345
```

**Semantic Search**
```http
POST /api/memory/search
Content-Type: application/json

{
  "user_id": "+15551234567",
  "query": "billing issues",
  "limit": 10
}
```

### Thread Management

**Get Thread History**
```http
GET /api/threads/{thread_id}/history
```

**Delete Thread**
```http
DELETE /api/threads/{thread_id}
```

### Admin Configuration (V2)

**Get System Config**
```http
GET /api/admin/config
```

**Update System Config**
```http
POST /api/admin/config
Content-Type: application/json

{
  "greeting_message": "Thanks for calling...",
  "voice_settings": {...},
  "ai_instructions": "You are Samantha..."
}
```

---

## Environment Variables

Required in `.env` file:

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname
PGHOST=localhost
PGPORT=5432
PGDATABASE=ai_memory
PGUSER=postgres
PGPASSWORD=secretpassword

# OpenAI
OPENAI_API_KEY=sk-...

# LLM Configuration
LLM_BASE_URL=https://api.openai.com/v1/chat/completions

# Optional
SESSION_SECRET=random-secret-key
```

---

## Memory V2 Performance

### Before V2 (Slow)
```
Query: "What does John usually ask about?"
  ↓
Search 5,755 raw memories
  ↓
Read all matching raw conversation data
  ↓
LLM processes thousands of tokens
  ↓
Response time: 2-3 seconds ❌
```

### After V2 (Fast)
```
Query: "What does John usually ask about?"
  ↓
Load caller profile (1 row)
  ↓
Get personality averages (1 row)
  ↓
Get 5 most recent summaries (5 rows)
  ↓
LLM processes ~500 tokens
  ↓
Response time: <1 second ✅
```

**Performance Gain:** 10x faster retrieval

---

## Integration Example

### From ChatStack (or other services)

```python
import requests

AI_MEMORY_URL = "http://209.38.143.71:8100"

# Get enriched context before a call
response = requests.post(
    f"{AI_MEMORY_URL}/api/memory/enriched-context",
    json={
        "user_id": "+15551234567",
        "num_summaries": 5
    }
)
context = response.json()["context"]

# Use in LLM system prompt
system_prompt = f"""You are Samantha, a helpful AI assistant.

{context}

Use this information to personalize your responses."""

# After call ends, store summary
requests.post(
    f"{AI_MEMORY_URL}/api/memory/process-call",
    json={
        "user_id": "+15551234567",
        "thread_id": "call_12345",
        "conversation_history": [
            ("user", "Hello, I need help"),
            ("assistant", "Sure, how can I help?"),
            # ... rest of conversation
        ]
    }
)
```

---

## Deployment

### Docker Container

**Build:**
```bash
docker build -t ai-memory-ai-memory-orchestrator-worker .
```

**Run:**
```bash
docker run -d \
  -p 8100:8100 \
  --env-file .env \
  --restart unless-stopped \
  --name ai-memory-ai-memory-orchestrator-worker \
  ai-memory-ai-memory-orchestrator-worker
```

**Entry Point:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

### Database Migration

**Run V2 migration:**
```bash
docker exec -it ai-memory-ai-memory-orchestrator-worker \
  python scripts/migrate_database.py
```

**Test V2 system:**
```bash
docker exec -it ai-memory-ai-memory-orchestrator-worker \
  python scripts/test_memory_v2.py
```

---

## Key Files

```
ai-memory/
├── app/
│   ├── main.py                  # FastAPI app entry point
│   ├── memory.py                # Memory storage (V1 + V2)
│   ├── summarizer.py            # Call summarization
│   ├── personality.py           # Personality tracking
│   ├── memory_integration.py    # High-level orchestration
│   ├── llm.py                   # LLM client wrapper
│   ├── models.py                # Pydantic models
│   └── tools.py                 # External tool system
├── migrations/
│   └── 001_add_memory_v2_tables.sql
├── scripts/
│   ├── migrate_database.py      # Run migrations
│   ├── test_memory_v2.py        # Test suite
│   └── backfill_memories.py     # Historical data processing
├── Dockerfile
├── requirements.txt
└── .env                         # Environment variables
```

---

## Current Status (Oct 2025)

✅ **Production Ready**
- Running on DigitalOcean at 209.38.143.71:8100
- Memory V2 system deployed and tested
- 4 new database tables operational
- Call summarization active
- Personality tracking active
- Response times: <1 second (target achieved)

✅ **Tested**
- 5/5 test suite passed
- Migration successful
- All V2 features working

⏳ **Optional Enhancement**
- Backfill 5,755 historical memories with summaries
- Script ready: `scripts/backfill_memories.py`

---

## Connection Details Summary

**For ChatStack or other clients:**

```python
# Connection Info
AI_MEMORY_HOST = "209.38.143.71"
AI_MEMORY_PORT = 8100
AI_MEMORY_BASE_URL = "http://209.38.143.71:8100"

# No authentication required (internal network)
# Content-Type: application/json
# All endpoints return JSON responses
```

**Health Check:**
```bash
curl http://209.38.143.71:8100/health
# Expected: {"status": "healthy"}
```

---

## Version History

- **Oct 23, 2025:** Memory V2 deployed (call summaries, personality tracking)
- **Oct 1, 2025:** Memory consolidation system added
- **Sep 25, 2025:** Microservices migration (config → ai-memory service)
- **Sep 13, 2025:** Migrated to HTTP-based architecture
- **Aug 2025:** Initial deployment with pgvector
