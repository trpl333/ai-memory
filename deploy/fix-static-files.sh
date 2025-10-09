#!/bin/bash

echo "🔧 Fixing static file serving..."

# 1. Deploy corrected nginx config (serves static files directly from disk)
echo "📝 Deploying corrected nginx config..."
sudo cp /opt/ChatStack/deploy/nginx/voice-theinsurancedoctors-com.conf /etc/nginx/sites-enabled/

# 2. Create a test file to verify access
echo "📄 Creating test file..."
echo "test audio file" > /opt/ChatStack/static/audio/test.txt

# 3. Test nginx configuration
echo "🔍 Testing nginx configuration..."
sudo nginx -t

if [ $? -eq 0 ]; then
    # 4. Reload nginx if test passes
    echo "✅ Configuration valid, reloading nginx..."
    sudo systemctl reload nginx
    
    echo "🎯 Static file fix complete!"
    echo ""
    echo "🧪 Testing static file access..."
    echo "Test file:"
    curl -I https://voice.theinsurancedoctors.com/static/audio/test.txt 2>/dev/null | head -1
    
    echo "Recent MP3 file:"
    RECENT_MP3=$(ls -t /opt/ChatStack/static/audio/*.mp3 2>/dev/null | head -1 | xargs basename)
    if [ ! -z "$RECENT_MP3" ]; then
        curl -I https://voice.theinsurancedoctors.com/static/audio/$RECENT_MP3 2>/dev/null | head -1
    fi
    
    echo ""
    echo "🧪 Testing phone endpoint..."
    curl -X POST https://voice.theinsurancedoctors.com/phone/incoming -d "From=+test&To=+19497071290" 2>/dev/null | grep -o 'https://[^<]*'
    echo ""
    echo "🎵 If both tests show 'HTTP/1.1 200 OK' and phone endpoint shows HTTPS URLs, call +19497071290!"
    
    # Cleanup test file
    rm -f /opt/ChatStack/static/audio/test.txt
    
else
    echo "❌ nginx configuration test failed. Please check the errors above."
    exit 1
fi