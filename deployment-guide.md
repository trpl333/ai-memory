# 🚀 DigitalOcean Deployment Guide for ChatStack AI Phone System

## Quick Start (5 minutes)

### 1. Create DigitalOcean Droplet
- Size: **Premium Intel with NVMe SSDs** (2 vCPUs, 4GB RAM minimum)
- OS: **Ubuntu 22.04 LTS**
- Region: Choose closest to your users for best latency
- Add your SSH key for secure access

### 2. Clone Repository
```bash
ssh root@your-droplet-ip
git clone https://github.com/trpl333/ChatStack.git
cd ChatStack
```

### 3. Configure Environment
```bash
cp .env.example .env
nano .env  # Fill in your API keys and database credentials
```

### 4. Run Deployment Script
```bash
chmod +x deploy.sh
./deploy.sh
```

That's it! Your AI phone system will be live in ~2 minutes.

---

## 📊 Performance Improvements

**Expected Response Times on DigitalOcean:**
- **Current (Replit)**: ~4 seconds total
- **DigitalOcean**: ~2-2.5 seconds total

**Breakdown:**
- Speech-to-Text: 0.3s (same)
- LLM Response: 0.8s (improved from 2.9s)
- Text-to-Speech: 0.86s (same)
- Network Overhead: 0.1s (reduced from 0.3s)

---

## 🔧 Configuration Details

### Required Environment Variables
```bash
# Database (Use DigitalOcean Managed Database)
DATABASE_URL=postgresql://user:pass@host:25060/dbname?sslmode=require
PGHOST=your-db.db.ondigitalocean.com
PGPORT=25060
PGDATABASE=your_db
PGUSER=your_user
PGPASSWORD=your_password

# Twilio (Phone System)
TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=+19497071290

# ElevenLabs (Voice)
ELEVENLABS_API_KEY=your_key
ELEVENLABS_VOICE_ID=dnRitNTYKgyEUEizTqqH  # Sol's voice

# LLM (RunPod or OpenAI)
LLM_BASE_URL=https://api.runpod.io/v2/your-endpoint/openai/v1
OPENAI_API_KEY=your_key

# Security
SESSION_SECRET=generate-random-string-here
```
## Configuration Files

The system uses two configuration files:

1. `config.json`  
   - External/public-facing settings (Twilio webhook URL, RunPod LLM URL, ElevenLabs voice ID, etc.).  
   - Safe to commit to GitHub (no secrets inside).  
   - Used by the orchestrator in production.

2. `config-internal.json`  
   - Internal/developer reference.  
   - Contains local loopback URLs (127.0.0.1), FastAPI backend port, Nginx proxy notes, and systemd service names.  
   - Not read by production code — for operator documentation only.  
   - Keeps infra details from cluttering `config.json`.

### Secrets

All sensitive values are stored in environment variables (Replit, GitHub Secrets, DO env):

- `DATABASE_URL`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `ELEVENLABS_API_KEY`
- `SESSION_SECRET`

### Database Setup (DigitalOcean Managed PostgreSQL)
1. Create database cluster in DigitalOcean
2. Enable pgvector extension
3. Add connection pool for better performance
4. Use connection string in DATABASE_URL

### Twilio Webhook Configuration
Update your Twilio phone number webhook to:
```
http://your-droplet-ip:5000/voice
```

---

## 🛡️ Security Recommendations

1. **SSL/HTTPS Setup** (After deployment)
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d your-domain.com
   ```

2. **Firewall Configuration**
   ```bash
   ufw allow 22/tcp  # SSH
   ufw allow 80/tcp  # HTTP
   ufw allow 443/tcp # HTTPS
   ufw allow 5000/tcp # Flask (temporary, remove after nginx setup)
   ufw enable
   ```

3. **Use DigitalOcean Spaces** for audio file storage (optional)
   - Reduces server load
   - Better scalability
   - CDN distribution

---

## 📈 Monitoring & Maintenance

### View Logs
```bash
docker-compose logs -f web  # Application logs
docker-compose logs -f nginx # Web server logs
```

### Restart Services
```bash
docker-compose restart
```

### Update Code
```bash
git pull origin main
docker-compose down
docker-compose up -d --build
```

### Health Check
```bash
curl http://localhost:5000/health
```

---

## 💰 Cost Optimization

**Recommended DigitalOcean Setup:**
- Droplet: $24/month (2 vCPU, 4GB RAM)
- Managed Database: $15/month (1GB RAM, 10GB storage)
- Spaces (optional): $5/month
- **Total: ~$44/month**

**GPU Considerations:**
- Current RunPod A40: Fast responses
- Alternative: Use OpenAI API directly (no GPU needed)
- Or: Deploy your own LLM on DigitalOcean GPU droplet

---

## 🚨 Troubleshooting

### Container won't start
```bash
docker-compose logs web
# Check for missing environment variables
```

### Database connection issues
```bash
# Test connection
docker exec -it chatstack_web_1 python -c "from app.memory import test_connection; test_connection()"
```

### Twilio webhooks not working
- Ensure firewall allows port 5000
- Check Twilio webhook URL is correct
- Verify ngrok isn't needed (direct IP works)

---

## 📞 Support

For Peterson Family Insurance specific questions:
- Phone system: Check Twilio console
- Voice issues: Check ElevenLabs dashboard
- Database: DigitalOcean support

Your AI assistant Samantha will be much faster on DigitalOcean!
