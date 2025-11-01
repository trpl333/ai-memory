import os
import time
import logging
from typing import List, Optional, Deque, Tuple, Dict, Any
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import json
import asyncio

from config_loader import get_secret, get_setting
import sys
import os
# Import get_admin_setting from main.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from main import get_admin_setting
except ImportError:
    # Fallback if main.py not available
    def get_admin_setting(setting_key, default=None):
        return get_setting(setting_key, default)
from app.models import ChatRequest, ChatResponse, MemoryObject
from app.llm import chat as llm_chat, chat_realtime_stream, _get_llm_config, validate_llm_connection
from app.memory import MemoryStore
from app.http_memory import HTTPMemoryStore
from app.packer import pack_prompt, should_remember, extract_carry_kit_items, detect_safety_triggers
from app.tools import tool_dispatcher, parse_tool_calls, execute_tool_calls
from app.middleware.auth import validate_jwt  # 🔐 Week 2: JWT authentication
from app.jwt_utils import generate_memory_token  # 🔐 Week 2: JWT generation (SHARED with ChatStack)

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Globals
# -----------------------------------------------------------------------------
memory_store: Optional[MemoryStore] = None

# In-process rolling history per thread (survives across calls in same container)
# 500 msgs ~= ~250 user/assistant turns. Consolidation triggers at 400.
THREAD_HISTORY: Dict[str, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=500))

# Track which threads have been loaded from database
THREAD_LOADED: Dict[str, bool] = {}

def load_thread_history(thread_id: str, mem_store: MemoryStore, user_id: Optional[str] = None):
    """Load thread history from ai-memory database if not already loaded"""
    if THREAD_LOADED.get(thread_id):
        logger.info(f"⏭️ Thread {thread_id} already loaded, skipping")
        return  # Already loaded
    
    try:
        # Search for stored thread history with exact key match
        history_key = f"thread_history:{thread_id}"
        
        logger.info(f"🔍 Loading thread history: key={history_key}, user_id={user_id}")
        
        # Strategy: Search broadly (type filter doesn't work in ai-memory service)
        # Then filter client-side for exact key match
        results = mem_store.search(history_key, user_id=user_id, k=200)
        
        logger.info(f"🔍 Search returned {len(results)} results for key: {history_key}")
        
        # Filter for exact key match (case-insensitive for safety)
        matching_memory = None
        for result in results:
            result_key = result.get("key") or result.get("k") or ""
            # Check exact match OR if the value contains our thread history
            if result_key == history_key:
                matching_memory = result
                logger.info(f"✅ Found exact match for key: {history_key}")
                break
            # Fallback: check if value contains thread history data
            elif isinstance(result.get("value"), dict) and "messages" in result.get("value", {}):
                # This might be our thread history with a different key format
                logger.info(f"🔍 Found potential match with key={result_key}")
                matching_memory = result
                break
        
        if matching_memory:
            value = matching_memory.get("value", {})
            if isinstance(value, dict) and "messages" in value:
                messages = value["messages"]
                # Restore to in-memory deque
                THREAD_HISTORY[thread_id] = deque(
                    [(msg["role"], msg["content"]) for msg in messages],
                    maxlen=500
                )
                logger.info(f"✅ Loaded {len(messages)} messages from database for thread {thread_id}")
                # Log first and last message for verification
                if messages:
                    first_msg = messages[0]
                    last_msg = messages[-1]
                    logger.info(f"📝 First message: {first_msg['role']}: {first_msg['content'][:100]}...")
                    logger.info(f"📝 Last message: {last_msg['role']}: {last_msg['content'][:100]}...")
                THREAD_LOADED[thread_id] = True
                return
        
        logger.info(f"🧵 No stored history found for thread {thread_id} (searched {len(results)} results)")
        THREAD_LOADED[thread_id] = True
    except Exception as e:
        logger.error(f"❌ Failed to load thread history for {thread_id}: {e}", exc_info=True)
        THREAD_LOADED[thread_id] = True  # Mark as attempted to avoid retry loops

def save_thread_history(thread_id: str, mem_store: MemoryStore, user_id: Optional[str] = None):
    """Save thread history to ai-memory database for persistence"""
    try:
        history = THREAD_HISTORY.get(thread_id)
        if not history:
            logger.warning(f"⚠️ No thread history to save for {thread_id}")
            return
        
        # Convert deque to list of dicts
        messages = [{"role": role, "content": content} for role, content in history]
        
        # Store in ai-memory
        history_key = f"thread_history:{thread_id}"
        logger.info(f"💾 Saving {len(messages)} messages to ai-memory with key={history_key}, user_id={user_id}")
        
        mem_store.write(
            memory_type="thread_recap",
            key=history_key,
            value={"messages": messages, "count": len(messages)},
            user_id=user_id,
            scope="user",
            ttl_days=7  # Keep for 7 days
        )
        logger.info(f"✅ Successfully saved {len(messages)} messages to database for thread {thread_id}")
        
        # ✅ Check if consolidation is needed (at 400/500 messages)
        if len(messages) >= 400:
            try:
                consolidate_thread_memories(thread_id, mem_store, user_id)
            except Exception as e:
                logger.error(f"Memory consolidation failed: {e}")
    except Exception as e:
        logger.error(f"❌ Failed to save thread history for {thread_id}: {e}", exc_info=True)

def consolidate_thread_memories(thread_id: str, mem_store: MemoryStore, user_id: Optional[str] = None):
    """
    Extract important information from thread history and save as structured long-term memories.
    Triggered when THREAD_HISTORY reaches 400 messages to prevent information loss.
    """
    import json
    
    history = THREAD_HISTORY.get(thread_id)
    if not history or len(history) < 400:
        return
    
    logger.info(f"🧠 Starting memory consolidation for thread {thread_id} ({len(history)} messages)")
    
    # Take the oldest 200 messages (100 turns) for consolidation
    messages_to_analyze = list(history)[:200]
    
    # Build conversation text for LLM analysis
    conversation_text = "\n".join([
        f"{role.upper()}: {content[:200]}" 
        for role, content in messages_to_analyze
    ])
    
    # Ask LLM to extract structured information
    extraction_prompt = f"""Analyze this conversation and extract important information in JSON format.

Conversation:
{conversation_text}

Extract:
1. **people**: Family members, friends (name, relationship)
2. **facts**: Important dates, events, details (description, value)
3. **preferences**: Likes, dislikes, interests (category, preference)
4. **commitments**: Promises, follow-ups, action items (description, deadline)

Return ONLY valid JSON in this format:
{{
  "people": [{{"name": "Kelly", "relationship": "wife"}}],
  "facts": [{{"description": "Kelly's birthday", "value": "January 3rd, 1966"}}],
  "preferences": [{{"category": "activities", "preference": "spa days"}}],
  "commitments": [{{"description": "plan birthday celebration", "deadline": "soon"}}]
}}"""
    
    try:
        # Call LLM for extraction
        from app.llm import chat as llm_chat
        extracted_text, _ = llm_chat(
            [{"role": "user", "content": extraction_prompt}],
            temperature=0.3,  # Low temperature for structured output
            max_tokens=1000
        )
        
        # Parse JSON response
        extracted_data = json.loads(extracted_text.strip())
        logger.info(f"✅ Extracted data: {len(extracted_data.get('people', []))} people, {len(extracted_data.get('facts', []))} facts")
        
        # Store extracted information with de-duplication
        import time
        import hashlib
        
        def stable_hash(text: str) -> str:
            """Generate stable deterministic hash for de-duplication"""
            return hashlib.sha1(text.lower().encode('utf-8')).hexdigest()[:8]
        
        timestamp = int(time.time())
        
        # Store people
        for person in extracted_data.get("people", []):
            if person.get("name"):
                key = f"person:{thread_id}:{person['name'].lower().replace(' ', '_')}"
                mem_store.write(
                    memory_type="person",
                    key=key,
                    value={**person, "extracted_at": timestamp, "source": "consolidation"},
                    user_id=user_id,
                    scope="user",
                    ttl_days=365
                )
        
        # Store facts
        for fact in extracted_data.get("facts", []):
            if fact.get("description"):
                key = f"fact:{thread_id}:{stable_hash(fact['description'])}"
                mem_store.write(
                    memory_type="fact",
                    key=key,
                    value={**fact, "extracted_at": timestamp, "source": "consolidation"},
                    user_id=user_id,
                    scope="user",
                    ttl_days=365
                )
        
        # Store preferences
        for pref in extracted_data.get("preferences", []):
            if pref.get("preference"):
                key = f"preference:{thread_id}:{stable_hash(pref['preference'])}"
                mem_store.write(
                    memory_type="preference",
                    key=key,
                    value={**pref, "extracted_at": timestamp, "source": "consolidation"},
                    user_id=user_id,
                    scope="user",
                    ttl_days=365
                )
        
        # Store commitments
        for commit in extracted_data.get("commitments", []):
            if commit.get("description"):
                key = f"project:{thread_id}:{stable_hash(commit['description'])}"
                mem_store.write(
                    memory_type="project",
                    key=key,
                    value={**commit, "extracted_at": timestamp, "source": "consolidation"},
                    user_id=user_id,
                    scope="user",
                    ttl_days=90  # Shorter TTL for action items
                )
        
        # Prune old messages from deque (keep last 300)
        while len(THREAD_HISTORY[thread_id]) > 300:
            THREAD_HISTORY[thread_id].popleft()
        
        logger.info(f"✅ Memory consolidation complete. Pruned history to {len(THREAD_HISTORY[thread_id])} messages")
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM extraction: {e}")
    except Exception as e:
        logger.error(f"Memory consolidation error: {e}")

# Feature flags
ENABLE_RECAP = True           # write/read tiny durable recap to AI-Memory
DISCOURAGE_GUESSING = True    # add a system rail when no memories are retrieved

# -----------------------------------------------------------------------------
# Lifespan
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global memory_store
    logger.info("Starting NeuroSphere Orchestrator...")
    try:
        memory_store = MemoryStore()
        if memory_store.available:
            logger.info("✅ Memory store initialized")
            try:
                cleanup_count = memory_store.cleanup_expired()
                logger.info(f"🧹 Cleaned up {cleanup_count} expired memories")
            except Exception as e:
                logger.warning(f"Cleanup expired failed (non-fatal): {e}")
        else:
            logger.warning("⚠️ Memory store running in degraded mode (database unavailable)")

        if not validate_llm_connection():
            logger.warning("⚠️ LLM connection validation failed - service may be unavailable")

        yield
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        logger.info("Starting app in degraded mode...")
    finally:
        logger.info("Shutting down NeuroSphere Orchestrator...")
        try:
            if memory_store:
                memory_store.close()
        except Exception:
            pass

# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
app = FastAPI(
    title="NeuroSphere Orchestrator",
    description="ChatGPT-style conversational AI with long-term memory and tool calling",
    version="1.0.0",
    lifespan=lifespan
)

# CORS disabled - Nginx proxy provides security
# No browser CORS needed for API-only service
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

app.mount("/static", StaticFiles(directory="static"), name="static")

def get_memory_store() -> MemoryStore:
    if memory_store is None:
        raise HTTPException(status_code=503, detail="Memory store not initialized - service degraded")
    if not memory_store.available:
        raise HTTPException(status_code=503, detail="Memory store unavailable - service degraded")
    return memory_store

IMPORTANT_TYPES = {"person", "preference", "project", "rule", "moment"}

def should_store_memory(user_text: str, memory_type: str = "") -> bool:
    return (
        should_remember(user_text)
        or memory_type in IMPORTANT_TYPES
        or "remember this" in user_text.lower()
        or "save this" in user_text.lower()
    )

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/")
async def root():
    return {
        "service": "NeuroSphere Orchestrator",
        "version": "1.0.0",
        "status": "running",
        "description": "ChatGPT-style AI with memory and tools",
    }

@app.get("/admin")
async def admin_interface():
    return FileResponse("static/admin.html")

@app.get("/health")
async def health_check(mem_store: MemoryStore = Depends(get_memory_store)):
    try:
        memory_status = "connected" if mem_store.available else "unavailable"
        total_memories = 0
        if mem_store.available:
            try:
                stats = mem_store.get_memory_stats()
                total_memories = stats.get("total", 0)
            except Exception as e:
                logger.error(f"Memory stats failed: {e}")
                memory_status = "error"

        llm_status = validate_llm_connection()

        return {
            "status": "healthy" if (mem_store.available and llm_status) else "degraded",
            "memory_store": memory_status,
            "llm_service": "connected" if llm_status else "unavailable",
            "total_memories": total_memories,
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

# -----------------------------------------------------------------------------
# Chat with persistent thread history + optional recap
# -----------------------------------------------------------------------------
@app.post("/v1/chat", response_model=ChatResponse)
async def chat_completion(
    request: ChatRequest,
    thread_id: str = "default",
    user_id: Optional[str] = None,
    mem_store: MemoryStore = Depends(get_memory_store),
):
    """
    Main chat completion endpoint with rolling thread history, durable recap,
    long-term memory retrieval, and tool calling.
    """
    try:
        logger.info(f"Chat request: {len(request.messages)} messages, thread={thread_id}")

        if not request.messages:
            raise HTTPException(status_code=400, detail="No messages provided")

        # Latest user message
        user_message = None
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_message = msg.content
                break
        if not user_message:
            raise HTTPException(status_code=400, detail="No user message found")

        # Safety rails
        safety_mode = request.safety_mode or detect_safety_triggers(user_message)
        if safety_mode:
            logger.info("🛡️ Safety mode activated")

        # Opportunistic carry-kit write
        if should_remember(user_message):
            for item in extract_carry_kit_items(user_message):
                try:
                    memory_id = mem_store.write(
                        item["type"], item["key"], item["value"],
                        user_id=user_id, scope="user", ttl_days=item.get("ttl_days", 365)
                    )
                    logger.info(f"🧠 Stored carry-kit for user {user_id}: {item['type']}:{item['key']} -> {memory_id}")
                except Exception as e:
                    logger.error(f"Carry-kit write failed: {e}")

        # ✅ CRITICAL FIX: First, explicitly fetch the manually saved normalized schema
        # Semantic search won't find it, so we need a direct lookup
        manual_schema_memory = None
        if user_id:
            try:
                # Get all memories for this user to find the manual schema
                all_user_memories = mem_store.search("", user_id=user_id, k=50, include_shared=False)
                
                # Find the most recent manually saved schema
                manual_schemas = [m for m in all_user_memories 
                                 if m.get("type") == "normalized_schema" and m.get("key") == "user_profile"]
                
                if manual_schemas:
                    manual_schema_memory = manual_schemas[-1]  # Most recent
                    logger.info(f"✅ Found manually saved schema for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to fetch manual schema: {e}")
        
        # Long-term memory retrieve (user-specific + shared)
        search_k = 15 if any(w in (user_message.lower()) for w in
                             ["wife","husband","family","friend","name","who is","kelly","job","work","teacher"]) else 6
        retrieved_memories = mem_store.search(user_message, user_id=user_id, k=search_k)
        
        # ✅ CRITICAL: Prepend manual schema so normalize_memories() sees it first
        if manual_schema_memory:
            retrieved_memories = [manual_schema_memory] + retrieved_memories
            logger.info(f"✅ Injected manual schema into memory bundle")
        
        logger.info(f"🔎 Retrieved {len(retrieved_memories)} relevant memories (including manual schema if exists)")
        
        # 🔍 DEBUG: Log what memories were actually retrieved
        if retrieved_memories:
            logger.info(f"🔍 DEBUG: Top 5 memories retrieved:")
            for i, mem in enumerate(retrieved_memories[:5]):
                mem_key = mem.get('key', 'no-key')
                mem_type = mem.get('type', 'no-type')
                mem_value_preview = str(mem.get('value', {}))[:100]
                logger.info(f"  [{i+1}] {mem_type}:{mem_key} = {mem_value_preview}")

        # Build current request messages
        message_dicts = [{"role": m.role, "content": m.content} for m in request.messages]

        # ✅ Load thread history from database if not already loaded
        if thread_id:
            load_thread_history(thread_id, mem_store, user_id)

        # Prepend rolling thread history (persistent across container restarts)
        if thread_id and THREAD_HISTORY.get(thread_id):
            hist = [{"role": r, "content": c} for (r, c) in THREAD_HISTORY[thread_id]]
            # Take last ~40 messages to keep prompt lean
            hist = hist[-40:]
            message_dicts = hist + message_dicts
            logger.info(f"🧵 Prepended {len(hist)} messages from THREAD_HISTORY[{thread_id}]")
        else:
            logger.info(f"🧵 No history found for thread_id={thread_id}")

        # Optional durable recap from AI-Memory (1 paragraph)
        if ENABLE_RECAP and thread_id and user_id:
            try:
                rec = mem_store.search(f"thread:{thread_id}:recap", user_id=user_id, k=1)
                if rec:
                    v = rec[0].get("value") or {}
                    summary = v.get("summary")
                    if summary:
                        message_dicts = [{"role":"system","content":f"Conversation recap:\n{summary}"}] + message_dicts
            except Exception as e:
                logger.warning(f"Recap load failed: {e}")

        # Add anti-guessing rail when we have no retrieved memories
        if DISCOURAGE_GUESSING and not retrieved_memories:
            message_dicts = [{"role":"system","content":
                "If you are not given a fact in retrieved memories or the current messages, say you don't know rather than guessing."}] + message_dicts
        
        # 🔍 DEBUG: Log complete message list being sent to LLM
        logger.info(f"🔍 DEBUG: Sending {len(message_dicts)} total messages to LLM:")
        for i, msg in enumerate(message_dicts[-10:]):  # Last 10 messages
            role = msg.get('role', 'unknown')
            content_preview = msg.get('content', '')[:80]
            logger.info(f"  [{i}] {role}: {content_preview}")

        # Final pack with system context + retrieved memories
        final_messages = pack_prompt(
            message_dicts,
            retrieved_memories,
            safety_mode=safety_mode,
            thread_id=thread_id
        )

        # Select path based on model
        logger.info("Calling LLM...")
        config = _get_llm_config()
        logger.info(f"🟢 Model in config: {config['model']}")

        if "realtime" in config["model"].lower():
            logger.info("🚀 Using realtime LLM")
            tokens = []
            for token in chat_realtime_stream(
                final_messages,
                temperature=request.temperature or 0.7,
                max_tokens=request.max_tokens or 800
            ):
                tokens.append(token)
            assistant_output = "".join(tokens).strip()
            usage_stats = {
                "prompt_tokens": sum(len(m.get("content","").split()) for m in final_messages),
                "completion_tokens": len(assistant_output.split()),
                "total_tokens": 0
            }
            usage_stats["total_tokens"] = usage_stats["prompt_tokens"] + usage_stats["completion_tokens"]
        else:
            logger.info("🧠 Using standard chat LLM")
            assistant_output, usage_stats = llm_chat(
                final_messages,
                temperature=request.temperature,
                top_p=request.top_p,
                max_tokens=request.max_tokens
            )

        # Tool calling (if present)
        tool_results = []
        tool_calls = parse_tool_calls(assistant_output)
        if tool_calls:
            logger.info(f"🛠️ Executing {len(tool_calls)} tool calls")
            tool_results = execute_tool_calls(tool_calls)
            if tool_results:
                summaries = []
                for r in tool_results:
                    summaries.append(r["result"] if r["success"] else f"Tool error: {r['error']}")
                if summaries:
                    assistant_output += "\n\n" + "\n".join(summaries)

        # Rolling in-process history append
        try:
            if thread_id:
                last_user = next((m for m in reversed(request.messages) if m.role == "user"), None)
                if last_user:
                    THREAD_HISTORY[thread_id].append(("user", last_user.content))
                    logger.info(f"🧵 Appended USER message to THREAD_HISTORY[{thread_id}]: {last_user.content[:50]}")
                THREAD_HISTORY[thread_id].append(("assistant", assistant_output))
                logger.info(f"🧵 Appended ASSISTANT message to THREAD_HISTORY[{thread_id}]: {assistant_output[:50]}")
                logger.info(f"🧵 Total messages in THREAD_HISTORY[{thread_id}]: {len(THREAD_HISTORY[thread_id])}")
                
                # ✅ Save thread history to database for persistence across restarts
                save_thread_history(thread_id, mem_store, user_id)
        except Exception as e:
            logger.warning(f"THREAD_HISTORY append failed: {e}")

        # Opportunistic durable recap write (tiny)
        if ENABLE_RECAP and thread_id and user_id:
            try:
                last_user = next((m for m in reversed(request.messages) if m.role == "user"), None)
                snippet_user = (last_user.content if last_user else "")[:300]
                snippet_assistant = assistant_output[:400]
                recap = f"{snippet_user} || {snippet_assistant}"
                mem_store.write(
                    "thread_recap",
                    key=f"thread:{thread_id}:recap",
                    value={"summary": recap, "updated_at": time.time()},
                    user_id=user_id,
                    scope="user",
                    source="recap"
                )
            except Exception as e:
                logger.warning(f"Recap write failed: {e}")

        # Store important info as short-lived "moment"
        if should_store_memory(assistant_output, "moment"):
            try:
                mem_store.write(
                    "moment",
                    f"conversation_{hash(user_message) % 100000}",
                    {
                        "user_message": user_message[:500],
                        "assistant_response": assistant_output[:500],
                        "summary": f"Conversation about: {user_message[:100]}..."
                    },
                    user_id=user_id,
                    scope="user",
                    ttl_days=90
                )
            except Exception as e:
                logger.error(f"Failed to store conversation moment: {e}")

        # Response
        response = ChatResponse(
            output=assistant_output,
            used_memories=[str(mem.get("id")) for mem in retrieved_memories if isinstance(mem, dict) and mem.get("id")],
            prompt_tokens=usage_stats.get("prompt_tokens", 0),
            completion_tokens=usage_stats.get("completion_tokens", 0),
            total_tokens=usage_stats.get("total_tokens", 0),
            memory_count=len(retrieved_memories),
        )
        logger.info(f"✅ Chat completed: {response.total_tokens} tokens, memories used={len(retrieved_memories)}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat completion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chat completion failed: {str(e)}")

# OpenAI-style alias
@app.post("/v1/chat/completions", response_model=ChatResponse)
async def chat_completions_alias(
    request: Request,
    thread_id: str = "default",
    user_id: Optional[str] = None,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    try:
        body = await request.json()
        chat_req = ChatRequest(**body)
        return await chat_completion(
            chat_req, thread_id=thread_id, user_id=user_id, mem_store=mem_store
        )
    except Exception as e:
        logger.error(f"Alias /v1/chat/completions failed: {e}")
        raise HTTPException(status_code=500, detail=f"Alias failed: {str(e)}")

# -----------------------------------------------------------------------------
# Memory APIs (unchanged interfaces)
# -----------------------------------------------------------------------------
@app.get("/v1/memories")
async def get_memories(
    limit: int = 50,
    memory_type: Optional[str] = None,
    user_id: Optional[str] = None,
    customer_id: int = Depends(validate_jwt),
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """🔐 Week 2: Now requires JWT authentication"""
    logger.info(f"🔐 JWT validated: customer_id={customer_id}")
    
    try:
        # 🔐 Set tenant context for RLS (psycopg2 style)
        with mem_store.conn.cursor() as cur:
            cur.execute("SET app.current_tenant = %s", (customer_id,))
        logger.debug(f"✅ Tenant context set to customer_id={customer_id}")
        
        if user_id:
            memories = mem_store.get_user_memories(user_id, limit=limit, include_shared=True)
        else:
            query = "general" if not memory_type else memory_type
            memories = mem_store.search(query, k=limit)
        return {"memories": memories, "count": len(memories), "stats": mem_store.get_memory_stats()}
    except Exception as e:
        logger.error(f"Failed to get memories: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve memories")
@app.post("/v1/memories")
async def store_memory(
    memory: MemoryObject,
    customer_id: int = Depends(validate_jwt),
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """🔐 Week 2: Now requires JWT authentication"""
    logger.info(f"🔐 JWT validated: customer_id={customer_id}")
    
    import json
    try:
        # 🔐 Set tenant context for RLS (psycopg2 style)
        with mem_store.conn.cursor() as cur:
            cur.execute("SET app.current_tenant = %s", (customer_id,))
        logger.debug(f"✅ Tenant context set to customer_id={customer_id}")
        
        if isinstance(memory.value, dict):
            # Ensure structured JSON (like prompt_blocks) is stored correctly
            memory.value = json.dumps(memory.value, ensure_ascii=False)
            logger.info(f"🧠 Stored structured JSON for key={memory.key}")    

        memory_id = mem_store.write(
            memory.type, memory.key, memory.value,
            user_id=None, scope="shared",
            ttl_days=memory.ttl_days, source=memory.source
        )
        return {
            "success": True,
            "id": memory_id,
            "memory_id": memory_id,
            "message": f"Memory stored: {memory.type}:{memory.key}"
        }
    except Exception as e:
        logger.error(f"Failed to store memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to store memory")
@app.delete("/v1/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    try:
        success = mem_store.delete_memory(memory_id)
        if success:
            return {"success": True, "message": f"Memory {memory_id} deleted"}
        raise HTTPException(status_code=404, detail="Memory not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete memory {memory_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete memory")

@app.post("/v1/memories/user")
async def store_user_memory(
    memory: MemoryObject,
    user_id: str,
    customer_id: int = Depends(validate_jwt),
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """🔐 Week 2: Now requires JWT authentication"""
    logger.info(f"🔐 JWT validated: customer_id={customer_id}")
    
    try:
        # 🔐 Set tenant context for RLS (psycopg2 style)
        with mem_store.conn.cursor() as cur:
            cur.execute("SET app.current_tenant = %s", (customer_id,))
        logger.debug(f"✅ Tenant context set to customer_id={customer_id}")
        
        memory_id = mem_store.write(
            memory.type, memory.key, memory.value,
            user_id=user_id, scope="user",
            ttl_days=memory.ttl_days, source=memory.source or "api"
        )
        return {"success": True, "memory_id": memory_id, "user_id": user_id,
                "message": f"User memory stored: {memory.type}:{memory.key}"}
    except Exception as e:
        logger.error(f"Failed to store user memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to store user memory")

@app.post("/v1/memories/shared")
async def store_shared_memory(
    memory: MemoryObject,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    try:
        memory_id = mem_store.write(
            memory.type, memory.key, memory.value,
            user_id=None, scope="shared",
            ttl_days=memory.ttl_days, source=memory.source or "admin"
        )
        return {"success": True, "memory_id": memory_id, "scope": "shared",
                "message": f"Shared memory stored: {memory.type}:{memory.key}"}
    except Exception as e:
        logger.error(f"Failed to store shared memory: {e}")
        raise HTTPException(status_code=500, detail="Failed to store shared memory")

@app.get("/v1/memories/user/{user_id}")
async def get_user_memories(
    user_id: str,
    query: str = "",
    limit: int = 10,
    include_shared: bool = True,
    customer_id: int = Depends(validate_jwt),
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """🔐 Week 2: Now requires JWT authentication"""
    logger.info(f"🔐 JWT validated: customer_id={customer_id}")
    
    try:
        # 🔐 Set tenant context for RLS (psycopg2 style)
        with mem_store.conn.cursor() as cur:
            cur.execute("SET app.current_tenant = %s", (customer_id,))
        logger.debug(f"✅ Tenant context set to customer_id={customer_id}")
        
        if query:
            memories = mem_store.search(query, user_id=user_id, k=limit, include_shared=include_shared)
        else:
            memories = mem_store.get_user_memories(user_id, limit=limit, include_shared=include_shared)
        return {"user_id": user_id, "memories": memories, "count": len(memories)}
    except Exception as e:
        logger.error(f"Failed to get user memories: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user memories")

@app.get("/v1/memories/shared")
async def get_shared_memories(
    query: str = "",
    limit: int = 20,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    try:
        if query:
            memories = mem_store.search(query, user_id=None, k=limit, include_shared=True)
            memories = [m for m in memories if m.get("scope") in ("shared", "global")]
        else:
            memories = mem_store.get_shared_memories(limit=limit)
                # 👇 Convert any JSON strings back into dictionaries
        for mem in memories:
            try:
                if isinstance(mem.get("value"), str):
                    parsed = json.loads(mem["value"])
                    if isinstance(parsed, dict):
                        mem["value"] = parsed
            except Exception:
                continue
        return {"memories": memories, "count": len(memories)}
    except Exception as e:
        logger.error(f"Failed to get shared memories: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve shared memories")

@app.get("/v1/tools")
async def get_available_tools():
    return {"tools": tool_dispatcher.get_available_tools(), "count": len(tool_dispatcher.tools)}

@app.post("/v1/tools/{tool_name}")
async def execute_tool(tool_name: str, parameters: dict):
    try:
        return tool_dispatcher.dispatch(tool_name, parameters)
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Tool execution failed: {str(e)}")

# -----------------------------------------------------------------------------
# Memory V2 API - Call Summaries & Personality Tracking
# -----------------------------------------------------------------------------

from app.models import ProcessCallRequest, EnrichedContextRequest, SearchSummariesRequest
from app.memory_integration import MemoryV2Integration

@app.post("/v2/process-call")
async def process_call_v2(
    request: ProcessCallRequest,
    customer_id: int = Depends(validate_jwt),
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """
    Process completed call - auto-summarize and track personality
    
    🔐 Requires JWT authentication
    🎯 RLS automatically filters by customer_id
    """
    logger.info(f"🔐 JWT validated: customer_id={customer_id}")
    
    try:
        # Set tenant context for RLS
        with mem_store.conn.cursor() as cur:
            cur.execute("SET app.current_tenant = %s", (customer_id,))
        
        memory_v2 = MemoryV2Integration(mem_store, llm_chat)
        result = memory_v2.process_completed_call(
            conversation_history=[(msg[0], msg[1]) for msg in request.conversation_history],
            user_id=request.user_id,
            thread_id=request.thread_id
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Failed to process call: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.post("/v2/context/enriched")
async def get_enriched_context_v2(
    request: EnrichedContextRequest,
    customer_id: int = Depends(validate_jwt),
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """
    Get enriched caller context (fast - <1 second)
    
    🔐 Requires JWT authentication
    🎯 RLS automatically filters by customer_id
    """
    logger.info(f"🔐 JWT validated: customer_id={customer_id}")
    
    try:
        # Set tenant context for RLS
        with mem_store.conn.cursor() as cur:
            cur.execute("SET app.current_tenant = %s", (customer_id,))
        
        memory_v2 = MemoryV2Integration(mem_store, llm_chat)
        # Note: num_summaries is currently hardcoded in the method (default: 5)
        context = memory_v2.get_enriched_context_for_call(user_id=request.user_id)
        summary_count = len([line for line in context.split("\n") if line.strip().startswith("Call")]) if context else 0
        return {
            "success": True,
            "context": context,
            "summary_count": summary_count,
            "has_personality_data": "PERSONALITY PROFILE" in context if context else False
        }
    except Exception as e:
        logger.error(f"Failed to get enriched context: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.get("/v2/summaries/{user_id}")
async def get_call_summaries_v2(
    user_id: str,
    limit: int = 10,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """Get call summaries for a user"""
    try:
        # Use search_call_summaries with empty query to get recent summaries
        summaries = mem_store.search_call_summaries(user_id, query_text="", limit=limit)
        return {
            "success": True,
            "user_id": user_id,
            "summaries": summaries,
            "total": len(summaries)
        }
    except Exception as e:
        logger.error(f"Failed to get call summaries: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.get("/v2/profiles")
async def get_all_caller_profiles_v2(
    limit: int = 100,
    customer_id: int = Depends(validate_jwt),
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """
    Get all caller profiles for the authenticated customer.
    
    🔐 Requires JWT authentication
    🎯 RLS automatically filters by customer_id
    """
    logger.info(f"🔐 JWT validated: customer_id={customer_id}")
    
    try:
        # Set tenant context for RLS
        with mem_store.conn.cursor() as cur:
            cur.execute("SET app.current_tenant = %s", (customer_id,))
        
        # Get profiles (RLS filters automatically)
        profiles = mem_store.get_all_caller_profiles(limit=limit)
        
        return {
            "success": True,
            "customer_id": customer_id,
            "profiles": profiles,
            "total": len(profiles)
        }
    except Exception as e:
        logger.error(f"Failed to get caller profiles: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.get("/v2/profile/{user_id}")
async def get_caller_profile_v2(
    user_id: str,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """Get caller profile"""
    try:
        profile = mem_store.get_or_create_caller_profile(user_id)
        return {
            "success": True,
            "profile": profile
        }
    except Exception as e:
        logger.error(f"Failed to get caller profile: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.get("/v2/personality/{user_id}")
async def get_personality_averages_v2(
    user_id: str,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """Get personality averages and trends"""
    try:
        averages = mem_store.get_personality_averages(user_id)
        if averages:
            # Structure the response for better readability
            personality_data = {
                "call_count": averages.get("call_count", 0),
                "big_five": {
                    "openness": averages.get("avg_openness"),
                    "conscientiousness": averages.get("avg_conscientiousness"),
                    "extraversion": averages.get("avg_extraversion"),
                    "agreeableness": averages.get("avg_agreeableness"),
                    "neuroticism": averages.get("avg_neuroticism")
                },
                "communication_style": {
                    "formality": averages.get("avg_formality"),
                    "directness": averages.get("avg_directness"),
                    "detail_orientation": averages.get("avg_detail_orientation"),
                    "patience": averages.get("avg_patience"),
                    "technical_comfort": averages.get("avg_technical_comfort")
                },
                "emotional_state": {
                    "frustration_level": averages.get("avg_frustration_level"),
                    "satisfaction_level": averages.get("avg_satisfaction_level"),
                    "urgency_level": averages.get("avg_urgency_level")
                },
                "trends": {
                    "satisfaction_trend": averages.get("satisfaction_trend", "stable")
                }
            }
            return {
                "success": True,
                "user_id": user_id,
                "personality": personality_data
            }
        else:
            return {
                "success": True,
                "user_id": user_id,
                "personality": None,
                "message": "No personality data available yet"
            }
    except Exception as e:
        logger.error(f"Failed to get personality averages: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.post("/v2/summaries/search")
async def search_call_summaries_v2(
    request: SearchSummariesRequest,
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """Semantic search on call summaries (not raw data)"""
    try:
        results = mem_store.search_call_summaries(
            user_id=request.user_id,
            query_text=request.query,
            limit=request.limit or 5
        )
        return {
            "success": True,
            "results": results
        }
    except Exception as e:
        logger.error(f"Failed to search call summaries: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

# -----------------------------------------------------------------------------
# Backward Compatibility Shim for ChatStack (DEPRECATED - use /v1 or /v2)
# -----------------------------------------------------------------------------
@app.post("/memory/store")
async def legacy_memory_store(
    request: Request,
    customer_id: int = Depends(validate_jwt),
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """
    DEPRECATED: Backward compatibility shim for ChatStack.
    Forwards to /v1/memories endpoint.
    ChatStack should migrate to /v1/memories or /v2/* endpoints.
    
    🔐 Week 2: Now requires JWT authentication
    """
    logger.warning("⚠️ Legacy endpoint /memory/store called - ChatStack should migrate to /v1 or /v2")
    logger.info(f"🔐 JWT validated: customer_id={customer_id}")
    
    try:
        # 🔐 Set tenant context for RLS (psycopg2 style)
        with mem_store.conn.cursor() as cur:
            cur.execute("SET app.current_tenant = %s", (customer_id,))
        logger.debug(f"✅ Tenant context set to customer_id={customer_id}")
        
        payload = await request.json()
        user_id = payload.get("user_id")
        role = payload.get("role", "user")
        content = payload.get("content", "")
        metadata = payload.get("metadata", {})
        
        # Convert old format to MemoryObject format
        memory_value = {"content": content, "role": role, "metadata": metadata}
        
        # Store using V1 logic (mem_store.write handles JSON encoding)
        # RLS automatically enforces customer_id filter
        memory_id = mem_store.write(
            memory_type="conversation",  # Fixed: parameter name is memory_type not type
            key=f"{role}:{user_id}",
            value=memory_value,  # Pass dict directly - mem_store.write will JSON-encode it
            user_id=user_id,
            scope="user",
            ttl_days=365,
            source="chatstack_legacy",
            customer_id=customer_id  # ← Pass tenant ID from JWT
        )
        
        # Return in old format
        return {
            "success": True,
            "id": memory_id,
            "memory_id": memory_id
        }
    except Exception as e:
        logger.error(f"Legacy memory store failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.post("/memory/retrieve")
async def legacy_memory_retrieve(
    request: Request,
    customer_id: int = Depends(validate_jwt),
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """
    DEPRECATED: Backward compatibility shim for ChatStack.
    Forwards to /v1/memories/user/{user_id} endpoint.
    ChatStack should migrate to /v2/context/enriched for 10x faster retrieval.
    
    🔐 Week 2: Now requires JWT authentication
    """
    logger.warning("⚠️ Legacy endpoint /memory/retrieve called - ChatStack should use /v2/context/enriched for 10x faster retrieval")
    logger.info(f"🔐 JWT validated: customer_id={customer_id}")
    
    try:
        # 🔐 Set tenant context for RLS (psycopg2 style)
        with mem_store.conn.cursor() as cur:
            cur.execute("SET app.current_tenant = %s", (customer_id,))
        logger.debug(f"✅ Tenant context set to customer_id={customer_id}")
        
        payload = await request.json()
        user_id = payload.get("user_id")
        limit = payload.get("limit", 500)
        thread_id = payload.get("thread_id")
        
        # Use V1 logic to get memories
        # RLS automatically enforces customer_id filter
        memories = mem_store.get_user_memories(user_id, limit=limit, include_shared=True)
        
        # Return in old format
        return {
            "success": True,
            "memories": memories,
            "count": len(memories)
        }
    except Exception as e:
        logger.error(f"Legacy memory retrieve failed: {e}", exc_info=True)
        return {"success": False, "error": str(e), "memories": []}

