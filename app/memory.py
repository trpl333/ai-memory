import os
import json
import uuid
import logging
from typing import List, Dict, Any, Optional
import numpy as np
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from datetime import datetime, timedelta

# Import centralized configuration
from config_loader import get_setting, get_database_url

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
EMBED_DIM = int(get_setting("embed_dim", 768))
DB_URL = get_database_url()

def embed(text: str) -> np.ndarray:
    """
    Generate embedding vector for the given text.
    
    This is currently a placeholder implementation using deterministic hashing.
    In production, replace with a real embedding service like OpenAI embeddings,
    Sentence Transformers, or similar.
    
    Args:
        text: Input text to embed
        
    Returns:
        Normalized embedding vector
    """
    # Deterministic hash-based embedding (placeholder)
    # This ensures consistent embeddings for the same text across runs
    text_hash = abs(hash(text.lower().strip())) % (2**32)
    rng = np.random.default_rng(text_hash)
    
    # Generate random vector and normalize
    vector = rng.normal(size=EMBED_DIM)
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    
    return vector

class MemoryStore:
    """
    PostgreSQL-based memory store with vector similarity search using pgvector.
    """
    
    def __init__(self):
        """Initialize connection to PostgreSQL database."""
        if not DB_URL:
            raise ValueError("DATABASE_URL environment variable is required")
            
        # Ensure SSL is enabled for managed databases
        db_url = DB_URL
        if 'sslmode=' not in db_url:
            db_url += ('&' if '?' in db_url else '?') + 'sslmode=require'
            
        try:
            logger.info("Connecting to PostgreSQL database...")
            self.conn = psycopg2.connect(db_url, connect_timeout=5)
            self.conn.autocommit = True
            self.available = True
            logger.info("✅ Connected to PostgreSQL database")
            
            # Verify pgvector extension is available
            self._verify_extension()
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to database: {e}")
            self.available = False
            self.conn = None
            # Don't raise - allow app to start in degraded mode

    def _check_connection(self):
        """Check if database connection is available."""
        if not self.available or not self.conn:
            raise RuntimeError("Memory store is not available (database connection failed)")
    
    def _verify_extension(self):
        """Verify that pgvector extension is installed."""
        if not self.available:
            return
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                if not cur.fetchone():
                    logger.warning("pgvector extension not found - attempting to install")
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception as e:
            logger.error(f"Failed to verify/install pgvector extension: {e}")
            raise

    def write(self, memory_type: str, key: str, value: Dict[str, Any], user_id: Optional[str] = None, scope: str = "user", ttl_days: int = 365, source: str = "orchestrator", customer_id: int = 1) -> str:
        """
        Store a memory object in the database.
        
        Args:
            memory_type: Type of memory (person, preference, project, rule, moment, fact)
            key: Unique key/identifier for the memory
            value: Memory content as dictionary
            user_id: User ID for user-scoped memories (None for shared)
            scope: Memory scope ('user', 'shared', 'global')
            ttl_days: Time to live in days
            source: Source of the memory
            customer_id: Tenant identifier for multi-tenant isolation
            
        Returns:
            UUID of the stored memory
        """
        try:
            # Generate embedding for the memory content
            content_text = json.dumps(value, sort_keys=True)
            embedding = embed(content_text).tolist()
            
            with self.conn.cursor() as cur:
                # Set tenant context for RLS
                cur.execute("SET app.current_tenant = %s", (customer_id,))
                
                cur.execute(
                    """
                    INSERT INTO memories (customer_id, type, k, value_json, embedding, user_id, scope, ttl_days, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (customer_id, memory_type, key, Json(value), embedding, user_id, scope, ttl_days, source)
                )
                result = cur.fetchone()
                if result:
                    memory_id = result[0]
                else:
                    raise Exception("Failed to get memory ID")
                
            scope_info = f" [{scope}]" + (f" user:{user_id}" if user_id else "")
            logger.info(f"Stored memory: {memory_type}:{key} with ID {memory_id}{scope_info} [customer:{customer_id}]")
            return str(memory_id)
            
        except Exception as e:
            logger.error(f"Failed to write memory: {e}")
            raise

    def search(self, query_text: str, user_id: Optional[str] = None, k: int = 6, memory_types: Optional[List[str]] = None, include_shared: bool = True) -> List[Dict[str, Any]]:
        """
        Search for relevant memories using vector similarity.
        
        Args:
            query_text: Text to search for
            user_id: User ID to filter personal memories (None for no user filter)
            k: Number of results to return
            memory_types: Optional filter by memory types
            include_shared: Whether to include shared/global memories
            
        Returns:
            List of memory objects with similarity scores
        """
        try:
            # Generate query embedding
            query_embedding = embed(query_text).tolist()
            
            # Build query with filtering
            filters = ["created_at > NOW() - INTERVAL '1 year'"]
            params = [query_embedding]
            
            # User and scope filtering
            if user_id is not None:
                if include_shared:
                    filters.append("(user_id = %s OR scope IN ('shared', 'global'))")
                    params.append(user_id)
                else:
                    filters.append("user_id = %s")
                    params.append(user_id)
            elif include_shared:
                filters.append("scope IN ('shared', 'global')")
            
            # Type filtering
            if memory_types:
                filters.append("type = ANY(%s)")
                params.append(memory_types)
            
            params.append(query_embedding)
            params.append(k)
            
            where_clause = " AND ".join(filters)
            query = f"""
                SELECT id, type, k, value_json, user_id, scope, embedding <-> %s::vector as distance
                FROM memories
                WHERE {where_clause}
                ORDER BY embedding <-> %s::vector
                LIMIT %s
            """
            
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    "id": str(row["id"]),
                    "type": row["type"],
                    "key": row["k"],
                    "value": row["value_json"],
                    "user_id": row["user_id"],
                    "scope": row["scope"],
                    "distance": float(row["distance"])
                })
            
            logger.info(f"Memory search for '{query_text[:50]}...' returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return []
    
    def get_user_memories(self, user_id: str, limit: int = 10, include_shared: bool = True) -> List[Dict[str, Any]]:
        """
        Get recent memories for a specific user.
        
        Args:
            user_id: User ID to filter memories
            limit: Maximum number of memories to return
            include_shared: Whether to include shared memories
            
        Returns:
            List of memory objects
        """
        try:
            filters = []
            params = []
            
            if include_shared:
                filters.append("(user_id = %s OR scope IN ('shared', 'global'))")
                params.append(user_id)
            else:
                filters.append("user_id = %s")
                params.append(user_id)
            
            params.append(limit)
            
            where_clause = " AND ".join(filters)
            query = f"""
                SELECT id, type, k, value_json, user_id, scope, created_at
                FROM memories
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s
            """
            
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    "id": str(row["id"]),
                    "type": row["type"],
                    "key": row["k"],
                    "value": row["value_json"],
                    "user_id": row["user_id"],
                    "scope": row["scope"],
                    "created_at": row["created_at"].isoformat()
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get user memories: {e}")
            return []
    
    def get_shared_memories(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent shared memories available to all users.
        
        Args:
            limit: Maximum number of memories to return
            
        Returns:
            List of shared memory objects
        """
        try:
            query = """
                SELECT id, type, k, value_json, scope, created_at
                FROM memories
                WHERE scope IN ('shared', 'global')
                ORDER BY created_at DESC
                LIMIT %s
            """
            
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, [limit])
                rows = cur.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    "id": str(row["id"]),
                    "type": row["type"],
                    "key": row["k"],
                    "value": row["value_json"],
                    "scope": row["scope"],
                    "created_at": row["created_at"].isoformat()
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get shared memories: {e}")
            return []

    def get_memory_by_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific memory by ID.
        
        Args:
            memory_id: UUID of the memory
            
        Returns:
            Memory object or None if not found
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, type, k, value_json FROM memories WHERE id = %s",
                    (memory_id,)
                )
                row = cur.fetchone()
                
            if row:
                return {
                    "id": str(row["id"]),
                    "type": row["type"],
                    "key": row["k"],
                    "value": row["value_json"]
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to get memory {memory_id}: {e}")
            return None

    def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a memory by ID.
        
        Args:
            memory_id: UUID of the memory to delete
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
                deleted = cur.rowcount > 0
                
            logger.info(f"Memory {memory_id} {'deleted' if deleted else 'not found'}")
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            return False

    def cleanup_expired(self) -> int:
        """
        Remove expired memories based on TTL.
        
        Returns:
            Number of memories deleted
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM memories 
                    WHERE created_at + INTERVAL '1 day' * ttl_days < NOW()
                    """
                )
                deleted_count = cur.rowcount
                
            logger.info(f"Cleaned up {deleted_count} expired memories")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired memories: {e}")
            return 0

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get statistics about stored memories.
        
        Returns:
            Dictionary with memory statistics
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT 
                        type,
                        COUNT(*) as count,
                        AVG(EXTRACT(days FROM NOW() - created_at)) as avg_age_days
                    FROM memories 
                    GROUP BY type
                    ORDER BY count DESC
                    """
                )
                type_stats = cur.fetchall()
                
                cur.execute("SELECT COUNT(*) as total FROM memories")
                result = cur.fetchone()
                total_count = result["total"] if result else 0
                
            return {
                "total_memories": total_count,
                "by_type": [dict(row) for row in type_stats]
            }
            
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"total_memories": 0, "by_type": []}

    def close(self):
        """Close the database connection."""
        if hasattr(self, 'conn'):
            self.conn.close()
            logger.info("Database connection closed")
    
    # =========================================================================
    # MEMORY V2: Call Summaries, Caller Profiles, Personality Tracking
    # =========================================================================
    
    def store_call_summary(self, summary_data: Dict[str, Any], customer_id: int = 1) -> str:
        """
        Store a call summary in the database.
        
        Args:
            summary_data: Dictionary with call_id, user_id, summary, key_topics,
                         key_variables, sentiment, duration_seconds, resolution_status
            customer_id: Tenant identifier for multi-tenant isolation
                         
        Returns:
            UUID of the stored summary
        """
        try:
            # Generate embedding for the summary
            summary_text = summary_data.get("summary", "")
            embedding = embed(summary_text).tolist() if summary_text else None
            
            with self.conn.cursor() as cur:
                # Set tenant context for RLS
                cur.execute("SET app.current_tenant = %s", (customer_id,))
                
                cur.execute(
                    """
                    INSERT INTO call_summaries (
                        customer_id, call_id, user_id, call_date, summary, key_topics,
                        key_variables, sentiment, duration_seconds, 
                        resolution_status, embedding
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        customer_id,
                        summary_data["call_id"],
                        summary_data["user_id"],
                        summary_data.get("call_date", datetime.now()),
                        summary_data.get("summary", ""),
                        Json(summary_data.get("key_topics", [])),
                        Json(summary_data.get("key_variables", {})),
                        summary_data.get("sentiment", "neutral"),
                        summary_data.get("duration_seconds", 0),
                        summary_data.get("resolution_status", "unknown"),
                        embedding
                    )
                )
                result = cur.fetchone()
                summary_id = result[0] if result else None
            
            logger.info(f"✅ Stored call summary {summary_data['call_id']} for user {summary_data['user_id']} [customer:{customer_id}]")
            return str(summary_id)
            
        except Exception as e:
            logger.error(f"❌ Failed to store call summary: {e}")
            raise
    
    def store_personality_metrics(self, metrics_data: Dict[str, Any], customer_id: int = 1) -> str:
        """
        Store personality metrics for a call.
        
        Args:
            metrics_data: Dictionary with user_id, call_id, and all personality scores
            customer_id: Tenant identifier for multi-tenant isolation
            
        Returns:
            UUID of the stored metrics
        """
        try:
            with self.conn.cursor() as cur:
                # Set tenant context for RLS
                cur.execute("SET app.current_tenant = %s", (customer_id,))
                
                cur.execute(
                    """
                    INSERT INTO personality_metrics (
                        customer_id, user_id, call_id, measured_at,
                        openness, conscientiousness, extraversion, agreeableness, neuroticism,
                        formality, directness, detail_orientation, patience, technical_comfort,
                        frustration_level, satisfaction_level, urgency_level
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        customer_id,
                        metrics_data["user_id"],
                        metrics_data["call_id"],
                        metrics_data.get("measured_at", datetime.now()),
                        metrics_data.get("openness", 50),
                        metrics_data.get("conscientiousness", 50),
                        metrics_data.get("extraversion", 50),
                        metrics_data.get("agreeableness", 50),
                        metrics_data.get("neuroticism", 50),
                        metrics_data.get("formality", 50),
                        metrics_data.get("directness", 50),
                        metrics_data.get("detail_orientation", 50),
                        metrics_data.get("patience", 50),
                        metrics_data.get("technical_comfort", 50),
                        metrics_data.get("frustration_level", 0),
                        metrics_data.get("satisfaction_level", 50),
                        metrics_data.get("urgency_level", 30)
                    )
                )
                result = cur.fetchone()
                metrics_id = result[0] if result else None
            
            logger.info(f"✅ Stored personality metrics for user {metrics_data['user_id']}, call {metrics_data['call_id']} [customer:{customer_id}]")
            return str(metrics_id)
            
        except Exception as e:
            logger.error(f"❌ Failed to store personality metrics: {e}")
            raise
    
    def get_or_create_caller_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Get existing caller profile or create a new one.
        
        Args:
            user_id: Caller identifier
            
        Returns:
            Caller profile dictionary
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM caller_profiles WHERE user_id = %s",
                    (user_id,)
                )
                row = cur.fetchone()
            
            if row:
                return dict(row)
            
            # Create new profile
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO caller_profiles (
                        user_id, first_call_date, last_call_date, total_calls
                    )
                    VALUES (%s, %s, %s, %s)
                    RETURNING *
                    """,
                    (user_id, datetime.now(), datetime.now(), 1)
                )
                row = cur.fetchone()
            
            logger.info(f"✅ Created new caller profile for {user_id}")
            return dict(row) if row else {}
            
        except Exception as e:
            logger.error(f"❌ Failed to get/create caller profile: {e}")
            return {}
    
    def update_caller_profile(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update caller profile information.
        
        Args:
            user_id: Caller identifier
            updates: Dictionary of fields to update (preferred_name, preferences, context)
            
        Returns:
            True if updated successfully
        """
        try:
            set_clauses = []
            params = []
            
            for key, value in updates.items():
                if key in ['preferred_name', 'preferences', 'context']:
                    set_clauses.append(f"{key} = %s")
                    params.append(Json(value) if isinstance(value, dict) else value)
            
            if not set_clauses:
                return False
            
            set_clauses.append("updated_at = NOW()")
            set_clauses.append("last_call_date = NOW()")
            set_clauses.append("total_calls = total_calls + 1")
            
            params.append(user_id)
            
            query = f"""
                UPDATE caller_profiles
                SET {', '.join(set_clauses)}
                WHERE user_id = %s
            """
            
            with self.conn.cursor() as cur:
                cur.execute(query, params)
            
            logger.info(f"✅ Updated caller profile for {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update caller profile: {e}")
            return False
    
    def get_all_caller_profiles(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all caller profiles (RLS automatically filters by customer_id).
        
        Args:
            limit: Maximum number of profiles to return
            
        Returns:
            List of caller profile dictionaries
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT 
                        user_id, 
                        preferred_name, 
                        total_calls, 
                        first_call_date, 
                        last_call_date,
                        preferences,
                        context,
                        created_at,
                        updated_at
                    FROM caller_profiles
                    ORDER BY last_call_date DESC
                    LIMIT %s
                    """,
                    (limit,)
                )
                rows = cur.fetchall()
            
            profiles = [dict(row) for row in rows]
            logger.info(f"✅ Retrieved {len(profiles)} caller profiles")
            return profiles
            
        except Exception as e:
            logger.error(f"❌ Failed to get all caller profiles: {e}")
            return []
    
    def get_personality_averages(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get personality averages for a caller.
        
        Args:
            user_id: Caller identifier
            
        Returns:
            Dictionary with averaged personality traits or None
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM personality_averages WHERE user_id = %s",
                    (user_id,)
                )
                row = cur.fetchone()
            
            return dict(row) if row else None
            
        except Exception as e:
            logger.error(f"❌ Failed to get personality averages: {e}")
            return None
    
    def search_call_summaries(self, user_id: str, query_text: str = "", limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search call summaries for a user (FAST - summaries only, not raw data).
        
        Args:
            user_id: Caller identifier
            query_text: Optional text to search for (uses vector similarity)
            limit: Maximum number of results
            
        Returns:
            List of call summary dictionaries
        """
        try:
            if query_text:
                # Vector similarity search
                query_embedding = embed(query_text).tolist()
                
                with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT call_id, call_date, summary, key_topics, key_variables,
                               sentiment, resolution_status,
                               embedding <-> %s::vector as distance
                        FROM call_summaries
                        WHERE user_id = %s
                        ORDER BY embedding <-> %s::vector
                        LIMIT %s
                        """,
                        (query_embedding, user_id, query_embedding, limit)
                    )
                    rows = cur.fetchall()
            else:
                # Recent calls
                with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT call_id, call_date, summary, key_topics, key_variables,
                               sentiment, resolution_status
                        FROM call_summaries
                        WHERE user_id = %s
                        ORDER BY call_date DESC
                        LIMIT %s
                        """,
                        (user_id, limit)
                    )
                    rows = cur.fetchall()
            
            results = [dict(row) for row in rows]
            logger.info(f"✅ Retrieved {len(results)} call summaries for user {user_id}")
            return results
            
        except Exception as e:
            logger.error(f"❌ Failed to search call summaries: {e}")
            return []
    
    def get_caller_context_for_llm(self, user_id: str) -> str:
        """
        Build optimized context string for LLM (summary-first approach).
        
        This is the NEW fast retrieval method that reads summaries instead of raw data.
        
        Args:
            user_id: Caller identifier
            
        Returns:
            Formatted string with caller profile, personality, and recent call summaries
        """
        try:
            context_parts = []
            
            # 1. Get caller profile
            profile = self.get_or_create_caller_profile(user_id)
            if profile:
                context_parts.append("=== CALLER PROFILE ===")
                if profile.get("preferred_name"):
                    context_parts.append(f"Name: {profile['preferred_name']}")
                context_parts.append(f"Total Calls: {profile.get('total_calls', 0)}")
                context_parts.append(f"First Call: {profile.get('first_call_date', 'Unknown')}")
                context_parts.append(f"Last Call: {profile.get('last_call_date', 'Unknown')}")
                
                if profile.get("preferences"):
                    context_parts.append(f"Preferences: {json.dumps(profile['preferences'])}")
                if profile.get("context"):
                    context_parts.append(f"Context: {json.dumps(profile['context'])}")
                context_parts.append("")
            
            # 2. Get personality averages
            personality = self.get_personality_averages(user_id)
            if personality:
                from app.personality import PersonalityTracker
                tracker = PersonalityTracker(None)
                context_parts.append(tracker.format_personality_summary(personality))
                context_parts.append("")
            
            # 3. Get recent call summaries
            summaries = self.search_call_summaries(user_id, limit=3)
            if summaries:
                context_parts.append("=== RECENT CALL SUMMARIES ===")
                for i, summary in enumerate(summaries, 1):
                    context_parts.append(f"\nCall {i} ({summary.get('call_date', 'Unknown')}):")
                    context_parts.append(f"  Summary: {summary.get('summary', 'N/A')}")
                    if summary.get('key_topics'):
                        context_parts.append(f"  Topics: {', '.join(summary['key_topics'])}")
                    if summary.get('key_variables'):
                        context_parts.append(f"  Key Info: {json.dumps(summary['key_variables'])}")
                    context_parts.append(f"  Sentiment: {summary.get('sentiment', 'neutral')}")
                context_parts.append("")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"❌ Failed to build caller context: {e}")
            return ""
