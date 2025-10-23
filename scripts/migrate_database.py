"""
Database Migration Script for Memory V2
Runs the SQL migration to create new tables

Usage:
    python scripts/migrate_database.py
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.memory import MemoryStore
from config_loader import get_database_url

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_migration():
    """Run the Memory V2 database migration."""
    logger.info("🚀 Starting Memory V2 database migration")
    
    memory_store = MemoryStore()
    
    try:
        # Read migration SQL
        migration_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "migrations",
            "001_add_memory_v2_tables.sql"
        )
        
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        logger.info(f"📖 Read migration file: {migration_file}")
        logger.info(f"📝 SQL length: {len(migration_sql)} characters")
        
        # Execute migration
        logger.info("⚙️ Executing migration...")
        
        with memory_store.conn.cursor() as cur:
            cur.execute(migration_sql)
        
        memory_store.conn.commit()
        
        logger.info("✅ Migration completed successfully!")
        logger.info("")
        logger.info("New tables created:")
        logger.info("  - call_summaries")
        logger.info("  - caller_profiles")
        logger.info("  - personality_metrics")
        logger.info("  - personality_averages")
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Test the new tables: python scripts/test_memory_v2.py")
        logger.info("  2. Backfill historical data: python scripts/backfill_memories.py --limit 100")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        memory_store.conn.rollback()
        raise
    finally:
        memory_store.close()

if __name__ == "__main__":
    run_migration()
