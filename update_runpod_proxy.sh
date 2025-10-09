#!/bin/bash
# Script to update the RunPod reverse proxy configuration
# Run this on your DigitalOcean server

echo "🔧 Updating a40.neurospherevoice.com reverse proxy..."

cd /opt/ChatStack

# Backup current config
sudo cp /etc/nginx/sites-enabled/neurosphere-llms.conf /etc/nginx/sites-enabled/neurosphere-llms.conf.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || echo "No existing config to backup"

# Read the new RunPod URL
echo "Please enter your current RunPod URL (without trailing slash):"
read -r NEW_RUNPOD_URL

# Update the neurosphere-llms config with new RunPod URL
echo "📝 Updating nginx config with new RunPod endpoint..."

# Create updated config
cat > /tmp/neurosphere-llms-updated.conf << EOF
server {
    listen 80;
    listen [::]:80;
    server_name a40.neurospherevoice.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name a40.neurospherevoice.com;

    # SSL configuration (adjust paths as needed)
    ssl_certificate /etc/letsencrypt/live/a40.neurospherevoice.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/a40.neurospherevoice.com/privkey.pem;
    
    # Proxy to RunPod LLM
    location / {
        proxy_pass ${NEW_RUNPOD_URL};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Increase timeouts for LLM responses
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Handle chunked responses for streaming
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
EOF

# Deploy the updated config
echo "🚀 Deploying updated reverse proxy config..."
sudo cp /tmp/neurosphere-llms-updated.conf /etc/nginx/sites-enabled/neurosphere-llms.conf

# Test nginx configuration
echo "🧪 Testing nginx configuration..."
sudo nginx -t

if [ $? -eq 0 ]; then
    echo "✅ Nginx config is valid!"
    
    # Reload nginx
    echo "🔄 Reloading nginx..."
    sudo systemctl reload nginx
    
    # Test the proxy
    echo "🧪 Testing reverse proxy..."
    curl -X POST "https://a40.neurospherevoice.com/v1/chat/completions" \
         -H "Content-Type: application/json" \
         -d '{"model":"mistralai/Mistral-7B-Instruct-v0.1","messages":[{"role":"user","content":"Hello"}],"max_tokens":50}' \
         --timeout 15
    
    if [ $? -eq 0 ]; then
        echo "✅ Reverse proxy is working!"
        echo "🎉 Now test your phone system - it should work with AI responses!"
    else
        echo "❌ Reverse proxy test failed. Check RunPod URL and SSL certificates."
    fi
    
else
    echo "❌ Nginx config test failed. Please check the configuration."
fi

# Clean up
rm -f /tmp/neurosphere-llms-updated.conf