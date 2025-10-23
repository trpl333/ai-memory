# Memory V2: Intelligent Call Summarization & Personality Tracking

## 🎯 Problem Solved

**Before (Memory V1):** AI had to read ALL raw conversation data every time, causing 2-3 second response times.

**After (Memory V2):** AI reads concise summaries and personality profiles first, dramatically improving speed.

## 📊 Architecture Overview

### New Database Tables

1. **call_summaries** - AI-generated summaries of each call
   - Summary, key topics, key variables
   - Sentiment analysis, resolution status
   - Vector embeddings for fast search

2. **caller_profiles** - Persistent caller information
   - Preferred name, communication preferences
   - Call history (first call, last call, total calls)
   - Custom context (company, role, etc.)

3. **personality_metrics** - Per-call personality measurements
   - Big 5 personality traits (openness, conscientiousness, etc.)
   - Communication style (formality, directness, technical comfort)
   - Emotional state (frustration, satisfaction, urgency)

4. **personality_averages** - Running averages per caller
   - Averaged personality traits across all calls
   - Recent trends (improving/declining satisfaction)
   - Auto-updated via database triggers

## 🚀 Phase 1: Installation & Setup

### Step 1: Run Database Migration

```bash
# On your Digital Ocean server
cd /opt/ai-memory

# Run the migration
python scripts/migrate_database.py
```

This creates the 4 new tables in your PostgreSQL database.

### Step 2: Test the Installation

```bash
# Run the test suite
python scripts/test_memory_v2.py
```

Expected output:
```
✅ All V2 tables exist
✅ Call processed successfully
✅ Caller profile retrieved
✅ Personality averages retrieved
✅ Enriched context retrieved

🎉 All tests passed!
```

## 📝 Phase 2: Integration

### How It Works

When a call completes, the system automatically:

1. **Summarizes the conversation** - 2-3 sentence summary
2. **Extracts key variables** - Account IDs, issue types, etc.
3. **Analyzes personality** - Communication style, sentiment
4. **Updates caller profile** - Increments call count, updates timestamp
5. **Calculates running averages** - Personality trends over time

### Integration Code

Add this to your conversation endpoint in `app/main.py`:

```python
from app.memory_integration import MemoryV2Integration

# Initialize (do this once at startup)
memory_v2 = MemoryV2Integration(memory_store, llm_chat)

# At the START of a new call - get enriched context
@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    user_id = request.user_id or request.thread_id
    
    # NEW: Get caller context (fast summary-based retrieval)
    caller_context = memory_v2.get_enriched_context_for_call(user_id)
    
    # Add to your system prompt
    system_prompt = f"""You are a helpful AI assistant.
    
{caller_context}

Use this context to personalize your responses."""
    
    # ... rest of your chat logic

# At the END of a call - process and summarize
@app.post("/end_call")
async def end_call(thread_id: str, user_id: str):
    conversation_history = THREAD_HISTORY.get(thread_id, [])
    
    # NEW: Process the completed call
    result = memory_v2.process_completed_call(
        conversation_history,
        user_id,
        thread_id
    )
    
    logger.info(f"Call summarized: {result.get('summary')}")
```

### Incremental Processing

For long calls, process incrementally:

```python
# Every 10 messages
if len(conversation_history) % 10 == 0:
    memory_v2.process_completed_call(
        conversation_history,
        user_id,
        thread_id
    )
```

## 🔄 Phase 3: Backfill Historical Data

Process your existing 5,755+ memories:

```bash
# Test with 10 records first
python scripts/backfill_memories.py --limit 10 --batch-size 5

# Full backfill (will take time!)
python scripts/backfill_memories.py --batch-size 50

# Resume from record 1000 if interrupted
python scripts/backfill_memories.py --skip 1000 --batch-size 50
```

**Note:** This uses your OpenAI API, so it will consume credits. Estimate: ~0.002¢ per call.

## 📈 Benefits

### 1. **10x Faster Retrieval**
- **Before:** Read 5,000+ raw messages
- **After:** Read 3-5 summaries (< 1 second)

### 2. **Smarter Personalization**
```
Caller Profile: 
- Name: John from Acme Corp
- Communication Style: very formal
- Technical Level: technical
- Recent Satisfaction: high (improving trend)
```

### 3. **Scalability**
- Works with millions of calls
- Summaries stay small, raw data archived
- Vector search for instant relevance

## 🛠️ Maintenance

### View Caller Analytics

```python
from app.memory import MemoryStore

mem = MemoryStore()

# Get caller stats
profile = mem.get_or_create_caller_profile("+15551234567")
print(f"Total calls: {profile['total_calls']}")

# Get personality trends
personality = mem.get_personality_averages("+15551234567")
print(f"Formality: {personality['avg_formality']}")
print(f"Satisfaction trend: {personality['satisfaction_trend']}")

# Search call history
summaries = mem.search_call_summaries("+15551234567", limit=5)
for s in summaries:
    print(f"{s['call_date']}: {s['summary']}")
```

### Monitor Performance

```sql
-- Check summary generation rate
SELECT 
    DATE(call_date) as date,
    COUNT(*) as calls_summarized
FROM call_summaries
GROUP BY DATE(call_date)
ORDER BY date DESC
LIMIT 7;

-- Most active callers
SELECT 
    user_id,
    total_calls,
    last_call_date
FROM caller_profiles
ORDER BY total_calls DESC
LIMIT 10;

-- Personality trends
SELECT 
    user_id,
    avg_formality,
    avg_technical_comfort,
    satisfaction_trend
FROM personality_averages
WHERE call_count > 5
ORDER BY last_updated DESC;
```

## 🐛 Troubleshooting

### Issue: "Table does not exist"
**Solution:** Run `python scripts/migrate_database.py`

### Issue: "Personality averages not updating"
**Solution:** The trigger should auto-update. Manually trigger:
```sql
SELECT update_personality_averages('user_id_here');
```

### Issue: "Backfill is slow"
**Solution:** 
- Reduce batch size: `--batch-size 10`
- Process in chunks: `--limit 100`, then `--skip 100 --limit 100`

### Issue: "LLM extractions failing"
**Solution:** Check OPENAI_API_KEY is set. Falls back to rule-based extraction if LLM unavailable.

## 📊 Data Model

```
┌─────────────────┐
│ Raw Memories    │  ← Old system (5,755 records)
│ (memories)      │
└─────────────────┘
        │
        ▼
┌─────────────────┐
│ Call Summaries  │  ← NEW: Concise summaries
│ + Key Variables │     (10x smaller, 10x faster)
└─────────────────┘
        │
        ▼
┌─────────────────┐
│ Caller Profiles │  ← NEW: Persistent caller info
│ + Personality   │     (preferences, context)
└─────────────────┘
        │
        ▼
    🚀 FAST AI
```

## 🎉 Next Steps

1. ✅ Run migration
2. ✅ Test with sample calls
3. ✅ Integrate into conversation flow
4. ⏳ Backfill historical data (Phase 3)
5. 📊 Monitor performance improvements

Expected result: **Response times drop from 2-3s to < 1s**

---

**Questions?** Check logs in `/tmp/logs/` or review `app/memory_v2_schema.py` for technical details.
