#!/bin/bash

echo "🔧 Updating nginx configuration for AI Phone System"

# Backup current config
cp /etc/nginx/sites-available/default /etc/nginx/sites-available/default.backup.$(date +%Y%m%d_%H%M%S)

# Copy new configuration
cp /opt/ChatStack/deploy/nginx/voice-theinsurancedoctors-com.conf /etc/nginx/sites-available/voice-theinsurancedoctors-com.conf

# Create symlink if it doesn't exist
ln -sf /etc/nginx/sites-available/voice-theinsurancedoctors-com.conf /etc/nginx/sites-enabled/

# Remove default if it's pointing to old config
rm -f /etc/nginx/sites-enabled/default

# Test nginx configuration
echo "🔍 Testing nginx configuration..."
nginx -t

if [ $? -eq 0 ]; then
    echo "✅ Configuration valid, reloading nginx..."
    systemctl reload nginx
    echo "✅ nginx reloaded successfully"
else
    echo "❌ Configuration invalid, please check nginx syntax"
    exit 1
fi

echo "🎯 AI Phone System nginx configuration updated!"
echo "Test with: curl https://voice.theinsurancedoctors.com/phone/incoming -X POST -d 'test=1'"