# 🚀 DigitalOcean Deployment Fix - AI Phone System

## Issue Summary
The AI Phone System Flask app is running correctly on port 5000, but nginx is not configured to proxy `/phone/` requests, causing calls to hang up with 404 errors.

## Immediate Fix Required on DigitalOcean Server

### Step 1: SSH into your DigitalOcean server
```bash
ssh root@209.38.143.71  # Replace with your server IP
cd /opt/ChatStack
```

### Step 2: Pull latest configuration
```bash
git pull origin main
```

### Step 3: Apply nginx configuration
```bash
chmod +x deploy/update-nginx.sh
./deploy/update-nginx.sh
```

### Step 4: Verify Fix
```bash
# Test the endpoint
curl https://voice.theinsurancedoctors.com/phone/incoming -X POST -d "From=+12345678901&To=+19497071290"

# Should return TwiML XML (not 404)
```

### Step 5: Test Phone Call
Call **+19497071290** - it should now work with Samantha's voice!

---

## What This Fix Does

✅ **Adds missing nginx proxy rules** for:
- `/phone/` → Flask app (port 5000) - **Critical for Twilio webhooks**  
- `/static/` → Audio files (ElevenLabs TTS output)
- `/admin` → Admin interface

✅ **Preserves existing configuration** for legacy endpoints

✅ **Maintains SSL/HTTPS** setup with Let's Encrypt certificates

---

## Expected Result After Fix

🎯 **Phone Call Flow:**
```
+19497071290 → Twilio → https://voice.theinsurancedoctors.com/phone/incoming 
→ nginx proxy → Flask (port 5000) → Samantha greeting → ElevenLabs TTS 
→ Natural voice response
```

🎵 **Response Time:** 2-2.5 seconds  
🤖 **AI:** RunPod Mistral model  
🎙️ **Voice:** ElevenLabs natural speech  

---

## Verification Commands

```bash
# Check nginx status
systemctl status nginx

# Check Docker container
docker ps

# Test Flask app directly
curl http://localhost:5000/phone/incoming -X POST -d "test=1"

# Test through nginx
curl https://voice.theinsurancedoctors.com/phone/incoming -X POST -d "test=1"
```

Both should return identical TwiML XML responses.

---

## Troubleshooting

If nginx fails to start:
```bash
nginx -t  # Check configuration syntax
journalctl -u nginx -f  # View nginx logs
```

If calls still hang up:
```bash
docker logs chatstack-web-1 --tail=20  # Check Flask logs
```

---

**🎯 This fix resolves the documented issue in `replit.md` troubleshooting checklist: "Check nginx proxy configuration for `/phone/` location"**