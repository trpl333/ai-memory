"""
Personality Tracker Module
Measures and tracks personality traits and communication styles
"""

import json
import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class PersonalityTracker:
    """
    Analyzes conversation to extract personality traits and communication style.
    Tracks both per-call metrics and running averages.
    """
    
    def __init__(self, llm_chat_function):
        """
        Initialize the personality tracker with an LLM chat function.
        
        Args:
            llm_chat_function: Function that takes messages and returns LLM response
        """
        self.llm_chat = llm_chat_function
    
    def analyze_personality(self, conversation_history: List[Tuple[str, str]], user_id: str, call_id: str) -> Dict[str, Any]:
        """
        Analyze personality traits from conversation.
        
        Args:
            conversation_history: List of (role, content) tuples
            user_id: Identifier for the caller
            call_id: Unique call identifier
            
        Returns:
            Dictionary with personality metrics (all values 0-100)
        """
        try:
            # Extract only user messages for personality analysis
            user_messages = [content for role, content in conversation_history if role == "user"]
            
            if not user_messages:
                return self._create_neutral_profile(user_id, call_id)
            
            # Analyze with LLM
            personality_data = self._extract_personality_with_llm(user_messages)
            
            result = {
                "user_id": user_id,
                "call_id": call_id,
                "measured_at": datetime.now(),
                
                # Big 5
                "openness": personality_data.get("openness", 50),
                "conscientiousness": personality_data.get("conscientiousness", 50),
                "extraversion": personality_data.get("extraversion", 50),
                "agreeableness": personality_data.get("agreeableness", 50),
                "neuroticism": personality_data.get("neuroticism", 50),
                
                # Communication style
                "formality": personality_data.get("formality", 50),
                "directness": personality_data.get("directness", 50),
                "detail_orientation": personality_data.get("detail_orientation", 50),
                "patience": personality_data.get("patience", 50),
                "technical_comfort": personality_data.get("technical_comfort", 50),
                
                # Emotional state
                "frustration_level": personality_data.get("frustration_level", 0),
                "satisfaction_level": personality_data.get("satisfaction_level", 50),
                "urgency_level": personality_data.get("urgency_level", 30)
            }
            
            logger.info(f"✅ Analyzed personality for user {user_id}: extraversion={result['extraversion']}, formality={result['formality']}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to analyze personality for call {call_id}: {e}", exc_info=True)
            return self._create_neutral_profile(user_id, call_id)
    
    def _extract_personality_with_llm(self, user_messages: List[str]) -> Dict[str, float]:
        """
        Use LLM to extract personality metrics from user messages.
        
        Returns metrics on 0-100 scale.
        """
        # Combine messages for analysis
        combined_text = "\n".join(user_messages)
        
        prompt = f"""Analyze the personality and communication style from these messages.

USER MESSAGES:
{combined_text}

Rate the following traits on a scale of 0-100:

BIG 5 PERSONALITY:
- openness: How curious, creative, open to new experiences (0=traditional, 100=very open)
- conscientiousness: How organized, dependable, disciplined (0=spontaneous, 100=very organized)
- extraversion: How sociable, assertive, energetic (0=introverted, 100=extraverted)
- agreeableness: How cooperative, empathetic, trusting (0=competitive, 100=very agreeable)
- neuroticism: Emotional reactivity (0=very stable, 100=highly reactive)

COMMUNICATION STYLE:
- formality: Communication formality (0=very casual, 100=very formal)
- directness: How direct they communicate (0=very indirect, 100=very direct)
- detail_orientation: Level of detail (0=high-level only, 100=very detailed)
- patience: Patience level (0=very impatient, 100=very patient)
- technical_comfort: Comfort with technical topics (0=non-technical, 100=very technical)

EMOTIONAL STATE (THIS CALL):
- frustration_level: Current frustration (0=none, 100=extremely frustrated)
- satisfaction_level: Current satisfaction (0=very unsatisfied, 100=very satisfied)
- urgency_level: Urgency/time pressure (0=no rush, 100=extremely urgent)

Respond ONLY with valid JSON mapping trait names to numbers 0-100:"""

        try:
            messages = [
                {"role": "system", "content": "You are a personality analysis expert. Provide objective ratings based on observable communication patterns."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.llm_chat(messages, temperature=0.2, max_tokens=400)
            
            # Parse JSON response
            response_text = response.get("content", "{}")
            # Remove markdown code blocks if present
            response_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
            
            data = json.loads(response_text)
            
            # Validate all values are 0-100
            validated_data = {}
            for key, value in data.items():
                try:
                    num_value = float(value)
                    validated_data[key] = max(0, min(100, num_value))  # Clamp to 0-100
                except (ValueError, TypeError):
                    validated_data[key] = 50  # Default to neutral
            
            return validated_data
            
        except Exception as e:
            logger.error(f"LLM personality extraction failed: {e}")
            return self._fallback_personality_analysis(user_messages)
    
    def _fallback_personality_analysis(self, user_messages: List[str]) -> Dict[str, float]:
        """Simple rule-based personality analysis when LLM fails."""
        combined_text = " ".join(user_messages).lower()
        
        # Simple heuristics
        metrics = {
            "openness": 50,
            "conscientiousness": 50,
            "extraversion": 50,
            "agreeableness": 50,
            "neuroticism": 50,
            "formality": 50,
            "directness": 50,
            "detail_orientation": 50,
            "patience": 50,
            "technical_comfort": 50,
            "frustration_level": 0,
            "satisfaction_level": 50,
            "urgency_level": 30
        }
        
        # Detect formality
        formal_words = ["please", "thank you", "kindly", "appreciate", "sincerely"]
        casual_words = ["yeah", "yep", "gonna", "wanna", "hey"]
        formal_count = sum(1 for word in formal_words if word in combined_text)
        casual_count = sum(1 for word in casual_words if word in combined_text)
        metrics["formality"] = 60 if formal_count > casual_count else 40
        
        # Detect frustration
        frustrated_words = ["frustrated", "angry", "upset", "annoyed", "terrible", "awful", "broken"]
        frustration_count = sum(1 for word in frustrated_words if word in combined_text)
        metrics["frustration_level"] = min(100, frustration_count * 25)
        
        # Detect satisfaction
        satisfied_words = ["great", "perfect", "excellent", "thank", "appreciate", "wonderful"]
        satisfaction_count = sum(1 for word in satisfied_words if word in combined_text)
        metrics["satisfaction_level"] = min(100, 50 + satisfaction_count * 15)
        
        # Detect urgency
        urgent_words = ["urgent", "asap", "immediately", "now", "quickly", "hurry"]
        urgency_count = sum(1 for word in urgent_words if word in combined_text)
        metrics["urgency_level"] = min(100, 30 + urgency_count * 20)
        
        # Detect directness
        metrics["directness"] = 70 if len(combined_text) < 200 else 50
        
        # Detect technical comfort
        technical_words = ["api", "database", "server", "code", "technical", "system", "configure"]
        technical_count = sum(1 for word in technical_words if word in combined_text)
        metrics["technical_comfort"] = min(100, 40 + technical_count * 15)
        
        return metrics
    
    def _create_neutral_profile(self, user_id: str, call_id: str) -> Dict[str, Any]:
        """Create neutral personality profile when analysis fails."""
        return {
            "user_id": user_id,
            "call_id": call_id,
            "measured_at": datetime.now(),
            "openness": 50,
            "conscientiousness": 50,
            "extraversion": 50,
            "agreeableness": 50,
            "neuroticism": 50,
            "formality": 50,
            "directness": 50,
            "detail_orientation": 50,
            "patience": 50,
            "technical_comfort": 50,
            "frustration_level": 0,
            "satisfaction_level": 50,
            "urgency_level": 30
        }
    
    def format_personality_summary(self, averages: Dict[str, Any]) -> str:
        """
        Format personality averages into human-readable summary for LLM context.
        
        Args:
            averages: Dict from personality_averages table
            
        Returns:
            Formatted string for LLM prompt
        """
        def score_to_label(score: float, low_label: str, high_label: str) -> str:
            if score < 35:
                return f"very {low_label}"
            elif score < 45:
                return low_label
            elif score < 55:
                return "neutral"
            elif score < 65:
                return high_label
            else:
                return f"very {high_label}"
        
        lines = [
            "CALLER PERSONALITY PROFILE:",
            f"Communication Style: {score_to_label(averages.get('avg_formality', 50), 'casual', 'formal')}",
            f"Directness: {score_to_label(averages.get('avg_directness', 50), 'indirect', 'direct')}",
            f"Technical Level: {score_to_label(averages.get('avg_technical_comfort', 50), 'non-technical', 'technical')}",
            f"Detail Preference: {score_to_label(averages.get('avg_detail_orientation', 50), 'high-level', 'detailed')}",
            f"Patience: {score_to_label(averages.get('avg_patience', 50), 'impatient', 'patient')}",
            f"Recent Satisfaction: {score_to_label(averages.get('recent_satisfaction', 50), 'low', 'high')}"
        ]
        
        if averages.get('satisfaction_trend'):
            lines.append(f"Trend: Satisfaction is {averages['satisfaction_trend']}")
        
        return "\n".join(lines)
