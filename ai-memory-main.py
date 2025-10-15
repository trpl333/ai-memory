# main.py — clean rebuild
import os
import time
import logging
from typing import List, Any, Dict
import ssl
import requests
import sqlalchemy
import databases
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

# Import memory normalization
from memory_schema import normalize_memories, MEMORY_TEMPLATE

# -------------------------------------------------------------------------------------
# Environment / Config
# -------------------------------------------------------------------------------------
DATABASE_URL   = os.getenv("DATABASE_URL", "")
LLM_BASE_URL   = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL      = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_API_KEY    = os.getenv("OPENAI_API_KEY", "")
LLM_TIMEOUT    = int(os.getenv("LLM_TIMEOUT", "180"))

# -------------------------------------------------------------------------------------
# Database (async via databases)
# -------------------------------------------------------------------------------------
# Create SSL context for asyncpg (toggle verification via env)
def _build_pg_ssl_context() -> ssl.SSLContext:
    # DB_SSL_VERIFY=true|false  (default: false to match psycopg's 'require' behavior)
    verify = os.getenv("DB_SSL_VERIFY", "false").lower() not in ("false", "0", "no", "off")
    if verify:
        return ssl.create_default_context()
    ctx = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

database = databases.Database(DATABASE_URL, ssl=_build_pg_ssl_context()) if DATABASE_URL else None
metadata = sqlalchemy.MetaData()

memory_logs = sqlalchemy.Table(
    "memory_logs",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("user_id", sqlalchemy.String),
    sqlalchemy.Column("prompt", sqlalchemy.Text),
    sqlalchemy.Column("memory", sqlalchemy.Text),
    sqlalchemy.Column("response", sqlalchemy.Text),
)

memory_table = sqlalchemy.Table(
    "memory",
    metadata,
    sqlalchemy.Column("user_id", sqlalchemy.String),
    sqlalchemy.Column("message", sqlalchemy.Text),
)

# -------------------------------------------------------------------------------------
# App
# -------------------------------------------------------------------------------------
app = FastAPI(title="NeuroSphereAI Orchestrator")

# ------------------------------------------------------------
# Basic routes / probes / static text
# ------------------------------------------------------------
@app.get("/")
def root():
    return {"ok": True, "msg": "NeuroSphere AI-Memory is running. See /health or /docs."}

@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return "User-agent: *\nDisallow: /\n"

@app.get("/favicon.ico", status_code=204)
def favicon():
    return None

@app.get("/.well-known/security.txt", response_class=PlainTextResponse)
def security_txt():
    return "Contact: mailto:security@theinsurancedoctors.com\nPolicy: https://theinsurancedoctors.com/security\n"

@app.get("/health")
async def health():
    db_ok = False
    if database:
        try:
            await database.execute("SELECT 1")
            db_ok = True
        except Exception:
            db_ok = False
    return {"status": "ok", "db": db_ok}

# ------------------------------------------------------------
# Startup / Shutdown
# ------------------------------------------------------------
@app.on_event("startup")
async def connect_to_db():
    if database:
        await database.connect()

@app.on_event("shutdown")
async def disconnect_from_db():
    if database:
        await database.disconnect()

# ------------------------------------------------------------
# Pydantic models
# ------------------------------------------------------------
class LLMRequest(BaseModel):
    user_id: str
    prompt: str

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
async def get_memory_text(user_id: str) -> str:
    """Join prior messages for a user into one context string."""
    if not database:
        return ""
    q = memory_table.select().where(memory_table.c.user_id == user_id)
    rows = await database.fetch_all(q)
    msgs = []
    for r in rows:
        msg = dict(r).get("message")   # databases.Record -> dict first
        if msg:
            msgs.append(msg)
    return "\n".join(msgs).strip()

# ------------------------------------------------------------
# Memory endpoints
# ------------------------------------------------------------
@app.post("/memory/store")
async def memory_store(request: Request):
    if not database:
        raise HTTPException(status_code=500, detail="Database not configured")
    data = await request.json()
    user_id = data.get("user_id")
    message = data.get("message")
    if not user_id or message is None:
        raise HTTPException(status_code=400, detail="user_id and message are required")

    # quick-retrieve table
    await database.execute(memory_table.insert().values(user_id=user_id, message=message))
    # log table
    await database.execute(memory_logs.insert().values(
        user_id=user_id, prompt="memory_store", memory=message, response=None
    ))
    return {"message": "Memory stored in PostgreSQL successfully"}

@app.post("/memory/retrieve")
async def memory_retrieve(request: Request):
    """
    ✅ COMPREHENSIVE: Returns normalized memory schema instead of raw text.
    Single source of truth for memory normalization.
    """
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    
    # Get raw memory text
    memory_text = await get_memory_text(user_id)
    
    # ✅ NEW: Normalize into structured schema
    normalized = normalize_memories(memory_text)
    
    # Return both raw and normalized for backwards compatibility
    return {
        "user_id": user_id,
        "memory": memory_text,  # Keep for backwards compatibility
        "normalized": normalized  # NEW: Structured schema
    }

@app.get("/memory/read")
async def memory_read(session_id: str = Query(..., alias="session_id")):
    if not database:
        raise HTTPException(status_code=500, detail="Database not configured")
    q = memory_logs.select().where(memory_logs.c.user_id == session_id)
    rows = await database.fetch_all(q)
    return {"rows": [dict(r) for r in rows]}

@app.get("/memory/keys")
async def list_user_ids():
    """
    Returns all unique user_ids currently stored in memory.
    Used by the Notion sync service to discover new callers automatically.
    """
    if not database:
        raise HTTPException(status_code=500, detail="Database not configured")
    
    try:
        # Get distinct user_ids from the memory table using raw SQL
        query = "SELECT DISTINCT user_id FROM memory WHERE user_id IS NOT NULL ORDER BY user_id"
        rows = await database.fetch_all(query)
        
        # Return as list of dicts for easy consumption
        user_ids = [{"user_id": row["user_id"]} for row in rows]
        return user_ids
    except Exception as e:
        logging.exception("Error fetching user_ids")
        raise HTTPException(status_code=500, detail=f"Failed to fetch user_ids: {str(e)}")

# ------------------------------------------------------------
# LLM endpoint (calls OpenAI API)
# ------------------------------------------------------------
@app.post("/llm/respond")
async def llm_respond(body: LLMRequest):
    try:
        # Build prompt + messages
        memory_text = await get_memory_text(body.user_id)
        full_prompt = f"Context:\n{memory_text}\n\nUser: {body.prompt}".strip()

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": full_prompt}
        ]

        # Call OpenAI API
        payload = {
            "model": LLM_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 80,
            "stream": False,
        }
        headers: Dict[str, str] = {}
        if LLM_API_KEY:
            headers["Authorization"] = f"Bearer {LLM_API_KEY}"
        
        r = requests.post(f"{LLM_BASE_URL}/chat/completions", json=payload, headers=headers, timeout=LLM_TIMEOUT)

        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"LLM call failed: {r.text}")
        data = r.json()

        # Extract OpenAI-style text
        text = ""
        if isinstance(data, dict) and data.get("choices"):
            ch0 = data["choices"][0]
            msg = (ch0.get("message") or {})
            text = (msg.get("content") or ch0.get("text") or "").strip()

        # Log the exchange
        if database:
            await database.execute(memory_logs.insert().values(
                user_id=body.user_id, prompt=body.prompt, memory=memory_text, response=text
            ))

        return {
            "id": "chatcmpl-local",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": LLM_MODEL or "custom-neurosphere-v1",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(full_prompt.split()),
                "completion_tokens": len(text.split()),
                "total_tokens": len(full_prompt.split()) + len(text.split())
            }
        }

    except Exception as e:
        logging.exception("LLM Respond error")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


# ------------------------------------------------------------
# OpenAI-style endpoint: /v1/chat/completions
# ------------------------------------------------------------
@app.post("/v1/chat/completions")
async def chat_completions(req: Request):
    body = await req.json()
    session_id = body.get("metadata", {}).get("session_id", "default")

    # 1. Retrieve memory (best-effort)
    past_context = ""
    try:
        r = requests.post(
            "http://127.0.0.1:8100/memory/retrieve",
            json={"session_id": session_id, "limit": 10}
        ).json()
        past_context = r.get("memory", "")
    except Exception as e:
        print("Memory retrieve error:", e)

    # 2. Inject memory into messages
    messages = body.get("messages", [])
    if past_context:
        messages.insert(
            0,
            {"role": "system", "content": f"Known context:\n{past_context}"}
        )

    # 3. Call OpenAI LLM
    payload = {
        "model": body.get("model", LLM_MODEL or "gpt-4o-mini"),
        "messages": messages,
        "temperature": 0.7,
        "stream": False,
    }

    headers: Dict[str, str] = {}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    try:
        resp = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=LLM_TIMEOUT
        ).json()
    except Exception as e:
        return {"error": f"LLM call failed: {e}"}

    # 4. Extract reply + store back into memory
    reply = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
    try:
        if reply:
            requests.post(
                "http://127.0.0.1:8100/memory/store",
                json={"session_id": session_id, "text": reply}
            )
    except Exception as e:
        print("Memory store error:", e)

    # 5. Return full LLM response
    return resp
