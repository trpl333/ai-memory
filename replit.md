# Peterson Family Insurance AI Phone System

## 📋 **CURRENT STATUS**

### **Production System** - Fully Operational
- **Platform**: DigitalOcean Droplet with Docker
- **Performance**: 2-2.5 second response times achieved
- **Architecture**: Microservices (Flask + FastAPI + AI-Memory service)
- **Status**: ✅ **PRODUCTION READY** with completed microservices migration

## Overview
This project is an AI-powered phone system for Peterson Family Insurance, utilizing "Samantha" as the AI agent. The system, built on NeuroSphere Orchestrator, is a FastAPI-based solution designed for intelligent call handling with persistent memory. It aims for a rapid response time of 2-2.5 seconds. Key capabilities include maintaining conversation continuity via HTTP-based AI-Memory service, integrating external tools for actions, and employing safety modes for content filtering. The orchestrator serves as middleware between Twilio voice calls and Language Learning Models (LLMs), enhancing conversations through memory retrieval, prompt engineering, and extensible tool functionality.

**✅ LATEST MAJOR ACHIEVEMENTS:**

- **Sept 25, 2025**: ✅ **MICROSERVICES MIGRATION COMPLETE** - Successfully migrated all admin settings from config.json to ai-memory service, implementing true microservices architecture with centralized configuration management
- **Sept 13, 2025**: ✅ **MEMORY SYSTEM OVERHAUL** - Migrated from direct PostgreSQL to HTTP-based AI-Memory service, eliminating "degraded mode" issues
- **Current**: ✅ **LLM MIGRATION COMPLETE** - Fully migrated from RunPod to OpenAI Realtime API (gpt-realtime, GA Aug 2025)

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture
**✅ MICROSERVICES ARCHITECTURE (Completed Sept 25, 2025)**

The system now operates as a true microservices architecture with complete separation of concerns:

1. **Phone System (ChatStack)**: Flask orchestrator (`main.py`) handles Twilio webhooks
2. **AI Engine**: FastAPI backend (`app/main.py`) manages LLM integration and conversation flow
3. **AI-Memory Service**: External HTTP service (http://209.38.143.71:8100) handles all persistent memory and admin configuration

**Configuration Flow**: Admin Panel → AI-Memory Service → Phone System → Twilio Calls

**Key Improvement**: All admin settings (greetings, voice settings, AI instructions) are now stored in the ai-memory service instead of local config files, enabling dynamic configuration without code deployment.

## ⚠️ CRITICAL: Environment Configuration

**NEVER TOUCH /opt/ChatStack/.env FILE**
- The `/opt/ChatStack/.env` file on DigitalOcean server contains all production secrets and is properly configured
- This file should NEVER be deleted, overwritten, or modified by scripts or agents
- All secrets are properly set in this file and working correctly
- Any issues should be debugged WITHOUT touching this file
- Architecture: Secrets in .env file, non-secrets in config.json

### Current Production Secrets (in .env file):
- DATABASE_URL, PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
- TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
- ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
- OPENAI_API_KEY, LLM_BASE_URL, SESSION_SECRET
- DEEPGRAM_API, HUGGINHFACE_TOKEN

### Core Components:
- **LLM Integration**: ✅ **FULLY MIGRATED TO OPENAI** - Uses OpenAI Realtime API (gpt-realtime, GA Aug 2025) for AI responses with 2-2.5 second response times. Completely replaced previous RunPod integration.

- **Memory System**: ✅ **PERSISTENT HYBRID ARCHITECTURE WITH CONSOLIDATION (Oct 1, 2025)** - Three-tier memory system for unlimited conversation memory:
  
  **Layer 1: Rolling Thread History (Database-Backed, 500 messages)**
  - FastAPI maintains `THREAD_HISTORY` deque (maxlen=500, ~250 turns) per stable `thread_id`
  - Thread ID format: `user_{phone_number}` (e.g., `user_9495565377`)
  - ✅ Automatically loads from database on first access
  - ✅ Saves to database after each turn (survives container restarts!)
  - ✅ **NEW**: Automatic memory consolidation at 400 messages
  - Provides within-call AND cross-call conversation continuity
  - Persists indefinitely (7-day TTL in ai-memory service)
  
  **Layer 2: Automatic Memory Consolidation (LLM-Powered)**
  - ✅ **NEW**: Triggers at 400/500 messages to prevent information loss
  - LLM analyzes oldest 200 messages and extracts structured data:
    - **People**: Family members, relationships (Kelly, Jack, Colin)
    - **Facts**: Important dates, events (birthdays, anniversaries)
    - **Preferences**: Likes/dislikes, interests (spa days, hobbies)
    - **Commitments**: Promises, follow-ups (plan celebration)
  - Deterministic de-duplication using SHA1 hashes
  - Prunes thread history to 300 messages after consolidation
  - Runs automatically in background during conversation
  
  **Layer 3: AI-Memory Service (Permanent Durable Storage)**
  - HTTP-based service at http://209.38.143.71:8100
  - Stores structured facts: person, preference, project, rule, moment, fact
  - Handles admin settings (greetings, voice settings, AI instructions)
  - User registration and caller management
  - Robust HTTPMemoryStore with concatenated JSON parser
  - Long-term retention (365 days for facts, 90 days for commitments)
  
  **Implementation Details:**
  - Flask (`main.py` line 686): Generates `thread_id = f"user_{user_id}"` instead of CallSid
  - FastAPI (`app/main.py` line 37): Maintains THREAD_HISTORY dict with deques
  - ✅ **NEW** (`app/main.py` line 42-92): `load_thread_history()` and `save_thread_history()` functions
  - Memory parser (`app/http_memory.py` line 175-191): Parses newline-separated JSON format
  - Message storage (line 81): Sends full JSON content via `json.dumps(value)`
  - Thread persistence: Stored as `thread_history:{thread_id}` in ai-memory service
  
  **Conversation Flow Improvements:**
  - ✅ **NEW**: Fresh start on callbacks - system asks "How can I help you today?" instead of continuing old topics
  - Callback detection: Automatically identifies returning callers vs new callers
  - Dual user_id search (normalized + raw) for reliable callback detection
  
  **Benefits:**
  - ✅ **Unlimited conversation memory** - consolidation prevents loss after 500 messages
  - Fast conversation flow without database queries every turn
  - ✅ Conversation history survives container restarts and worker reloads
  - ✅ Important facts automatically extracted and preserved forever
  - ✅ Natural callback experience - fresh greeting + open-ended prompt
  - 500+ message history window (5x increase from previous 100)
  - Natural cross-call continuity (same thread_id = same history)
  - Zero data loss on deployment/restart events

- **Prompt Engineering**: Employs file-based system prompts for AI personalities, intelligent context packing from memory, and safety triggers for content filtering.
- **Tool System**: An extensible, JSON schema-based architecture for external tool execution (e.g., meeting booking, message sending) with a central dispatcher and error recovery.
- **Data Models**: Pydantic for type-safe validation of request/response models, including role-based messages and structured memory objects.
- **Safety & Security**: Features multi-tier content filtering, PII protection, rate limiting, and comprehensive input validation.

### UI/UX Decisions:
- **Admin Panel**: Web interface at `/admin.html` provides full control over:
  - Greeting messages for different caller types
  - Voice settings and AI personality
  - System configuration via ai-memory service
- **Voice-First Design**: Seamless voice interaction with ElevenLabs TTS integration
- **Real-time Updates**: Admin changes take effect immediately without code deployment

### Technical Implementations:
- **Python Frameworks**: Flask and FastAPI.
- **Database**: PostgreSQL with `pgvector` for vector embeddings and `pgcrypto` for UUIDs.
- **Containerization**: Docker for deployment, with `docker-compose.yml` for orchestration.
- **Web Server**: Nginx for HTTPS termination, proxying requests to the Flask and FastAPI services.
- **Deployment**: Primarily on DigitalOcean Droplets with OpenAI API for LLM inference.

## External Dependencies

### Services:
- **Twilio**: For voice call management and incoming call webhooks.
- **OpenAI API**: Primary LLM service using GPT Realtime model (`https://api.openai.com/v1/chat/completions`).
- **ElevenLabs**: For natural voice synthesis and text-to-speech conversion.
- **AI-Memory Service**: An external service for conversation memory persistence (`http://209.38.143.71:8100`).

### Databases:
- **PostgreSQL**: Used with `pgvector` extension for conversation memory and semantic search.

### Libraries (Key Examples):
- **FastAPI** & **Uvicorn**: Web framework and ASGI server.
- **Pydantic**: Data validation.
- **NumPy**: Vector operations.
- **Requests**: HTTP client.
- **psycopg2**: PostgreSQL adapter.

### Optional Integrations (Planned/Recommended):
- **Redis**: For production short-term memory.
- **Embedding Services**: Such as OpenAI Embeddings or Sentence Transformers for production embedding generation.

---

## Nginx Configuration Management

### **Check Active Configurations**
```bash
ls /etc/nginx/sites-enabled/
```

**Expected configurations:**
- `voice-theinsurancedoctors-com.conf` → AI Phone System
- `neurosphere-llms.conf` → Legacy config (should serve different domain or be removed)

### **Rules**
1. **Only one config** should claim `server_name voice.theinsurancedoctors.com`
2. **The `voice-theinsurancedoctors-com.conf`** must contain both `/phone/` and `/static/` proxy blocks:
   ```nginx
   location /phone/ {
       proxy_pass http://127.0.0.1:5000/phone/;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
   }

   location /static/ {
       proxy_pass http://127.0.0.1:5000/static/;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
   }
   ```
3. **`neurosphere-llms.conf`** is legacy config - should serve different hostname or be removed (RunPod no longer used)

### **Conflict Detection**
```bash
# Check what neurosphere-llms.conf serves
sudo cat /etc/nginx/sites-enabled/neurosphere-llms.conf | grep -E "server_name|listen|default_server"
```

**Action Rules:**
- **Keep it** if it serves different domain
- **Disable it** if it references `voice.theinsurancedoctors.com` or has `default_server`

### **Deployment Commands**
```bash
# Deploy canonical config
sudo cp /opt/ChatStack/deploy/nginx/voice-theinsurancedoctors-com.conf /etc/nginx/sites-enabled/

# Remove conflicts (only if they claim same domain)
sudo rm /etc/nginx/sites-enabled/default  # if exists
sudo rm /etc/nginx/sites-enabled/neurosphere-llms.conf  # legacy RunPod config, remove if conflicts

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

### **Verification**
```bash
# Test static files proxied correctly
curl -I https://voice.theinsurancedoctors.com/static/audio/
# Should return: HTTP/1.1 200 OK (not 404)

# Test phone endpoint
curl -X POST https://voice.theinsurancedoctors.com/phone/incoming -d "test=1"
# Should return TwiML with HTTPS URLs
```

---

## Troubleshooting Checklist

### **Call Hangs Up Issues**
1. ✅ **Memory System**: Fixed - HTTP-based AI-Memory service working perfectly 
2. ✓ **Check for multiple nginx configurations causing conflicts**:
   ```bash
   ls /etc/nginx/sites-enabled/
   # Should prioritize: voice-theinsurancedoctors-com.conf
   # Check conflicts: sudo cat /etc/nginx/sites-enabled/neurosphere-llms.conf | grep -E "server_name|default_server"
   ```
3. ✓ **Verify `/static/` proxy is configured** for audio file access:
   ```bash
   curl -I https://voice.theinsurancedoctors.com/static/audio/
   # Should return 200 OK, not 404
   ```
4. ✓ Check nginx proxy configuration for `/phone/` location
5. ✓ Verify Flask app responding: `curl http://localhost:5000/phone/incoming`
6. ✓ Check Docker container logs: `docker logs chatstack-web-1`
7. ✓ Test HTTPS endpoint: `curl https://voice.theinsurancedoctors.com/phone/incoming`

### **Current Status (Sept 25, 2025)**
- ✅ **MICROSERVICES MIGRATION**: Complete - all admin settings in ai-memory service
- ✅ **Memory System**: Fully operational with HTTP-based AI-Memory service
- ✅ **LLM Integration**: OpenAI Realtime API (https://api.openai.com/v1) - RunPod completely removed
- ✅ **Admin Panel**: Dynamic configuration via web interface
- ✅ **User Registration**: Automatic caller registration with persistent memory
- **Performance**: Achieving 2-2.5 second response times in production

### **Voice Issues**
1. ✓ Verify `ELEVENLABS_API_KEY` is set
2. ✓ Check `/static/audio/` directory permissions
3. ✓ Test ElevenLabs integration in logs
4. ✓ Fallback to Twilio voice if ElevenLabs fails

### **AI Response Issues**
1. ✓ Verify OpenAI API endpoint: `https://api.openai.com/v1`
2. ✓ Check `OPENAI_API_KEY` environment variable
3. ✓ Check `LLM_BASE_URL` environment variable
4. ✓ Test LLM connection in startup logs