#!/bin/bash

# DigitalOcean Deployment Script for ChatStack AI Phone System
# This script helps deploy your AI phone system to a DigitalOcean droplet

echo "==================================="
echo "ChatStack AI Phone System Deployment"
echo "==================================="

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Please copy .env.example to .env and fill in your credentials:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    exit 1
fi

# Pull latest code from GitHub
echo "📥 Pulling latest code from GitHub..."
git pull origin main || {
    echo "❌ Error: Failed to pull from GitHub"
    echo "Make sure you're in a git repository and have access to the remote"
    exit 1
}

# Load environment variables (filter out comments and empty lines)
export $(cat .env | grep -v '^#' | grep -v '^$' | xargs)

# Check for required environment variables
required_vars=("DATABASE_URL" "TWILIO_ACCOUNT_SID" "TWILIO_AUTH_TOKEN" "ELEVENLABS_API_KEY")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Error: $var is not set in .env file"
        exit 1
    fi
done

echo "✅ Environment variables loaded"

# Update system packages
echo "📦 Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "🐳 Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
fi

# Install Docker Compose if not present
if ! command -v docker-compose &> /dev/null; then
    echo "🐳 Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Stop existing containers if any
echo "🛑 Stopping existing containers..."
docker-compose down 2>/dev/null || true

# Build and start containers
echo "🚀 Building and starting containers..."
docker-compose up -d --build

# Wait for services to start
echo "⏳ Waiting for services to start..."
sleep 10

# Check if services are running
if docker-compose ps | grep -q "Up"; then
    echo "✅ Services are running!"
    echo ""
    echo "==================================="
    echo "Deployment Complete!"
    echo "==================================="
    echo "Your AI phone system is now running on:"
    echo "  - Web Interface: http://$(curl -s ifconfig.me):5000"
    echo "  - Phone Number: +1 (949) 707-1290"
    echo ""
    echo "To view logs: docker-compose logs -f"
    echo "To stop: docker-compose down"
    echo "To restart: docker-compose restart"
else
    echo "❌ Error: Services failed to start"
    echo "Check logs with: docker-compose logs"
    exit 1
fi