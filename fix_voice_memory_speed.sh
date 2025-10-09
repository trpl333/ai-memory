#!/bin/bash
# Comprehensive fix for ElevenLabs voice, memory, and speed issues
echo "🔧 Fixing voice, memory, and speed issues..."

cd /opt/ChatStack

# 1. Check current environment variables
echo "📋 Checking current environment..."
echo "ELEVENLABS_API_KEY: $(if docker-compose exec web printenv ELEVENLABS_API_KEY 2>/dev/null | grep -q .; then echo "SET"; else echo "MISSING"; fi)"
echo "DATABASE_URL: $(if docker-compose exec web printenv DATABASE_URL 2>/dev/null | grep -q .; then echo "SET"; else echo "MISSING"; fi)"

# 2. Test ElevenLabs connectivity
echo "🧪 Testing ElevenLabs API..."
if [ -n "$ELEVENLABS_API_KEY" ]; then
    curl -X GET "https://api.elevenlabs.io/v1/voices" \
         -H "xi-api-key: $ELEVENLABS_API_KEY" \
         -H "Content-Type: application/json" \
         --timeout 10
else
    echo "❌ ELEVENLABS_API_KEY not set in environment"
fi

# 3. Test database connectivity
echo "🧪 Testing database connectivity..."
if [ -n "$DATABASE_URL" ]; then
    timeout 5 psql "$DATABASE_URL" -c "SELECT 1;" || echo "❌ Database connection failed"
else
    echo "❌ DATABASE_URL not set"
fi

# 4. Check docker-compose logs for specific errors
echo "📝 Recent application logs:"
docker-compose logs --tail=20 web | grep -E "(ElevenLabs|ELEVENLABS|Memory|Database|ERROR|WARNING)"

echo ""
echo "🎯 Issues found:"
echo "1. Memory database connection failing (ai-memory-do-user-17983093-0.e.db.ondigitalocean.com timeout)"
echo "2. ElevenLabs potentially not configured or import failing"
echo "3. Multiple connection timeouts causing slowness"

echo ""
echo "📞 Testing current phone system:"
curl -s -X POST "https://voice.theinsurancedoctors.com/phone/process-speech" \
     -d "SpeechResult=Hello&CallSid=test123&From=+test" | grep -E "(Say|Play)"