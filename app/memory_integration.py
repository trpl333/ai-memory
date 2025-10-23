"""
Memory V2 Integration Module
Hooks into conversation flow to automatically summarize calls and track personality
"""

import logging
import uuid
from typing import List, Tuple, Optional
from app.memory import MemoryStore
from app.summarizer import CallSummarizer
from app.personality import PersonalityTracker

logger = logging.getLogger(__name__)

class MemoryV2Integration:
    """
    Integrates Memory V2 into the conversation flow.
    Automatically processes calls to extract summaries and personality metrics.
    """
    
    def __init__(self, memory_store: MemoryStore, llm_chat_function):
        """
        Initialize the integration.
        
        Args:
            memory_store: MemoryStore instance with V2 methods
            llm_chat_function: LLM chat function for summarization
        """
        self.memory_store = memory_store
        self.summarizer = CallSummarizer(llm_chat_function)
        self.personality_tracker = PersonalityTracker(llm_chat_function)
    
    def process_completed_call(
        self, 
        conversation_history: List[Tuple[str, str]], 
        user_id: str,
        thread_id: Optional[str] = None
    ) -> dict:
        """
        Process a completed call - extract summary and personality metrics.
        
        This should be called AFTER a conversation ends or at strategic checkpoints.
        
        Args:
            conversation_history: List of (role, content) tuples
            user_id: Caller identifier (phone number, etc)
            thread_id: Optional thread ID (uses UUID if not provided)
            
        Returns:
            Dictionary with processing results
        """
        try:
            call_id = thread_id or str(uuid.uuid4())
            
            logger.info(f"🔄 Processing call {call_id} for user {user_id}")
            
            # Step 1: Generate call summary
            summary_data = self.summarizer.summarize_call(
                conversation_history, 
                user_id, 
                call_id
            )
            
            # Step 2: Analyze personality
            personality_data = self.personality_tracker.analyze_personality(
                conversation_history,
                user_id,
                call_id
            )
            
            # Step 3: Store in database
            summary_id = self.memory_store.store_call_summary(summary_data)
            personality_id = self.memory_store.store_personality_metrics(personality_data)
            
            # Step 4: Update caller profile
            self.memory_store.update_caller_profile(user_id, {})
            
            logger.info(f"✅ Processed call {call_id}: summary={summary_id}, personality={personality_id}")
            
            return {
                "success": True,
                "call_id": call_id,
                "summary_id": summary_id,
                "personality_id": personality_id,
                "summary": summary_data.get("summary", ""),
                "sentiment": summary_data.get("sentiment", "neutral")
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to process call: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_enriched_context_for_call(self, user_id: str) -> str:
        """
        Get enriched context for starting a new call.
        
        This is the FAST retrieval method that uses summaries instead of raw data.
        
        Args:
            user_id: Caller identifier
            
        Returns:
            Formatted context string for LLM prompt
        """
        try:
            context = self.memory_store.get_caller_context_for_llm(user_id)
            return context if context else "No previous call history found."
            
        except Exception as e:
            logger.error(f"❌ Failed to get enriched context: {e}")
            return ""
    
    def should_process_call(self, message_count: int) -> bool:
        """
        Determine if we should process the call now.
        
        Triggers:
        - Every 10 messages (for long calls)
        - At end of call
        
        Args:
            message_count: Number of messages in current conversation
            
        Returns:
            True if should process now
        """
        # Process every 10 messages for long ongoing calls
        return message_count > 0 and message_count % 10 == 0
