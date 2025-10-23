# AI-Memory Agent Tasks

## Task #1: Implement Memory V2 REST API Endpoints ✅ READY TO IMPLEMENT

### Status
- ✅ Backend components complete (CallSummarizer, PersonalityTracker, MemoryStore V2 methods)
- ✅ Database schema deployed and tested (4 new tables)
- ✅ Integration layer complete (MemoryV2Integration)
- ⏳ **TODO: Create FastAPI REST endpoints to expose V2 functionality**

### Background
All Memory V2 backend logic is implemented and tested. The system can:
- Summarize calls automatically
- Track personality metrics (Big 5 + communication style)
- Store and retrieve caller profiles
- Generate enriched context in <1 second (10x faster than V1)

**What's missing:** REST API endpoints in `app/main.py` to expose this functionality.

---

## Implementation Guide

### Files Already Complete
- `app/summarizer.py` - Call summarization logic
- `app/personality.py` - Personality tracking
- `app/memory.py` - Database operations (9 new V2 methods)
- `app/memory_integration.py` - High-level orchestration (`MemoryV2Integration` class)
- `migrations/001_add_memory_v2_tables.sql` - Database schema (already deployed)

### File to Modify
**`app/main.py`** - Add new FastAPI endpoints

---

## Required Endpoints

### 1. Process Completed Call
**Endpoint:** `POST /v2/process-call`

**Purpose:** Automatically summarize a completed call and store personality metrics

**Request Body:**
```python
{
  "user_id": "+15551234567",
  "thread_id": "call_12345",
  "conversation_history": [
    ["user", "Hello, I need help with billing"],
    ["assistant", "I can help you with that..."],
    # ... more conversation turns
  ]
}
```

**Response:**
```python
{
  "success": true,
  "summary": "Brief 2-3 sentence summary",
  "sentiment": "frustrated",
  "key_topics": ["billing", "account_issue"],
  "summary_id": "uuid-here",
  "personality_id": "uuid-here"
}
```

**Implementation:**
```python
from app.memory_integration import MemoryV2Integration

@app.post("/v2/process-call")
async def process_call(request: ProcessCallRequest):
    memory_v2 = MemoryV2Integration(memory_store, llm_chat)
    result = memory_v2.process_completed_call(
        conversation_history=request.conversation_history,
        user_id=request.user_id,
        thread_id=request.thread_id
    )
    return result
```

---

### 2. Get Enriched Context (Fast!)
**Endpoint:** `POST /v2/context/enriched`

**Purpose:** Get caller context for new call (personality + recent summaries)

**Request Body:**
```python
{
  "user_id": "+15551234567",
  "num_summaries": 5  # Optional, default 5
}
```

**Response:**
```python
{
  "success": true,
  "context": """
=== CALLER PROFILE ===
Total Calls: 12
Communication Style: formal
Technical Level: technical
Recent Satisfaction: high

RECENT CALL SUMMARIES:
1. Oct 20: Billing error resolved...
2. Oct 15: API integration help...
  """,
  "summary_count": 5,
  "has_personality_data": true
}
```

**Implementation:**
```python
@app.post("/v2/context/enriched")
async def get_enriched_context(request: EnrichedContextRequest):
    memory_v2 = MemoryV2Integration(memory_store, llm_chat)
    context = memory_v2.get_enriched_context_for_call(
        user_id=request.user_id,
        num_summaries=request.num_summaries or 5
    )
    return {
        "success": True,
        "context": context,
        "summary_count": len(context.split("\n\n")) if context else 0,
        "has_personality_data": "PERSONALITY PROFILE" in context
    }
```

---

### 3. Get Call Summaries
**Endpoint:** `GET /v2/summaries/{user_id}`

**Purpose:** Retrieve call summaries for a user

**Query Parameters:**
- `limit` (optional, default 10)

**Response:**
```python
{
  "success": true,
  "user_id": "+15551234567",
  "summaries": [
    {
      "id": "uuid",
      "thread_id": "call_12345",
      "call_date": "2025-10-23T10:30:00",
      "summary": "Brief summary text",
      "sentiment": "satisfied",
      "key_topics": ["billing"],
      "resolution_status": "resolved"
    }
  ],
  "total": 12
}
```

**Implementation:**
```python
@app.get("/v2/summaries/{user_id}")
async def get_call_summaries(user_id: str, limit: int = 10):
    summaries = memory_store.get_call_summaries(user_id, limit)
    return {
        "success": True,
        "user_id": user_id,
        "summaries": summaries,
        "total": len(summaries)
    }
```

---

### 4. Get Caller Profile
**Endpoint:** `GET /v2/profile/{user_id}`

**Purpose:** Get persistent caller profile

**Response:**
```python
{
  "success": true,
  "profile": {
    "user_id": "+15551234567",
    "preferred_name": "John",
    "total_calls": 12,
    "first_call_date": "2025-09-01T14:20:00",
    "last_call_date": "2025-10-23T10:30:00",
    "preferences": {...},
    "notes": "Prefers email communication"
  }
}
```

**Implementation:**
```python
@app.get("/v2/profile/{user_id}")
async def get_caller_profile(user_id: str):
    profile = memory_store.get_or_create_caller_profile(user_id)
    return {
        "success": True,
        "profile": profile
    }
```

---

### 5. Get Personality Averages
**Endpoint:** `GET /v2/personality/{user_id}`

**Purpose:** Get personality averages and trends

**Response:**
```python
{
  "success": true,
  "user_id": "+15551234567",
  "personality": {
    "call_count": 12,
    "big_five": {
      "openness": 65.5,
      "conscientiousness": 72.0,
      "extraversion": 50.0,
      "agreeableness": 80.0,
      "neuroticism": 30.0
    },
    "communication_style": {
      "formality": 70.0,
      "directness": 65.0,
      "technical_comfort": 85.0
    },
    "trends": {
      "satisfaction_trend": "improving"
    }
  }
}
```

**Implementation:**
```python
@app.get("/v2/personality/{user_id}")
async def get_personality_averages(user_id: str):
    averages = memory_store.get_personality_averages(user_id)
    return {
        "success": True,
        "user_id": user_id,
        "personality": averages
    }
```

---

### 6. Search Call Summaries (Semantic)
**Endpoint:** `POST /v2/summaries/search`

**Purpose:** Semantic search on call summaries (not raw data)

**Request Body:**
```python
{
  "user_id": "+15551234567",
  "query": "billing issues",
  "limit": 5
}
```

**Response:**
```python
{
  "success": true,
  "results": [
    {
      "id": "uuid",
      "summary": "Summary text",
      "call_date": "2025-10-20T10:00:00",
      "similarity": 0.92
    }
  ]
}
```

**Implementation:**
```python
@app.post("/v2/summaries/search")
async def search_call_summaries(request: SearchSummariesRequest):
    results = memory_store.search_call_summaries(
        user_id=request.user_id,
        query=request.query,
        limit=request.limit or 5
    )
    return {
        "success": True,
        "results": results
    }
```

---

## Pydantic Models Needed

Add these to `app/models.py`:

```python
from pydantic import BaseModel
from typing import List, Optional, Tuple

class ProcessCallRequest(BaseModel):
    user_id: str
    thread_id: str
    conversation_history: List[Tuple[str, str]]

class EnrichedContextRequest(BaseModel):
    user_id: str
    num_summaries: Optional[int] = 5

class SearchSummariesRequest(BaseModel):
    user_id: str
    query: str
    limit: Optional[int] = 5
```

---

## Testing

After implementation, test with:

```bash
# Test process call
curl -X POST http://localhost:8100/v2/process-call \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "+15551234567",
    "thread_id": "test_call_001",
    "conversation_history": [
      ["user", "Hello"],
      ["assistant", "Hi there!"]
    ]
  }'

# Test enriched context
curl -X POST http://localhost:8100/v2/context/enriched \
  -H "Content-Type: application/json" \
  -d '{"user_id": "+15551234567"}'

# Test get summaries
curl http://localhost:8100/v2/summaries/+15551234567

# Test get profile
curl http://localhost:8100/v2/profile/+15551234567

# Test personality
curl http://localhost:8100/v2/personality/+15551234567
```

---

## Success Criteria

✅ All 6 endpoints implemented  
✅ Proper error handling (try/except blocks)  
✅ Pydantic models for request validation  
✅ All endpoints return JSON with `success` field  
✅ Test with curl commands - all return 200 OK  
✅ Documentation updated in MULTI_PROJECT_ARCHITECTURE.md  

---

## Notes

- **All backend logic is complete** - just wire it up to FastAPI
- **Use existing classes:** `MemoryV2Integration`, `MemoryStore`
- **Error handling:** Wrap in try/except, return `{"success": false, "error": "..."}`
- **Performance:** Endpoints should respond in <1 second
- **Imports needed:** Already in place (`memory_store`, `llm_chat` initialized in `app/main.py`)

---

## After Completion

1. Restart the service: `docker restart ai-memory-ai-memory-orchestrator-worker`
2. Test all endpoints
3. Update ChatStack to use new V2 endpoints
4. Monitor performance (should see <1 second response times)

**Estimated time:** 30-45 minutes to implement all endpoints
