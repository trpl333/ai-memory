#!/bin/bash
# Script to fix RunPod endpoint configuration
# Run this on your DigitalOcean server

echo "🔧 Fixing RunPod endpoint configuration..."

cd /opt/ChatStack

# Read the RunPod URL from user input for security
echo "Please enter your RunPod endpoint URL:"
read -r RUNPOD_URL

# Test connectivity first
echo "🧪 Testing connectivity to RunPod endpoint..."
curl -X POST "${RUNPOD_URL}/v1/chat/completions" \
     -H "Content-Type: application/json" \
     -d '{"model":"mistralai/Mistral-7B-Instruct-v0.1","messages":[{"role":"user","content":"Hello"}],"max_tokens":50}' \
     --timeout 15

if [ $? -eq 0 ]; then
    echo "✅ RunPod endpoint is reachable!"
    
    # Update config.json
    echo "📝 Updating config.json..."
    cp config.json config.json.backup.$(date +%Y%m%d_%H%M%S)
    sed -i "s|\"llm_base_url\": \".*\"|\"llm_base_url\": \"${RUNPOD_URL}\"|" config.json
    
    # Update environment variable
    echo "🔧 Setting environment variable..."
    export LLM_BASE_URL="${RUNPOD_URL}"
    
    # Add to .env for persistence (without exposing in logs)
    echo "LLM_BASE_URL=${RUNPOD_URL}" >> .env
    
    echo "🚀 Redeploying application..."
    docker-compose down
    docker-compose up -d --build
    
    echo "⏳ Waiting for application to start..."
    sleep 15
    
    echo "📞 Testing phone system..."
    curl -s -X POST https://voice.theinsurancedoctors.com/phone/incoming \
         -d "From=+test&To=+19497071290" | grep -E "(Play|Say|Gather)"
    
    echo "✅ RunPod endpoint configuration updated!"
    
else
    echo "❌ RunPod endpoint is not reachable. Please check:"
    echo "  1. RunPod instance is running"
    echo "  2. URL is correct"
    echo "  3. Network connectivity"
fi