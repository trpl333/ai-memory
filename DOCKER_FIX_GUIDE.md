# Docker Deployment Fix for Digital Ocean

## Problem
Your Docker container was restarting immediately with exit code 0 because the Dockerfile was missing the `CMD` instruction. When running with `docker run` (not docker-compose), it defaulted to executing just `python3` which exits immediately.

## Solution Applied
Fixed the `Dockerfile` by adding the proper startup command:

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
```

## Deployment Steps for Digital Ocean

### 1. Push Changes to GitHub
Since git operations are restricted in Replit, you'll need to push manually:

```bash
# In the Replit Shell:
git add Dockerfile
git commit -m "Fix Docker startup command for production deployment"
git push origin main
```

### 2. Deploy on Digital Ocean Server

SSH into your Digital Ocean droplet and run:

```bash
cd /opt/ai-memory

# Pull latest changes from GitHub
git pull origin main

# Stop and remove old container
docker stop ai-memory-ai-memory-orchestrator-worker-1
docker rm ai-memory-ai-memory-orchestrator-worker-1

# Rebuild with the fixed Dockerfile
docker build -t ai-memory-ai-memory-orchestrator-worker .

# Run the container
docker run -d \
  -p 8100:8100 \
  --env-file .env \
  --restart unless-stopped \
  --name ai-memory-ai-memory-orchestrator-worker \
  ai-memory-ai-memory-orchestrator-worker

# Check if it's running
docker ps

# Check logs
docker logs ai-memory-ai-memory-orchestrator-worker

# Test the health endpoint
curl http://localhost:8100/health
```

### 3. Verify Deployment

The container should now:
- ✅ Stay running (not restart)
- ✅ Respond to health checks on port 8100
- ✅ Show "Up" status in `docker ps`

## Alternative: Use Docker Compose (Recommended)

For easier management, use the docker-compose file instead:

```bash
cd /opt/ai-memory
git pull origin main
docker-compose -f docker-compose-ai.yml up -d --build

# View logs
docker-compose -f docker-compose-ai.yml logs -f

# Check status
docker-compose -f docker-compose-ai.yml ps
```

## What Changed

**Before:**
```dockerfile
# Dockerfile ended with just a comment
# Command is specified in docker-compose.yml to use start_server.py
```

**After:**
```dockerfile
# Expose ports for Flask (5000), FastAPI (8001), and production (8100)
EXPOSE 5000 8001 8100

# Start the FastAPI application on port 8100 (production)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
```

## Troubleshooting

If the container still fails:

1. **Check environment variables:**
   ```bash
   docker run --rm --env-file .env ai-memory-ai-memory-orchestrator-worker env | grep -E "DATABASE_URL|OPENAI_API_KEY|TWILIO"
   ```

2. **Check logs for errors:**
   ```bash
   docker logs -f ai-memory-ai-memory-orchestrator-worker
   ```

3. **Verify database connection:**
   Make sure your `DATABASE_URL` in `.env` is accessible from the container

4. **Test locally first:**
   ```bash
   # Run interactively to see errors
   docker run --rm -it --env-file .env -p 8100:8100 ai-memory-ai-memory-orchestrator-worker
   ```

## Next Steps

1. Push the Dockerfile fix to GitHub from Replit Shell
2. Pull on Digital Ocean server
3. Rebuild and restart the container
4. Your AI memory service should be live on port 8100!
