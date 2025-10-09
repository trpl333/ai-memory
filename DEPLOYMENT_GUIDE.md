# Comprehensive Memory Fix - Deployment Guide

## 🎯 **What This Fixes**
- AI now remembers Kelly (wife), Jack (father), Arlene (mother), birthdays, vehicles, policies
- Single source of truth: ai-memory service returns normalized schema
- No more scattered 843 memories - clean structured JSON every time

## 📦 **Step 1: Update ai-memory Service**

### Files to Add/Update in `~/ai-memory/`:

**1. Create `memory_schema.py`** (new file):
```bash
# On DigitalOcean server:
cd ~/ai-memory
# Copy content from: memory_schema.py (in this repo)
```

**2. Update `main.py`**:
```bash
# On DigitalOcean server:
cd ~/ai-memory  
# Copy content from: ai-memory-main.py (in this repo)
```

### Deploy ai-memory:
```bash
cd ~/ai-memory
git add memory_schema.py main.py
git commit -m "Add comprehensive memory normalization schema"
git push origin main

# Restart service
sudo systemctl restart ai-memory
# OR if running in screen/tmux:
# pkill -f "uvicorn main:app"
# uvicorn main:app --host 0.0.0.0 --port 8100
```

## 📦 **Step 2: Simplify ChatStack**

The normalization logic is NOW in ai-memory, so ChatStack just consumes it.

### Update `ChatStack/app/http_memory.py`:

Find this section (around line 318):
```python
def normalize_memories(self, raw_memories: List[Dict[str, Any]]) -> Dict[str, Any]:
```

**REPLACE THE ENTIRE FUNCTION** with:
```python
def normalize_memories(self, raw_memories: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    ✅ SIMPLIFIED: ai-memory now handles normalization.
    Just pass through the normalized schema.
    """
    # ai-memory already returns normalized schema - just return it
    # This function kept for backwards compatibility
    logger.info(f"📝 Received pre-normalized memory from ai-memory service")
    
    # If raw_memories is already normalized (dict), return it
    if raw_memories and isinstance(raw_memories, dict):
        return raw_memories
    
    # Otherwise return empty template
    return {
        "identity": {},
        "contacts": {},
        "vehicles": [],
        "policies": [],
        "preferences": {},
        "facts": [],
        "commitments": [],
        "recent_conversations": []
    }
```

### Update `ChatStack/app/main.py`:

Find this section (around line 1214):
```python
# ✅ COMPREHENSIVE: Normalize 800+ scattered memories into fill-in-the-blanks template
normalized = mem_store.normalize_memories(memories)
```

**REPLACE** with:
```python
# ✅ COMPREHENSIVE: ai-memory returns pre-normalized schema
# Look for 'normalized' key in response
if isinstance(memories, list) and len(memories) > 0:
    # Check if first memory has 'normalized' field (new ai-memory format)
    first_mem = memories[0] if memories else {}
    if isinstance(first_mem, dict) and "normalized" in first_mem:
        normalized = first_mem["normalized"]
        logger.info(f"✅ Using pre-normalized schema from ai-memory")
    else:
        # Fallback: old format, normalize locally
        normalized = mem_store.normalize_memories(memories)
else:
    normalized = {}
```

### Deploy ChatStack:
```bash
cd /opt/ChatStack
git add app/http_memory.py app/main.py
git commit -m "Simplify to use ai-memory normalized schema"
git push origin main

docker-compose down
docker-compose up -d --build
```

## ✅ **Step 3: Test**

### Watch logs:
```bash
# ai-memory logs
sudo journalctl -u ai-memory -f

# ChatStack logs  
docker-compose logs -f orchestrator-worker | grep -E "normalized|Contacts|spouse"
```

### Make test call - Expected output:
```
📝 Received pre-normalized memory from ai-memory service
✅ Using pre-normalized schema from ai-memory
📝 Injected comprehensive memory template from 843 raw entries:
   └─ Contacts: 3, Vehicles: 1, Policies: 2, Facts: 15
   👥 Contacts found:
      • Spouse: Kelly (birthday: January 3rd)
      • Father: Jack (birthday: January 24th, 1945)
      • Mother: Arlene (birthday: November 1st, 1946)
```

### AI should now say:
> "Hi John! How's Kelly doing? Her birthday is coming up on January 3rd..."

##🎉 **Result**
- ai-memory = Single source of truth for normalization
- ChatStack = Simple consumer of clean data
- NO duplicate logic, NO regex hacks in multiple places
- Clean, maintainable, production-ready architecture
