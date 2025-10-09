#!/bin/bash
# Test RunPod LLM endpoint connectivity
echo "🧪 Testing RunPod LLM endpoint connectivity..."

# Test basic connectivity
echo "1. Testing basic HTTP connectivity..."
curl -I "https://a40.neurospherevoice.com" --timeout 10

echo ""
echo "2. Testing LLM endpoint with sample request..."
curl -X POST "https://a40.neurospherevoice.com/v1/chat/completions" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer dummy" \
     -d '{
       "model": "mistralai/Mistral-7B-Instruct-v0.1",
       "messages": [{"role": "user", "content": "Hello"}],
       "max_tokens": 100,
       "temperature": 0.7
     }' \
     --timeout 15 \
     --verbose

echo ""
echo "3. Testing alternative endpoints..."
curl -I "https://a40.neurospherevoice.com/v1/models" --timeout 10

echo ""
echo "4. Testing different model name..."
curl -X POST "https://a40.neurospherevoice.com/v1/chat/completions" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "Qwen2-7B-Instruct",
       "messages": [{"role": "user", "content": "Hello"}],
       "max_tokens": 50
     }' \
     --timeout 15

echo ""
echo "✅ Test complete!"