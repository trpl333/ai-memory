# memory_schema.py
# Comprehensive memory normalization for ai-memory service
import re
import json
import copy
from typing import Dict, List, Any

# ============================================================================
# COMPREHENSIVE MEMORY SCHEMA - Fill-in-the-blanks template
# ============================================================================

MEMORY_TEMPLATE = {
    "identity": {
        "caller_name": None,
        "caller_phone": None,
        "caller_email": None,
        "caller_address": None,
        "date_of_birth": None,
        "notes": []
    },
    "contacts": {
        "spouse": {
            "name": None,
            "nickname": None,
            "relationship": "spouse",
            "birthday": None,
            "phone": None,
            "email": None,
            "notes": []
        },
        "father": {
            "name": None,
            "nickname": None,
            "relationship": "father",
            "birthday": None,
            "phone": None,
            "notes": []
        },
        "mother": {
            "name": None,
            "nickname": None,
            "relationship": "mother",
            "birthday": None,
            "phone": None,
            "notes": []
        },
        "children": [],  # List of child dicts
        "siblings": [],
        "friends": [],
        "business": []
    },
    "vehicles": [],  # List of vehicle dicts
    "policies": [],  # List of policy dicts
    "claims": [],    # List of claim dicts
    "properties": [], # List of property dicts
    "preferences": {
        "communication_method": None,
        "language": None,
        "timezone": None,
        "interests": [],
        "notes": []
    },
    "commitments": [],  # Promises, follow-ups, reminders
    "facts": [],        # General important facts
    "recent_conversations": []  # Last 5 conversation snippets
}

# ============================================================================
# KEYWORD MAPS for Classification
# ============================================================================

RELATIONSHIP_KEYWORDS = {
    "spouse": ["wife", "husband", "spouse", "kelly", "married"],
    "father": ["dad", "father", "jack", "pop", "papa"],
    "mother": ["mom", "mother", "arlene", "mama"],
    "son": ["son", "boy", "male child"],
    "daughter": ["daughter", "girl", "female child"],
    "child": ["child", "kid"],
    "brother": ["brother", "bro"],
    "sister": ["sister", "sis"],
    "friend": ["friend", "buddy", "pal"],
}

POLICY_KEYWORDS = {
    "auto": ["auto", "car", "vehicle", "automobile"],
    "home": ["home", "house", "property", "homeowners"],
    "life": ["life insurance", "life policy"],
    "umbrella": ["umbrella", "excess liability"],
    "business": ["commercial", "business", "liability"]
}

VEHICLE_KEYWORDS = ["bmw", "toyota", "honda", "ford", "chevrolet", "car", "truck", "suv", "sedan"]

# ============================================================================
# REGEX PATTERNS for Extraction
# ============================================================================

PATTERNS = {
    "birthday": re.compile(r"\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?(?:[,\s]+\d{4})?|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b", re.IGNORECASE),
    "phone": re.compile(r"\b(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})\b"),
    "email": re.compile(r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"),
    "names": re.compile(r"\b([A-Z][a-z]+ [A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"),
    "single_name": re.compile(r"\b([A-Z][a-z]{2,})\b")
}

def normalize_memories(raw_memory_text: str) -> Dict[str, Any]:
    """
    Transform raw memory text into comprehensive structured schema.
    
    Args:
        raw_memory_text: Newline-separated JSON memory entries from database
        
    Returns:
        Complete MEMORY_TEMPLATE dict with populated fields
    """
    result = copy.deepcopy(MEMORY_TEMPLATE)
    
    # Parse raw text into list of memory objects
    memories = []
    for line in raw_memory_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        try:
            mem = json.loads(line)
            memories.append(mem)
        except json.JSONDecodeError:
            # Plain text memory - wrap it
            memories.append({"value": line})
    
    # Track contacts found
    seen_contacts = {}
    
    # Process each memory
    for idx, mem in enumerate(memories):
        value = mem.get("value", mem)  # Handle both {"value": ...} and direct values
        mem_key = str(mem.get("key", "")).lower()
        
        # Convert to string for text mining
        value_str = json.dumps(value) if isinstance(value, dict) else str(value)
        value_lower = value_str.lower()
        
        # IDENTITY (Caller info)
        if "phone_number" in value_lower:
            if isinstance(value, dict) and value.get("phone_number"):
                result["identity"]["caller_phone"] = value["phone_number"]
        
        # CONTACTS - Extract from both structured and unstructured data
        for rel, keywords in RELATIONSHIP_KEYWORDS.items():
            if any(kw in value_lower for kw in keywords):
                name = None
                
                # Strategy 1: Structured data
                if isinstance(value, dict) and value.get("name"):
                    name = value["name"]
                
                # Strategy 2: Full name pattern
                if not name:
                    name_match = PATTERNS["names"].search(value_str)
                    if name_match:
                        name = name_match.group(1)
                
                # Strategy 3: Single name after keyword ("wife Kelly", "wife is Kelly")
                if not name:
                    for keyword in keywords:
                        single_pattern = re.compile(
                            rf"\b{re.escape(keyword)}(?:'?s?\s+name)?(?:\s+is)?\s+([A-Z][a-z]{{2,}})\b",
                            re.IGNORECASE
                        )
                        match = single_pattern.search(value_str)
                        if match:
                            name = match.group(1).strip().title()
                            break
                
                if name and rel in ["spouse", "father", "mother"]:
                    if not result["contacts"][rel].get("name"):
                        result["contacts"][rel]["name"] = name
                        
                        # Extract birthday
                        bday_match = PATTERNS["birthday"].search(value_str)
                        if bday_match:
                            result["contacts"][rel]["birthday"] = bday_match.group(1)
                        
                        # Extract phone
                        phone_match = PATTERNS["phone"].search(value_str)
                        if phone_match:
                            result["contacts"][rel]["phone"] = phone_match.group(1)
                        
                        seen_contacts[rel] = True
        
        # VEHICLES
        for veh_keyword in VEHICLE_KEYWORDS:
            if veh_keyword in value_lower and len(result["vehicles"]) < 5:
                vehicle_dict = {"make": veh_keyword.upper()}
                if isinstance(value, dict):
                    if value.get("year"):
                        vehicle_dict["year"] = value["year"]
                    if value.get("model"):
                        vehicle_dict["model"] = value["model"]
                if not any(v.get("make") == vehicle_dict["make"] for v in result["vehicles"]):
                    result["vehicles"].append(vehicle_dict)
                break
        
        # PREFERENCES
        if "preference" in mem_key or "preference" in value_lower:
            if isinstance(value, dict) and value.get("item"):
                result["preferences"]["interests"].append(value["item"])
            elif isinstance(value, str) and len(value) < 100:
                if value not in result["preferences"]["notes"]:
                    result["preferences"]["notes"].append(value)
        
        # CONVERSATION SUMMARIES
        if isinstance(value, dict) and "summary" in value:
            if len(result["recent_conversations"]) < 5:
                result["recent_conversations"].append(value["summary"])
        
        # GENERAL FACTS
        elif isinstance(value, str) and len(value) > 10 and len(value) < 300:
            # Filter out conversational responses
            if not any(x in value_lower for x in ["assistant:", "user:", "hey", "how's it going"]):
                if len(result["facts"]) < 20:
                    result["facts"].append(value[:150])
    
    return result
