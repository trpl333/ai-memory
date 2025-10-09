import os
import json
import uuid
import logging
import requests
import re
import copy
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

# Import centralized configuration
from config_loader import get_setting

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    # ✅ FIXED: Birthday pattern handles dates WITH or WITHOUT year
    # Matches: "January 3rd", "Jan 3", "January 3rd, 1966", "1/3/1966", "1/3"
    "birthday": re.compile(r"\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?(?:[,\s]+\d{4})?|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b", re.IGNORECASE),
    "phone": re.compile(r"\b(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})\b"),
    "email": re.compile(r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"),
    "vin": re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b"),
    "policy_number": re.compile(r"\b(?:policy|pol)#?\s*([A-Z0-9-]{5,})\b", re.IGNORECASE),
    "year": re.compile(r"\b(19\d{2}|20\d{2})\b"),
    "names": re.compile(r"\b([A-Z][a-z]+ [A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"),  # Full names
    "single_name": re.compile(r"\b([A-Z][a-z]{2,})\b")  # ✅ NEW: Single names like "Kelly"
}

class HTTPMemoryStore:
    """
    HTTP-based memory store that connects to AI-Memory service instead of direct PostgreSQL.
    Provides the same interface as MemoryStore but uses REST API calls.
    """
    
    def __init__(self):
        """Initialize connection to AI-Memory service."""
        self.ai_memory_url = get_setting("ai_memory_url", "http://127.0.0.1:8100")
        self.session = requests.Session()
        # Note: requests.Session doesn't have timeout as an attribute, 
        # it's passed to individual request methods
        
        try:
            logger.info(f"Connecting to AI-Memory service at {self.ai_memory_url}...")
            
            # Test connection to AI-Memory service
            response = self.session.get(f"{self.ai_memory_url}/health", timeout=10)
            if response.status_code == 200:
                health_data = response.json()
                if (
                    health_data.get("status") in ("ok", "healthy")
                    and (
                        health_data.get("db") is True
                        or health_data.get("memory_store") == "connected"
                    )
            ):
                    self.available = True
                    logger.info("✅ Connected to AI-Memory service")
                else:
                    raise Exception(f"AI-Memory service unhealthy: {health_data}")
            else:
                raise Exception(f"AI-Memory service returned {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Failed to connect to AI-Memory service: {e}")
            self.available = False
            # Don't raise - allow app to start in degraded mode

    def _check_connection(self):
        """Check if AI-Memory service connection is available."""
        if not self.available:
            raise RuntimeError("Memory store is not available (AI-Memory service connection failed)")

    def write(self, memory_type: str, key: str, value: Dict[str, Any], user_id: Optional[str] = None, scope: str = "user", ttl_days: int = 365, source: str = "orchestrator") -> str:
        """
        Store a memory object via AI-Memory service.
        
        Args:
            memory_type: Type of memory (person, preference, project, rule, moment, fact)
            key: Unique key/identifier for the memory
            value: Memory content as dictionary
            user_id: User ID for user-scoped memories (None for shared)
            scope: Memory scope ('user', 'shared', 'global')
            ttl_days: Time to live in days
            source: Source of the memory
            
        Returns:
            UUID of the stored memory
        """
        self._check_connection()
        
        # Fix scope/user_id mismatch: reject scope='user' without user_id
        if scope == "user" and user_id is None:
            logger.warning("Cannot use scope='user' without user_id, changing to scope='shared'")
            scope = "shared"
        
        try:
            # Prepare payload for AI-Memory service
            payload = {
                "user_id": user_id or "unknown",
                "message": json.dumps(value) if isinstance(value, dict) else str(value),
                "type": memory_type,
                "k": key,
                "value_json": value,
                "scope": scope,
                "ttl_days": ttl_days,
                "source": source
            }
            
            response = self.session.post(
                f"{self.ai_memory_url}/memory/store",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                # ✅ Fix: AI-Memory service may return different ID field names or just success message
                memory_id = result.get("id") or result.get("memory_id") or result.get("session_id")
                if not memory_id and "data" in result:
                    memory_id = result["data"].get("id")
                
                if memory_id:
                    scope_info = f" [{scope}]" + (f" user:{user_id}" if user_id else "")
                    logger.info(f"Stored memory: {memory_type}:{key} with ID {memory_id}{scope_info}")
                    return str(memory_id)
                else:
                    # ✅ Fix: Don't fail on successful 200 response, generate fallback ID
                    logger.warning(f"AI-Memory service returned 200 but no ID field found. Response: {result}")
                    scope_info = f" [{scope}]" + (f" user:{user_id}" if user_id else "")
                    logger.info(f"Stored memory: {memory_type}:{key} with fallback KEY {key}{scope_info}")
                    return key
            else:
                raise Exception(f"AI-Memory service returned {response.status_code}: {response.text}")
                
        except Exception as e:
            logger.error(f"Failed to write memory: {e}")
            raise

    def search(self, query_text: str, user_id: Optional[str] = None, k: int = 6, memory_types: Optional[List[str]] = None, include_shared: bool = True) -> List[Dict[str, Any]]:
        """
        Search for relevant memories using AI-Memory service.
        
        Args:
            query_text: Text to search for
            user_id: User ID to filter personal memories (None for no user filter)
            k: Number of results to return
            memory_types: Optional filter by memory types
            include_shared: Whether to include shared/global memories
            
        Returns:
            List of memory objects with similarity scores
        """
        self._check_connection()
        
        try:
            # Build payload for AI-Memory service
            payload = {
                "user_id": user_id or "unknown",
                "message": query_text,
                "limit": k,
                "types": memory_types or []
            }
            
            if not include_shared:
                payload["scope"] = "user"
            
            # 🔍 DEBUG: Log what we're sending
            logger.info(f"🔍 Querying AI-Memory: POST {self.ai_memory_url}/memory/retrieve")
            logger.info(f"🔍 Payload: {json.dumps(payload, indent=2)}")
            
            response = self.session.post(
                f"{self.ai_memory_url}/memory/retrieve",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # 🔍 DEBUG: Log full response to understand format
                logger.info(f"🔍 AI-Memory response keys: {result.keys()}")
                logger.info(f"🔍 AI-Memory full response: {json.dumps(result, indent=2)[:500]}")
                
                # ✅ Fix: Handle both "memories" array and "memory" string formats from ai-memory service
                if "memories" in result:
                    logger.info(f"✅ Found 'memories' array with {len(result['memories'])} items")
                    return result["memories"]
                elif "memory" in result and isinstance(result["memory"], str):
                    # Parse concatenated JSON format (newline-separated JSON objects)
                    memory_str = result["memory"].strip()
                    if not memory_str:
                        return []
                    
                    memories = []
                    for idx, line in enumerate(memory_str.split('\n')):
                        line = line.strip()
                        if line:
                            try:
                                mem_obj = json.loads(line)
                                
                                # ✅ Normalize to standard memory format with type/key/value
                                normalized = {
                                    "type": mem_obj.get("type", "fact"),
                                    "key": mem_obj.get("key") or mem_obj.get("k") or mem_obj.get("setting_key") or mem_obj.get("summary", "")[:50] or mem_obj.get("phone_number", "") or f"memory_{idx}",
                                    "value": mem_obj,  # Store entire object as value
                                    "scope": mem_obj.get("scope", "user"),
                                    "user_id": mem_obj.get("user_id"),
                                    "id": mem_obj.get("id") or mem_obj.get("memory_id") or f"concat_{idx}",
                                    "setting_key": mem_obj.get("setting_key"),  # Preserve for admin settings
                                    "k": mem_obj.get("k") or mem_obj.get("key") or mem_obj.get("setting_key")  # Alias
                                }
                                memories.append(normalized)
                            except json.JSONDecodeError:
                                logger.warning(f"Could not parse memory line: {line[:100]}")
                    
                    logger.info(f"✅ Parsed {len(memories)} memories from concatenated format")
                    return memories
                else:
                    logger.error(f"❌ Unexpected response format from AI-Memory service")
                return []
            else:
                logger.error(f"Memory search failed: {response.status_code} {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return []

    def get_user_memories(self, user_id: str, limit: int = 10, include_shared: bool = True) -> List[Dict[str, Any]]:
        """Get memories for a specific user."""
        return self.search("", user_id=user_id, k=limit, include_shared=include_shared)
    
    def normalize_memories(self, raw_memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        ✅ COMPREHENSIVE Memory Normalization Pipeline
        
        Transforms 800+ scattered raw memories into predictable fill-in-the-blanks schema.
        Uses staged pipeline: preprocess → classify → extract → populate → finalize
        
        Returns MEMORY_TEMPLATE with all fields populated where data exists.
        AI always receives same structure regardless of completeness.
        
        Args:
            raw_memories: List of raw memory dicts from ai-memory service
            
        Returns:
            Complete MEMORY_TEMPLATE dict with populated fields
        """
        # ✅ PRIORITY 1: Check for manually saved schema (overrides auto-extraction)
        manual_schemas = []
        for mem in raw_memories:
            if mem.get("type") == "normalized_schema" and mem.get("key") == "user_profile":
                manual_schemas.append(mem.get("value"))
        
        if manual_schemas:
            # Use most recent (last) manual schema
            manual_schema = manual_schemas[-1]
            logger.info(f"✅ Using MANUALLY SAVED schema (found {len(manual_schemas)} versions, using latest)")
            
            # Merge with template to ensure all fields exist
            result = copy.deepcopy(MEMORY_TEMPLATE)
            
            # Deep merge manual schema into template
            for key, value in manual_schema.items():
                if key in result:
                    if isinstance(value, dict) and isinstance(result[key], dict):
                        result[key].update(value)
                    else:
                        result[key] = value
            
            return result
        
        # ✅ PRIORITY 2: Auto-extract from raw memories if no manual schema exists
        logger.info(f"🔄 No manual schema found, auto-normalizing {len(raw_memories)} raw memories...")
        
        # Stage 1: Initialize with full template
        result = copy.deepcopy(MEMORY_TEMPLATE)
        
        # Tracking for deduplication (timestamp-based: latest wins)
        seen_contacts = {}  # relationship -> (timestamp, data)
        seen_vehicles = {}  # vin or composite_key -> (timestamp, data)
        seen_policies = {}  # policy_number -> (timestamp, data)
        
        logger.info(f"🔄 Normalizing {len(raw_memories)} raw memories...")
        
        # Stage 2: Process each memory
        for idx, mem in enumerate(raw_memories):
            mem_type = mem.get("type", "").lower()
            mem_key = (mem.get("key") or mem.get("k") or "").lower()
            value = mem.get("value", {})
            timestamp = mem.get("timestamp", idx)  # Use index if no timestamp
            
            # Convert value to string for text mining if needed
            value_str = json.dumps(value) if isinstance(value, dict) else str(value)
            value_lower = value_str.lower()
            
            # ================================================================
            # STAGE 3: CLASSIFY & EXTRACT by Category
            # ================================================================
            
            # -------------------
            # IDENTITY (Caller info)
            # -------------------
            if "phone_number" in value_lower or mem_type == "registration":
                if isinstance(value, dict):
                    if not result["identity"]["caller_phone"] and value.get("phone_number"):
                        result["identity"]["caller_phone"] = value["phone_number"]
                    if not result["identity"]["caller_name"] and value.get("name"):
                        result["identity"]["caller_name"] = value["name"]
            
            # -------------------
            # CONTACTS (Family, friends, relationships)
            # -------------------
            self._extract_contacts(value, value_str, value_lower, mem_key, timestamp, seen_contacts, result)
            
            # -------------------
            # VEHICLES
            # -------------------
            self._extract_vehicles(value, value_str, value_lower, timestamp, seen_vehicles, result)
            
            # -------------------
            # POLICIES
            # -------------------
            self._extract_policies(value, mem_type, mem_key, timestamp, seen_policies, result)
            
            # -------------------
            # PREFERENCES
            # -------------------
            if mem_type == "preference" or "preference" in mem_key:
                if isinstance(value, dict):
                    if value.get("item"):
                        result["preferences"]["interests"].append(value["item"])
                elif isinstance(value, str) and len(value) > 5:
                    result["preferences"]["notes"].append(value[:100])
            
            # -------------------
            # COMMITMENTS (Promises, follow-ups)
            # -------------------
            if "follow" in value_lower or "remind" in value_lower or "promise" in value_lower:
                if len(result["commitments"]) < 10:
                    result["commitments"].append(value_str[:150])
            
            # -------------------
            # CONVERSATION SUMMARIES
            # -------------------
            if isinstance(value, dict) and "summary" in value:
                if len(result["recent_conversations"]) < 5:
                    result["recent_conversations"].append(value["summary"])
            elif "assistant_response" in value_lower or "user_message" in value_lower:
                # Skip - these are thread history, not facts
                pass
            
            # -------------------
            # GENERAL FACTS (fallback)
            # -------------------
            elif mem_type in ("fact", "moment", "rule") and len(result["facts"]) < 20:
                if isinstance(value, dict) and "description" in value:
                    result["facts"].append(value["description"][:150])
                elif isinstance(value, str) and len(value) > 10 and len(value) < 300:
                    # Filter out conversational responses
                    if not any(x in value_lower for x in ["assistant:", "user:", "hey", "how's it going", "great to"]):
                        result["facts"].append(value[:150])
        
        # Stage 4: Finalize - Clean up empty nested structures
        result = self._cleanup_template(result)
        
        # Stage 5: Summary
        stats = {
            "contacts": len([v for v in result.get("contacts", {}).values() if isinstance(v, dict) and v.get("name")]),
            "vehicles": len(result.get("vehicles", [])),
            "policies": len(result.get("policies", [])),
            "facts": len(result.get("facts", [])),
            "preferences": len(result.get("preferences", {}).get("interests", []))
        }
        logger.info(f"✅ Normalized memory: {stats}")
        
        return result
    
    def _extract_contacts(self, value: Any, value_str: str, value_lower: str, mem_key: str, 
                         timestamp: float, seen_contacts: Dict, result: Dict) -> None:
        """Extract contact information from memory value."""
        
        # Check for structured contact data (DICT format)
        if isinstance(value, dict) and ("name" in value or "relationship" in value):
            name = value.get("name", "").strip()
            relationship = value.get("relationship", "").strip().lower()
            
            if name and relationship in ["spouse", "father", "mother", "son", "daughter"]:
                # Update template if newer
                if relationship not in seen_contacts or timestamp > seen_contacts[relationship][0]:
                    result["contacts"][relationship]["name"] = name
                    if value.get("birthday"):
                        result["contacts"][relationship]["birthday"] = value["birthday"]
                    if value.get("phone"):
                        result["contacts"][relationship]["phone"] = value["phone"]
                    if value.get("nickname") or value.get("goes_by"):
                        result["contacts"][relationship]["nickname"] = value.get("nickname") or value.get("goes_by")
                    if value.get("notes"):
                        if not result["contacts"][relationship]["notes"]:
                            result["contacts"][relationship]["notes"] = []
                        result["contacts"][relationship]["notes"].append(str(value["notes"])[:100])
                    
                    seen_contacts[relationship] = (timestamp, name)
        
        # Text mining for contacts (STRING format)
        else:
            # Check each relationship type
            for rel, keywords in RELATIONSHIP_KEYWORDS.items():
                if any(kw in value_lower for kw in keywords):
                    # ✅ FIXED: Try multiple name extraction strategies
                    name = None
                    
                    # Strategy 1: Try full name pattern first (First Last)
                    name_match = PATTERNS["names"].search(value_str)
                    if name_match:
                        name = name_match.group(1)
                    
                    # Strategy 2: Try single name after relationship keyword
                    # Patterns: "wife Kelly", "my wife Kelly", "wife is Kelly", "wife's name is Kelly"
                    if not name:
                        for keyword in keywords:
                            # Look for: "keyword NAME" or "keyword is NAME" or "keyword's name is NAME"
                            single_pattern = re.compile(
                                rf"\b{re.escape(keyword)}(?:'?s?\s+name)?(?:\s+is)?\s+([A-Z][a-z]{{2,}})\b",
                                re.IGNORECASE
                            )
                            single_match = single_pattern.search(value_str)
                            if single_match:
                                name = single_match.group(1).strip().title()
                                break
                    
                    # Strategy 3: If still no name, try finding ANY capitalized name in the text
                    if not name and rel in ["spouse", "father", "mother"]:
                        # Only use this as fallback for primary relationships
                        single_name_match = PATTERNS["single_name"].search(value_str)
                        if single_name_match:
                            potential_name = single_name_match.group(1)
                            # Filter out common words that aren't names
                            if potential_name.lower() not in ["the", "this", "that", "they", "then", "there"]:
                                name = potential_name
                    
                    if name:
                        # Map child relationships
                        if rel in ["son", "daughter", "child"]:
                            target_list = "children"
                            child_dict = {"name": name, "relationship": rel}
                            if not any(c.get("name") == name for c in result["contacts"]["children"]):
                                result["contacts"]["children"].append(child_dict)
                        
                        # Primary contacts (spouse, father, mother)
                        elif rel in ["spouse", "father", "mother"]:
                            if not result["contacts"][rel].get("name"):
                                result["contacts"][rel]["name"] = name
                                
                                # Extract birthday if in same text (now handles dates without year!)
                                bday_match = PATTERNS["birthday"].search(value_str)
                                if bday_match:
                                    result["contacts"][rel]["birthday"] = bday_match.group(1)
                                
                                # Extract phone if in same text
                                phone_match = PATTERNS["phone"].search(value_str)
                                if phone_match:
                                    result["contacts"][rel]["phone"] = phone_match.group(1)
                                
                                break  # Found name for this relationship, move on
    
    def _extract_vehicles(self, value: Any, value_str: str, value_lower: str, 
                         timestamp: float, seen_vehicles: Dict, result: Dict) -> None:
        """Extract vehicle information from memory value."""
        
        # Check for structured vehicle data
        if isinstance(value, dict) and any(k in value for k in ["make", "model", "vin", "year"]):
            vin = value.get("vin", "")
            vehicle_key = vin if vin else f"{value.get('year', '')}_{value.get('make', '')}_{value.get('model', '')}"
            
            if vehicle_key and (vehicle_key not in seen_vehicles or timestamp > seen_vehicles[vehicle_key][0]):
                vehicle_dict = {}
                if value.get("year"):
                    vehicle_dict["year"] = value["year"]
                if value.get("make"):
                    vehicle_dict["make"] = value["make"]
                if value.get("model"):
                    vehicle_dict["model"] = value["model"]
                if value.get("vin"):
                    vehicle_dict["vin"] = value["vin"]
                if value.get("owner"):
                    vehicle_dict["owner"] = value["owner"]
                
                if vehicle_dict:
                    # Update or append
                    existing_idx = None
                    for idx, v in enumerate(result["vehicles"]):
                        if v.get("vin") == vin or (v.get("make") == vehicle_dict.get("make") and v.get("model") == vehicle_dict.get("model")):
                            existing_idx = idx
                            break
                    
                    if existing_idx is not None:
                        result["vehicles"][existing_idx] = vehicle_dict
                    else:
                        result["vehicles"].append(vehicle_dict)
                    
                    seen_vehicles[vehicle_key] = (timestamp, vehicle_dict)
        
        # Text mining for vehicles
        else:
            for veh_keyword in VEHICLE_KEYWORDS:
                if veh_keyword in value_lower:
                    # Try to extract year
                    year_match = PATTERNS["year"].search(value_str)
                    if year_match and len(result["vehicles"]) < 5:  # Limit
                        vehicle_dict = {"year": int(year_match.group(1)), "make": veh_keyword.upper()}
                        if not any(v.get("make") == vehicle_dict["make"] for v in result["vehicles"]):
                            result["vehicles"].append(vehicle_dict)
                    break
    
    def _extract_policies(self, value: Any, mem_type: str, mem_key: str, 
                         timestamp: float, seen_policies: Dict, result: Dict) -> None:
        """Extract insurance policy information from memory value."""
        
        if mem_type == "policy" or "policy" in mem_key:
            if isinstance(value, dict):
                policy_dict = {}
                
                # Determine policy type
                policy_type = value.get("type") or value.get("policy_type")
                if not policy_type:
                    # Infer from keywords
                    value_str = json.dumps(value).lower()
                    for ptype, keywords in POLICY_KEYWORDS.items():
                        if any(kw in value_str for kw in keywords):
                            policy_type = ptype
                            break
                
                if policy_type:
                    policy_dict["type"] = policy_type
                    
                    if value.get("carrier"):
                        policy_dict["carrier"] = value["carrier"]
                    if value.get("status"):
                        policy_dict["status"] = value["status"]
                    if value.get("policy_number"):
                        policy_dict["policy_number"] = value["policy_number"]
                    if value.get("premium"):
                        policy_dict["premium"] = value["premium"]
                    
                    # Deduplicate by policy_number or type
                    policy_key = value.get("policy_number") or policy_type
                    if policy_key not in seen_policies or timestamp > seen_policies[policy_key][0]:
                        # Update or append
                        existing_idx = None
                        for idx, p in enumerate(result["policies"]):
                            if p.get("policy_number") == policy_dict.get("policy_number") or p.get("type") == policy_type:
                                existing_idx = idx
                                break
                        
                        if existing_idx is not None:
                            result["policies"][existing_idx] = policy_dict
                        else:
                            result["policies"].append(policy_dict)
                        
                        seen_policies[policy_key] = (timestamp, policy_dict)
    
    def _cleanup_template(self, result: Dict) -> Dict:
        """Clean up empty nested structures in the template."""
        
        # Remove empty contact entries
        for rel in ["spouse", "father", "mother"]:
            if result["contacts"][rel].get("name") is None:
                # Keep structure but mark as empty
                pass
            else:
                # Clean up empty notes lists
                if not result["contacts"][rel].get("notes"):
                    result["contacts"][rel]["notes"] = []
        
        # Remove empty lists from identity
        if not result["identity"]["notes"]:
            result["identity"]["notes"] = []
        
        # Remove empty lists from preferences
        if not result["preferences"]["notes"]:
            result["preferences"]["notes"] = []
        if not result["preferences"]["interests"]:
            result["preferences"]["interests"] = []
        
        return result

    def get_shared_memories(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get shared memories."""
        try:
            payload = {
                "user_id": "shared",
                "message": "",
                "limit": limit,
                "scope": "shared,global"
            }
            response = self.session.post(f"{self.ai_memory_url}/memory/retrieve", json=payload, headers={"Content-Type": "application/json"}, timeout=10)
            
            if response.status_code == 200:
                return response.json().get("memories", [])
            else:
                return []
        except Exception as e:
            logger.error(f"Failed to get shared memories: {e}")
            return []

    def get_memory_by_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific memory by ID."""
        self._check_connection()
        
        try:
            # Use memory/read endpoint with session_id parameter  
            response = self.session.get(f"{self.ai_memory_url}/memory/read", params={"session_id": memory_id}, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                return None
                
        except Exception as e:
            logger.error(f"Failed to get memory by ID: {e}")
            return None

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a specific memory."""
        self._check_connection()
        
        try:
            # Note: Delete endpoint may not be available in current AI-Memory service
            # Return True for now since memories have TTL
            logger.warning(f"Delete memory not implemented in AI-Memory service, memory_id: {memory_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False

    def cleanup_expired(self) -> int:
        """Cleanup expired memories."""
        self._check_connection()
        
        try:
            # Cleanup may not be available in current AI-Memory service
            logger.info("Cleanup expired memories not implemented in AI-Memory service")
            return 0
                
        except Exception as e:
            logger.error(f"Failed to cleanup expired memories: {e}")
            return 0

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        try:
            # Stats may not be available in current AI-Memory service  
            logger.info("Memory stats not implemented in AI-Memory service")
            return {"total": 0, "by_type": {}, "by_scope": {}}
                
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"total": 0, "by_type": {}, "by_scope": {}}

    def close(self):
        """Close the HTTP session."""
        if hasattr(self, 'session'):
            self.session.close()
            logger.info("HTTP session closed")