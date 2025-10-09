# Peterson Family Insurance AI Phone System - Complete Technical Documentation

## System Overview

**Purpose**: AI-powered phone system for Peterson Family Insurance Agency using Samantha as the AI agent
**Phone Number**: +19497071290
**Production URL**: https://voice.theinsurancedoctors.com
**Target Response Time**: 2-2.5 seconds
**Deployment**: DigitalOcean Droplet with Docker + RunPod GPU for LLM

---

## Architecture Flow

```
Twilio Call → nginx (HTTPS) → Flask Orchestrator (port 5000) → FastAPI Backend (port 8001) → RunPod LLM → ElevenLabs TTS → MP3 Audio → Twilio → Caller
                                     ↓
                            AI-Memory Service (port 8100) + PostgreSQL + pgvector
```

---

## Core Files & Scripts

### **Main Application Files**
| File | Purpose | Key Responsibilities |
|------|---------|---------------------|
| `main.py` | Flask Orchestrator | Twilio webhooks, config bootstrap, static serving, starts FastAPI backend |
| `app/main.py` | FastAPI Backend | `/v1/chat` endpoint, health checks, admin interface |
| `app/llm.py` | LLM Integration | Communicates with RunPod endpoint for AI responses |
| `app/memory.py` | Memory Store | PostgreSQL + pgvector operations for conversation memory |
| `app/models.py` | Data Models | Pydantic request/response models |
| `app/packer.py` | Prompt Engineering | Context packing and memory injection |
| `app/tools.py` | Tool System | External tool execution and integration |

### **Configuration Files**
| File | Purpose | Contents |
|------|---------|----------|
| `config.json` | Public Configuration | Non-secret settings, URLs, model names |
| `config-internal.json` | Internal Configuration | Internal ports, hosts, service endpoints |
| `config_loader.py` | Configuration Manager | Centralized config, hot-reload, secret masking |

### **Deployment Files**
| File | Purpose | Usage |
|------|---------|--------|
| `docker-compose.yml` | Container Orchestration | Defines web service (nginx commented out) |
| `Dockerfile` | Container Build | Python 3.11, gunicorn, production setup |
| `deploy.sh` | Deployment Script | DigitalOcean automated deployment |
| `deploy-requirements.txt` | Production Dependencies | Production-specific Python packages |
| `nginx.conf` | Nginx Configuration | Proxy rules template |

### **Admin & Static Files**
| Path | Purpose |
|------|---------|
| `static/admin.html` | Admin Interface | Knowledge base management |
| `static/admin.html` | Admin Controls | System configuration |
| `static/audio/*.mp3` | Generated Audio | ElevenLabs TTS output files |

---

## Required Secrets (Environment Variables)

### **Critical Secrets**
| Secret | Purpose | Format |
|--------|---------|---------|
| `DATABASE_URL` | PostgreSQL Connection | `postgresql://user:pass@host:port/dbname` |
| `TWILIO_ACCOUNT_SID` | Twilio API Authentication | `ACxxxxxxxx...` |
| `TWILIO_AUTH_TOKEN` | Twilio API Authentication | `xxxxxxxx...` |
| `ELEVENLABS_API_KEY` | Text-to-Speech Service | `sk-xxxxxxxx...` |
| `SESSION_SECRET` | Flask Session Security | Strong random string |

### **Database Secrets**
| Secret | Purpose |
|--------|---------|
| `PGHOST` | PostgreSQL Host |
| `PGPORT` | PostgreSQL Port (typically 25060 for DigitalOcean) |
| `PGDATABASE` | Database Name |
| `PGUSER` | Database Username |
| `PGPASSWORD` | Database Password |

### **Optional Secrets**
| Secret | Purpose | When Needed |
|--------|---------|-------------|
| `OPENAI_API_KEY` | OpenAI API Access | If using OpenAI instead of RunPod |
| `LLM_API_KEY` | Custom LLM Authentication | For RunPod or other LLM services |

---

## Non-Secret Configuration (config.json)

### **LLM Configuration**
```json
{
  "llm_base_url": "https://a40.neurospherevoice.com",
  "llm_model": "mistralai/Mistral-7B-Instruct-v0.1"
}
```

### **Service URLs**
```json
{
  "ai_memory_url": "http://209.38.143.71:8100",
  "server_url": "https://voice.theinsurancedoctors.com/phone/incoming"
}
```

### **System Settings**
```json
{
  "embed_dim": 768,
  "port": 5000,
  "log_level": "INFO",
  "hot_reload_enabled": true,
  "config_reload_interval": 30,
  "environment": "production",
  "version": "2.1"
}
```

### **Voice Configuration**
```json
{
  "elevenlabs_voice_id": "dnRitNTYKgyEUEizTqqH",
  "twilio_phone_number": "+19497071290"
}
```

---

## Network Architecture

### **External Ports**
| Port | Service | Purpose |
|------|---------|---------|
| 80 | nginx | HTTP (redirects to HTTPS) |
| 443 | nginx | HTTPS with SSL certificates |
| 22 | SSH | Server administration |

### **Internal Ports**
| Port | Service | Purpose |
|------|---------|---------|
| 5000 | Flask App | Main orchestrator, Twilio webhooks |
| 8001 | FastAPI | LLM backend, chat API |
| 8100 | AI-Memory | Memory service (external) |
| 5432 | PostgreSQL | Database (managed service) |

### **SSL Configuration**
- **Certificates**: Let's Encrypt managed by certbot
- **Location**: `/etc/letsencrypt/live/voice.theinsurancedoctors.com/`
- **Protocols**: TLSv1.2, TLSv1.3

---

## API Endpoints

### **Public Endpoints (Flask - Port 5000)**
| Method | Endpoint | Purpose | Called By |
|--------|----------|---------|-----------|
| POST | `/phone/incoming` | Twilio webhook for incoming calls | Twilio |
| POST | `/phone/process-speech` | Handle user speech input | Twilio |
| GET | `/static/audio/*.mp3` | Serve generated audio files | Twilio |
| GET | `/admin` | Admin interface | Administrators |

### **Internal Endpoints (FastAPI - Port 8001)**
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Health check |
| POST | `/v1/chat/completions` | LLM chat completions |
| POST | `/v1/memories` | Memory storage |
| GET | `/admin` | Admin static files |

### **External Dependencies**
| Service | Endpoint | Purpose |
|---------|----------|---------|
| RunPod LLM | `https://a40.neurospherevoice.com/v1/chat/completions` | AI responses |
| ElevenLabs | `https://api.elevenlabs.io/v1/text-to-speech` | Natural voice synthesis |
| AI-Memory | `http://209.38.143.71:8100` | Conversation memory |
| Twilio | Webhook callbacks | Voice call management |

---

## Data Flow - Complete Call Process

### **1. Incoming Call**
```
Caller dials +19497071290
↓
Twilio receives call
↓
POST to https://voice.theinsurancedoctors.com/phone/incoming
```

### **2. Initial Greeting**
```
nginx proxy → Flask main.py:handle_incoming_call()
↓
get_personalized_greeting() checks memory
↓
text_to_speech() → ElevenLabs TTS → saves audio/greeting_CALLSID.mp3
↓
Returns TwiML with <Play> tag for audio file
```

### **3. Speech Processing**
```
User speaks → Twilio ASR → POST /phone/process-speech
↓
Flask receives transcription
↓
Calls ai_response() → FastAPI backend port 8001
↓
Backend calls RunPod LLM via app/llm.py
↓
LLM response → ElevenLabs TTS → saves audio/response_TIMESTAMP.mp3
↓
Returns TwiML with <Play> tag
```

### **4. Memory Storage**
```
Throughout conversation:
↓
Memory objects saved via AI-Memory service
↓
PostgreSQL with pgvector for semantic search
↓
Retrieved for context in future calls
```

---

## Deployment Components

### **Docker Configuration**
```yaml
# docker-compose.yml
services:
  web:
    build: .
    ports: ["5000:5000"]
    restart: unless-stopped
    # nginx service commented out (uses system nginx)
```

### **System Services**
| Service | Status | Purpose |
|---------|--------|---------|
| nginx | systemd | Reverse proxy, SSL termination |
| docker | systemd | Container runtime |
| chatstack-web-1 | docker | Main application container |

### **Required nginx Configuration**
```nginx
# Location block needed in /etc/nginx/sites-available/default
location /phone/ {
    proxy_pass http://127.0.0.1:5000/phone/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

---

## Security Configuration

### **SSL/TLS**
- **Provider**: Let's Encrypt (certbot)
- **Renewal**: Automatic
- **Protocols**: TLSv1.2, TLSv1.3 only
- **Ciphers**: HIGH:!aNULL:!MD5

### **Application Security**
- **Session Secret**: Must be set (falls back to insecure default)
- **API Keys**: Environment variables only, masked in logs
- **HTTPS Enforcement**: HTTP redirects to HTTPS

---

## Voice & AI Configuration

### **ElevenLabs Settings**
```python
VOICE_SETTINGS = {
    "stability": 0.71,
    "similarity_boost": 0.5,  # Fixed from clarity_boost
    "style": 0.0,
    "use_speaker_boost": True
}
```

### **LLM Settings**
```python
MAX_TOKENS = 75
TEMPERATURE = 0.6
TOP_P = 0.9
MODEL = "mistralai/Mistral-7B-Instruct-v0.1"
```

### **Call Routing Keywords**
- **Billing**: "billing", "payment", "premium", "pay bill"
- **Claims**: "claim", "accident", "damage", "injury"
- **Colin**: "colin", "ask for colin", "speak to colin"
- **Transfer**: "speak to human", "transfer me", "representative"

---

## Troubleshooting Checklist

### **Call Hangs Up Issues**
1. ✓ Check nginx proxy configuration for `/phone/` location
2. ✓ Verify Flask app responding: `curl http://localhost:5000/phone/incoming`
3. ✓ Check Docker container logs: `docker logs chatstack-web-1`
4. ✓ Test HTTPS endpoint: `curl https://voice.theinsurancedoctors.com/phone/incoming`

### **Voice Issues**
1. ✓ Verify `ELEVENLABS_API_KEY` is set
2. ✓ Check `/static/audio/` directory permissions
3. ✓ Test ElevenLabs integration in logs
4. ✓ Fallback to Twilio voice if ElevenLabs fails

### **AI Response Issues**
1. ✓ Verify RunPod endpoint: `https://a40.neurospherevoice.com`
2. ✓ Check `LLM_BASE_URL` environment variable
3. ✓ Test LLM connection in startup logs
4. ✓ Verify no `/v1/v1/` duplicate in URLs

### **Memory Issues**
1. ✓ Check `DATABASE_URL` connection
2. ✓ Verify AI-Memory service at `:8100`
3. ✓ Falls back to no-memory mode if unavailable

---

## Deployment Command Reference

### **Initial Deployment**
```bash
git clone https://github.com/trpl333/ChatStack.git
cd ChatStack
nano .env  # Configure all secrets
chmod +x deploy.sh
./deploy.sh
```

### **Updates**
```bash
git pull origin main
docker-compose down
docker-compose up -d --build
```

### **Verification**
```bash
docker ps  # Should show chatstack-web-1 running
curl https://voice.theinsurancedoctors.com/phone/incoming -X POST -d "test=1"
# Should return TwiML XML response
```

---

## Critical Success Factors

1. **All secrets properly set in environment**
2. **nginx proxy correctly routes `/phone/` to port 5000**
3. **Docker container running without errors**
4. **RunPod LLM endpoint accessible**
5. **ElevenLabs API key valid and working**
6. **SSL certificates valid and auto-renewing**
7. **Twilio webhook pointing to correct HTTPS URL**

---

**System Status**: Ready for production deployment with 2-2.5 second response times
**Last Updated**: September 12, 2025
**Version**: 2.1
