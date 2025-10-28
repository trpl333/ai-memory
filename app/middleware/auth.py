"""
JWT Authentication Middleware for Multi-Tenant Security

Validates JWT tokens from Chad (ChatStack) and extracts customer_id.
This prevents tenant spoofing and ensures secure service-to-service communication.
"""

import os
import jwt
import logging
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# Security scheme for FastAPI
security = HTTPBearer()

# JWT secret key (shared with Chad)
# MUST match the key used by Chad to sign tokens
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")

if not JWT_SECRET_KEY:
    logger.warning("JWT_SECRET_KEY not set! JWT validation will fail.")
    logger.warning("Set JWT_SECRET_KEY in environment variables.")


def validate_jwt(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> int:
    """
    Validate JWT token and extract customer_id.
    
    This function is used as a FastAPI dependency to protect endpoints.
    It validates the JWT signature and extracts the customer_id claim.
    
    Args:
        credentials: HTTP Authorization header with Bearer token
    
    Returns:
        customer_id (int): The validated customer/tenant ID
    
    Raises:
        HTTPException 401: If token is invalid, expired, or missing
    
    Example:
        @app.post("/v2/context/enriched")
        def enriched_context(
            request: ContextRequest,
            customer_id: int = Depends(validate_jwt)  # ← Validates JWT
        ):
            # customer_id is now cryptographically verified
            ...
    
    Security:
        - Token must be signed with JWT_SECRET_KEY
        - Signature verification prevents spoofing
        - Expired tokens are rejected
        - Missing or malformed tokens are rejected
    """
    if not JWT_SECRET_KEY:
        logger.error("JWT_SECRET_KEY not configured - cannot validate tokens")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication system not configured"
        )
    
    try:
        # Extract token from "Bearer <token>"
        token = credentials.credentials
        
        # Decode and verify JWT signature
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=["HS256"]
        )
        
        # Extract customer_id claim
        customer_id = payload.get("customer_id")
        
        if customer_id is None:
            logger.error("JWT token missing customer_id claim")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing customer_id"
            )
        
        # Convert to integer (should be int in JWT, but validate)
        try:
            customer_id = int(customer_id)
        except (TypeError, ValueError):
            logger.error(f"Invalid customer_id in JWT: {customer_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: customer_id must be integer"
            )
        
        logger.debug(f"JWT validated successfully for customer_id={customer_id}")
        return customer_id
        
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired - please obtain a new token"
        )
    
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )
    
    except Exception as e:
        logger.error(f"Unexpected error validating JWT: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication error"
        )


def validate_jwt_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Optional[int]:
    """
    Optional JWT validation for endpoints that support both authenticated
    and unauthenticated access.
    
    Returns:
        customer_id if valid token provided, None if no token
    
    Raises:
        HTTPException 401: If token is provided but invalid
    """
    if credentials is None:
        return None
    
    return validate_jwt(credentials)


def generate_jwt_token(customer_id: int, expires_in_hours: int = 1) -> str:
    """
    Generate a JWT token (for testing or internal use).
    
    NOTE: In production, Chad (ChatStack) generates tokens, not Alice.
    This function is only for testing purposes.
    
    Args:
        customer_id: The customer/tenant ID to embed in token
        expires_in_hours: Token expiration time (default: 1 hour)
    
    Returns:
        JWT token string
    """
    from datetime import datetime, timedelta
    
    if not JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY not configured")
    
    payload = {
        "customer_id": customer_id,
        "scope": "read:memories write:memories",
        "exp": datetime.utcnow() + timedelta(hours=expires_in_hours),
        "iat": datetime.utcnow()
    }
    
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")
    return token


# Example usage in FastAPI:
"""
from fastapi import FastAPI, Depends
from app.middleware.auth import validate_jwt
from app.middleware.tenant_context import set_tenant_context

app = FastAPI()

@app.post("/v2/process-call")
def process_call(
    request: ProcessCallRequest,
    customer_id: int = Depends(validate_jwt),  # ← JWT validation
    db: Session = Depends(get_db)
):
    # Set tenant context for RLS
    set_tenant_context(db, customer_id)
    
    # Now all queries are filtered by customer_id
    # Both through RLS (automatic) and explicit filters (defense-in-depth)
    ...
"""
