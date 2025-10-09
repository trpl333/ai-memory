#!/bin/bash
# Script to fix the TwiML hangup bug on DigitalOcean server
# Run this on your server: bash fix_hangup_bug.sh

echo "🔧 Fixing TwiML hangup bug..."

cd /opt/ChatStack

# Sync with remote changes first
echo "📥 Syncing with remote repository..."
git pull origin main --rebase

# Backup the original file
echo "💾 Creating backup..."
cp main.py main.py.backup.$(date +%Y%m%d_%H%M%S)

# Apply fix 1: Replace hangup with redirect in /phone/incoming
echo "🔧 Applying fix 1: /phone/incoming fallback..."
sed -i 's/response\.say("I didn'\''t hear anything\. Please try calling back\.")/response.say("I didn'\''t catch that. Let me try again.")/' main.py
sed -i '/I didn'\''t catch that\. Let me try again\./,+1s/response\.hangup()/response.redirect("\/phone\/incoming")/' main.py

# Apply fix 2: Replace hangup with pause in /phone/process-speech  
echo "🔧 Applying fix 2: /phone/process-speech ending..."
sed -i 's/response\.say("Thanks for calling! Have a great day!", voice='\''alice'\'')/response.say("Thanks for calling Peterson Family Insurance! Have a great day!")/' main.py
sed -i '/Thanks for calling Peterson Family Insurance!/,+1s/response\.hangup()/response.pause(length=1)/' main.py

# Show what changed
echo "📝 Changes made:"
echo "1. Replaced hangup with redirect in /phone/incoming"
echo "2. Replaced hangup with pause in /phone/process-speech"

# Commit and deploy
echo "📤 Committing changes..."
git add main.py
git commit -m "Fix TwiML hangup bug: replace <Hangup/> with <Redirect>"
git push origin main

echo "🚀 Redeploying application..."
docker-compose down
docker-compose up -d --build

echo "⏳ Waiting for application to start..."
sleep 10

# Test the fix
echo "🧪 Testing the fix..."
TEST_RESULT=$(curl -s -X POST https://voice.theinsurancedoctors.com/phone/incoming \
     -d "From=+test&To=+19497071290")

if echo "$TEST_RESULT" | grep -q "<Redirect>"; then
    echo "✅ SUCCESS! TwiML now uses <Redirect> instead of <Hangup>"
    echo "📞 Try calling +19497071290 - it should no longer hang up!"
else
    echo "❌ Fix may not have been applied correctly"
    echo "TwiML Response:"
    echo "$TEST_RESULT"
fi

echo ""
echo "🔍 To manually verify, run:"
echo "curl -X POST https://voice.theinsurancedoctors.com/phone/incoming -d 'From=+test&To=+19497071290'"
echo ""
echo "✅ If you see <Redirect>/phone/incoming</Redirect> instead of <Hangup/>, the fix worked!"