"""
CSRF middleware for protecting form submissions
"""
import secrets
import time
from typing import Dict, Optional
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF protection middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        # In-memory CSRF token storage (in production, use Redis or similar)
        self.csrf_tokens: Dict[str, float] = {}
        # CSRF exempt paths
        self.exempt_paths = {
            "/api/auth/login",
            "/api/auth/logout",
            "/api/process",  # File processing endpoint
            "/api/packing/preview",  # File preview endpoint
            "/api/chat/upload",  # File upload endpoint
            "/api/shopify/config",  # Shopify configuration
            "/api/shopify/test-connection",  # Shopify connection test
            "/api/shopify/sync",  # Shopify sync
            "/api/shopify/instant-sync",  # Shopify instant sync
        }
    
    def generate_csrf_token(self) -> str:
        """Generate a new CSRF token with expiration"""
        token = secrets.token_urlsafe(32)
        # Store token with 1 hour expiration
        self.csrf_tokens[token] = time.time() + 3600
        return token
    
    def verify_csrf_token(self, token: str) -> bool:
        """Verify CSRF token and clean expired ones"""
        if token not in self.csrf_tokens:
            return False
        
        # Check if token is expired
        if time.time() > self.csrf_tokens[token]:
            del self.csrf_tokens[token]
            return False
        
        # Token is valid, remove it (one-time use)
        del self.csrf_tokens[token]
        return True
    
    def cleanup_expired_tokens(self):
        """Remove expired CSRF tokens"""
        current_time = time.time()
        expired_tokens = [
            token for token, expiry in self.csrf_tokens.items()
            if current_time > expiry
        ]
        for token in expired_tokens:
            del self.csrf_tokens[token]
    
    async def dispatch(self, request: Request, call_next):
        # Clean up expired tokens periodically
        if len(self.csrf_tokens) > 100:  # Only cleanup when we have many tokens
            self.cleanup_expired_tokens()
        
        # Skip CSRF check for exempt paths
        if request.url.path in self.exempt_paths:
            return await call_next(request)
        
        # Skip CSRF check for non-modifying methods
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            return await call_next(request)
        
        # For POST/PATCH/DELETE, require CSRF token
        csrf_token = None
        
        # Check header first
        if "X-CSRF-Token" in request.headers:
            csrf_token = request.headers["X-CSRF-Token"]
        # Fall back to form data
        elif request.method == "POST":
            try:
                form_data = await request.form()
                csrf_token = form_data.get("csrf_token")
            except:
                pass
        
        if not csrf_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token required"
            )
        
        if not self.verify_csrf_token(csrf_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or expired CSRF token"
            )
        
        # Add CSRF token to request state for templates
        request.state.csrf_token = self.generate_csrf_token()
        
        response = await call_next(request)
        return response
