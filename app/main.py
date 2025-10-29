import os
import time
import logging
from typing import List, Optional, Deque, Tuple, Dict, Any
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from starlette.websockets import WebSocketState
import json
import base64
import audioop
import numpy as np
import asyncio
import threading
from websocket import WebSocketApp

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
from app.packer import pack_prompt, should_remember, extract_carry_kit_items, detect_safety_triggers
from app.tools import tool_dispatcher, parse_tool_calls, execute_tool_calls
from app.middleware.auth import validate_jwt  # 🔐 Week 2: JWT authentication

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

# CORS disabled for WebSocket compatibility with Twilio Media Streams
# Nginx proxy provides security - no browser CORS needed
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
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """Process completed call - auto-summarize and track personality"""
    try:
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
    mem_store: MemoryStore = Depends(get_memory_store)
):
    """Get enriched caller context (fast - <1 second)"""
    try:
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
            source="chatstack_legacy"
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

# -----------------------------------------------------------------------------
# OpenAI Realtime API Bridge for Twilio Media Streams
# -----------------------------------------------------------------------------

def pcmu8k_to_pcm16_8k(b: bytes) -> bytes:
    """Convert Twilio mulaw to PCM16"""
    return audioop.ulaw2lin(b, 2)

def upsample_8k_to_24k(pcm16_8k: bytes) -> bytes:
    """Upsample 8kHz to 24kHz (3x)"""
    arr = np.frombuffer(pcm16_8k, dtype=np.int16)
    arr3 = np.repeat(arr, 3)
    return arr3.tobytes()

def downsample_24k_to_8k(pcm16_24k: bytes) -> bytes:
    """Downsample 24kHz to 8kHz (1/3)"""
    arr = np.frombuffer(pcm16_24k, dtype=np.int16)
    arr8k = arr[::3]
    return arr8k.tobytes()

def pcm16_8k_to_pcmu8k(pcm16_8k: bytes) -> bytes:
    """Convert PCM16 to Twilio mulaw"""
    return audioop.lin2ulaw(pcm16_8k, 2)

class OAIRealtime:
    """OpenAI Realtime API WebSocket client"""
    
    def __init__(self, system_instructions: str, on_audio_delta, on_text_delta, thread_id: Optional[str] = None, user_id: Optional[str] = None, voice: str = "alloy"):
        self.ws = None
        self.system_instructions = system_instructions
        self.on_audio_delta = on_audio_delta
        self.on_text_delta = on_text_delta
        self.voice = voice  # OpenAI voice (alloy, echo, shimmer)
        self.thread_id = thread_id
        self.user_id = user_id
        self._connected = threading.Event()
        self.audio_buffer_size = 0  # Track buffered audio bytes (24kHz PCM16)
    
    def _on_open(self, ws):
        """Configure session when WebSocket opens"""
        session_update = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": self.system_instructions,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": {"type": "server_vad"},
                "temperature": 0.7,
                "voice": self.voice  # Dynamic voice from admin panel
            }
        }
        ws.send(json.dumps(session_update))
        logger.info(f"✅ OpenAI Realtime session configured with voice: {self.voice}")
        
        # Trigger immediate greeting - tell AI to start speaking first
        # Get the appropriate greeting from session instructions
        greeting_instruction = "Start the call by speaking first. Say your greeting exactly as specified in your GREETING GUIDANCE section. Speak in English."
        
        response_create = {
            "type": "response.create",
            "response": {
                "modalities": ["text", "audio"],
                "instructions": greeting_instruction
            }
        }
        ws.send(json.dumps(response_create))
        logger.info(f"📞 Triggered AI greeting: {greeting_instruction}")
        
        self._connected.set()
    
    def _on_message(self, ws, msg):
        """Handle incoming messages from OpenAI"""
        try:
            ev = json.loads(msg)
        except Exception:
            return
        
        event_type = ev.get("type")
        
        # Log ALL events for debugging
        logger.info(f"🔔 OpenAI event: {event_type}")
        
        if event_type == "response.audio.delta":
            b64 = ev.get("delta", "")
            if b64:
                pcm24 = base64.b64decode(b64)
                logger.info(f"🔊 Received audio delta: {len(pcm24)} bytes")
                self.on_audio_delta(pcm24)
        
        elif event_type == "response.text.delta":
            delta = ev.get("delta", "")
            if delta:
                self.on_text_delta(delta)
        
        elif event_type == "response.text.done":
            # Text response complete (not used in audio mode)
            text = ev.get("text", "")
            if text:
                logger.info(f"📝 OpenAI text response: {text[:100]}...")
        
        elif event_type == "session.created":
            logger.info(f"✅ OpenAI session created: {ev.get('session', {}).get('id')}")
        
        elif event_type == "input_audio_buffer.speech_started":
            logger.info("🎤 User started speaking")
        
        elif event_type == "input_audio_buffer.speech_stopped":
            logger.info("🎤 User stopped speaking")
            self.audio_buffer_size = 0  # Reset buffer after speech
        
        elif event_type == "conversation.item.created":
            # Capture user or assistant messages
            item = ev.get("item", {})
            role = item.get("role")
            if role in ("user", "assistant"):
                content_list = item.get("content", [])
                for content in content_list:
                    if content.get("type") == "input_text":
                        text = content.get("text", "")
                        logger.info(f"💬 User said: {text}")
                        # Store in thread history
                        if hasattr(self, 'thread_id') and self.thread_id:
                            THREAD_HISTORY[self.thread_id].append(("user", text))
                    elif content.get("type") == "text":
                        text = content.get("text", "")
                        logger.info(f"🤖 Assistant said: {text}")
                        if hasattr(self, 'thread_id') and self.thread_id:
                            THREAD_HISTORY[self.thread_id].append(("assistant", text))
        
        elif event_type == "response.audio_transcript.done":
            # Capture assistant's spoken response transcript
            transcript = ev.get("transcript", "")
            if transcript:
                logger.info(f"🗣️ Assistant transcript: {transcript}")
                if hasattr(self, 'thread_id') and self.thread_id:
                    THREAD_HISTORY[self.thread_id].append(("assistant", transcript))
        
        elif event_type == "conversation.item.input_audio_transcription.completed":
            # Capture user's spoken input transcript
            transcript = ev.get("transcript", "")
            if transcript:
                logger.info(f"🎤 User transcript: {transcript}")
                if hasattr(self, 'thread_id') and self.thread_id:
                    THREAD_HISTORY[self.thread_id].append(("user", transcript))
        
        elif event_type == "response.done":
            logger.info("✅ OpenAI response complete")
            self.audio_buffer_size = 0  # Reset buffer after response
            
            # Save thread history to database after each response
            if hasattr(self, 'thread_id') and self.thread_id and hasattr(self, 'user_id') and self.user_id:
                try:
                    mem_store = MemoryStore()
                    save_thread_history(self.thread_id, mem_store, self.user_id)
                    
                    # ✅ Extract and save structured facts from recent conversation
                    # Get last user message from thread history for memory extraction
                    try:
                        history = THREAD_HISTORY.get(self.thread_id, [])
                        if history:
                            # Check last 5 messages for important information
                            recent_messages = list(history)[-5:]
                            for role, content in recent_messages:
                                if role == "user":
                                    try:
                                        if should_remember(content):
                                            logger.info(f"🧠 Extracting memories from: {content[:100]}...")
                                            items = extract_carry_kit_items(content)
                                            for item in items:
                                                try:
                                                    memory_id = mem_store.write(
                                                        memory_type=item["type"],
                                                        key=item["key"],
                                                        value=item["value"],
                                                        user_id=self.user_id,
                                                        scope="user",
                                                        ttl_days=item.get("ttl_days", 365)
                                                    )
                                                    logger.info(f"💾 Saved structured memory: {item['type']}:{item['key']} -> {memory_id}")
                                                except Exception as e:
                                                    logger.error(f"Failed to save structured memory: {e}")
                                    except Exception as e:
                                        logger.error(f"Memory extraction error: {e}")
                    except Exception as e:
                        logger.error(f"Memory processing error: {e}")
                except Exception as e:
                    logger.warning(f"Failed to save thread history: {e}")
        
        elif event_type == "error":
            error_msg = ev.get("error", {}).get("message", "Unknown error")
            logger.error(f"❌ OpenAI error: {error_msg}")
    
    def _on_error(self, ws, err):
        logger.error(f"OpenAI WebSocket error: {err}")
    
    def _on_close(self, ws, *args):
        """Handle WebSocket close (compatible with any websocket-client version)"""
        if len(args) >= 2:
            logger.info(f"OpenAI WebSocket closed: code={args[0]}, reason={args[1]}")
        elif len(args) == 1:
            logger.info(f"OpenAI WebSocket closed: {args[0]}")
        else:
            logger.info("OpenAI WebSocket closed")
    
    def connect(self):
        """Establish WebSocket connection to OpenAI Realtime API"""
        openai_key = get_secret("OPENAI_API_KEY")
        model = get_setting("realtime_model", "gpt-realtime")
        realtime_url = f"wss://api.openai.com/v1/realtime?model={model}"
        
        headers = [
            f"Authorization: Bearer {openai_key}",
            "OpenAI-Beta: realtime=v1"
        ]
        
        self.ws = WebSocketApp(
            realtime_url,
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        
        threading.Thread(target=self.ws.run_forever, daemon=True).start()
        self._connected.wait(timeout=5)
    
    def send_pcm16_24k(self, chunk: bytes):
        """Send audio chunk to OpenAI"""
        if not self.ws:
            return
        ev = {
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(chunk).decode("ascii")
        }
        self.ws.send(json.dumps(ev))
        self.audio_buffer_size += len(chunk)
    
    def commit_and_respond(self):
        """Commit audio buffer and request response (only if >= 100ms buffered)"""
        if not self.ws:
            return
        
        # 100ms at 24kHz PCM16 = 24000 samples/sec * 0.1 sec * 2 bytes = 4800 bytes
        MIN_BUFFER_SIZE = 4800
        
        if self.audio_buffer_size >= MIN_BUFFER_SIZE:
            self.ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            self.ws.send(json.dumps({"type": "response.create"}))
            self.audio_buffer_size = 0  # Reset after commit
        else:
            logger.debug(f"⏸️ Skipping commit - buffer too small ({self.audio_buffer_size} < {MIN_BUFFER_SIZE} bytes)")
    
    def close(self):
        """Close the WebSocket connection"""
        if self.ws:
            self.ws.close()

@app.websocket("/phone/media-stream")
async def media_stream_endpoint(websocket: WebSocket):
    """Twilio Media Streams WebSocket endpoint"""
    await websocket.accept()
    logger.info("🌐 Twilio Media Stream connected")
    
    # Capture the event loop for use in threaded callbacks
    event_loop = asyncio.get_event_loop()
    
    stream_sid = None
    oai = None
    last_media_ts = time.time()
    
    def on_oai_audio(pcm24):
        """Handle audio from OpenAI - send to Twilio"""
        logger.info(f"📤 Sending audio to Twilio: {len(pcm24)} bytes PCM24 -> mulaw")
        pcm8 = downsample_24k_to_8k(pcm24)
        mulaw = pcm16_8k_to_pcmu8k(pcm8)
        payload = base64.b64encode(mulaw).decode("ascii")
        
        if websocket.application_state == WebSocketState.CONNECTED:
            # Schedule coroutine in the FastAPI event loop from this thread
            asyncio.run_coroutine_threadsafe(
                websocket.send_text(json.dumps({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload}
                })),
                event_loop
            )
            logger.info(f"✅ Audio sent to Twilio ({len(payload)} base64 chars)")
        else:
            logger.warning("⚠️ WebSocket not connected, skipping audio send")
    
    def on_oai_text(delta):
        """Handle text transcript from OpenAI"""
        logger.info(f"📝 OpenAI: {delta}")
    
    def on_tts_needed(text):
        """Generate ElevenLabs audio and stream to Twilio"""
        try:
            logger.info(f"🎙️ Generating ElevenLabs TTS for: {text[:100]}...")
            
            # Get voice_id from admin panel
            voice_id = get_admin_setting("voice_id", "FGY2WhTYpPnrIDTdsKH5")
            logger.info(f"🔊 Using ElevenLabs voice_id: {voice_id}")
            
            # Import ElevenLabs client
            from elevenlabs.client import ElevenLabs
            from elevenlabs import VoiceSettings
            
            client = ElevenLabs(api_key=get_secret("ELEVENLABS_API_KEY"))
            
            # Stream audio from ElevenLabs
            audio_stream = client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_turbo_v2_5",  # Fast model for real-time
                output_format="pcm_24000"  # 24kHz PCM16 to match OpenAI
            )
            
            # Stream to Twilio
            for chunk in audio_stream:
                if chunk:
                    # Chunk is already 24kHz PCM16 from ElevenLabs
                    pcm8 = downsample_24k_to_8k(chunk)
                    mulaw = pcm16_8k_to_pcmu8k(pcm8)
                    payload = base64.b64encode(mulaw).decode("ascii")
                    
                    if websocket.application_state == WebSocketState.CONNECTED:
                        asyncio.run_coroutine_threadsafe(
                            websocket.send_text(json.dumps({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": payload}
                            })),
                            event_loop
                        )
            
            logger.info("✅ ElevenLabs audio streaming complete")
            
        except Exception as e:
            logger.error(f"❌ ElevenLabs TTS failed: {e}")
    
    try:
        while True:
            msg = await websocket.receive_text()
            ev = json.loads(msg)
            event_type = ev.get("event")
            
            if event_type == "start":
                stream_sid = ev["start"]["streamSid"]
                custom_params = ev["start"].get("customParameters", {})
                user_id = custom_params.get("user_id")
                is_callback = custom_params.get("is_callback") == "True"
                
                # ✅ Create stable thread_id for conversation continuity
                thread_id = f"user_{user_id}" if user_id else None
                
                logger.info(f"📞 Stream started: {stream_sid}, User: {user_id}, Thread: {thread_id}, Callback: {is_callback}")
                
                # Build system instructions with memory context
                try:
                    mem_store = MemoryStore()
                    
                    # ✅ CRITICAL: Load thread history from database for conversation continuity
                    if thread_id and user_id:
                        load_thread_history(thread_id, mem_store, user_id)
                        logger.info(f"🔄 Loaded thread history for {thread_id}: {len(THREAD_HISTORY.get(thread_id, []))} messages")
                    
                    # ✅ CRITICAL FIX: Use get_user_memories instead of search("") to retrieve ALL user memories
                    if user_id:
                        memories = mem_store.get_user_memories(user_id, limit=50, include_shared=True)
                        logger.info(f"🧠 Retrieved {len(memories)} memories for user {user_id}")
                        # DEBUG: Log first few memories
                        for i, mem in enumerate(memories[:5]):
                            mem_type = mem.get('type', 'unknown')
                            mem_key = mem.get('key') or mem.get('k', 'no-key')
                            logger.info(f"  Memory {i+1}: {mem_type}:{mem_key}")
                    else:
                        memories = []
                    
                    # Load base system prompt
                    system_prompt_path = "app/prompts/system_sam.txt"
                    try:
                        with open(system_prompt_path, "r") as f:
                            instructions = f.read()
                    except FileNotFoundError:
                        instructions = "You are Samantha for Peterson Family Insurance. Be concise, warm, and human."
                    
                    # Add identity and greeting context - use get_admin_setting to query ai-memory directly
                    agent_name = get_admin_setting("agent_name", "Betsy")
                    instructions += f"\n\n=== YOUR IDENTITY ===\nYour name is {agent_name} and you work for Peterson Family Insurance Agency."
                    
                    # Add conversation history context
                    if thread_id and THREAD_HISTORY.get(thread_id):
                        history = list(THREAD_HISTORY[thread_id])
                        if history:
                            instructions += f"\n\n=== CONVERSATION HISTORY ===\nThis is a continuing conversation. Previous messages:\n"
                            for role, content in history[-10:]:  # Last 5 turns
                                instructions += f"{role}: {content[:200]}...\n" if len(content) > 200 else f"{role}: {content}\n"
                    
                    # Add caller context
                    if is_callback and memories:
                        # Existing user - look for their name
                        user_name = None
                        for mem in memories[:10]:
                            value = mem.get("value", {})
                            if isinstance(value, dict) and "name" in value:
                                user_name = value.get("name")
                                break
                        
                        greeting_template = get_admin_setting("existing_user_greeting", 
                                                             f"Hi, this is {agent_name} from Peterson Family Insurance Agency. Is this {{user_name}}?")
                        if user_name:
                            greeting = greeting_template.replace("{user_name}", user_name).replace("{agent_name}", agent_name)
                            instructions += f"\n\n=== GREETING GUIDANCE ===\nThis is a returning caller named {user_name}. Use this greeting style: '{greeting}'"
                        else:
                            greeting = greeting_template.replace("{user_name}", "").replace("{agent_name}", agent_name)
                            instructions += f"\n\n=== GREETING GUIDANCE ===\nThis is a returning caller. Use this greeting style: '{greeting}'"
                    else:
                        # New caller
                        import datetime
                        hour = datetime.datetime.now().hour
                        if hour < 12:
                            time_greeting = "Good morning"
                        elif hour < 18:
                            time_greeting = "Good afternoon"
                        else:
                            time_greeting = "Good evening"
                        
                        greeting_template = get_admin_setting("new_caller_greeting", 
                                                             f"{{time_greeting}}! This is {agent_name} from Peterson Family Insurance Agency. How can I help you?")
                        greeting = greeting_template.replace("{time_greeting}", time_greeting).replace("{agent_name}", agent_name)
                        instructions += f"\n\n=== GREETING GUIDANCE ===\nThis is a new caller. Use this greeting: '{greeting}'"
                    
                    # Inject normalized memory context (organized dict instead of raw entries)
                    if memories:
                        # ✅ COMPREHENSIVE: Normalize 800+ scattered memories into fill-in-the-blanks template
                        normalized = mem_store.normalize_memories(memories)
                        
                        if normalized:
                            # Format as structured memory for AI
                            instructions += "\n\n=== YOUR_MEMORY_OF_THIS_CALLER ===\n"
                            instructions += "Below is everything you know about this caller, organized by category:\n\n"
                            instructions += json.dumps(normalized, indent=2)
                            instructions += "\n\nIMPORTANT: Use this structured data naturally in conversation. "
                            instructions += "If you see a spouse name, use it. If you see a birthday, remember it. "
                            instructions += "Empty fields (null values) mean you haven't learned that info yet.\n"
                            instructions += "=== END_MEMORY ===\n"
                            
                            # Count actual populated data
                            filled_contacts = sum(1 for rel in ["spouse", "father", "mother"] 
                                                if normalized.get("contacts", {}).get(rel, {}).get("name"))
                            filled_contacts += len(normalized.get("contacts", {}).get("children", []))
                            
                            stats = {
                                "contacts": filled_contacts,
                                "vehicles": len(normalized.get("vehicles", [])),
                                "policies": len(normalized.get("policies", [])),
                                "facts": len(normalized.get("facts", [])),
                                "commitments": len(normalized.get("commitments", []))
                            }
                            
                            logger.info(f"📝 Injected comprehensive memory template from {len(memories)} raw entries:")
                            logger.info(f"   └─ Contacts: {stats['contacts']}, Vehicles: {stats['vehicles']}, Policies: {stats['policies']}, Facts: {stats['facts']}")
                            
                            # 🔍 DEBUG: Show what contacts were extracted
                            if stats['contacts'] > 0:
                                logger.info(f"   👥 Contacts found:")
                                for rel in ["spouse", "father", "mother"]:
                                    contact = normalized.get("contacts", {}).get(rel, {})
                                    if contact.get("name"):
                                        logger.info(f"      • {rel.title()}: {contact['name']}" + 
                                                  (f" (birthday: {contact['birthday']})" if contact.get("birthday") else ""))
                                
                                for child in normalized.get("contacts", {}).get("children", []):
                                    logger.info(f"      • {child.get('relationship', 'child').title()}: {child.get('name', 'unknown')}")
                        else:
                            logger.warning(f"⚠️ normalize_memories returned empty dict from {len(memories)} raw memories")
                
                except Exception as e:
                    logger.error(f"Failed to load memory context: {e}")
                    instructions = "You are Samantha for Peterson Family Insurance. Be concise, warm, and human."
                
                # Get voice from admin panel (alloy, echo, shimmer)
                openai_voice = get_admin_setting("openai_voice", "alloy")
                logger.info(f"🎤 Using OpenAI voice from admin panel: {openai_voice}")
                
                # Connect to OpenAI with thread tracking
                oai = OAIRealtime(
                    instructions, 
                    on_oai_audio, 
                    on_oai_text, 
                    thread_id=thread_id, 
                    user_id=user_id,
                    voice=openai_voice
                )
                oai.connect()
                logger.info(f"🔗 OpenAI client initialized with thread_id={thread_id}, user_id={user_id}")
            
            elif event_type == "media":
                # Audio from Twilio (mulaw 8kHz base64)
                b64 = ev["media"]["payload"]
                mulaw = base64.b64decode(b64)
                pcm16_8k = pcmu8k_to_pcm16_8k(mulaw)
                pcm16_24k = upsample_8k_to_24k(pcm16_8k)
                
                if oai:
                    oai.send_pcm16_24k(pcm16_24k)
                last_media_ts = time.time()
            
            elif event_type == "mark":
                # Mark event - commit audio buffer
                if oai:
                    oai.commit_and_respond()
            
            elif event_type == "stop":
                logger.info(f"📞 Stream stopped: {stream_sid}")
                break
            
            # Auto-commit on pause (rudimentary VAD assist)
            if (time.time() - last_media_ts) > 0.7 and oai:
                oai.commit_and_respond()
                last_media_ts = time.time()
    
    except WebSocketDisconnect:
        logger.info("Twilio disconnected")
    except Exception as e:
        logger.exception(f"Media stream error: {e}")
    finally:
        if oai:
            oai.close()
        logger.info("🔌 WebSocket closed")

# -----------------------------------------------------------------------------
# Entrypoint (dev)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(get_setting("port", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
