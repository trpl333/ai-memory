# Manual Code Changes for TwiML Hangup Fix

If you prefer to make the changes manually, here are the exact code replacements needed in `main.py`:

## Change 1: /phone/incoming Function (around line 784)

**Find this code:**
```python
response.say("I didn't hear anything. Please try calling back.")
response.hangup()
```

**Replace with:**
```python
response.say("I didn't catch that. Let me try again.")
response.redirect('/phone/incoming')
```

## Change 2: /phone/process-speech Function (around line 1003)

**Find this code:**
```python
response.say("Thanks for calling! Have a great day!", voice='alice')
response.hangup()
```

**Replace with:**
```python
response.say("Thanks for calling Peterson Family Insurance! Have a great day!")
response.pause(length=1)
```

## Commands to Deploy

After making the changes:

```bash
cd /opt/ChatStack
git add main.py
git commit -m "Fix TwiML hangup bug: replace <Hangup/> with <Redirect>"
git push origin main
docker-compose down
docker-compose up -d --build
```

## Test the Fix

```bash
curl -X POST https://voice.theinsurancedoctors.com/phone/incoming \
     -d "From=+test&To=+19497071290"
```

You should see `<Redirect>/phone/incoming</Redirect>` instead of `<Hangup/>`.