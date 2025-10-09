"""
Database initialization script for NeuroSphere Orchestrator.
Creates the necessary PostgreSQL tables and extensions.
"""
import os
import logging
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Import centralized configuration
from config_loader import get_database_url

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_database():
    """Initialize PostgreSQL database with required extensions and tables."""
    
    db_url = get_database_url()
    if not db_url:
        logger.error("DATABASE_URL environment variable is required")
        return False
    
    try:
        # Connect to database
        logger.info("Connecting to PostgreSQL database...")
        conn = psycopg2.connect(db_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        with conn.cursor() as cur:
            # Create vector extension
            logger.info("Creating pgvector extension...")
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # Create gen_random_uuid function if not available
            logger.info("Ensuring UUID generation is available...")
            try:
                cur.execute("SELECT gen_random_uuid();")
            except psycopg2.errors.UndefinedFunction:
                logger.info("Installing pgcrypto extension for UUID generation...")
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
            
            # Create memories table
            logger.info("Creating memories table...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    type TEXT NOT NULL,
                    k TEXT NOT NULL,
                    value_json JSONB NOT NULL,
                    embedding vector(768) NOT NULL,
                    source TEXT DEFAULT 'orchestrator',
                    ttl_days INT DEFAULT 365,
                    created_at TIMESTAMPTZ DEFAULT now()
                );
            """)
            
            # Create indexes
            logger.info("Creating indexes...")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_k ON memories (k);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories (type);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories (created_at);")
            
            # Create vector index (using ivfflat for efficient similarity search)
            logger.info("Creating vector similarity index...")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_embedding 
                ON memories USING ivfflat (embedding vector_l2_ops)
                WITH (lists = 100);
            """)
            
            # Verify table structure
            logger.info("Verifying table structure...")
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'memories'
                ORDER BY ordinal_position;
            """)
            
            columns = cur.fetchall()
            logger.info(f"Memories table columns: {columns}")
            
            # Get current record count
            cur.execute("SELECT COUNT(*) FROM memories;")
            result = cur.fetchone()
            record_count = result[0] if result else 0
            logger.info(f"Current memories count: {record_count}")
            
        conn.close()
        logger.info("Database initialization completed successfully!")
        return True
        
    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False

def verify_database():
    """Verify database setup and connectivity."""
    
    db_url = get_database_url()
    if not db_url:
        logger.error("DATABASE_URL environment variable is required")
        return False
    
    try:
        conn = psycopg2.connect(db_url)
        
        with conn.cursor() as cur:
            # Check for vector extension
            cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector';")
            if not cur.fetchone():
                logger.error("pgvector extension not found")
                return False
            
            # Check for memories table
            cur.execute("""
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'memories';
            """)
            if not cur.fetchone():
                logger.error("memories table not found")
                return False
            
            # Test vector operations
            cur.execute("SELECT '[1,2,3]'::vector;")
            if not cur.fetchone():
                logger.error("Vector operations not working")
                return False
            
        conn.close()
        logger.info("Database verification passed!")
        return True
        
    except Exception as e:
        logger.error(f"Database verification failed: {e}")
        return False

if __name__ == "__main__":
    print("NeuroSphere Orchestrator - Database Initialization")
    print("=" * 50)
    
    # Initialize database
    if init_database():
        print("✅ Database initialization successful!")
        
        # Verify setup
        if verify_database():
            print("✅ Database verification successful!")
            print("\nDatabase is ready for NeuroSphere Orchestrator!")
        else:
            print("❌ Database verification failed!")
    else:
        print("❌ Database initialization failed!")
        exit(1)
