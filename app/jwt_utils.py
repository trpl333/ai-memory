import os
import jwt
from datetime import datetime, timedelta
from typing import Optional

def generate_memory_token(customer_id: int, scope: str = "memory:read:write") -> str:
    """Generate JWT token for AI-Memory service authentication"""
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise ValueError("JWT_SECRET_KEY not configured")
    
    payload = {
        "customer_id": customer_id,
        "scope": scope,
        "exp": datetime.utcnow() + timedelta(minutes=30)
    }
    
    return jwt.encode(payload, secret, algorithm="HS256")

def verify_token(token: str) -> Optional[dict]:
    """Verify and decode JWT token"""
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        return None
    
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except:
        return None
