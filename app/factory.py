"""
Application factory for creating and configuring the FastAPI app
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse
from fastapi import Request, Depends, Cookie, status, HTTPException
import secrets
import time
from typing import Optional, Dict

from app.config import APP_TITLE, APP_VERSION, DEBUG, USE_JSON
from app.services import supa
from app.middleware import CSRFMiddleware

# Navigation items for the sidebar
NAV_ITEMS = [
    {"id": "dashboard", "name": "Dashboard", "icon": "📊", "url": "/hub", "active": True, "required_roles": []},
    {"id": "orders", "name": "Orders", "icon": "🧭", "url": "/orders", "active": True, "required_roles": ["owner", "admin", "manager"]},
    {"id": "packing", "name": "Packing Management", "icon": "📦", "url": "/packing", "active": True, "required_roles": []},
    {"id": "attendance", "name": "Employee Attendance", "icon": "🗓️", "url": "/attendance", "active": True, "required_roles": []},
    {"id": "chat", "name": "Team Chat", "icon": "💬", "url": "/chat", "active": True, "required_roles": []},
    {"id": "tasks", "name": "Tasks", "icon": "📝", "url": "/task", "active": True, "required_roles": []},
    {"id": "reports", "name": "Reports & Analytics", "icon": "📊", "url": "/attendance/report_page", "active": True, "required_roles": []},
    {"id": "separator", "type": "separator", "name": "ADDITIONAL FEATURES"},
    {"id": "team", "name": "Team Management", "icon": "👥", "url": "/team", "active": False, "badge": "Soon", "required_roles": ["owner", "admin"]},
    {"id": "shopify", "name": "Shopify Settings", "icon": "🛒", "url": "/shopify/settings", "active": True, "required_roles": ["owner", "admin"]},
    {"id": "settings", "name": "System Settings", "icon": "⚙️", "url": "/admin/settings", "active": False, "badge": "Soon", "required_roles": ["owner"]},
    {"id": "users", "name": "User Management", "icon": "👨‍💼", "url": "/admin/users", "active": True, "required_roles": ["owner", "admin"]},
    {"id": "security", "name": "Security Settings", "icon": "🔐", "url": "/admin/security", "active": False, "badge": "Soon", "required_roles": ["owner"]},
    {"id": "analytics", "name": "System Analytics", "icon": "📈", "url": "/admin/analytics", "active": False, "badge": "Soon", "required_roles": ["owner", "admin"]},
]

# Authentication middleware
class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to handle authentication redirects."""
    
    def __init__(self, app):
        super().__init__(app)
        # Protected paths that require authentication
        self.protected_paths = {
            "/hub", "/orders", "/packing", "/attendance", "/admin/users", 
            "/shopify/settings", "/chat", "/team", "/admin/settings", 
            "/admin/security", "/admin/analytics", "/task"
        }
        # Public paths that don't require authentication
        self.public_paths = {"/", "/login", "/static", "/favicon.ico", "/__whoami"}
        # API paths that handle their own authentication
        self.api_paths = {"/api/"}
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Skip middleware for static files, API endpoints, and public paths
        if (any(path.startswith(public) for public in self.public_paths) or 
            any(path.startswith(api) for api in self.api_paths) or
            path.endswith(('.css', '.js', '.png', '.jpg', '.ico', '.svg'))):
            return await call_next(request)
        
        # Check if path requires authentication
        if any(path.startswith(protected) for protected in self.protected_paths):
            # Check for session cookie
            session_id = request.cookies.get("session_id")
            
            if not session_id or not supa.get_user_by_session(session_id):
                # Redirect to login if not authenticated
                return RedirectResponse(url="/login", status_code=302)
        
        return await call_next(request)

def create_app() -> FastAPI:
    """Create and configure the FastAPI application"""
    
    # Create FastAPI instance
    app = FastAPI(
        title=APP_TITLE,
        version=APP_VERSION,
        debug=DEBUG
    )
    
    # Add CORS middleware
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    
    # Add CSRF middleware
    app.add_middleware(CSRFMiddleware)
    
    # Add authentication middleware
    # app.add_middleware(AuthMiddleware)  # TEMPORARILY DISABLED
    
    # Set up Jinja2 templates
    templates = Jinja2Templates(directory="templates")
    templates.env.globals["NAV_ITEMS"] = NAV_ITEMS
    
    # Mount static files
    app.mount("/static", StaticFiles(directory="static"), name="static")
    
    # Health check endpoint
    @app.get("/__whoami")
    def health_check():
        """Health check endpoint to confirm we're running the consolidated app"""
        return {
            "entrypoint": "main.py",
            "supabase_client": "app/services/supa.py",
            "status": "healthy",
            "version": APP_VERSION,
            "debug": DEBUG
        }
    
    # Root redirect
    @app.get("/")
    def root():
        """Redirect to the hub (dashboard) page"""
        return RedirectResponse(url="/hub")
    
    # Import and register routers
    try:
        # Import routers
        from app.routers import hub, users, orders, tasks, chat_channels, chat_messages, tasks_ultra
        from app.routers import auth, packing, jobs, attendance, shopify, chat, orders_extras
        
        # Register routers
        app.include_router(hub.router, prefix="")
        app.include_router(users.router, prefix="")
        app.include_router(orders.router, prefix="")
        app.include_router(tasks.router, prefix="")
        app.include_router(chat_channels.router, prefix="")
        app.include_router(chat_messages.router, prefix="")
        app.include_router(tasks_ultra.router, prefix="")
        app.include_router(auth.router, prefix="")
        app.include_router(packing.router, prefix="")
        app.include_router(jobs.router, prefix="")
        app.include_router(attendance.router, prefix="")
        app.include_router(shopify.router, prefix="")
        app.include_router(chat.router, prefix="")
        app.include_router(orders_extras.router, prefix="")
        
        print("✅ All routers registered successfully")
        
    except ImportError as e:
        print(f"⚠️ Warning: Could not import some routers: {e}")
        print("   Some functionality may not be available")
    
    # Store templates in app state for access in routers
    app.state.templates = templates
    
    # Add startup and shutdown events for Shopify sync service
    @app.on_event("startup")
    async def startup_event():
        """Start background services on app startup"""
        try:
            from app.services.shopify_sync_service import start_shopify_sync
            await start_shopify_sync()
            print("🔄 Shopify sync service started")
        except Exception as e:
            print(f"⚠️ Warning: Could not start Shopify sync service: {e}")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """Stop background services on app shutdown"""
        try:
            from app.services.shopify_sync_service import stop_shopify_sync
            await stop_shopify_sync()
            print("🛑 Shopify sync service stopped")
        except Exception as e:
            print(f"⚠️ Warning: Error stopping Shopify sync service: {e}")
    
    print(f"🚀 Application factory completed:")
    print(f"   Title: {APP_TITLE}")
    print(f"   Version: {APP_VERSION}")
    print(f"   Debug: {DEBUG}")
    print(f"   Use JSON: {USE_JSON}")
    
    return app
