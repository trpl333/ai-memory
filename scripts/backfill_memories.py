"""
Backfill Script for Memory V2
Processes historical memories (5,755+ records) to generate summaries and personality data

Usage:
    python scripts/backfill_memories.py --limit 100 --batch-size 10
"""

import sys
import os
import argparse
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.memory import MemoryStore
from app.llm import chat as llm_chat
from app.memory_integration import MemoryV2Integration

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def extract_conversation_from_memory(memory_value: dict) -> list:
    """
    Extract conversation history from a memory record.
    
    Args:
        memory_value: The value_json field from memories table
        
    Returns:
        List of (role, content) tuples
    """
    # Handle different memory formats
    if isinstance(memory_value, dict):
        if "messages" in memory_value:
            # Thread history format
            messages = memory_value["messages"]
            return [(msg["role"], msg["content"]) for msg in messages]
        elif "content" in memory_value:
            # Single message format
            return [("user", memory_value.get("content", ""))]
    
    return []

def backfill_memories(limit: int = None, batch_size: int = 10, skip: int = 0):
    """
    Backfill historical memories with summaries and personality data.
    
    Args:
        limit: Maximum number of memories to process (None = all)
        batch_size: Number of memories to process before committing
        skip: Number of memories to skip (for resuming)
    """
    logger.info("🚀 Starting Memory V2 backfill process")
    logger.info(f"Parameters: limit={limit}, batch_size={batch_size}, skip={skip}")
    
    # Initialize
    memory_store = MemoryStore()
    integration = MemoryV2Integration(memory_store, llm_chat)
    
    # Get all memories
    try:
        with memory_store.conn.cursor() as cur:
            query = "SELECT id, type, k, value_json, user_id, created_at FROM memories ORDER BY created_at DESC"
            if limit:
                query += f" LIMIT {limit} OFFSET {skip}"
            
            cur.execute(query)
            all_memories = cur.fetchall()
        
        total = len(all_memories)
        logger.info(f"📊 Found {total} memories to process")
        
        processed = 0
        skipped = 0
        failed = 0
        
        for i, memory_row in enumerate(all_memories, 1):
            memory_id, memory_type, key, value, user_id, created_at = memory_row
            
            try:
                # Skip if not a conversation memory
                if memory_type not in ["moment", "thread_history"]:
                    skipped += 1
                    continue
                
                # Extract conversation
                conversation = extract_conversation_from_memory(value)
                if not conversation or len(conversation) < 2:
                    skipped += 1
                    continue
                
                # Generate call_id from memory
                call_id = f"backfill_{memory_id}"
                
                # Process the conversation
                logger.info(f"Processing {i}/{total}: memory_id={memory_id}, user={user_id}, messages={len(conversation)}")
                
                result = integration.process_completed_call(
                    conversation,
                    user_id or "unknown",
                    call_id
                )
                
                if result.get("success"):
                    processed += 1
                    logger.info(f"✅ {i}/{total} - Processed: {result.get('summary', '')[:100]}...")
                else:
                    failed += 1
                    logger.error(f"❌ {i}/{total} - Failed: {result.get('error')}")
                
                # Progress report every batch
                if i % batch_size == 0:
                    logger.info(f"📈 Progress: {i}/{total} | ✅ {processed} | ⏭️ {skipped} | ❌ {failed}")
                
            except Exception as e:
                failed += 1
                logger.error(f"❌ Error processing memory {memory_id}: {e}", exc_info=True)
        
        # Final report
        logger.info("=" * 80)
        logger.info(f"🎉 Backfill complete!")
        logger.info(f"Total memories: {total}")
        logger.info(f"✅ Processed: {processed}")
        logger.info(f"⏭️ Skipped: {skipped}")
        logger.info(f"❌ Failed: {failed}")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ Backfill failed: {e}", exc_info=True)
    finally:
        memory_store.close()

def main():
    parser = argparse.ArgumentParser(description="Backfill Memory V2 summaries and personality data")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of memories to process")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for processing")
    parser.add_argument("--skip", type=int, default=0, help="Number of memories to skip (for resuming)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to database")
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No data will be written")
    
    backfill_memories(
        limit=args.limit,
        batch_size=args.batch_size,
        skip=args.skip
    )

if __name__ == "__main__":
    main()
