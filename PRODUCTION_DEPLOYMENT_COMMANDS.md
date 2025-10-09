# 🚀 Production Deployment - Phone System Fixes

## CRITICAL: These fixes resolve phone number lookup and user identification

### Changes Made (Ready for Production):
✅ **Fixed Flask → FastAPI communication** - Routes calls to local orchestrator instead of external LLM
✅ **Fixed user lookup system** - Phone numbers now properly identified and stored in memory  
✅ **Fixed conversation memory** - User history retrieved and maintained across calls
✅ **Fixed Twilio webhook routing** - Absolute URLs with actionOnEmptyResult for reliability
✅ **Added comprehensive logging** - Full visibility into phone processing flow

---

## 📋 Step 1: Commit and Push Changes

**Run these commands in your development environment:**

```bash
# Commit the phone system fixes
git add .
git commit -m "Fix phone number lookup and user identification system

- Fix Flask to FastAPI communication routing
- Add proper user_id parameter for memory operations  
- Fix payload format to match ChatRequest schema
- Add absolute URLs with actionOnEmptyResult for Twilio
- Add comprehensive logging for debugging
- Enable caller recognition with 'Remember me?' functionality"

# Push to main branch
git push origin main
```

---

## 📋 Step 2: Deploy to Production Server

**SSH into your production server:**

```bash
ssh root@209.38.143.71
cd /opt/ChatStack
```

**Pull the latest changes:**

```bash
# Pull latest fixes
git pull origin main

# Verify the key files were updated
ls -la main.py app/main.py app/llm.py
```

**Rebuild and restart services:**

```bash
# Stop current containers
docker-compose down

# Rebuild with latest code
docker-compose up -d --build

# Wait for services to start
sleep 15

# Check services are running
docker-compose ps
```

---

## 📋 Step 3: Verify Deployment

**Test the phone system:**

```bash
# Test phone endpoint
curl -X POST "https://voice.theinsurancedoctors.com/phone/process-speech" \
  -d "SpeechResult=Remember me?&CallSid=test123&From=+19495565377"

# Should return TwiML with AI response (not generic fallback)
```

**Check logs for phone processing:**

```bash
# Watch live logs
docker logs chatstack-web-1 --tail=50 -f

# Look for these log patterns after testing:
# 📞 /phone/process-speech route called
# 🎤 Speech from +19495565377 
# 🔍 Calling FastAPI orchestrator
# 🌐 FastAPI Response received
# 🤖 AI Response: [actual AI response]
```

---

## 📋 Step 4: Test Real Phone Call

**Call +19497071290 and say "Remember me?"**

**Expected behavior:**
- ✅ System recognizes phone number: +19495565377
- ✅ Retrieves conversation history from memory
- ✅ AI provides personalized response
- ✅ Fast response time (2-3 seconds)

---

## 🔧 Key Files Changed

1. **main.py** - Fixed Flask phone processing and FastAPI communication
2. **app/main.py** - Enhanced orchestrator with proper user_id handling  
3. **app/llm.py** - Improved LLM integration and error handling
4. **config.json** - Updated LLM backend configuration

---

## ⚠️ Important Notes

- **DO NOT touch `/opt/ChatStack/.env`** - All secrets are properly configured
- **Nginx config is already correct** - Proxies all `/phone/*` to Flask
- **A40 LLM endpoint working** - Backend switching operational
- **Memory service connected** - HTTP-based AI-Memory at 209.38.143.71:8100

---

## 🎯 Expected Results After Deployment

✅ **Phone calls will show processing logs**  
✅ **"Remember me?" will work with caller recognition**  
✅ **AI responses instead of generic fallback**  
✅ **2-2.5 second response times**  
✅ **Conversation memory preserved across calls**  

The phone system will fully recognize callers by number and maintain conversation history!
## 📋 Nginx + Send_Text Notes (Sept 2025)

1. **Call Summary Webhook**
   - Added nginx block to forward `/call-summary` → port 3000 (send_text.py).
   - `GET` returns 405 (expected), `POST` triggers SMS via Twilio.

2. **Config Cleanup**
   - Removed duplicate `/etc/nginx/sites-available/voice-theinsurancedoctors-com.conf`.
   - Confirmed only `/etc/nginx/sites-enabled/voice-theinsurancedoctors-com.conf` is active.

3. **send_text.py Service**
   - Location: `/root/neurosphere_send_text/send_text.py`.
   - Run inside tmux:
     ```bash
     tmux new -s sendtext
     cd /root/neurosphere_send_text
     python3 send_text.py
     # CTRL+b d to detach
     ```
   - Logs show SMS delivery on POST webhook from ElevenLabs.
## 📋 Nginx & Send_Text Notes (Sept 2025)

- Cleaned up duplicate configs:
  - Removed `/etc/nginx/sites-available/voice-theinsurancedoctors-com.conf`
  - Kept `/etc/nginx/sites-enabled/voice-theinsurancedoctors-com.conf` as the active config
- Added `/call-summary` block to forward ElevenLabs post-call webhooks to send_text.py on port 3000.
- Verified with:
  - `curl https://voice.theinsurancedoctors.com/call-summary` → returns 405
  - POST from ElevenLabs → 200 + SMS sent
- Confirmed nginx process list is clean: one master, four workers, ports 80/443 only.
- `send_text.py` runs inside tmux:
  ```bash
  tmux new -s sendtext
  cd /root/neurosphere_send_text
  python3 send_text.py
  CTRL+b d   # detach
