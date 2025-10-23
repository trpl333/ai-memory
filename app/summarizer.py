"""
Call Summarizer Module
Extracts summaries, key variables, and sentiment from conversations
"""

import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import re

logger = logging.getLogger(__name__)

class CallSummarizer:
    """
    Extracts structured summaries from call transcripts.
    Uses LLM to generate concise summaries and extract key information.
    """
    
    def __init__(self, llm_chat_function):
        """
        Initialize the summarizer with an LLM chat function.
        
        Args:
            llm_chat_function: Function that takes messages and returns LLM response
        """
        self.llm_chat = llm_chat_function
    
    def summarize_call(self, conversation_history: List[Tuple[str, str]], user_id: str, call_id: str) -> Dict[str, Any]:
        """
        Generate comprehensive summary of a call.
        
        Args:
            conversation_history: List of (role, content) tuples
            user_id: Identifier for the caller
            call_id: Unique call identifier
            
        Returns:
            Dictionary with summary, key_topics, key_variables, sentiment, etc.
        """
        try:
            # Build conversation transcript
            transcript = self._build_transcript(conversation_history)
            
            # Generate summary using LLM
            summary_data = self._extract_summary_with_llm(transcript)
            
            # Calculate duration (estimate based on message count)
            duration_seconds = self._estimate_duration(conversation_history)
            
            result = {
                "call_id": call_id,
                "user_id": user_id,
                "call_date": datetime.now(),
                "summary": summary_data.get("summary", ""),
                "key_topics": summary_data.get("key_topics", []),
                "key_variables": summary_data.get("key_variables", {}),
                "sentiment": summary_data.get("sentiment", "neutral"),
                "resolution_status": summary_data.get("resolution_status", "unknown"),
                "duration_seconds": duration_seconds
            }
            
            logger.info(f"✅ Summarized call {call_id} for user {user_id}: {len(summary_data.get('summary', ''))} chars")
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to summarize call {call_id}: {e}", exc_info=True)
            return self._create_fallback_summary(conversation_history, user_id, call_id)
    
    def _build_transcript(self, conversation_history: List[Tuple[str, str]]) -> str:
        """Build readable transcript from conversation history."""
        lines = []
        for role, content in conversation_history:
            speaker = "User" if role == "user" else "Assistant"
            lines.append(f"{speaker}: {content}")
        return "\n".join(lines)
    
    def _extract_summary_with_llm(self, transcript: str) -> Dict[str, Any]:
        """
        Use LLM to extract structured summary from transcript.
        
        Returns:
            {
                "summary": "Brief 2-3 sentence summary",
                "key_topics": ["topic1", "topic2"],
                "key_variables": {"var_name": "value"},
                "sentiment": "positive/neutral/negative/frustrated/satisfied",
                "resolution_status": "resolved/pending/escalated"
            }
        """
        prompt = f"""Analyze this conversation and extract structured information.

CONVERSATION:
{transcript}

Extract the following in JSON format:
1. summary: A brief 2-3 sentence summary of what was discussed
2. key_topics: List of main topics discussed (e.g., ["billing", "technical_support"])
3. key_variables: Important details mentioned (e.g., {{"account_id": "12345", "issue_type": "billing error"}})
4. sentiment: Overall caller sentiment (positive, neutral, negative, frustrated, satisfied)
5. resolution_status: Was issue resolved? (resolved, pending, escalated, unknown)

Respond ONLY with valid JSON, no other text:"""

        try:
            messages = [
                {"role": "system", "content": "You are a conversation analysis expert. Extract structured information from conversations."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.llm_chat(messages, temperature=0.3, max_tokens=500)
            
            # Parse JSON response
            response_text = response.get("content", "{}")
            # Remove markdown code blocks if present
            response_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
            
            data = json.loads(response_text)
            
            # Validate and set defaults
            return {
                "summary": data.get("summary", "Call summary unavailable"),
                "key_topics": data.get("key_topics", []),
                "key_variables": data.get("key_variables", {}),
                "sentiment": data.get("sentiment", "neutral"),
                "resolution_status": data.get("resolution_status", "unknown")
            }
            
        except Exception as e:
            logger.error(f"LLM summary extraction failed: {e}")
            return self._fallback_extraction(transcript)
    
    def _fallback_extraction(self, transcript: str) -> Dict[str, Any]:
        """Simple rule-based extraction when LLM fails."""
        summary = transcript[:200] + "..." if len(transcript) > 200 else transcript
        
        # Detect sentiment from keywords
        sentiment = "neutral"
        frustrated_words = ["frustrated", "angry", "upset", "annoyed", "problem", "issue", "broken"]
        satisfied_words = ["thank", "great", "perfect", "resolved", "fixed", "appreciate"]
        
        lower_transcript = transcript.lower()
        if any(word in lower_transcript for word in frustrated_words):
            sentiment = "frustrated"
        elif any(word in lower_transcript for word in satisfied_words):
            sentiment = "satisfied"
        
        return {
            "summary": f"Conversation summary: {summary}",
            "key_topics": [],
            "key_variables": {},
            "sentiment": sentiment,
            "resolution_status": "unknown"
        }
    
    def _estimate_duration(self, conversation_history: List[Tuple[str, str]]) -> int:
        """Estimate call duration based on message count and length."""
        total_chars = sum(len(content) for _, content in conversation_history)
        # Rough estimate: 150 words per minute, 5 chars per word
        words = total_chars / 5
        minutes = words / 150
        return int(minutes * 60)
    
    def _create_fallback_summary(self, conversation_history: List[Tuple[str, str]], user_id: str, call_id: str) -> Dict[str, Any]:
        """Create basic summary when extraction fails."""
        return {
            "call_id": call_id,
            "user_id": user_id,
            "call_date": datetime.now(),
            "summary": f"Call with {len(conversation_history)} messages",
            "key_topics": [],
            "key_variables": {},
            "sentiment": "neutral",
            "resolution_status": "unknown",
            "duration_seconds": self._estimate_duration(conversation_history)
        }
