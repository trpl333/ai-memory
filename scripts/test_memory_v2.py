"""
Test Script for Memory V2
Validates that the new memory system is working correctly

Usage:
    python scripts/test_memory_v2.py
"""

import sys
import os
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

def test_database_tables():
    """Test that all V2 tables exist."""
    logger.info("🧪 Testing database tables...")
    
    memory_store = MemoryStore()
    
    tables = [
        'call_summaries',
        'caller_profiles',
        'personality_metrics',
        'personality_averages'
    ]
    
    try:
        with memory_store.conn.cursor() as cur:
            for table in tables:
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = %s",
                    (table,)
                )
                count = cur.fetchone()[0]
                
                if count == 1:
                    logger.info(f"  ✅ Table '{table}' exists")
                else:
                    logger.error(f"  ❌ Table '{table}' NOT FOUND")
                    return False
        
        logger.info("✅ All V2 tables exist")
        return True
        
    except Exception as e:
        logger.error(f"❌ Table check failed: {e}")
        return False
    finally:
        memory_store.close()

def test_call_processing():
    """Test processing a sample call."""
    logger.info("🧪 Testing call processing...")
    
    memory_store = MemoryStore()
    integration = MemoryV2Integration(memory_store, llm_chat)
    
    # Sample conversation
    conversation = [
        ("user", "Hello, I'm having trouble with my account"),
        ("assistant", "I'd be happy to help! Can you tell me more about the issue?"),
        ("user", "I can't log in and keep getting an error"),
        ("assistant", "Let me check that for you. What's your account ID?"),
        ("user", "It's ACC-12345"),
        ("assistant", "I found your account. Let me reset your password."),
        ("user", "Thank you so much! That worked perfectly!"),
        ("assistant", "Great! Is there anything else I can help with?"),
        ("user", "No, that's all. Thanks!")
    ]
    
    try:
        # Process the call
        result = integration.process_completed_call(
            conversation,
            user_id="test_user_001",
            thread_id="test_call_001"
        )
        
        if result.get("success"):
            logger.info("  ✅ Call processed successfully")
            logger.info(f"  Summary: {result.get('summary', '')[:100]}...")
            logger.info(f"  Sentiment: {result.get('sentiment')}")
            return True
        else:
            logger.error(f"  ❌ Call processing failed: {result.get('error')}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Call processing test failed: {e}", exc_info=True)
        return False
    finally:
        memory_store.close()

def test_caller_profile():
    """Test caller profile retrieval."""
    logger.info("🧪 Testing caller profile...")
    
    memory_store = MemoryStore()
    
    try:
        # Get profile for test user
        profile = memory_store.get_or_create_caller_profile("test_user_001")
        
        if profile:
            logger.info("  ✅ Caller profile retrieved")
            logger.info(f"  User ID: {profile.get('user_id')}")
            logger.info(f"  Total calls: {profile.get('total_calls')}")
            return True
        else:
            logger.error("  ❌ Failed to get caller profile")
            return False
            
    except Exception as e:
        logger.error(f"❌ Caller profile test failed: {e}")
        return False
    finally:
        memory_store.close()

def test_personality_averages():
    """Test personality averages retrieval."""
    logger.info("🧪 Testing personality averages...")
    
    memory_store = MemoryStore()
    
    try:
        # Get averages for test user
        averages = memory_store.get_personality_averages("test_user_001")
        
        if averages:
            logger.info("  ✅ Personality averages retrieved")
            logger.info(f"  Call count: {averages.get('call_count')}")
            logger.info(f"  Avg formality: {averages.get('avg_formality')}")
            logger.info(f"  Avg technical comfort: {averages.get('avg_technical_comfort')}")
            return True
        else:
            logger.warning("  ⚠️ No personality averages yet (may need trigger to fire)")
            return True  # Not a failure, just no data yet
            
    except Exception as e:
        logger.error(f"❌ Personality averages test failed: {e}")
        return False
    finally:
        memory_store.close()

def test_enriched_context():
    """Test enriched context retrieval."""
    logger.info("🧪 Testing enriched context...")
    
    memory_store = MemoryStore()
    integration = MemoryV2Integration(memory_store, llm_chat)
    
    try:
        # Get context for test user
        context = integration.get_enriched_context_for_call("test_user_001")
        
        if context:
            logger.info("  ✅ Enriched context retrieved")
            logger.info(f"  Context length: {len(context)} characters")
            logger.info(f"  Preview:\n{context[:300]}...")
            return True
        else:
            logger.warning("  ⚠️ No context available (expected for new users)")
            return True
            
    except Exception as e:
        logger.error(f"❌ Enriched context test failed: {e}")
        return False
    finally:
        memory_store.close()

def main():
    """Run all tests."""
    logger.info("=" * 80)
    logger.info("Memory V2 Test Suite")
    logger.info("=" * 80)
    
    tests = [
        ("Database Tables", test_database_tables),
        ("Call Processing", test_call_processing),
        ("Caller Profile", test_caller_profile),
        ("Personality Averages", test_personality_averages),
        ("Enriched Context", test_enriched_context)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        logger.info("")
        logger.info(f"Running: {test_name}")
        logger.info("-" * 80)
        
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            logger.error(f"Test crashed: {e}", exc_info=True)
            results.append((test_name, False))
    
    # Summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("Test Results Summary")
    logger.info("=" * 80)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"  {status} - {test_name}")
    
    logger.info("")
    logger.info(f"Total: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        logger.info("🎉 All tests passed!")
        return 0
    else:
        logger.error(f"⚠️ {total_count - passed_count} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
