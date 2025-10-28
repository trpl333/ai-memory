"""
Tenant Context Middleware for Multi-Tenant RLS
Sets PostgreSQL session variable for Row-Level Security enforcement

This middleware ensures that all database queries are automatically
filtered by customer_id through PostgreSQL RLS policies.
"""

import logging
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def set_tenant_context(db_session: Session, customer_id: int) -> None:
    """
    Set PostgreSQL session variable for RLS enforcement.
    
    This sets the 'app.current_tenant' session variable that RLS policies use
    to automatically filter queries by customer_id.
    
    Args:
        db_session: SQLAlchemy database session
        customer_id: The tenant/customer ID to set as context
    
    Example:
        set_tenant_context(db.session, customer_id=1)
        # Now all queries in this session are filtered to customer_id=1
        profiles = db.query(CallerProfile).all()  # Only returns customer_id=1 data
    
    Security:
        - MUST be called before ANY database query
        - customer_id should come from validated JWT token, not request body
        - Session variable persists for the entire database session
        - Different sessions have different tenant contexts (isolation)
    """
    try:
        # Set session variable for RLS
        db_session.execute(
            text("SET app.current_tenant = :tenant_id"),
            {"tenant_id": customer_id}
        )
        logger.debug(f"Tenant context set to customer_id={customer_id}")
    except Exception as e:
        logger.error(f"Failed to set tenant context for customer_id={customer_id}: {e}")
        raise


def clear_tenant_context(db_session: Session) -> None:
    """
    Clear the tenant context (resets session variable).
    
    This should be called when you want to remove the tenant filter,
    though in multi-tenant applications this is rarely needed.
    
    Args:
        db_session: SQLAlchemy database session
    """
    try:
        db_session.execute(text("RESET app.current_tenant"))
        logger.debug("Tenant context cleared")
    except Exception as e:
        logger.error(f"Failed to clear tenant context: {e}")
        raise


def get_current_tenant(db_session: Session) -> Optional[int]:
    """
    Get the current tenant ID from session variable.
    
    Useful for debugging or verification that tenant context is set correctly.
    
    Args:
        db_session: SQLAlchemy database session
    
    Returns:
        The current customer_id, or None if not set
    """
    try:
        result = db_session.execute(
            text("SELECT current_setting('app.current_tenant', true)")
        )
        tenant_id_str = result.scalar()
        
        if tenant_id_str and tenant_id_str != '':
            return int(tenant_id_str)
        return None
    except Exception as e:
        logger.debug(f"No tenant context set or error retrieving: {e}")
        return None


# Example usage in FastAPI endpoints:
"""
from fastapi import Depends
from app.middleware.tenant_context import set_tenant_context
from app.middleware.auth import validate_jwt

@app.get("/caller/profile/{user_id}")
def get_caller_profile(
    user_id: str,
    customer_id: int = Depends(validate_jwt),
    db: Session = Depends(get_db)
):
    # Set tenant context from JWT-validated customer_id
    set_tenant_context(db, customer_id)
    
    # Now query is automatically filtered by customer_id through RLS
    profile = db.query(CallerProfile).filter_by(user_id=user_id).first()
    
    # Even if developer forgets WHERE customer_id filter,
    # PostgreSQL RLS ensures only customer_id data is returned
    return profile
"""
