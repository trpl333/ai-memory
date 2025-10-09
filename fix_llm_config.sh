#!/bin/bash
# Script to fix LLM configuration on DigitalOcean server
# Run this on your server: bash fix_llm_config.sh

echo "🔧 Fixing LLM configuration..."

cd /opt/ChatStack

# Set the environment variables manually for immediate fix
echo "📝 Setting LLM environment variables..."
export LLM_BASE_URL="https://a40.neurospherevoice.com"
export LLM_MODEL="mistralai/Mistral-7B-Instruct-v0.1"

# Add to .env file for persistence
echo "💾 Adding to .env file for persistence..."
echo "LLM_BASE_URL=https://a40.neurospherevoice.com" >> .env
echo "LLM_MODEL=mistralai/Mistral-7B-Instruct-v0.1" >> .env

# Update config.json if it exists
echo "⚙️ Updating config.json..."
if [ -f config.json ]; then
    # Create backup
    cp config.json config.json.backup.$(date +%Y%m%d_%H%M%S)
    
    # Update or add llm_base_url in config.json
    if grep -q "llm_base_url" config.json; then
        sed -i 's|"llm_base_url": ".*"|"llm_base_url": "https://a40.neurospherevoice.com"|' config.json
    else
        # Add llm_base_url to config.json
        sed -i '2i\  "llm_base_url": "https://a40.neurospherevoice.com",' config.json
    fi
    
    if grep -q "llm_model" config.json; then
        sed -i 's|"llm_model": ".*"|"llm_model": "mistralai/Mistral-7B-Instral-v0.1"|' config.json
    else
        sed -i '3i\  "llm_model": "mistralai/Mistral-7B-Instruct-v0.1",' config.json
    fi
fi

echo "🧪 Testing LLM connectivity..."
curl -X POST "https://a40.neurospherevoice.com/v1/chat/completions" \
     -H "Content-Type: application/json" \
     -d '{"model":"mistralai/Mistral-7B-Instruct-v0.1","messages":[{"role":"user","content":"Hello"}]}' \
     --timeout 10

if [ $? -eq 0 ]; then
    echo "✅ LLM endpoint is reachable!"
else
    echo "❌ LLM endpoint test failed - check network connectivity"
fi

echo "🚀 Redeploying application..."
docker-compose down
docker-compose up -d --build

echo "⏳ Waiting for application to start..."
sleep 15

echo "📞 Testing phone system..."
TEST_RESULT=$(curl -s -X POST https://voice.theinsurancedoctors.com/phone/incoming \
     -d "From=+test&To=+19497071290")

if echo "$TEST_RESULT" | grep -q "Play\|Say"; then
    echo "✅ Phone system is responding!"
else
    echo "❌ Phone system test failed"
    echo "Response: $TEST_RESULT"
fi

echo ""
echo "🎉 LLM configuration fix complete!"
echo ""
echo "To verify:"
echo "1. Check: echo \$LLM_BASE_URL (should show: https://a40.neurospherevoice.com)"
echo "2. Try calling: +19497071290"
echo "3. Check logs: docker-compose logs -f web | grep -E 'LLM|Backend'"