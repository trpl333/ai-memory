"""
Request-Level Tenant Context Management

Integrates tenant_context with FastAPI request lifecycle.
Ensures session variable is set and cleared on every request.
"""

import logging
from typing import Optional
from fastapi import Request, Depends
from sqlalchemy.orm import Session

from app.middleware.tenant_context import set_tenant_context, clear_tenant_context
from app.middleware.auth import validate_jwt

logger = logging.getLogger(__name__)


class TenantContextMiddleware:
    """
    FastAPI middleware to manage tenant context for database session.
    
    This middleware:
    1. Extracts customer_id from validated JWT token
    2. Sets PostgreSQL session variable for RLS enforcement
    3. Clears session variable after request completes
    4. Handles pooled connections correctly (no tenant leakage)
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        # This middleware is handled by FastAPI dependency injection
        # See get_tenant_session() below for actual implementation
        await self.app(scope, receive, send)


def get_tenant_session(
    customer_id: int = Depends(validate_jwt),
    db: Session = Depends(get_db)
) -> Session:
    """
    FastAPI dependency that sets tenant context for database session.
    
    Use this as a dependency in endpoints that need tenant-scoped queries.
    
    Args:
        customer_id: Validated customer ID from JWT token
        db: Database session from FastAPI dependency
    
    Returns:
        Database session with tenant context set
    
    Example:
        @app.get("/caller/profile/{user_id}")
        def get_profile(
            user_id: str,
            db: Session = Depends(get_tenant_session)  # ← Automatic tenant context
        ):
            # Session variable already set, RLS active
            profile = db.query(CallerProfile).filter_by(user_id=user_id).first()
            return profile
    
    Security:
        - customer_id comes from validated JWT (not spoofable)
        - Session variable set before any query runs
        - RLS policies automatically filter all queries
        - Pooled connections safe (variable cleared after request)
    """
    try:
        # Set tenant context for this request
        set_tenant_context(db, customer_id)
        logger.debug(f"Tenant context set for request: customer_id={customer_id}")
        
        # Yield session for request to use
        yield db
        
    finally:
        # Clear tenant context after request completes
        # Critical for connection pooling - prevents tenant leakage
        try:
            clear_tenant_context(db)
            logger.debug(f"Tenant context cleared after request")
        except Exception as e:
            logger.error(f"Error clearing tenant context: {e}")


def get_db():
    """
    Placeholder for database session dependency.
    
    This should be replaced with your actual database session factory.
    
    Example implementation:
        from app.database import SessionLocal
        
        def get_db():
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()
    """
    # TODO: Import and use actual database session factory
    raise NotImplementedError("Replace with actual database session factory")


# Example usage in FastAPI routes:
"""
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from app.middleware.request_tenant import get_tenant_session
from app.models import CallerProfile

app = FastAPI()

@app.get("/caller/profile/{user_id}")
def get_caller_profile(
    user_id: str,
    db: Session = Depends(get_tenant_session)  # ← Automatic tenant + JWT validation
):
    # Tenant context already set from JWT
    # RLS automatically filters by customer_id
    profile = db.query(CallerProfile).filter_by(user_id=user_id).first()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return profile


@app.post("/caller/profile")
def create_caller_profile(
    profile_data: CallerProfileCreate,
    db: Session = Depends(get_tenant_session)
):
    # customer_id automatically populated by RLS context
    new_profile = CallerProfile(**profile_data.dict())
    db.add(new_profile)
    db.commit()
    return new_profile
"""


# Alternative: Manual tenant context management (if not using dependency)
"""
from fastapi import Request
from app.middleware.auth import validate_jwt
from app.middleware.tenant_context import set_tenant_context

@app.post("/v2/process-call")
async def process_call(
    request: ProcessCallRequest,
    db: Session = Depends(get_db)
):
    # Manually validate JWT and set tenant context
    auth_header = request.headers.get("Authorization")
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=auth_header.replace("Bearer ", "")
    )
    
    customer_id = validate_jwt(credentials)
    set_tenant_context(db, customer_id)
    
    # Now queries are tenant-scoped
    ...
"""
