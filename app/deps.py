"""
Authentication dependencies and helpers
"""
import os
from typing import Optional, List, Dict, Any
from fastapi import Depends, HTTPException, status, Cookie, Request
from fastapi.responses import JSONResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.services import supa

# Session management
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
SESSION_EXPIRY_DAYS = int(os.getenv("SESSION_EXPIRY_DAYS", "7"))
REMEMBER_ME_DAYS = int(os.getenv("REMEMBER_ME_DAYS", "30"))

# Create serializer for secure cookies
serializer = URLSafeTimedSerializer(SECRET_KEY)

def create_session(user_id: str, remember_me: bool = False) -> str:
    """Create a secure session token"""
    expiry_days = REMEMBER_ME_DAYS if remember_me else SESSION_EXPIRY_DAYS
    return serializer.dumps(user_id, salt="session")

def verify_session(session_token: str) -> Optional[str]:
    """Verify and extract user ID from session token"""
    try:
        # Default expiry is 7 days, max is 30 days
        user_id = serializer.loads(
            session_token, 
            salt="session", 
            max_age=REMEMBER_ME_DAYS * 24 * 60 * 60
        )
        return user_id
    except (BadSignature, SignatureExpired):
        return None

def get_current_user(session_id: str = Cookie(None, alias="session_id")) -> Optional[Dict[str, Any]]:
    """Get current authenticated user from session"""
    if not session_id:
        return None
    
    user_id = verify_session(session_id)
    if not user_id:
        return None
    
    # Get user from Supabase
    user = supa.get_user(user_id)
    if not user:
        return None
    
    # Add session info
    user["session_id"] = session_id
    return user

def require_auth() -> Dict[str, Any]:
    """Require authentication - raises 401 if not authenticated"""
    def _require_auth(current_user: Optional[Dict] = Depends(get_current_user)) -> Dict[str, Any]:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        return current_user
    return _require_auth

def require_role(allowed_roles: List[str]) -> Dict[str, Any]:
    """Require specific role(s) - raises 403 if insufficient permissions"""
    def _require_role(current_user: Dict = Depends(require_auth())) -> Dict[str, Any]:
        user_role = current_user.get("role", "").lower()
        if not any(role.lower() in allowed_roles for role in [user_role]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user
    return _require_role

# Convenience decorators for common roles
def require_owner() -> Dict[str, Any]:
    """Require owner role"""
    return require_role(["owner"])

def require_admin() -> Dict[str, Any]:
    """Require admin or owner role"""
    return require_role(["owner", "admin"])

def require_manager() -> Dict[str, Any]:
    """Require manager, admin, or owner role"""
    return require_role(["owner", "admin", "manager"])

def require_employee() -> Dict[str, Any]:
    """Require any authenticated user"""
    return require_auth()
