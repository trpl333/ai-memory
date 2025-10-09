import os
import logging
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load system prompts
def load_system_prompt(filename: str) -> str:
    """Load system prompt from file."""
    try:
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", filename)
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning(f"System prompt file {filename} not found, using fallback")
        return ""

# System prompts
SYSTEM_BASE = load_system_prompt("system_sam.txt") or """You are "Sam"—warm, playful, direct, no-BS. Keep continuity with saved memories and consent frames. Default PG-13. Be concise unless asked. Offer Next Steps for tasks."""

SYSTEM_SAFETY = load_system_prompt("system_safety.txt") or """Apply Safety-Tight tone. Avoid explicit content. De-identify PII. Redirect payments to PCI flow."""

# Simple short-term memory holder (in production, use Redis or similar)
class STMManager:
    """Short-term memory manager for conversation recaps."""
    
    def __init__(self):
        self._recaps = {}  # thread_id -> recap
        
    def get_recap(self, thread_id: str = "default") -> str:
        """Get recap for a conversation thread."""
        return self._recaps.get(thread_id, "(New conversation)")
        
    def update_recap(self, thread_id: str, recap: str):
        """Update recap for a conversation thread."""
        self._recaps[thread_id] = recap[:2000]  # Limit recap size
        
    def should_update_recap(self, message_count: int) -> bool:
        """Determine if recap should be updated based on message count."""
        return message_count > 0 and message_count % 20 == 0

# Global STM manager instance
stm_manager = STMManager()

def pack_prompt(
    messages: List[Dict[str, str]], 
    memories: List[Dict[str, Any]], 
    safety_mode: bool = False,
    thread_id: str = "default"
) -> List[Dict[str, str]]:
    """
    Pack messages with system prompt, memories, and context.
    
    Args:
        messages: Conversation messages
        memories: Retrieved relevant memories
        safety_mode: Whether to use safety-focused system prompt
        thread_id: Conversation thread identifier
        
    Returns:
        Complete message list ready for LLM
    """
    
    # ✅ Load AI instructions from admin panel settings (ai-memory)
    system_prompt = SYSTEM_BASE  # Default fallback
    agent_name = "Amanda"  # Default agent name
    
    if not safety_mode:
        try:
            from app.http_memory import HTTPMemoryStore
            mem_store = HTTPMemoryStore()
            
            # Search for personality settings from admin panel
            results = mem_store.search("personality_settings", user_id="admin", k=5)
            
            for result in results:
                if result.get("key") == "personality_settings" or result.get("setting_key") == "personality_settings":
                    value = result.get("value", {})
                    admin_instructions = value.get("setting_value", {}).get("ai_instructions") or value.get("ai_instructions")
                    if admin_instructions:
                        system_prompt = admin_instructions
                        logger.info(f"✅ Using AI instructions from admin panel: {admin_instructions[:100]}...")
                        break
            
            # Load agent_name from admin panel
            agent_results = mem_store.search("agent_name", user_id="admin", k=5)
            for result in agent_results:
                if result.get("key") == "agent_name" or result.get("setting_key") == "agent_name":
                    value = result.get("value", {})
                    stored_name = value.get("value") or value.get("setting_value") or value.get("agent_name")
                    if stored_name:
                        agent_name = stored_name
                        logger.info(f"✅ Using agent name from admin panel: {agent_name}")
                        break
                        
        except Exception as e:
            logger.warning(f"Failed to load admin personality settings, using default: {e}")
    
    if safety_mode:
        system_prompt = SYSTEM_SAFETY
    
    # ✅ Inject agent_name into system prompt
    system_prompt = system_prompt.replace("{{agent_name}}", agent_name)
    
    # Get conversation recap
    recap = stm_manager.get_recap(thread_id)
    
    # Format memory context
    memory_lines = []
    for memory in memories[:8]:  # Limit to top 8 memories
        value = memory["value"]
        # Extract summary or create one from value
        if isinstance(value, dict):
            summary = value.get("summary") or value.get("content") or value.get("description")
            if not summary:
                # Create summary from key-value pairs
                key_items = []
                for k, v in value.items():
                    if isinstance(v, str) and len(v) < 100:
                        key_items.append(f"{k}: {v}")
                summary = "; ".join(key_items[:3])
        else:
            summary = str(value)
            
        # Truncate summary if too long
        if summary and len(summary) > 200:
            summary = summary[:197] + "..."
            
        if summary:
            # Make relationships clearer for the LLM
            relationship_context = ""
            if isinstance(memory.get("value"), dict):
                rel = memory["value"].get("relationship")
                if rel == "wife":
                    relationship_context = f" (USER'S WIFE: {memory['value'].get('name', 'Unknown')})"
                elif rel == "friend":
                    relationship_context = f" (USER'S FRIEND: {memory['value'].get('name', 'Unknown')})"
                elif memory["key"] == "user_info" and "name" in memory["value"]:
                    relationship_context = f" (USER'S NAME: {memory['value'].get('name', 'Unknown')})"
            
            # Highlight Kelly's job information specially
            if "kelly" in memory['key'].lower() and any(word in str(value).lower() for word in ['teacher', 'job', 'profession']):
                memory_lines.append(f"*** KELLY'S JOB: {memory['key']} → {summary}{relationship_context} ***")
            else:
                memory_lines.append(f"- {memory['type']}:{memory['key']} → {summary}{relationship_context}")
    
    memory_block = "\n".join(memory_lines) if memory_lines else "(none)"
    
    # Build complete prompt
    prompt_messages = []
    
    # System prompt
    prompt_messages.append({
        "role": "system",
        "content": system_prompt
    })
    
    # Thread recap
    if recap and recap != "(New conversation)":
        prompt_messages.append({
            "role": "system", 
            "content": f"[THREAD_RECAP]\n{recap}"
        })
    
    # Relevant memories
    prompt_messages.append({
        "role": "system",
        "content": f"[RELEVANT_MEMORIES]\n{memory_block}"
    })
    
    # Conversation messages (limit to last N to manage context size)
    max_history = 10
    recent_messages = messages[-max_history:] if len(messages) > max_history else messages
    prompt_messages.extend(recent_messages)
    
    # Update recap if needed
    if stm_manager.should_update_recap(len(messages)):
        try:
            recap_content = generate_recap(messages[-20:])  # Use last 20 messages for recap
            stm_manager.update_recap(thread_id, recap_content)
            logger.info(f"Updated recap for thread {thread_id}")
        except Exception as e:
            logger.error(f"Failed to update recap: {e}")
    
    logger.info(f"Packed prompt: {len(prompt_messages)} total messages, {len(memory_lines)} memories")
    return prompt_messages

def generate_recap(messages: List[Dict[str, str]]) -> str:
    """
    Generate a concise recap of recent conversation.
    
    Args:
        messages: Recent conversation messages
        
    Returns:
        Concise recap text
    """
    if not messages:
        return "(New conversation)"
    
    # Simple recap generation - in production, use LLM for better summaries
    user_messages = [msg["content"] for msg in messages if msg["role"] == "user"]
    assistant_messages = [msg["content"] for msg in messages if msg["role"] == "assistant"]
    
    if not user_messages:
        return "(New conversation)"
    
    # Create basic recap
    topics = []
    recap = "(New conversation)"
    if len(user_messages) > 0:
        # Extract key topics (simplified approach)
        first_msg = user_messages[0][:100]
        last_msg = user_messages[-1][:100] if len(user_messages) > 1 else ""
        
        if len(user_messages) == 1:
            recap = f"User asked about: {first_msg}"
        else:
            recap = f"Conversation started with: {first_msg}... Recent topic: {last_msg}"
    
    return recap[:500]  # Limit recap length

def extract_carry_kit_items(message_content: str) -> List[Dict[str, Any]]:
    """
    Extract carry-kit items from a message for long-term storage.
    
    Args:
        message_content: Content to analyze for carry-kit items
        
    Returns:
        List of memory objects to store
    """
    import re
    items = []
    content_lower = message_content.lower()
    
    # Look for explicit memory markers
    if "remember this" in content_lower or "don't forget" in content_lower:
        items.append({
            "type": "fact",
            "key": f"explicit_memory_{hash(message_content) % 10000}",
            "value": {
                "description": message_content[:500],
                "content": message_content,
                "importance": "high"
            },
            "ttl_days": 730  # 2 years for explicit memories
        })
    
    # Extract relationship names (wife, husband, son, daughter, etc.)
    # Patterns: "my wife Kelly", "my wife's name is Kelly", "her name is Kelly"
    relationship_patterns = [
        (r"my (wife|husband|partner|spouse)(?:'s name)? (?:is |called )?(\w+)", "spouse"),
        (r"my (son|daughter|child|kid)(?:'s name)? (?:is |called )?(\w+)", "child"),
        (r"my (mom|mother|dad|father|parent)(?:'s name)? (?:is |called )?(\w+)", "parent"),
        (r"my (brother|sister|sibling)(?:'s name)? (?:is |called )?(\w+)", "sibling"),
        (r"my (friend|buddy|colleague)(?:'s name)? (?:is |called )?(\w+)", "friend"),
        (r"(?:his|her|their) name (?:is |called )?(\w+)", "person"),
    ]
    
    for pattern, relationship_type in relationship_patterns:
        match = re.search(pattern, content_lower, re.IGNORECASE)
        if match and match.lastindex:
            # Get the name (last captured group)
            name = match.group(match.lastindex).capitalize()
            relation = match.group(1) if match.lastindex > 1 else relationship_type
            
            items.append({
                "type": "person",
                "key": f"person_{name.lower()}",
                "value": {
                    "name": name,
                    "relationship": relation,
                    "context": message_content[:300]
                },
                "ttl_days": 730
            })
            break
    
    # Extract birthdays and dates
    # Patterns: "birthday is January 3rd", "born on 1/3/1966", "birthday January 3"
    birthday_patterns = [
        r"birthday (?:is |on )?([A-Za-z]+ \d+(?:st|nd|rd|th)?(?:,? \d{4})?)",
        r"born (?:on |in )?([A-Za-z]+ \d+(?:st|nd|rd|th)?(?:,? \d{4})?)",
        r"birthday (?:is )?(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)",
    ]
    
    for pattern in birthday_patterns:
        match = re.search(pattern, content_lower, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            # Try to identify whose birthday
            person_name = "user"
            
            # Check for "my wife Kelly's birthday" or "my wife's birthday"
            # Priority: specific name > relationship > generic
            name_with_relation = re.search(r"my (wife|husband|partner|son|daughter|mom|mother|dad|father) (\w+)(?:'s)? birthday", content_lower)
            if name_with_relation:
                # Found "my wife Kelly's birthday" - use the name
                person_name = name_with_relation.group(2).capitalize()
            else:
                # Check for possessive patterns: "my wife's birthday", "her birthday", "his birthday"
                possessive_match = re.search(r"my (wife|husband|partner|son|daughter|mom|mother|dad|father)(?:'s)? birthday", content_lower)
                if possessive_match:
                    person_name = possessive_match.group(1)
                elif re.search(r"(?:her|his|their) birthday", content_lower):
                    # Look for a name mentioned earlier in the message
                    name_match = re.search(r"(\w+)(?:'s)? birthday", message_content, re.IGNORECASE)
                    if name_match:
                        person_name = name_match.group(1)
            
            items.append({
                "type": "fact",
                "key": f"birthday_{person_name.lower()}",
                "value": {
                    "description": f"{person_name}'s birthday is {date_str}",
                    "date": date_str,
                    "person": person_name,
                    "fact_type": "birthday"
                },
                "ttl_days": 730
            })
            break
    
    # Extract car/vehicle information
    # Patterns: "drives a Honda", "has a Tesla", "owns a Ford"
    car_patterns = [
        r"(?:drive|drives|driving|has|have|own|owns) (?:a |an )?(\w+)(?: (\w+))?(?:\s+car|\s+truck|\s+vehicle)?",
    ]
    
    if any(word in content_lower for word in ["car", "vehicle", "truck", "drive", "drives", "honda", "toyota", "ford", "tesla", "bmw", "mercedes"]):
        for pattern in car_patterns:
            match = re.search(pattern, content_lower, re.IGNORECASE)
            if match:
                make = match.group(1).capitalize()
                model = match.group(2).capitalize() if match.group(2) else ""
                vehicle = f"{make} {model}".strip()
                
                # Determine owner
                owner = "user"
                if re.search(r"(?:she|he|her|his|their) (?:drives|has|owns)", content_lower):
                    # Look for a name
                    name_match = re.search(r"(\w+) (?:drives|has|owns)", message_content, re.IGNORECASE)
                    if name_match:
                        owner = name_match.group(1)
                
                items.append({
                    "type": "fact",
                    "key": f"vehicle_{owner.lower()}",
                    "value": {
                        "description": f"{owner} drives a {vehicle}",
                        "vehicle": vehicle,
                        "owner": owner,
                        "fact_type": "vehicle"
                    },
                    "ttl_days": 365
                })
                break
    
    # Look for preference statements
    preference_keywords = ["i prefer", "i like", "i don't like", "i hate", "my favorite", "favorite"]
    for keyword in preference_keywords:
        if keyword in content_lower:
            items.append({
                "type": "preference",
                "key": f"user_preference_{hash(message_content) % 10000}",
                "value": {
                    "description": message_content[:300],
                    "preference": message_content,
                },
                "ttl_days": 365
            })
            break
    
    # Extract user's own name
    name_patterns = [
        r"my name is (\w+)",
        r"i'?m (\w+)",
        r"this is (\w+) (?:calling|speaking)",
        r"call me (\w+)"
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, content_lower, re.IGNORECASE)
        if match:
            user_name = match.group(1).capitalize()
            items.append({
                "type": "person",
                "key": "user_name",
                "value": {
                    "name": user_name,
                    "relationship": "self",
                    "caller_name": user_name
                },
                "ttl_days": 730
            })
            break
    
    return items

def should_remember(message_content: str, context: Optional[Dict[str, Any]] = None) -> bool:
    """
    Determine if a message should be stored in long-term memory.
    
    Args:
        message_content: Message content to evaluate
        context: Additional context for decision making
        
    Returns:
        True if message should be remembered
    """
    content_lower = message_content.lower()
    
    # Explicit memory requests
    explicit_markers = ["remember this", "save this", "don't forget", "keep in mind"]
    if any(marker in content_lower for marker in explicit_markers):
        return True
    
    # Important personal information
    important_patterns = [
        "my name is", "i am", "i work at", "my contact", "my email",
        "my phone", "my address", "my preference", "i prefer", "i like",
        "i don't like", "important to me", "my wife", "my husband", "my partner",
        "my son", "my daughter", "my child", "my friend", "my family"
    ]
    if any(pattern in content_lower for pattern in important_patterns):
        return True
    
    # Dates and birthdays
    date_patterns = ["birthday", "born on", "anniversary", "born in"]
    if any(pattern in content_lower for pattern in date_patterns):
        return True
    
    # Vehicles and possessions
    vehicle_patterns = ["car", "truck", "vehicle", "drives", "honda", "toyota", "ford", "tesla"]
    if any(pattern in content_lower for pattern in vehicle_patterns):
        return True
    
    # Project or task-related information
    project_patterns = ["project", "task", "deadline", "meeting", "schedule"]
    if any(pattern in content_lower for pattern in project_patterns) and len(message_content) > 50:
        return True
    
    return False

def detect_safety_triggers(message_content: str) -> bool:
    """
    Detect if a message contains content that should trigger safety mode.
    
    Args:
        message_content: Message content to analyze
        
    Returns:
        True if safety mode should be activated
    """
    content_lower = message_content.lower()
    
    # Safety trigger patterns
    trigger_patterns = [
        "help me hack", "how to steal", "illegal", "harmful", "dangerous",
        "violence", "threat", "suicide", "self-harm", "abuse"
    ]
    
    return any(pattern in content_lower for pattern in trigger_patterns)
