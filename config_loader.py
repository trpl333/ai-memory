"""
Centralized Configuration Loader for NeuroSphere Orchestrator
Reads from both config.json (GitHub-synced) and environment variables (secure)
"""
import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ConfigLoader:
    def __init__(self, config_file: str = "config.json", internal_config_file: str = "config-internal.json"):
        self.config_file = config_file
        self.internal_config_file = internal_config_file
        self._config_cache = None
        self._internal_config_cache = None
        self._last_modified = 0
        self._internal_last_modified = 0
        
    def _load_config_file(self) -> Dict[str, Any]:
        """Load configuration from JSON file with hot reload support"""
        try:
            # Check if file was modified for hot reload
            if os.path.exists(self.config_file):
                modified_time = os.path.getmtime(self.config_file)
                if modified_time > self._last_modified:
                    with open(self.config_file, 'r') as f:
                        self._config_cache = json.load(f)
                        self._last_modified = modified_time
                        logger.info(f"✅ Configuration reloaded from {self.config_file}")
                        
            return self._config_cache or {}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"⚠️ Could not load {self.config_file}: {e}")
            return {}
            
    def _load_internal_config_file(self) -> Dict[str, Any]:
        """Load internal configuration from JSON file with hot reload support"""
        try:
            # Check if file was modified for hot reload
            if os.path.exists(self.internal_config_file):
                modified_time = os.path.getmtime(self.internal_config_file)
                if modified_time > self._internal_last_modified:
                    with open(self.internal_config_file, 'r') as f:
                        self._internal_config_cache = json.load(f)
                        self._internal_last_modified = modified_time
                        logger.info(f"✅ Internal configuration reloaded from {self.internal_config_file}")
                        
            return self._internal_config_cache or {}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"⚠️ Could not load {self.internal_config_file}: {e}")
            return {}
    
    def get(self, key: str, default: Any = None, fallback_env: Optional[str] = None) -> Any:
        """
        Get configuration value with priority:
        1. Environment variable (for secrets)
        2. config.json file (for settings)
        3. config-internal.json file (for internal settings)
        4. Default value
        """
        # Priority 1: Environment variable (secrets)
        env_value = os.environ.get(key.upper())
        if env_value is not None:
            return env_value
            
        # Check fallback environment variable name if provided
        if fallback_env:
            fallback_value = os.environ.get(fallback_env)
            if fallback_value is not None:
                return fallback_value
        
        # Priority 2: config.json file (settings)
        config = self._load_config_file()
        if key.lower() in config:
            return config[key.lower()]
            
        # Priority 3: config-internal.json file (internal settings)
        internal_config = self._load_internal_config_file()
        if key.lower() in internal_config:
            return internal_config[key.lower()]
            
        # Priority 4: Default value
        return default
    
    def get_all_config(self) -> Dict[str, Any]:
        """Get complete configuration for debugging/admin interface with proper security masking"""
        config = self._load_config_file()
        internal_config = self._load_internal_config_file()
        
        # Sensitive key patterns for security masking
        sensitive_keys = ['api_key', 'token', 'secret', 'password', 'auth', 'sid', 'database_url', 'db_', 'connection', 'dsn']
        
        def is_sensitive_key(key: str) -> bool:
            """Check if a key contains sensitive information"""
            lower_key = key.lower()
            return any(sensitive in lower_key for sensitive in sensitive_keys)
            
        def mask_if_sensitive(key: str, value: Any) -> Any:
            """Mask value if key is sensitive"""
            if is_sensitive_key(key):
                return "***MASKED***"
            return value
        
        result = {}
        
        # Add config.json values with masking
        for key, value in config.items():
            result[f"config.{key}"] = mask_if_sensitive(key, value)
            
        # Add config-internal.json values with masking
        for key, value in internal_config.items():
            result[f"internal.{key}"] = mask_if_sensitive(key, value)
            
        # Add all environment variables with masking
        for env_key in os.environ:
            result[f"env.{env_key.lower()}"] = mask_if_sensitive(env_key, os.environ[env_key])
                
        return result
    
    def reload(self):
        """Force reload configuration from both files"""
        self._last_modified = 0
        self._internal_last_modified = 0
        config = self._load_config_file()
        internal_config = self._load_internal_config_file()
        return {"config": config, "internal": internal_config}

# Global configuration loader instance
config = ConfigLoader()

# Convenience functions for common usage patterns
def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get secret from environment variables with fallback"""
    return config.get(key, default)

def get_setting(key: str, default: Any = None) -> Any:
    """Get setting from config.json, with support for admin: pointers resolved via AI-Memory"""
    import logging

    value = config.get(key, default)

    # If this is an admin pointer, fetch the live value from AI-Memory using HTTPMemoryStore
    if isinstance(value, str) and value.startswith("admin:"):
        admin_key = value.split(":", 1)[1]
        try:
            # ✅ Use HTTPMemoryStore instead of direct requests to avoid localhost hardcoding
            from app.http_memory import HTTPMemoryStore
            memory_store = HTTPMemoryStore()
            
            # Search for admin setting by key using the proper memory store
            results = memory_store.search(
                query_text=f"admin_setting {admin_key}",
                user_id="admin",
                k=5,
                memory_types=["admin_setting"],
                include_shared=True
            )
            
            # Look for exact key match in results
            for result in results:
                if result.get("key") == admin_key or result.get("k") == admin_key:
                    # Extract value from the stored admin setting
                    stored_value = result.get("value_json", {})
                    if isinstance(stored_value, dict):
                        return stored_value.get("value", default)
                    return stored_value

        except Exception as e:
            logging.warning(f"⚠️ Could not fetch {admin_key} from AI-Memory: {e}")
        return default

    return value

def get_database_url() -> str:
    """Get database URL from environment"""
    return config.get("DATABASE_URL", default="")

def get_llm_config() -> Dict[str, str]:
    """Get LLM configuration"""
    return {
        "base_url": config.get("LLM_BASE_URL", default=config.get("llm_base_url", "https://api.openai.com/v1")),
        "model": config.get("LLM_MODEL", default=config.get("llm_model", "gpt-4o-mini")),
        "api_key": config.get("OPENAI_API_KEY", default=config.get("LLM_API_KEY", default=config.get("llm_api_key", "")))
    }

def get_twilio_config() -> Dict[str, str]:
    """Get Twilio configuration"""
    return {
        "account_sid": config.get("TWILIO_ACCOUNT_SID", default=""),
        "auth_token": config.get("TWILIO_AUTH_TOKEN", default=""),
        "phone_number": config.get("TWILIO_PHONE_NUMBER", default=config.get("twilio_phone_number", "+19497071290"))
    }

def get_elevenlabs_config() -> Dict[str, str]:
    """Get ElevenLabs configuration"""
    # Check admin panel first, then env, then config.json
    voice_id = get_setting("voice_id", 
                          config.get("ELEVENLABS_VOICE_ID", 
                                    default=config.get("elevenlabs_voice_id", "FGY2WhTYpPnrIDTdsKH5")))
    
    return {
        "api_key": config.get("ELEVENLABS_API_KEY", default=""),
        "voice_id": voice_id
    }

def get_all_config() -> Dict[str, Any]:
    """Get complete configuration from all sources (global convenience function)"""
    return config.get_all_config()

# New convenience functions for internal configuration
def get_internal_setting(key: str, default: Any = None) -> Any:
    """Get setting from config-internal.json"""
    internal_config = config._load_internal_config_file()
    return internal_config.get(key.lower(), default)
    
def get_internal_urls() -> Dict[str, str]:
    """Get internal service URLs"""
    return {
        "flask_internal_url": get_internal_setting("flask_internal_url", "http://127.0.0.1:5000"),
        "fastapi_backend_url": get_internal_setting("fastapi_backend_url", "http://127.0.0.1:8001")
    }
    
def get_internal_ports() -> Dict[str, int]:
    """Get internal service port mappings"""
    ports = get_internal_setting("critical_ports", {})
    return {
        "flask_orchestrator": ports.get("flask_orchestrator", 5000),
        "fastapi_backend": ports.get("fastapi_backend", 8001),
        "ai_memory": ports.get("ai_memory", 8100)
    }
