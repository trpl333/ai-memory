#!/bin/bash

echo "🔧 Complete fix for audio serving issues..."

# 1. Remove ALL conflicting nginx configs
echo "🗑️ Removing conflicting nginx configurations..."
sudo rm -f /etc/nginx/sites-enabled/default
sudo rm -f /etc/nginx/sites-enabled/neurosphere-llms.conf

# 2. Deploy ONLY the corrected voice config  
echo "📝 Deploying corrected voice config with alias serving..."
sudo cp /opt/ChatStack/deploy/nginx/voice-theinsurancedoctors-com.conf /etc/nginx/sites-enabled/

# 3. Verify nginx config
echo "🔍 Testing nginx configuration..."
sudo nginx -t

if [ $? -ne 0 ]; then
    echo "❌ nginx configuration test failed!"
    exit 1
fi

# 4. Show active server blocks
echo "📋 Active server blocks:"
sudo nginx -T 2>/dev/null | grep -A5 -B2 "server_name.*theinsurancedoctors.com"

# 5. Reload nginx
echo "🔄 Reloading nginx..."
sudo systemctl reload nginx

# 6. Fix Docker volume mounting for static files
echo "🐳 Stopping containers to add volume mount..."
docker-compose down

# 7. Backup and modify docker-compose.yml to add volume mount
echo "💾 Adding static directory volume mount to docker-compose.yml..."
if ! grep -q "/opt/ChatStack/static:/app/static" docker-compose.yml; then
    # Add volume mount for static directory
    sed -i '/services:/,/web:/{
        /volumes:/,/^[[:space:]]*[^[:space:]]/{
            /volumes:/a\
      - /opt/ChatStack/static:/app/static:rw
        }
    }' docker-compose.yml
    
    # If no volumes section exists, add it
    if ! grep -q "volumes:" docker-compose.yml; then
        sed -i '/web:/a\
    volumes:\
      - /opt/ChatStack/static:/app/static:rw' docker-compose.yml
    fi
fi

# 8. Ensure static directory exists with correct permissions
echo "📁 Creating static directory with correct permissions..."
sudo mkdir -p /opt/ChatStack/static/audio
sudo chown -R root:www-data /opt/ChatStack/static
sudo find /opt/ChatStack/static -type d -exec chmod 755 {} \;
sudo find /opt/ChatStack/static -type f -exec chmod 644 {} \;

# 9. Restart containers with volume mount
echo "🚀 Starting containers with volume mount..."
docker-compose up -d --build

# 10. Wait for containers to start
sleep 5

# 11. Create test file to verify nginx alias works
echo "🧪 Testing nginx alias serving..."
echo "nginx test file" > /opt/ChatStack/static/audio/nginx_test.txt
curl -I https://voice.theinsurancedoctors.com/static/audio/nginx_test.txt 2>/dev/null | head -1

# 12. Test phone endpoint
echo "📞 Testing phone endpoint..."
RESPONSE=$(curl -s -X POST https://voice.theinsurancedoctors.com/phone/incoming -d "From=+test&To=+19497071290")
echo "TwiML response:"
echo "$RESPONSE" | grep -o 'https://[^<]*'

# 13. Check if new audio files appear on host
echo "🎵 Recent audio files on host:"
ls -lt /opt/ChatStack/static/audio/ | head -5

# Cleanup
rm -f /opt/ChatStack/static/audio/nginx_test.txt

echo ""
echo "✅ Complete fix applied!"
echo "🎯 Test: Call +19497071290 - Samantha should answer without hanging up!"