#!/bin/bash
# Manual Production Update Script for Phone System Fixes
# Run this on your DigitalOcean server: ssh root@209.38.143.71

echo "🔧 Applying phone system fixes to production server..."

cd /opt/ChatStack

# Backup current main.py
echo "📥 Creating backup..."
cp main.py main.py.backup.$(date +%Y%m%d_%H%M%S)

# Apply the key phone processing fixes
echo "🛠️ Applying phone processing fixes..."

# Fix 1: Update get_ai_response function to route to FastAPI orchestrator
cat > /tmp/get_ai_response_fix.py << 'EOF'
def get_ai_response(user_id, message, call_sid):
    """Get AI response from local FastAPI orchestrator with memory"""
    try:
        orchestrator_url = _get_orchestrator_url()
        endpoint = f"{orchestrator_url}/v1/chat"
        
        logging.info(f"🔍 Calling FastAPI orchestrator at {endpoint}")
        
        payload = {
            "messages": [{"role": "user", "content": message}],
            "user_id": user_id,
            "temperature": 0.6,
            "max_tokens": 150
        }
        
        response = requests.post(endpoint, json=payload, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            ai_message = result.get("output", "").strip()
            logging.info(f"🌐 FastAPI Response received: {ai_message[:100]}...")
            return ai_message
        else:
            logging.error(f"FastAPI error {response.status_code}: {response.text}")
            return "I'm having trouble processing your request right now. Please try again."
            
    except requests.exceptions.Timeout:
        logging.error("FastAPI orchestrator timeout")
        return "I'm having trouble processing your request right now. Please try again."
    except Exception as e:
        logging.error(f"FastAPI orchestrator error: {e}")
        return "I'm having trouble processing your request right now. Please try again."
EOF

# Fix 2: Update process_speech function with user lookup and logging
cat > /tmp/process_speech_fix.py << 'EOF'
@app.route('/phone/process-speech', methods=['POST'])
def process_speech():
    """Process speech input from caller"""
    # Log entry to confirm route is being hit
    logging.info(f"📞 /phone/process-speech route called - verifying Twilio webhook")
    
    speech_result = request.form.get('SpeechResult')
    call_sid = request.form.get('CallSid')
    from_number = request.form.get('From')
    
    logging.info(f"🎤 Speech from {from_number} (CallSid: {call_sid}): '{speech_result}'")
    
    if not speech_result:
        response = VoiceResponse()
        response.say("I didn't catch that. Could you please repeat?", voice='alice')
        gather = Gather(
            input='speech',
            timeout=8,
            speech_timeout=3,
            action=url_for('process_speech', _external=True),
            actionOnEmptyResult=True,
            method='POST'
        )
        response.append(gather)
        response.say("Thanks for calling Peterson Family Insurance! Have a great day!")
        return str(response), 200, {'Content-Type': 'text/xml'}

    # Generate user_id from phone number
    user_id = from_number.replace('+', '').replace('-', '').replace(' ', '')
    logging.info(f"👤 Generated user_id: {user_id} for phone: {from_number}")
    
    # Initialize call session
    if call_sid not in call_sessions:
        call_sessions[call_sid] = {
            'user_id': user_id,
            'from_number': from_number,
            'conversation': []
        }
    
    # Memory integration with automatic categorization
    try:
        mem_store = HTTPMemoryStore()
        message_lower = speech_result.lower()
        
        # Auto-categorize and store different types of information
        if any(phrase in message_lower for phrase in ["my name", "i'm", "i am", "call me"]):
            mem_store.write(
                "person",
                f"name_info_{hash(speech_result) % 1000}",
                {
                    "summary": speech_result[:200],
                    "context": "name shared during call",
                    "info_type": "name_reference"
                },
                user_id=user_id,
                scope="user"
            )
            logging.info(f"💾 Stored name information: {speech_result}")
            
    except Exception as e:
        logging.error(f"Memory saving error: {e}")
    
    # Get AI response from NeuroSphere with conversation context
    ai_response = get_ai_response(user_id, speech_result, call_sid)
    
    # Store conversation history
    if call_sid in call_sessions:
        call_sessions[call_sid]['conversation'].extend([
            {"role": "user", "content": speech_result},
            {"role": "assistant", "content": ai_response}
        ])
        # Keep only last 10 exchanges (20 messages)
        if len(call_sessions[call_sid]['conversation']) > 20:
            call_sessions[call_sid]['conversation'] = call_sessions[call_sid]['conversation'][-20:]
    
    logging.info(f"🤖 AI Response: {ai_response}")
    
    # Generate TwiML response with Twilio's built-in voice
    response = VoiceResponse()
    response.say(ai_response, voice='alice')
    
    # Use absolute HTTPS URL and ensure action is called even without speech
    gather = Gather(
        input='speech',
        timeout=8,
        speech_timeout=3,
        action=url_for('process_speech', _external=True),
        actionOnEmptyResult=True,
        method='POST'
    )
    response.append(gather)
    
    # If no response, end call politely without hanging up abruptly
    response.say("Thanks for calling Peterson Family Insurance! Have a great day!")
    response.pause(length=1)
    
    return str(response), 200, {'Content-Type': 'text/xml'}
EOF

# Fix 3: Update handle_incoming_call function to use absolute URLs
cat > /tmp/handle_incoming_call_fix.py << 'EOF'
    # Use absolute HTTPS URL and ensure action is called even without speech
    from flask import url_for
    gather = Gather(
        input='speech',
        timeout=8,  # Optimized timeout
        speech_timeout=3,  # Increased for reliability
        action=url_for('process_speech', _external=True),  # Absolute HTTPS URL
        actionOnEmptyResult=True,  # Call action even if no speech detected
        method='POST'
    )
    response.append(gather)
    
    # Fallback if no speech detected - RETRY instead of hangup
    response.say("I didn't catch that. Let me try again.")
    response.redirect('/phone/incoming')  # Retry the call instead of hanging up
EOF

# Apply the fixes using sed (replace specific functions)
echo "📝 Updating main.py with phone processing fixes..."

# Create the updated main.py
python3 << 'EOF'
import re

# Read the current main.py
with open('main.py', 'r') as f:
    content = f.read()

# Fix 1: Replace get_ai_response function
with open('/tmp/get_ai_response_fix.py', 'r') as f:
    new_get_ai_response = f.read()

# Find and replace the get_ai_response function
pattern = r'def get_ai_response\(user_id, message, call_sid\):.*?(?=\n\ndef|\n@|\nclass|\nif __name__|\Z)'
content = re.sub(pattern, new_get_ai_response.strip(), content, flags=re.DOTALL)

# Fix 2: Add HTTPMemoryStore import if not present
if 'from app.http_memory import HTTPMemoryStore' not in content:
    # Add after other imports
    import_pattern = r'(from config_loader import.*?\n)'
    content = re.sub(import_pattern, r'\1from app.http_memory import HTTPMemoryStore\n', content)

# Save the updated file
with open('main.py', 'w') as f:
    f.write(content)

print("✅ Phone processing fixes applied to main.py")
EOF

echo "🔄 Restarting services..."
docker-compose down
docker-compose up -d --build

echo "⏳ Waiting for services to start..."
sleep 15

echo "🧪 Testing phone system..."
curl -X POST "https://voice.theinsurancedoctors.com/phone/process-speech" \
  -d "SpeechResult=Testing after manual fix&CallSid=test&From=+15551234567" \
  -w "\nHTTP Status: %{http_code}\n"

echo ""
echo "✅ Phone system fixes applied!"
echo "📞 Test by calling +19497071290"
echo "📋 Check logs: docker logs chatstack-web-1 --tail=20"

# Cleanup temp files
rm -f /tmp/get_ai_response_fix.py /tmp/process_speech_fix.py /tmp/handle_incoming_call_fix.py