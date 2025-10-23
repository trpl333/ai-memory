# NeuroSphere Multi-Project Architecture
**Last Updated:** October 23, 2025  
**Version:** 1.3.0 - AI-Memory V2 with call summaries and personality tracking

> **⚠️ IMPORTANT**: This file is shared across ChatStack, AI-Memory, LeadFlowTracker, and NeuroSphere Send Text projects.  
> When making changes, update the version number and commit to GitHub so all projects can sync.
> 
> **GitHub Repos:**
> - ChatStack: `trpl333/ChatStack`
> - AI-Memory: `trpl333/ai-memory`
> - LeadFlowTracker: `trpl333/LeadFlowTracker`
> - NeuroSphere Send Text: `trpl333/neurosphere_send_text`

---

## 🏗️ System Overview

NeuroSphere is a multi-service AI phone system platform with 4 interconnected services:

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐      ┌─────────────┐
│  ChatStack  │─────▶│  AI-Memory   │      │   LeadLow   │      │  SentText   │
│  (Phone AI) │      │  (Storage)   │      │  (CRM/Leads)│      │    (SMS)    │
└─────────────┘      └──────────────┘      └─────────────┘      └─────────────┘
     │                      ▲                      │                    │
     │                      │                      │                    │
     └──────────────────────┴──────────────────────┴────────────────────┘
                      All services share AI-Memory
```

---

## 📡 Service Details

### 1. ChatStack (AI Phone System)
**Repository:** `chatstack`  
**Production:** DigitalOcean (209.38.143.71)  
**Ports:**
- 5000: Flask Admin Panel (Web UI)
- 8001: FastAPI Orchestrator (Phone WebSocket handler)

**Key Responsibilities:**
- Twilio voice call handling
- OpenAI Realtime API integration
- Call recording & transcription
- Admin configuration interface
- Real-time conversation management

**Dependencies:**
- AI-Memory (port 8100) - Memory storage & retrieval
- OpenAI API - LLM responses
- Twilio - Voice calls
- ElevenLabs - Text-to-Speech

---

### 2. AI-Memory (Memory Service)
**Repository:** `ai-memory` (GitHub: trpl333/ai-memory)  
**Production:** DigitalOcean (209.38.143.71:8100)  
**Port:** 8100

**API Endpoints:**
```
# Core Service
GET  /                              - Service info & status
GET  /admin                         - Admin interface
GET  /health                        - Health check (DB status)

# Memory V1 API (Legacy)
GET  /v1/memories                   - Retrieve memories (params: user_id, limit, memory_type)
POST /v1/memories                   - Store new memory
POST /v1/memories/user              - Store user-specific memory
POST /v1/memories/shared            - Store shared memory
GET  /v1/memories/user/{user_id}    - Get all memories for user
GET  /v1/memories/shared            - Get shared memories
DELETE /v1/memories/{memory_id}     - Delete specific memory

# Chat & LLM
POST /v1/chat                       - Chat completion with memory context
POST /v1/chat/completions           - OpenAI-compatible chat endpoint

# Tools
GET  /v1/tools                      - List available tools
POST /v1/tools/{tool_name}          - Execute specific tool

# Memory V2 API (NEW - Deployed Oct 23, 2025)
# ✅ 10x faster retrieval with call summaries and personality tracking

# Call Summarization
POST /v2/process-call               - Process completed call (auto-summarize + personality)
                                     - Input: conversation_history, user_id, thread_id
                                     - Returns: summary, sentiment, personality metrics
                                     
GET  /v2/summaries/{user_id}        - Get call summaries for user
POST /v2/summaries/search           - Semantic search on call summaries (not raw data)

# Caller Profiles & Context
GET  /v2/profile/{user_id}          - Get caller profile
POST /v2/context/enriched           - Get enriched context for new call (fast!)
                                     - Returns: personality profile + recent summaries
                                     - Response time: <1 second (vs 2-3 sec for V1)

# Personality Tracking
GET  /v2/personality/{user_id}      - Get personality averages
                                     - Returns: Big 5 traits + communication style + trends
                                     
POST /v2/personality/metrics        - Store personality metrics for call
```

**Data Models:**
- **Memories** (V1 - key-value with semantic search)
- **Call Summaries** (V2 - AI-generated 2-3 sentence summaries)
- **Caller Profiles** (V2 - persistent caller info: name, total_calls, preferences)
- **Personality Metrics** (V2 - per-call: Big 5, communication style, emotional state)
- **Personality Averages** (V2 - running averages with trend indicators)

**Database:** PostgreSQL with pgvector for semantic search

**V2 Tables (Oct 23, 2025):**
- `call_summaries` - AI-generated summaries with embeddings
- `caller_profiles` - Persistent caller information
- `personality_metrics` - Per-call personality measurements (13 metrics)
- `personality_averages` - Running averages with auto-update triggers

**Performance:**
- V1: 2-3 seconds (reads 5,755+ raw memories)
- V2: <1 second (reads 5 summaries + personality profile)
- **10x improvement** via summary-first retrieval

**Used By:**
- ChatStack (primary consumer)
- LeadLow (lead enrichment)
- SentText (personalization data)

---

### 3. LeadFlowTracker (CRM/Lead Management)
**Repository:** `LeadFlowTracker` (GitHub: trpl333/LeadFlowTracker)  
**Production:** TBD  
**Port:** TBD (likely 3001 or 5001)

**Tech Stack:** Node.js, Express, TypeScript, Drizzle ORM, PostgreSQL

**Key Responsibilities:**
- Lead capture and management
- Lead pipeline tracking with milestone system
- Google Sheets integration for data sync
- Lead status management (active/lost/reactivated)
- Notes and stage tracking

**API Endpoints:**
```
# Lead Management
GET    /api/leads              - Get all leads
GET    /api/leads/:id          - Get lead by ID
POST   /api/leads              - Create new lead
DELETE /api/leads/:id          - Delete lead

# Lead Actions
POST   /api/leads/:id/milestone       - Toggle milestone for lead
POST   /api/leads/:id/mark-lost       - Mark lead as lost
POST   /api/leads/:id/reactivate      - Reactivate lost lead
PATCH  /api/leads/:id/notes           - Update lead notes
PATCH  /api/leads/:id/stage           - Update lead stage
```

**Dependencies:**
- PostgreSQL database (Drizzle ORM)
- Google Sheets API (for data sync)
- AI-Memory (potential - for lead enrichment)

---

### 4. NeuroSphere Send Text (SMS Service)
**Repository:** `neurosphere_send_text` (GitHub: trpl333/neurosphere_send_text)  
**Production:** DigitalOcean (/root/neurosphere_send_text/)  
**Port:** 3000

**Tech Stack:** Python, Flask, Twilio SDK

**Key Responsibilities:**
- Post-call SMS notifications with summaries
- Call transcript and audio file management
- ElevenLabs webhook handler
- Multi-recipient SMS delivery
- Call index maintenance (calls.json)

**API Endpoints:**
```
POST /call-summary    - Receive ElevenLabs webhook, save transcript, send SMS
                       - Extracts: call_sid, caller, transcript summary
                       - Saves: {call_sid}.txt (transcript), {call_sid}.mp3 (audio chunks)
                       - Updates: calls.json index
                       - Sends: SMS to configured recipients with summary + links
```

**Data Flow:**
1. ElevenLabs calls POST /call-summary after call ends
2. Extracts metadata from `data.metadata.phone_call`
3. Saves transcript summary to `/opt/ChatStack/static/calls/{call_sid}.txt`
4. Appends audio chunks (base64) to `/opt/ChatStack/static/calls/{call_sid}.mp3`
5. Updates `/opt/ChatStack/static/calls/calls.json` with call record
6. Sends SMS to recipients: +19493342332, +19495565379

**SMS Recipients:**
- Primary: +19493342332
- Secondary: +19495565379

**Dependencies:**
- Twilio SMS API (from: +18633433339)
- ElevenLabs (webhook trigger)
- ChatStack filesystem (shares /opt/ChatStack/static/calls/)

**Integration:**
- Nginx forwards `/call-summary` → port 3000 (send_text.py)
- Runs in tmux session: `cd /root/neurosphere_send_text && python3 send_text.py`
- Shares call storage directory with ChatStack

---

## 🔄 Integration Patterns

### ChatStack ↔ AI-Memory
**Connection:** HTTP REST API  
**Endpoint:** `http://209.38.143.71:8100`

**Usage:**
```python
# ChatStack retrieves memories
GET http://209.38.143.71:8100/v1/memories?user_id={phone}&limit=500

# ChatStack stores memories
POST http://209.38.143.71:8100/v1/memories
{
  "user_id": "{phone}",
  "type": "fact",
  "key": "caller_name",
  "value": {"name": "John Smith"},
  "scope": "user"
}
```

**Memory V2 API (NEW - Oct 23, 2025):**
```python
# Get enriched context (fast - <1 second!)
POST http://209.38.143.71:8100/v2/context/enriched
{
  "user_id": "+15551234567",
  "num_summaries": 5
}

# Returns:
# - Caller profile (name, total calls, preferences)
# - Personality summary (Big 5, communication style, satisfaction trend)
# - Recent call summaries (5 concise summaries instead of 5,755 raw memories)
# - Response time: <1 second (vs 2-3 seconds with V1)

# Process completed call (auto-summarize + personality tracking)
POST http://209.38.143.71:8100/v2/process-call
{
  "user_id": "+15551234567",
  "thread_id": "call_12345",
  "conversation_history": [
    ("user", "Hello, I need help with billing"),
    ("assistant", "I can help you with that...")
  ]
}

# Returns:
# - summary: AI-generated 2-3 sentence summary
# - sentiment: frustrated/satisfied/neutral
# - key_topics: ["billing", "account_issue"]
# - personality_metrics: Big 5 + communication style scores
```

### LeadLow ↔ AI-Memory
**Connection:** TBD  
**Usage:** TBD

### SentText ↔ AI-Memory
**Connection:** TBD  
**Usage:** TBD

---

## 🚀 Deployment Locations

| Service           | Environment | Location                      | Port | Status  | Notes                    |
|-------------------|-------------|-------------------------------|------|---------|--------------------------|
| ChatStack (Flask) | Production  | DO: 209.38.143.71            | 5000 | Running | Admin UI                 |
| ChatStack (FastAPI)| Production  | DO: 209.38.143.71            | 8001 | Running | Phone orchestrator       |
| AI-Memory         | Production  | DO: 209.38.143.71            | 8100 | Running | Memory service           |
| Send Text         | Production  | DO: /root/neurosphere_send_text | 3000 | Running | SMS service (tmux)      |
| LeadFlowTracker   | Development | Replit/Local                 | TBD  | Dev     | CRM system               |

---

## 📝 Update Protocol (CRITICAL - READ THIS!)

**🎯 GitHub is the Single Source of Truth**
- Master copy lives at: `https://github.com/trpl333/ChatStack/blob/main/MULTI_PROJECT_ARCHITECTURE.md`
- All 4 Replits sync from GitHub (not from each other)
- ChatGPT always reads from GitHub (always latest)

---

### **When You Make Changes to ANY Service:**

**Step 1: Pull Latest Before Working**
```bash
# In any Replit (ChatStack, AI-Memory, LeadFlowTracker, neurosphere_send_text)
./sync_architecture.sh pull
```

**Step 2: Make Your Changes**
- Update your service code
- Edit `MULTI_PROJECT_ARCHITECTURE.md` with new endpoints/changes
- Update section for your service

**Step 3: Push Updates to GitHub**
```bash
./sync_architecture.sh push
# Script will:
# - Ask you to update version number (e.g., 1.2.0 → 1.3.0)
# - Update the "Last Updated" date automatically
# - Commit and push to GitHub
```

**Step 4: Other Replits Auto-Sync**
- Agents in other Replits run `./sync_architecture.sh pull` before working
- They get your latest changes immediately

---

### **Quick Command Reference:**

```bash
# Pull latest from GitHub (do this BEFORE working)
./sync_architecture.sh pull

# Check current version
./sync_architecture.sh version

# Push your updates to GitHub (do this AFTER making changes)
./sync_architecture.sh push
```

---

### **For ChatGPT Consultation:**

**Always use the latest version from GitHub:**
```
https://raw.githubusercontent.com/trpl333/ChatStack/main/MULTI_PROJECT_ARCHITECTURE.md
```

ChatGPT can read this URL directly and will always see the most current architecture!

**Example ChatGPT prompt:**
```
Please read my architecture documentation from GitHub:
https://raw.githubusercontent.com/trpl333/ChatStack/main/MULTI_PROJECT_ARCHITECTURE.md

Question: [your question about the system]
```

---

## 🔧 Environment Variables

### ChatStack
```bash
DATABASE_URL=postgresql://...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
OPENAI_API_KEY=...
ELEVENLABS_API_KEY=...
SESSION_SECRET=...
LLM_BASE_URL=https://api.openai.com/v1
```

### AI-Memory
```bash
DATABASE_URL=postgresql://...
# Add AI-Memory specific vars
```

### LeadLow
```bash
# TODO: Add LeadLow environment variables
```

### SentText
```bash
# TODO: Add SentText environment variables
```

---

## 📚 Key Learnings

### API Endpoint Mismatches (Oct 23, 2025)
**Issue:** ChatStack was calling wrong AI-Memory endpoints:
- ❌ `POST /memory/retrieve` (404)
- ❌ `POST /memory/store` (404)

**Fix:** Updated to correct endpoints:
- ✅ `GET /v1/memories`
- ✅ `POST /v1/memories`

**Lesson:** Always check this file before integrating. Keep endpoint specs up-to-date!

---

## 🔗 Cross-Project Code Access (ChatStack Only)

**ChatStack Replit has all 4 repos cloned locally** in the `external/` directory:

```bash
external/
├── ai-memory/           # Full AI-Memory codebase
├── LeadFlowTracker/     # Full CRM codebase  
└── neurosphere-send_text/  # Full SMS service codebase
```

**Benefits:**
- ✅ I can see actual endpoints and code from all services
- ✅ No more endpoint mismatches (like the `/memory/retrieve` vs `/v1/memories` issue)
- ✅ Architecture always stays aligned
- ✅ Easy to search across all projects

**To Update:**
```bash
# Re-download latest code from all repos
node fetch_repos.js
```

This uses the GitHub integration to pull latest code from your private repos.

---

## 🎯 Future Enhancements

- [x] Clone all 4 repos into ChatStack for full visibility
- [x] Document real endpoints from actual code
- [ ] Add Memory V2 endpoint specifications when implemented
- [ ] Add webhook specifications
- [ ] Document error codes and handling
- [ ] Add sequence diagrams for complex flows
- [ ] Create OpenAPI specs for each service
- [x] Find correct neurosphere_send_text repo name and add

---

**Maintained by:** NeuroSphere Development Team  
**Questions?** Check individual project READMEs or update this file with clarifications.
