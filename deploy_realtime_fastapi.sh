#!/bin/bash
# Deployment script for OpenAI Realtime API integration to DigitalOcean server
# Uses existing FastAPI service (port 8001) for WebSocket bridge
# Usage: ./deploy_realtime_fastapi.sh [server_ip] [ssh_user]

set -e  # Exit on error

# Configuration
SERVER_IP="${1:-209.38.143.71}"
SSH_USER="${2:-root}"
REMOTE_PATH="/opt/ChatStack"
LOCAL_FILES=(
    "main.py"
    "app/main.py"
)

echo "🚀 Starting deployment to DO server at $SSH_USER@$SERVER_IP:$REMOTE_PATH"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Step 1: Backup current code on server
echo ""
echo "📦 Step 1: Creating backup of current code..."
ssh $SSH_USER@$SERVER_IP << 'ENDSSH'
cd /opt/ChatStack
BACKUP_DIR="/opt/ChatStack_backup_$(date +%Y%m%d_%H%M%S)"
echo "Creating backup at: $BACKUP_DIR"
cp -r /opt/ChatStack "$BACKUP_DIR"
echo "✅ Backup created successfully"
ENDSSH

# Step 2: Upload new files
echo ""
echo "📤 Step 2: Uploading updated files..."
for file in "${LOCAL_FILES[@]}"; do
    echo "  → Uploading $file"
    scp "$file" "$SSH_USER@$SERVER_IP:$REMOTE_PATH/$file"
done
echo "✅ Files uploaded successfully"

# Step 3: Check/Update nginx configuration
echo ""
echo "🔧 Step 3: Checking nginx WebSocket configuration..."
ssh $SSH_USER@$SERVER_IP << 'ENDSSH'
# Check if WebSocket proxy exists for FastAPI
if ! grep -q "/phone/media-stream" /etc/nginx/sites-enabled/voice-theinsurancedoctors-com.conf 2>/dev/null; then
    echo "⚠️  WebSocket proxy configuration missing!"
    echo ""
    echo "Add this to your nginx config (/etc/nginx/sites-enabled/voice-theinsurancedoctors-com.conf):"
    echo ""
    echo "    # WebSocket proxy for Twilio Media Streams (FastAPI port 8001)"
    echo "    location /phone/media-stream {"
    echo "        proxy_pass http://127.0.0.1:8001/phone/media-stream;"
    echo "        proxy_http_version 1.1;"
    echo "        proxy_set_header Upgrade \$http_upgrade;"
    echo "        proxy_set_header Connection \"upgrade\";"
    echo "        proxy_set_header Host \$host;"
    echo "        proxy_set_header X-Real-IP \$remote_addr;"
    echo "        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;"
    echo "        proxy_set_header X-Forwarded-Proto \$scheme;"
    echo "        proxy_read_timeout 3600;"
    echo "        proxy_send_timeout 3600;"
    echo "    }"
    echo ""
else
    echo "✅ WebSocket proxy configuration found"
fi

# Test nginx config
sudo nginx -t
ENDSSH

# Step 4: Restart Docker containers
echo ""
echo "🔄 Step 4: Restarting Docker containers..."
ssh $SSH_USER@$SERVER_IP << 'ENDSSH'
cd /opt/ChatStack
echo "Restarting containers..."
docker-compose restart web
echo "✅ Containers restarted"

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10
ENDSSH

# Step 5: Verify deployment
echo ""
echo "✅ Step 5: Verifying deployment..."
ssh $SSH_USER@$SERVER_IP << 'ENDSSH'
cd /opt/ChatStack

# Check if containers are running
echo "Docker container status:"
docker-compose ps

# Check FastAPI logs
echo ""
echo "Recent FastAPI logs (last 15 lines):"
docker-compose logs --tail=15 web | grep -i "fastapi\|websocket\|realtime" || echo "No FastAPI logs yet"

# Check Flask logs
echo ""
echo "Recent Flask logs (last 15 lines):"
docker-compose logs --tail=15 web | grep -i "flask\|incoming" || echo "No Flask logs yet"

echo ""
echo "✅ Deployment verification complete"
ENDSSH

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Deployment Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. ✅ Code deployed to $REMOTE_PATH"
echo "2. ✅ Docker containers restarted"
echo "3. ⚠️  MANUAL: Add nginx WebSocket proxy config (see output above)"
echo "4. ⚠️  MANUAL: Update Twilio webhook to /phone/incoming-realtime"
echo "5. 📞 Test by calling your Twilio number"
echo ""
echo "🔧 Nginx config location:"
echo "   /etc/nginx/sites-enabled/voice-theinsurancedoctors-com.conf"
echo ""
echo "📊 Monitor logs:"
echo "   ssh $SSH_USER@$SERVER_IP 'docker-compose -f $REMOTE_PATH/docker-compose.yml logs -f web'"
echo ""
echo "🔧 Rollback if needed:"
echo "   ssh $SSH_USER@$SERVER_IP 'ls -la /opt/ChatStack_backup_*'"
echo ""
echo "📖 Test Endpoints:"
echo "   Old: https://voice.theinsurancedoctors.com/phone/incoming"
echo "   New: https://voice.theinsurancedoctors.com/phone/incoming-realtime"
echo ""
