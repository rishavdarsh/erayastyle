import os
import uuid
import threading
import hashlib
import secrets
import datetime
from pathlib import Path
import re
import urllib.request
import urllib.parse
import json
# import aiohttp  # Temporarily disabled for Windows compatibility
from PIL import Image
# import zipstream_ng as zipstream  # Removed for Windows compatibility
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends, Cookie, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

# Authentication imports
from passlib.context import CryptContext
from passlib.hash import bcrypt
import secrets
import time
from datetime import datetime

from processor import process_csv_file, extract_color

import io
import pandas as pd
import datetime
import requests
from typing import Dict, List, Any
import json
# import aiohttp  # Temporarily disabled for Windows compatibility
from PIL import Image
# import zipstream_ng as zipstream  # Removed for Windows compatibility

app = FastAPI(title="Eraya Style Order Processor")

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
        self.public_paths = {"/", "/login", "/static", "/favicon.ico"}
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
            
            if not session_id or not get_current_user_from_session(session_id):
                # Redirect to login if not authenticated
                return RedirectResponse(url="/login", status_code=302)
        
        return await call_next(request)

# Add authentication middleware
app.add_middleware(AuthMiddleware)

# Shopify configuration from environment variables
SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP", "")  # e.g., "mystore.myshopify.com"
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN", "")  # Admin API token

def _shopify_get(path: str, params: dict = None) -> dict:
    """Helper function to make Shopify API calls with pagination support."""
    # Try environment variables first, then fall back to SHOPIFY_CONFIG
    shop = SHOPIFY_SHOP or SHOPIFY_CONFIG.get("store_name")
    token = SHOPIFY_TOKEN or SHOPIFY_CONFIG.get("access_token")
    
    if not shop or not token:
        raise HTTPException(status_code=400, detail="Shopify configuration missing. Set SHOPIFY_SHOP and SHOPIFY_TOKEN environment variables or configure via /shopify/settings.")
    
    # Ensure shop has the right format
    if shop and not shop.endswith('.myshopify.com'):
        shop = f"{shop}.myshopify.com"
    
    url = f"https://{shop}/admin/api/2024-07{path}"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params or {})
        response.raise_for_status()
        
        # Parse pagination info from Link header
        next_page_info = None
        prev_page_info = None
        
        if "Link" in response.headers:
            link_header = response.headers["Link"]
            # Parse next page info
            if 'rel="next"' in link_header:
                next_match = re.search(r'<[^>]*[?&]page_info=([^&>]+)[^>]*>;\s*rel="next"', link_header)
                if next_match:
                    next_page_info = next_match.group(1)
            
            # Parse previous page info
            if 'rel="previous"' in link_header:
                prev_match = re.search(r'<[^>]*[?&]page_info=([^&>]+)[^>]*>;\s*rel="previous"', link_header)
                if prev_match:
                    prev_page_info = prev_match.group(1)
        
        data = response.json()
        data["_pagination"] = {
            "next_page_info": next_page_info,
            "prev_page_info": prev_page_info
        }
        return data
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Shopify API error: {str(e)}")

# In-memory store for attendance records
ATTENDANCE_RECORDS = {}

# In-memory store for employee data (name to ID mapping)
EMPLOYEES = {
    "Ritik": "EMP001",
    "Sunny": "EMP002",
    "Rahul": "EMP003",
    "Sumit": "EMP004",
    "Vishal": "EMP005",
    "Nishant": "EMP006",
}

# User roles and permissions - ALL USERS GET FULL ACCESS
USER_ROLES = {
    "EMP001": {"name": "Ritik", "role": "admin", "permissions": ["all"]},
    "EMP002": {"name": "Sunny", "role": "admin", "permissions": ["all"]},
    "EMP003": {"name": "Rahul", "role": "admin", "permissions": ["all"]},
    "EMP004": {"name": "Sumit", "role": "admin", "permissions": ["all"]},
    "EMP005": {"name": "Vishal", "role": "admin", "permissions": ["all"]},
    "EMP006": {"name": "Nishant", "role": "admin", "permissions": ["all"]},
}



def get_navigation_with_access(user_role: str):
    """Get navigation menu with access information for the user's role."""
    menu_with_access = []
    
    for item in NAV_ITEMS:
        # Copy the item
        menu_item = item.copy()
        
        # Skip separators - they don't need access control
        if item.get("type") == "separator":
            menu_with_access.append(menu_item)
            continue
        
        # Check if user has access to this item
        required_roles = item.get("required_roles", [])
        
        # If no required roles, everyone has access
        if not required_roles:
            menu_item["has_access"] = True
            menu_item["locked"] = False
        # If owner, always has access
        elif user_role == "owner":
            menu_item["has_access"] = True
            menu_item["locked"] = False
        # Check if user's role is in required roles
        elif user_role in required_roles:
            menu_item["has_access"] = True
            menu_item["locked"] = False
        else:
            menu_item["has_access"] = False
            menu_item["locked"] = True
        
        menu_with_access.append(menu_item)
    
    return menu_with_access

# In-memory store for team chat messages
CHAT_MESSAGES = []

# In-memory store for chat channels and DMs
CHAT_CHANNELS = {
    "general": {"name": "General", "messages": []},
    "packing": {"name": "Packing Team", "messages": []},
    "management": {"name": "Management", "messages": []},
    "announcements": {"name": "Announcements", "messages": []}
}

# In-memory store for direct messages (DMs)
DIRECT_MESSAGES = {}  # Format: {"EMP001_EMP002": [messages]}

# In-memory store for user online status
USER_STATUS = {}  # Format: {"EMP001": {"status": "online", "last_seen": timestamp}}

# In-memory store for message reactions
MESSAGE_REACTIONS = {}

# -------------------- SHOPIFY INTEGRATION --------------------
# Shopify store configuration - In production, use environment variables or database
SHOPIFY_CONFIG = {
    "store_name": "",  # Will be set via settings page
    "access_token": "",  # Will be set via settings page
    "api_version": "2024-01"  # Latest stable API version
}

# In-memory store for cached Shopify data
SHOPIFY_CACHE = {
    "orders": [],
    "analytics": {},
    "last_updated": None
}

# -------------------- USER MANAGEMENT SYSTEM --------------------
# Role-based Icon System
ROLE_ICONS = {
    "owner": {
        "icon": "💎",  # Diamond - represents ultimate value, rarity, and ownership
        "icon_color": "#FFD700"
    },
    "admin": {
        "icon": "🛡️",  # Shield - represents protection and administration
        "icon_color": "#4F46E5"
    },
    "manager": {
        "icon": "🎯",  # Target - represents focus, goals, and management
        "icon_color": "#EF4444"
    },
    "packer": {
        "icon": "⭐",  # Star - represents talent and contribution
        "icon_color": "#10B981"
    }
}

# Helper function to get role-based icon data
def get_role_icon(role):
    return ROLE_ICONS.get(role, {"icon": "👤", "icon_color": "#6B7280"})

# -------------------- DATA PERSISTENCE --------------------
import json
import os
from pathlib import Path

# File paths for data persistence
DATA_DIR = Path("data")
USERS_DB_FILE = DATA_DIR / "users_database.json"
USERS_AUTH_FILE = DATA_DIR / "users_auth.json"

def ensure_data_directory():
    """Ensure the data directory exists."""
    DATA_DIR.mkdir(exist_ok=True)

def save_users_database():
    """Save USERS_DATABASE to JSON file."""
    ensure_data_directory()
    with open(USERS_DB_FILE, 'w') as f:
        json.dump(USERS_DATABASE, f, indent=2, default=str)

def load_users_database():
    """Load USERS_DATABASE from JSON file."""
    if USERS_DB_FILE.exists():
        try:
            with open(USERS_DB_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            print("Warning: Could not load users database, using defaults")
    return None

def save_users_auth():
    """Save USERS authentication data to JSON file."""
    ensure_data_directory()
    with open(USERS_AUTH_FILE, 'w') as f:
        json.dump(USERS, f, indent=2, default=str)

def load_users_auth():
    """Load USERS authentication data from JSON file."""
    if USERS_AUTH_FILE.exists():
        try:
            with open(USERS_AUTH_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            print("Warning: Could not load users auth, using defaults")
    return None

# User Management System - Default data (used if no saved data exists)
DEFAULT_USERS_DATABASE = {
    "rishavdarsh": {
        "id": "rishavdarsh",
        "name": "Rishav Darsh",
        "email": "rishav@company.com",
        "role": "owner",
        "status": "active",
        "photo": "https://via.placeholder.com/100/FFD700/000000?text=RD",
        "phone": "+1 (555) 001-0001",
        "joining_date": "2024-01-01",
        "shift": "flexible",
        "manager": "",
        "address": "123 Owner Street",
        "city": "Business City",
        "state": "NY",
        "zip": "10001",
        "emergency_contact": {
            "name": "Emergency Contact",
            "relation": "Spouse",
            "phone": "+1 (555) 001-0002",
            "email": "emergency@owner.com"
        },
        "documents": [],
        "created_date": "2024-01-01",
        "last_login": "2024-01-20 16:00:00",
        "login_count": 100,
        "permissions": ["all"],
        "session_id": "sess_owner_active"
    },
    "EMP001": {
        "id": "EMP001",
        "name": "Ritik",
        "email": "ritik@company.com",
        "role": "admin",
        "status": "active",
        "photo": "https://via.placeholder.com/100/4f46e5/ffffff?text=R",
        "phone": "+1 (555) 001-0011",
        "joining_date": "2024-01-15",
        "shift": "morning",
        "manager": "rishavdarsh",
        "address": "456 Admin Avenue",
        "city": "Tech City",
        "state": "CA",
        "zip": "90210",
        "emergency_contact": {
            "name": "Admin Emergency",
            "relation": "Parent",
            "phone": "+1 (555) 001-0012",
            "email": "emergency@admin.com"
        },
        "documents": [],
        "created_date": "2024-01-15",
        "last_login": "2024-01-20 14:30:00",
        "login_count": 45,
        "permissions": ["dashboard", "orders", "packing", "attendance", "chat", "reports", "shopify", "users"],
        "session_id": "sess_001_active"
    },
    "EMP002": {
        "id": "EMP002",
        "name": "Sunny",
        "email": "sunny@company.com",
        "role": "admin",
        "status": "active",
        "photo": "https://via.placeholder.com/100/059669/ffffff?text=S",
        "created_date": "2024-01-16",
        "last_login": "2024-01-20 10:15:00",
        "login_count": 32,
        "permissions": ["dashboard", "orders", "packing", "attendance", "chat", "reports"],
        "session_id": "sess_002_active"
    },
    "EMP003": {
        "id": "EMP003",
        "name": "Rahul",
        "email": "rahul@company.com",
        "role": "manager",
        "status": "active",
        "photo": "https://via.placeholder.com/100/dc2626/ffffff?text=R",
        "created_date": "2024-01-17",
        "last_login": "2024-01-19 16:45:00",
        "login_count": 28,
        "permissions": ["dashboard", "orders", "packing", "attendance", "chat"],
        "session_id": "sess_003_active"
    },
    "EMP004": {
        "id": "EMP004",
        "name": "Sumit",
        "email": "sumit@company.com",
        "role": "packer",
        "status": "inactive",
        "photo": "https://via.placeholder.com/100/7c3aed/ffffff?text=S",
        "created_date": "2024-01-18",
        "last_login": "2024-01-18 09:20:00",
        "login_count": 12,
        "permissions": ["dashboard", "attendance", "chat"],
        "session_id": None
    },
    "EMP005": {
        "id": "EMP005",
        "name": "Vishal",
        "email": "vishal@company.com",
        "role": "manager",
        "status": "active",
        "photo": "https://via.placeholder.com/100/ea580c/ffffff?text=V",
        "created_date": "2024-01-19",
        "last_login": "2024-01-20 11:30:00",
        "login_count": 15,
        "permissions": ["dashboard", "orders", "packing", "attendance", "chat"],
        "session_id": "sess_005_active"
    },
    "EMP006": {
        "id": "EMP006",
        "name": "Nishant",
        "email": "nishant@company.com",
        "role": "packer",
        "status": "active",
        "photo": "https://via.placeholder.com/100/0891b2/ffffff?text=N",
        "created_date": "2024-01-20",
        "last_login": "2024-01-20 08:45:00",
        "login_count": 8,
        "permissions": ["dashboard", "attendance", "chat"],
        "session_id": "sess_006_active"
    }
}

# Load saved data or use defaults
USERS_DATABASE = load_users_database() or DEFAULT_USERS_DATABASE

# -------------------- AUTHENTICATION SYSTEM --------------------
# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Dev auto-login user (for development only)
DEV_AUTOLOGIN_USER = os.getenv("DEV_AUTOLOGIN_USER")

# Authentication users database with hashed passwords - Default data
DEFAULT_USERS = {
    "rishavdarsh": {
        "employee_id": "rishavdarsh",
        "name": "Rishav Darsh",
        "role": "owner",
        "password_hash": pwd_context.hash("ER9919@"),  # Owner password: ER9919@
    },
    "EMP001": {
        "employee_id": "EMP001",
        "name": "Ritik",
        "role": "admin",
        "password_hash": pwd_context.hash("admin123"),  # Default password: admin123
    },
    "EMP002": {
        "employee_id": "EMP002", 
        "name": "Sunny",
        "role": "admin",
        "password_hash": pwd_context.hash("admin123"),  # Default password: admin123
    },
    "EMP003": {
        "employee_id": "EMP003",
        "name": "Rahul", 
        "role": "manager",
        "password_hash": pwd_context.hash("manager123"),  # Default password: manager123
    },
    "EMP004": {
        "employee_id": "EMP004",
        "name": "Sumit",
        "role": "packer",
        "password_hash": pwd_context.hash("packer123"),  # Default password: packer123
    },
    "EMP005": {
        "employee_id": "EMP005",
        "name": "Vishal",
        "role": "manager", 
        "password_hash": pwd_context.hash("manager123"),  # Default password: manager123
    },
    "EMP006": {
        "employee_id": "EMP006",
        "name": "Nishant",
        "role": "packer",
        "password_hash": pwd_context.hash("packer123"),  # Default password: packer123
    }
}

# Load saved authentication data or use defaults
USERS = load_users_auth() or DEFAULT_USERS

def sync_user_databases():
    """Synchronize USERS and USERS_DATABASE to ensure consistency."""
    for user_id, user_data in USERS_DATABASE.items():
        if user_id in USERS:
            # Update role in USERS to match USERS_DATABASE
            USERS[user_id]["role"] = user_data["role"]
            USERS[user_id]["name"] = user_data["name"]
        else:
            # Add missing user to USERS (with default password)
            USERS[user_id] = {
                "employee_id": user_id,
                "name": user_data["name"],
                "role": user_data["role"],
                "password_hash": pwd_context.hash("default123")  # Default password
            }
    
    # Also sync the other direction
    for user_id, user_data in USERS.items():
        if user_id not in USERS_DATABASE:
            # Add missing user to USERS_DATABASE with complete profile
            USERS_DATABASE[user_id] = {
                "id": user_id,
                "name": user_data["name"],
                "email": f"{user_data['name'].lower().replace(' ', '')}@company.com",
                "role": user_data["role"],
                "status": "active",
                "photo": f"https://via.placeholder.com/100/4F46E5/ffffff?text={user_data['name'][0]}",
                "phone": "",
                "joining_date": "2024-01-20",
                "shift": "",
                "manager": "",
                "address": "",
                "city": "",
                "state": "",
                "zip": "",
                "emergency_contact": {
                    "name": "",
                    "relation": "",
                    "phone": "",
                    "email": ""
                },
                "documents": [],
                "created_date": "2024-01-20",
                "last_login": "2024-01-20 12:00:00",
                "login_count": 1,
                "permissions": ROLE_DEFINITIONS.get(user_data["role"], {}).get("permissions", []),
                "session_id": None
            }
    
    # Save changes after synchronization
    save_users_database()
    save_users_auth()


def sync_user_to_task_system(employee_id: str, user_data: dict, auth_data: dict):
    """Sync a single user to the task management system."""
    try:
        from models import SessionLocal, User as TaskUser
        
        db = SessionLocal()
        
        # Role mapping
        role_map = {
            "owner": "ADMIN", 
            "admin": "ADMIN", 
            "manager": "MANAGER",
            "packer": "EMPLOYEE",
            "employee": "EMPLOYEE"
        }
        mapped_role = role_map.get(user_data.get("role", "").lower(), "EMPLOYEE")
        
        # Find or create user in task system
        task_user = db.query(TaskUser).filter(TaskUser.id == employee_id).first()
        
        if not task_user:
            # Create new user
            task_user = TaskUser(
                id=employee_id,
                email=user_data.get('email', f"{employee_id}@company.com"),
                name=user_data.get("name", employee_id),
                password_hash="synced_from_main_app",
                role=mapped_role,
                team=user_data.get('team', None)
            )
            db.add(task_user)
        else:
            # Update existing user
            task_user.name = user_data.get("name", employee_id)
            task_user.role = mapped_role
            task_user.email = user_data.get('email', f"{employee_id}@company.com")
            task_user.team = user_data.get('team', None)
        
        db.commit()
        db.close()
        print(f"Successfully synced user {employee_id} to task system")
        
    except Exception as e:
        print(f"Failed to sync user {employee_id} to task system: {e}")
        raise

# Initialize database synchronization
sync_user_databases()

# Active sessions: token -> {employee_id, expires_at}
SESSIONS = {}

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)

def create_session_token() -> str:
    """Create a secure session token."""
    return secrets.token_urlsafe(32)

def create_session(employee_id: str, remember_me: bool = False) -> str:
    """Create a new session for a user."""
    token = create_session_token()
    expires_in_days = 30 if remember_me else 7
    expires_at = time.time() + (expires_in_days * 24 * 60 * 60)
    
    SESSIONS[token] = {
        "employee_id": employee_id,
        "expires_at": expires_at
    }
    
    return token

def get_current_user_from_session(session_id: str = None) -> Optional[Dict]:
    """Get current user from session token."""
    # Dev auto-login bypass
    if DEV_AUTOLOGIN_USER and DEV_AUTOLOGIN_USER in USERS:
        # Even in dev mode, check if user is active
        user_profile = USERS_DATABASE.get(DEV_AUTOLOGIN_USER)
        if user_profile and user_profile["status"] == "active":
            return USERS[DEV_AUTOLOGIN_USER]
        return None
    
    if not session_id:
        return None
    
    session = SESSIONS.get(session_id)
    if not session:
        return None
    
    # Check if session is expired
    if time.time() > session["expires_at"]:
        del SESSIONS[session_id]
        return None
    
    employee_id = session["employee_id"]
    
    # Check if user exists in auth database
    if employee_id not in USERS:
        del SESSIONS[session_id]
        return None
    
    # Check if user is active in user management database
    user_profile = USERS_DATABASE.get(employee_id)
    if not user_profile or user_profile["status"] != "active":
        # User is deactivated, invalidate session
        del SESSIONS[session_id]
        return None
    
    # Return user data from USERS (auth database)
    return USERS[employee_id]

def cleanup_expired_sessions():
    """Remove expired sessions from memory."""
    current_time = time.time()
    expired_tokens = [token for token, session in SESSIONS.items() 
                     if current_time > session["expires_at"]]
    
    for token in expired_tokens:
        del SESSIONS[token]

def invalidate_user_sessions(employee_id: str):
    """Invalidate all sessions for a specific user (useful when role changes)."""
    tokens_to_remove = []
    for token, session in SESSIONS.items():
        if session["employee_id"] == employee_id:
            tokens_to_remove.append(token)
    
    for token in tokens_to_remove:
        del SESSIONS[token]
    
    # Also clear session_id in USERS_DATABASE
    if employee_id in USERS_DATABASE:
        USERS_DATABASE[employee_id]["session_id"] = None

def require_roles(*allowed_roles):
    """Dependency to require authentication and optionally specific roles."""
    def dependency(session_id: str = Cookie(None, alias="session_id")):
        # Clean up expired sessions periodically
        cleanup_expired_sessions()
        
        user = get_current_user_from_session(session_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please login.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Ensure user still exists in database (handle deleted users)
        if user["employee_id"] not in USERS:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account no longer exists. Please login again."
            )
        
        # Get fresh user data to ensure role is up-to-date
        fresh_user = USERS[user["employee_id"]]
        
        # Owner has access to everything
        if fresh_user["role"] == "owner":
            return fresh_user
        
        # If no roles specified, any authenticated user is allowed
        if not allowed_roles:
            return fresh_user
        
        # Check if user has required role
        if fresh_user["role"] not in allowed_roles:
            role_names = ", ".join(allowed_roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {role_names}. Your role: {fresh_user['role']}"
            )
        
        return fresh_user
    
    return dependency

# Role definitions with permissions
ROLE_DEFINITIONS = {
    "owner": {
        "name": "Company Owner",
        "description": "Ultimate system access - controls all users and permissions",
        "permissions": ["all"],
        "color": "#FFD700"
    },
    "admin": {
        "name": "Admin",
        "description": "Administrative access to most features",
        "permissions": ["dashboard", "orders", "packing", "attendance", "chat", "reports", "shopify", "users"],
        "color": "#4F46E5"
    },
    "manager": {
        "name": "Manager",
        "description": "Management access to operational features",
        "permissions": ["dashboard", "orders", "packing", "attendance", "chat"],
        "color": "#EF4444"
    },
    "packer": {
        "name": "Packer",
        "description": "Basic access to essential features",
        "permissions": ["dashboard", "packing", "attendance", "chat"],
        "color": "#10B981"
    }
}

# Permission definitions
PERMISSION_DEFINITIONS = {
    "dashboard": {"name": "Dashboard Access", "description": "View main dashboard and statistics"},
    "orders": {"name": "Order Management", "description": "Manage orders and order processing"},
    "packing": {"name": "Packing Operations", "description": "Access packing management features"},
    "attendance": {"name": "Attendance Tracking", "description": "View and manage attendance records"},
    "chat": {"name": "Team Chat", "description": "Access team communication features"},
    "reports": {"name": "Reports & Analytics", "description": "View reports and analytics"},
    "user_management": {"name": "User Management", "description": "Manage users and permissions"},
    "system_settings": {"name": "System Settings", "description": "Configure system settings"},
    "shopify": {"name": "Shopify Integration", "description": "Access Shopify integration features"},
    "all": {"name": "All Permissions", "description": "Complete system access"}
}

# Activity logs for audit trail
USER_ACTIVITY_LOGS = []
USER_AUDIT_TRAIL = []

def get_timestamp():
    """Returns current UTC timestamp in ISO format."""
    return datetime.datetime.utcnow().isoformat()
# -------------------- USER MANAGEMENT HELPERS --------------------
def log_user_activity(user_id: str, action: str, details: str = "", ip_address: str = ""):
    """Log user activity for audit trail."""
    activity = {
        "timestamp": get_timestamp(),
        "user_id": user_id,
        "user_name": USERS_DATABASE.get(user_id, {}).get("name", "Unknown"),
        "action": action,
        "details": details,
        "ip_address": ip_address
    }
    USER_ACTIVITY_LOGS.append(activity)
    
    # Keep only last 1000 entries
    if len(USER_ACTIVITY_LOGS) > 1000:
        USER_ACTIVITY_LOGS.pop(0)

def log_audit_trail(admin_user_id: str, target_user_id: str, action: str, old_value: str = "", new_value: str = ""):
    """Log administrative actions for audit trail."""
    audit_entry = {
        "timestamp": get_timestamp(),
        "admin_user_id": admin_user_id,
        "admin_name": USERS_DATABASE.get(admin_user_id, {}).get("name", "Unknown"),
        "target_user_id": target_user_id,
        "target_name": USERS_DATABASE.get(target_user_id, {}).get("name", "Unknown"),
        "action": action,
        "old_value": old_value,
        "new_value": new_value
    }
    USER_AUDIT_TRAIL.append(audit_entry)
    
    # Keep only last 1000 entries
    if len(USER_AUDIT_TRAIL) > 1000:
        USER_AUDIT_TRAIL.pop(0)

def get_user_stats():
    """Get user statistics for dashboard."""
    total_users = len(USERS_DATABASE)
    active_users = len([u for u in USERS_DATABASE.values() if u["status"] == "active"])
    inactive_users = total_users - active_users
    admin_count = len([u for u in USERS_DATABASE.values() if u["role"] in ["owner", "admin"]])
    
    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": inactive_users,
        "admin_count": admin_count,
        "roles_breakdown": {role: len([u for u in USERS_DATABASE.values() if u["role"] == role]) for role in ROLE_DEFINITIONS.keys()}
    }

# -------------------- SHOPIFY API HELPERS --------------------
def make_shopify_request(endpoint: str, params: Dict = None) -> Dict:
    """Make a request to Shopify Admin API."""
    if not SHOPIFY_CONFIG["store_name"] or not SHOPIFY_CONFIG["access_token"]:
        raise HTTPException(status_code=400, detail="Shopify store not configured. Please add your store details in settings.")
    
    url = f"https://{SHOPIFY_CONFIG['store_name']}.myshopify.com/admin/api/{SHOPIFY_CONFIG['api_version']}/{endpoint}"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_CONFIG["access_token"],
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params or {})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Shopify API error: {str(e)}")

def fetch_shopify_orders(limit: int = 50, status: str = "any") -> List[Dict]:
    """Fetch orders from Shopify."""
    params = {
        "limit": limit,
        "status": status,
        "fields": "id,name,email,created_at,updated_at,total_price,currency,financial_status,fulfillment_status,line_items,customer,shipping_address"
    }
    
    try:
        data = make_shopify_request("orders.json", params)
        return data.get("orders", [])
    except Exception as e:
        print(f"Error fetching Shopify orders: {e}")
        return []

def fetch_all_orders_rest(
    status: str = "any",
    fulfillment_status: str = None,
    created_at_min: str = None,
    created_at_max: str = None,
    limit: int = 250
) -> List[Dict]:
    """
    Fetch ALL orders from Shopify using REST API cursor-based pagination.
    
    Args:
        status: Order status filter (any, open, closed, cancelled)
        fulfillment_status: Fulfillment status filter (fulfilled, partial, unfulfilled, etc.)
        created_at_min: Start date filter (ISO format)
        created_at_max: End date filter (ISO format)
        limit: Orders per page (max 250)
    
    Returns:
        List of all orders matching the criteria
    """
    all_orders = []
    page_info = None
    page_count = 0
    max_pages = 1000  # Safety limit to prevent infinite loops
    
    # Fields to retrieve from Shopify
    fields = "id,name,order_number,created_at,financial_status,fulfillment_status,customer,email,order_status_url,line_items,total_price,currency"
    
    try:
        while page_count < max_pages:
            page_count += 1
            
            # Build parameters for this request
            params = {
                "limit": min(limit, 250),  # Shopify max is 250
                "fields": fields
            }
            
            if page_info:
                # For subsequent pages, only send page_info, limit, and fields
                params["page_info"] = page_info
            else:
                # For first page, apply all filters
                params["status"] = status
                if fulfillment_status:
                    params["fulfillment_status"] = fulfillment_status
                if created_at_min:
                    params["created_at_min"] = created_at_min
                if created_at_max:
                    params["created_at_max"] = created_at_max
            
            print(f"Fetching orders page {page_count} (page_info: {'Yes' if page_info else 'No'})")
            
            # Make API call using existing helper
            data = _shopify_get("/orders.json", params)
            
            # Get orders from this page
            orders = data.get("orders", [])
            if not orders:
                print(f"No orders found on page {page_count}, stopping pagination")
                break
            
            # Add orders to our collection
            all_orders.extend(orders)
            print(f"Retrieved {len(orders)} orders from page {page_count} (total so far: {len(all_orders)})")
            
            # Check if there's a next page
            next_page_info = data.get("_pagination", {}).get("next_page_info")
            if not next_page_info:
                print(f"No more pages available, stopping pagination")
                break
            
            page_info = next_page_info
        
        if page_count >= max_pages:
            print(f"Warning: Reached maximum page limit ({max_pages}), there may be more orders")
        
        print(f"Finished fetching all orders: {len(all_orders)} total orders across {page_count} pages")
        return all_orders
        
    except Exception as e:
        print(f"Error in fetch_all_orders_rest: {e}")
        # Return what we have so far
        return all_orders

def fetch_shopify_analytics() -> Dict:
    """Fetch analytics data from Shopify."""
    try:
        # Get order count for today
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Fetch recent orders for analytics
        recent_orders = fetch_shopify_orders(limit=250)
        
        # Calculate analytics
        total_orders = len(recent_orders)
        today_orders = [o for o in recent_orders if o["created_at"].startswith(today)]
        yesterday_orders = [o for o in recent_orders if o["created_at"].startswith(yesterday)]
        
        total_revenue = sum(float(o.get("total_price", 0)) for o in recent_orders)
        today_revenue = sum(float(o.get("total_price", 0)) for o in today_orders)
        
        pending_orders = [o for o in recent_orders if o.get("financial_status") == "pending"]
        fulfilled_orders = [o for o in recent_orders if o.get("fulfillment_status") == "fulfilled"]
        
        return {
            "total_orders": total_orders,
            "today_orders": len(today_orders),
            "yesterday_orders": len(yesterday_orders),
            "total_revenue": round(total_revenue, 2),
            "today_revenue": round(today_revenue, 2),
            "pending_orders": len(pending_orders),
            "fulfilled_orders": len(fulfilled_orders),
            "currency": recent_orders[0].get("currency", "USD") if recent_orders else "USD",
            "last_updated": get_timestamp()
        }
    except Exception as e:
        print(f"Error fetching Shopify analytics: {e}")
        return {
            "error": str(e),
            "last_updated": get_timestamp()
        }

def calculate_duration(start_time_str: str, end_time_str: str) -> float:
    """Calculates duration in hours between two ISO formatted timestamps."""
    start_time = datetime.datetime.fromisoformat(start_time_str)
    end_time = datetime.datetime.fromisoformat(end_time_str)
    duration = end_time - start_time
    return duration.total_seconds() / 3600 # duration in hours

def extract_links_from_message(message: str) -> list:
    """Extract URLs from message text."""
    url_pattern = re.compile(
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    )
    return url_pattern.findall(message)

def get_link_preview(url: str) -> dict:
    """Get basic link preview information."""
    try:
        # Simple link preview - in production you'd use a proper service
        parsed = urllib.parse.urlparse(url)
        return {
            "url": url,
            "title": parsed.netloc,
            "description": f"Link to {parsed.netloc}",
            "image": None
        }
    except:
        return {
            "url": url,
            "title": "Link",
            "description": "External link",
            "image": None
        }

def get_file_type(filename: str) -> str:
    """Determine file type from filename."""
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
        return 'image'
    elif ext in ['mp4', 'avi', 'mov', 'wmv']:
        return 'video'
    elif ext in ['mp3', 'wav', 'ogg']:
        return 'audio'
    elif ext in ['pdf']:
        return 'pdf'
    elif ext in ['doc', 'docx', 'txt']:
        return 'document'
    else:
        return 'file'

# Serve static frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount uploads directory for profile photos and documents
try:
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
except:
    # Create uploads directory if it doesn't exist
    os.makedirs("uploads", exist_ok=True)
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Simple CORS for local dev or static hosting
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Jobs memory store (in-memory; for production you'd use Redis/DB)
JOBS = {}
BASE_DIR = Path(os.getenv("DATA_DIR", "jobs"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

# Chat uploads directory
UPLOADS_DIR = Path("uploads/chat")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Serve uploaded files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Templates for new task dashboard
try:
    templates = Jinja2Templates(directory="templates")
    
    # Make NAV_ITEMS available to all templates
    templates.env.globals["NAV_ITEMS"] = NAV_ITEMS
except Exception:
    import os as _os
    _os.makedirs("templates", exist_ok=True)
    templates = Jinja2Templates(directory="templates")
    
    # Make NAV_ITEMS available to all templates
    templates.env.globals["NAV_ITEMS"] = NAV_ITEMS

# Include Tasks router
# Include Tasks router
try:
    from routers.tasks import router as tasks_router
    from routers.chat_channels import router as chat_channels_router
    from routers.chat_messages import router as chat_messages_router
    from routers.tasks_ultra import router as tasks_ultra_router

    app.include_router(tasks_router, prefix="")
    app.include_router(chat_channels_router, prefix="")
    app.include_router(chat_messages_router, prefix="")
    app.include_router(tasks_ultra_router, prefix="")
except Exception as e:
    print(f"Warning: could not include routers: {e}")


# DB init for tasks module
try:
    from models import init_db as _init_db
    _init_db()
except Exception as e:
    print(f"Warning: DB init failed: {e}")


def run_job(job_id: str, csv_path: Path, out_dir: Path, options: dict):
    JOBS[job_id] = {"status": "processing", "message": "Starting...", "zip_path": None, "progress": 0}

    def status_cb(step: str, progress: float = None):
        if job_id in JOBS:
            JOBS[job_id]["message"] = step
            if progress is not None:
                JOBS[job_id]["progress"] = float(progress)

    try:
        zip_path = process_csv_file(csv_path, out_dir, status_cb, options=options)
        JOBS[job_id]["status"] = "done"
        JOBS[job_id]["zip_path"] = str(zip_path)
        JOBS[job_id]["message"] = "Completed"
        JOBS[job_id]["progress"] = 100.0
    except Exception as e:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["message"] = f"Error: {e}"
        JOBS[job_id]["progress"] = 0.0


@app.get("/", response_class=HTMLResponse)
def root():
    # Redirect to the hub (dashboard) page instead of showing raw static HTML
    return RedirectResponse(url="/hub")


@app.post("/api/process")
async def api_process(
    file: UploadFile = File(...),
    order_prefix: str = Form("#ER"),
    max_threads: int = Form(8),
    retry_total: int = Form(3),
    backoff_factor: float = Form(0.6),
    timeout_sec: int = Form(15),
    include_per_product_csv: bool = Form(True),
    include_back_messages_csv: bool = Form(True),
    zip_name: str = Form("results"),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    job_id = uuid.uuid4().hex[:12]
    job_dir = BASE_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    csv_path = job_dir / file.filename

    with open(csv_path, "wb") as f:
        f.write(await file.read())

    options = {
        "order_prefix": order_prefix or "#ER",
        "max_threads": max(1, min(int(max_threads), 32)),
        "retry_total": max(0, int(retry_total)),
        "backoff_factor": float(backoff_factor),
        "timeout_sec": max(3, int(timeout_sec)),
        "include_per_product_csv": bool(include_per_product_csv),
        "include_back_messages_csv": bool(include_back_messages_csv),
        "zip_name": zip_name.strip() or "results",
    }

    t = threading.Thread(target=run_job, args=(job_id, csv_path, job_dir, options), daemon=True)
    t.start()
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def api_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    return JOBS[job_id]


@app.get("/api/download/{job_id}")
def api_download(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    job = JOBS[job_id]
    if job["status"] != "done" or not job["zip_path"]:
        raise HTTPException(status_code=400, detail="Job not finished yet")
    path = Path(job["zip_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="ZIP not found")
    return FileResponse(path, media_type="application/zip", filename=Path(path).name)


# -------------------- ERAYA HUB ADD-ON (UI shell) --------------------
def _eraya_style_page(title: str, body_html: str) -> HTMLResponse:
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} — Eraya Ops</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    :root {{ --brand:#a78bfa; --brand-strong:#8b5cf6; --accent:#f0abfc; }}
    .glass{{backdrop-filter:blur(10px);background:linear-gradient(180deg,rgba(255,255,255,.06),rgba(255,255,255,.02));border:1px solid rgba(255,255,255,.12);border-radius:1.25rem;}}
    .btn{{display:inline-flex;align-items:center;justify-content:center;border-radius:1rem;padding:.6rem 1rem;font-weight:600;box-shadow:0 6px 20px rgba(168,139,250,.25), inset 0 1px 0 rgba(255,255,255,.08);}}
    .btn-primary{{background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416}}
    .btn-secondary{{background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.2)}}
    *{{scrollbar-width:thin;scrollbar-color:var(--brand) #0f172a}}
    *::-webkit-scrollbar{{height:8px;width:8px}}
    *::-webkit-scrollbar-thumb{{background:var(--brand);border-radius:8px}}

    /* Sidebar Styles */
    .sidebar {{
      width: 280px;
      transition: width 0.3s ease;
    }}
    .sidebar.collapsed {{
      width: 80px;
    }}
    .sidebar-item {{
      display: flex;
      align-items: center;
      padding: 12px 16px;
      margin: 4px 8px;
      border-radius: 12px;
      transition: all 0.2s ease;
      cursor: pointer;
      text-decoration: none;
      color: rgba(255,255,255,0.7);
    }}
    .sidebar-item:hover {{
      background: rgba(255,255,255,0.08);
      color: white;
      transform: translateX(4px);
    }}
    .sidebar-item.active {{
      background: linear-gradient(135deg,var(--brand-strong),var(--accent));
      color: #0b0416;
      font-weight: 600;
    }}
    .sidebar-item.disabled {{
      opacity: 0.5;
      cursor: not-allowed;
    }}
    .sidebar-item.locked {{
      opacity: 0.6;
      cursor: not-allowed;
      background: rgba(255,255,255,0.02);
    }}
    .sidebar-item.locked:hover {{
      background: rgba(255,255,255,0.04);
      transform: none;
      color: rgba(255,255,255,0.5);
    }}
    .sidebar-lock {{
      font-size: 12px;
      margin-left: auto;
      opacity: 0.7;
      color: #fbbf24;
    }}
    .sidebar-icon {{
      width: 24px;
      height: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      margin-right: 12px;
    }}
    .sidebar-text {{
      flex: 1;
      font-size: 14px;
      font-weight: 500;
    }}
    .sidebar.collapsed .sidebar-text {{
      display: none;
    }}
    .sidebar-badge {{
      background: rgba(239, 68, 68, 0.9);
      color: white;
      font-size: 10px;
      padding: 2px 6px;
      border-radius: 10px;
      font-weight: 600;
    }}
    .sidebar.collapsed .sidebar-badge {{
      display: none;
    }}
    .sidebar-separator {{
      margin: 16px 12px 8px 12px;
      padding: 8px 4px;
      font-size: 11px;
      font-weight: 600;
      color: rgba(255,255,255,0.4);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-top: 1px solid rgba(255,255,255,0.1);
    }}
    .sidebar.collapsed .sidebar-separator {{
      display: none;
    }}
    .main-content {{
      margin-left: 280px;
      transition: margin-left 0.3s ease;
    }}
    .main-content.expanded {{
      margin-left: 80px;
    }}
    .role-badge {{
      background: linear-gradient(135deg, #10b981, #059669);
      color: white;
      font-size: 10px;
      padding: 2px 8px;
      border-radius: 12px;
      font-weight: 600;
      text-transform: uppercase;
    }}
    .role-badge.manager {{
      background: linear-gradient(135deg, #f59e0b, #d97706);
    }}
    .role-badge.admin {{
      background: linear-gradient(135deg, #dc2626, #b91c1c);
    }}
    
    @media (max-width: 768px) {{
      .sidebar {{
        transform: translateX(-100%);
        z-index: 50;
      }}
      .sidebar.mobile-open {{
        transform: translateX(0);
      }}
      .main-content {{
        margin-left: 0;
      }}
    }}
  </style>
</head>
<body class="min-h-screen text-white bg-gradient-to-br from-slate-950 via-indigo-950 to-fuchsia-900">
  
  <!-- Side Navigation -->
  <div id="sidebar" class="sidebar fixed left-0 top-0 h-full glass border-r border-white/10 z-30 flex flex-col">
    <!-- Logo & User Section -->
    <div class="p-4 border-b border-white/10">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl flex-shrink-0" style="background:linear-gradient(135deg,var(--brand),var(--accent))"></div>
        <div class="flex-1 min-w-0">
          <div class="text-lg font-semibold tracking-wide">Eraya Ops</div>
                <div id="userInfo" class="flex items-center gap-2 mt-1">
        <span class="text-xs text-white/60">Admin Access</span>
        <span class="role-badge admin">Full Access</span>
      </div>
    </div>
    <button id="sidebarToggle" class="p-2 hover:bg-white/10 rounded-lg">
      <span class="text-lg">⟨</span>
    </button>
  </div>
    </div>

    <!-- Navigation Menu -->
    <div class="flex-1 overflow-y-auto py-4" id="navigationMenu">
      <!-- Navigation will be loaded here by JavaScript -->
    </div>

    <!-- Quick Actions -->
    <div class="p-4 border-t border-white/10">
      <div class="sidebar-item" onclick="window.location.href='/hub'">
        <div class="sidebar-icon">🏠</div>
        <div class="sidebar-text">Home</div>
      </div>
      <div class="sidebar-item" onclick="logout()" style="cursor: pointer;">
        <div class="sidebar-icon">🚪</div>
        <div class="sidebar-text">Logout</div>
      </div>
    </div>
  </div>

  <!-- Main Content Area -->
  <div id="mainContent" class="main-content min-h-screen">
    <!-- Top Header (Mobile) -->
    <header class="sticky top-0 z-20 backdrop-blur bg-slate-900/40 border-b border-white/10 md:hidden">
      <div class="px-4 py-4 flex items-center justify-between">
        <button id="mobileMenuToggle" class="p-2 hover:bg-white/10 rounded-lg">
          <span class="text-lg">☰</span>
        </button>
        <div class="text-lg font-semibold">Eraya Ops</div>
        <div class="w-8"></div>
    </div>
  </header>

    <main class="px-4 py-10 md:px-8 lg:px-12">
    {body_html}
  </main>

  <footer class="border-t border-white/10 py-8 text-center text-white/70">
    Built with ❤️ for Eraya — {title}
  </footer>
  </div>

  <script>
    // Global state
    let sidebarCollapsed = false;
    
    // Logout function
    async function logout() {{
      try {{
        const response = await fetch('/api/auth/logout', {{
          method: 'POST',
          credentials: 'include'
        }});
        
        // Always redirect to login, regardless of response
        window.location.href = '/login';
      }} catch (error) {{
        console.error('Logout error:', error);
        // Still redirect to login on error
        window.location.href = '/login';
      }}
    }}

    // DOM elements
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('mainContent');
    const navigationMenu = document.getElementById('navigationMenu');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const mobileMenuToggle = document.getElementById('mobileMenuToggle');

    // Toggle sidebar
    function toggleSidebar() {{
        sidebarCollapsed = !sidebarCollapsed;
        if (sidebarCollapsed) {{
            sidebar.classList.add('collapsed');
            mainContent.classList.add('expanded');
            sidebarToggle.innerHTML = '<span class="text-lg">⟩</span>';
        }} else {{
            sidebar.classList.remove('collapsed');
            mainContent.classList.remove('expanded');
            sidebarToggle.innerHTML = '<span class="text-lg">⟨</span>';
        }}
        // Save state
        localStorage.setItem('sidebarCollapsed', sidebarCollapsed.toString());
    }}

    // Mobile menu toggle
    function toggleMobileMenu() {{
        sidebar.classList.toggle('mobile-open');
    }}

    // Load navigation menu directly
    async function loadNavigation() {{
        try {{
            const response = await fetch('/api/auth/navigation');
            if (!response.ok) {{
                throw new Error(`HTTP ${{response.status}}: ${{response.statusText}}`);
            }}
            const data = await response.json();
            
            // Render navigation menu
            renderNavigationMenu(data.menu);
            
        }} catch (error) {{
            console.error('Error loading navigation:', error);
            navigationMenu.innerHTML = '<div class="text-center text-red-400 text-sm p-4">Error loading navigation</div>';
        }}
    }}
    
    // Refresh navigation (useful when roles change)
    window.refreshNavigation = loadNavigation;
    
    // Auto-refresh navigation when user role might have changed
    let lastKnownRole = null;
    
    async function checkRoleChange() {{
        try {{
            const response = await fetch('/api/auth/me');
            if (response.ok) {{
                const userData = await response.json();
                if (lastKnownRole && lastKnownRole !== userData.role) {{
                    // Role has changed, refresh navigation
                    console.log(`Role changed from ${{lastKnownRole}} to ${{userData.role}}`);
                    await loadNavigation();
                }}
                lastKnownRole = userData.role;
            }}
        }} catch (error) {{
            console.error('Error checking role change:', error);
        }}
    }}
    
    // Check for role changes every 10 seconds
    setInterval(checkRoleChange, 10000);
    
    // Initial role check
    checkRoleChange();

    // Render navigation menu
    function renderNavigationMenu(menuItems) {{
        let html = '';
        
        menuItems.forEach(item => {{
            if (item.type === 'separator') {{
                html += `<div class="sidebar-separator">${{item.name}}</div>`;
            }} else {{
                const activeClass = window.location.pathname === item.url ? 'active' : '';
                const disabledClass = !item.active ? 'disabled' : '';
                const lockedClass = item.locked ? 'locked' : '';
                const badge = item.badge ? `<span class="sidebar-badge">${{item.badge}}</span>` : '';
                const lockIcon = item.locked ? `<span class="sidebar-lock">🔒</span>` : '';
                
                // If locked, make it non-clickable and show lock
                const href = item.locked ? '#' : (item.active ? item.url : '#');
                const onclick = item.locked ? 'onclick="return false;"' : (!item.active ? 'onclick="return false;"' : '');
                
                html += `
                    <a href="${{href}}" class="sidebar-item ${{activeClass}} ${{disabledClass}} ${{lockedClass}}" ${{onclick}}>
                        <div class="sidebar-icon">${{item.icon}}</div>
                        <div class="sidebar-text">${{item.name}}</div>
                        ${{lockIcon}}
                        ${{badge}}
                    </a>
                `;
            }}
        }});
        
        navigationMenu.innerHTML = html;
    }}

    // Event listeners
    sidebarToggle.addEventListener('click', toggleSidebar);
    mobileMenuToggle?.addEventListener('click', toggleMobileMenu);

    // Initialize sidebar - ENSURE THIS RUNS AFTER DOM IS READY
    function initializeSidebar() {{
        // Restore sidebar collapsed state
        const savedCollapsed = localStorage.getItem('sidebarCollapsed');
        if (savedCollapsed === 'true') {{
            sidebarCollapsed = true;
            sidebar.classList.add('collapsed');
            mainContent.classList.add('expanded');
            sidebarToggle.innerHTML = '<span class="text-lg">⟩</span>';
        }}
        
        // Load navigation menu directly
        loadNavigation();
    }}
    
    // Initialize after a short delay to ensure DOM is ready
    setTimeout(initializeSidebar, 100);
    
    // Also initialize when DOM is fully loaded (backup)
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', initializeSidebar);
    }} else {{
        // DOM is already loaded, initialize immediately as backup
        initializeSidebar();
    }}

    // Handle responsive behavior
    function handleResize() {{
        if (window.innerWidth < 768) {{
            mainContent.style.marginLeft = '0';
        }} else {{
            sidebar.classList.remove('mobile-open');
            mainContent.style.marginLeft = sidebarCollapsed ? '80px' : '280px';
        }}
    }}

    window.addEventListener('resize', handleResize);
    handleResize(); // Initial call

    // Close mobile menu when clicking outside
    document.addEventListener('click', function(e) {{
        if (window.innerWidth < 768 && !sidebar.contains(e.target) && !mobileMenuToggle?.contains(e.target)) {{
            sidebar.classList.remove('mobile-open');
        }}
    }});
  </script>
</body>
</html>
"""
    return HTMLResponse(html)


# -------------------- ROOT REDIRECT --------------------
@app.get("/")
def root():
    """Redirect root to login page."""
    return RedirectResponse(url="/login")
# -------------------- LOGIN PAGE --------------------
@app.get("/login")
def login_page():
    """Login page for employee authentication."""
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Eraya Ops - Login</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #581c87 100%);
            min-height: 100vh;
        }
        .glass {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .btn-primary {
            background: linear-gradient(135deg, #3b82f6, #1d4ed8);
            transition: all 0.3s ease;
        }
        .btn-primary:hover {
            background: linear-gradient(135deg, #2563eb, #1e40af);
            transform: translateY(-2px);
        }
        .input-field {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
        }
        .input-field:focus {
            border-color: #3b82f6;
            background: rgba(255, 255, 255, 0.08);
        }
    </style>
</head>
<body class="min-h-screen flex items-center justify-center text-white">
    <div class="w-full max-w-md p-6">
        <!-- Logo Section -->
        <div class="text-center mb-8">
            <div class="w-16 h-16 mx-auto mb-4 rounded-xl glass flex items-center justify-center">
                <span class="text-2xl">🏭</span>
            </div>
            <h1 class="text-3xl font-bold mb-2">Eraya Ops</h1>
            <p class="text-white/60">Employee Portal Login</p>
        </div>

        <!-- Login Form -->
        <div class="glass rounded-2xl p-8">
            <form id="loginForm">
                <div class="space-y-6">
                    <div>
                        <label for="employee_id" class="block text-sm font-medium text-white/90 mb-2">
                            Employee ID
                        </label>
                        <input type="text" id="employee_id" name="employee_id" required
                               class="w-full px-4 py-3 rounded-xl input-field text-white placeholder-white/50 focus:outline-none"
                               placeholder="Enter your Employee ID (e.g., EMP001)">
                    </div>

                    <div>
                        <label for="password" class="block text-sm font-medium text-white/90 mb-2">
                            Password
                        </label>
                        <input type="password" id="password" name="password" required
                               class="w-full px-4 py-3 rounded-xl input-field text-white placeholder-white/50 focus:outline-none"
                               placeholder="Enter your password">
                    </div>

                    <div class="flex items-center">
                        <input type="checkbox" id="remember_me" name="remember_me" 
                               class="w-4 h-4 text-blue-600 bg-transparent border-white/30 rounded focus:ring-blue-500">
                        <label for="remember_me" class="ml-2 text-sm text-white/80">
                            Remember me for 30 days
                        </label>
                    </div>

                    <button type="submit" id="loginBtn"
                            class="w-full py-3 px-4 rounded-xl btn-primary text-white font-semibold">
                        Sign In
                    </button>
                </div>
            </form>

            <!-- Error Message -->
            <div id="errorMessage" class="mt-4 p-3 rounded-lg bg-red-500/20 border border-red-500/30 text-red-200 text-sm hidden">
                <span id="errorText"></span>
            </div>

            <!-- Loading State -->
            <div id="loadingState" class="mt-4 text-center text-white/60 hidden">
                <span class="inline-block animate-spin">⚪</span>
                Signing in...
            </div>
        </div>

        <!-- Default Credentials Help -->
        <div class="mt-6 text-center">
            <details class="glass rounded-lg p-4">
                <summary class="cursor-pointer text-white/80 text-sm">Default Login Credentials</summary>
                <div class="mt-3 text-xs text-white/60 space-y-1">
                    <div><strong>Owner:</strong> rishavdarsh / ER9919@</div>
                    <div><strong>Admin:</strong> EMP001 / admin123</div>
                    <div><strong>Admin:</strong> EMP002 / admin123</div>
                    <div><strong>Manager:</strong> EMP003 / manager123</div>
                    <div><strong>Packer:</strong> EMP004 / packer123</div>
                    <div><strong>Manager:</strong> EMP005 / manager123</div>
                    <div><strong>Packer:</strong> EMP006 / packer123</div>
                </div>
            </details>
        </div>
    </div>

    <script>
        const loginForm = document.getElementById('loginForm');
        const loginBtn = document.getElementById('loginBtn');
        const errorMessage = document.getElementById('errorMessage');
        const errorText = document.getElementById('errorText');
        const loadingState = document.getElementById('loadingState');

        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            // Show loading state
            loginBtn.disabled = true;
            loadingState.classList.remove('hidden');
            errorMessage.classList.add('hidden');

            // Get form data
            const formData = new FormData(loginForm);

            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (response.ok) {
                    // Login successful - redirect to hub
                    window.location.href = '/hub';
                } else {
                    // Show error message
                    errorText.textContent = result.detail || 'Login failed';
                    errorMessage.classList.remove('hidden');
                }
            } catch (error) {
                errorText.textContent = 'Network error. Please try again.';
                errorMessage.classList.remove('hidden');
            } finally {
                // Hide loading state
                loginBtn.disabled = false;
                loadingState.classList.add('hidden');
            }
        });

        // Auto-focus first input
        document.getElementById('employee_id').focus();
    </script>
</body>
</html>
    """
    return HTMLResponse(html)

@app.get("/chat")
def chat_page(request: Request, current_user: Dict = Depends(require_roles())):
    """Chat interface."""
    return templates.TemplateResponse("chat.html", {"request": request})


# Redirect /dashboard to /hub for compatibility
@app.get("/dashboard")
def dashboard_redirect():
    return RedirectResponse(url="/hub")

@app.get("/hub")
def eraya_hub_home(request: Request, current_user: Dict = Depends(require_roles())):
    # Get user info for personalized greeting
    user_name = current_user.get("name", "User")
    first_name = user_name.split()[0] if user_name else "User"
    
    # Generate time-based greeting
    from datetime import datetime as dt
    current_hour = dt.now().hour
    
    if 5 <= current_hour < 12:
        time_greeting = "Good morning"
        day_message = "Ready to make today productive? ☀️"
    elif 12 <= current_hour < 17:
        time_greeting = "Good afternoon"  
        day_message = "Hope your day is going smoothly! 🌤️"
    elif 17 <= current_hour < 21:
        time_greeting = "Good evening"
        day_message = "Wrapping up another great day? 🌅"
    else:
        time_greeting = "Good evening"
        day_message = "Working late? You're dedicated! 🌙"
    

    greeting_section = f"""
    <!-- Personalized Greeting Section -->
    <section class="mt-8 mb-6">
      <div class="glass p-6 text-center max-w-2xl mx-auto">
        <div class="text-2xl font-semibold text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-400">
          {time_greeting}, {first_name}! 👋
        </div>
        <p class="mt-2 text-white/70">{day_message}</p>
        <div class="mt-3 text-sm text-white/50">
          Welcome back to your dashboard
        </div>
      </div>
    </section>
    """
    
    body = """
    <!-- Header Section -->
    <section class="text-center">
      <h1 class="text-4xl md:text-5xl font-bold">Eraya Ops Hub</h1>
      <p class="mt-3 text-white/80">Fast, reliable tools for fulfillment — all in one place.</p>
    </section>

    """ + greeting_section + """

    <!-- Dashboard Overview Section -->
    <section class="mt-10">
      <h2 class="text-2xl font-bold mb-6">Dashboard Overview</h2>
      <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-5" id="statsCards">
        <div class="glass p-5 text-center">
          <div class="text-3xl font-bold text-blue-400" id="ordersToday">-</div>
          <p class="text-white/70 text-sm">Orders Today</p>
          <div id="shopifyStatus" class="mt-1 text-xs text-white/50">📊 Shopify</div>
        </div>
        <div class="glass p-5 text-center">
          <div class="text-3xl font-bold text-green-400" id="activeEmployees">-</div>
          <p class="text-white/70 text-sm">Active Employees</p>
        </div>
        <div class="glass p-5 text-center">
          <div class="text-3xl font-bold text-yellow-400" id="pendingOrders">-</div>
          <p class="text-white/70 text-sm">Pending Orders</p>
        </div>
        <div class="glass p-5 text-center">
          <div class="text-3xl font-bold text-purple-400" id="ordersWeek">-</div>
          <p class="text-white/70 text-sm">Orders This Week</p>
        </div>
      </div>
      
      <!-- Revenue Cards (Shopify Integration) -->
      <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-5 mt-6" id="revenueCards">
        <div class="glass p-5 text-center">
          <div class="text-2xl font-bold text-emerald-400" id="todayRevenue">-</div>
          <p class="text-white/70 text-sm">Today's Revenue</p>
        </div>
        <div class="glass p-5 text-center">
          <div class="text-2xl font-bold text-teal-400" id="totalRevenue">-</div>
          <p class="text-white/70 text-sm">Total Revenue</p>
        </div>
        <div class="glass p-5 text-center">
          <div class="text-2xl font-bold text-cyan-400" id="fulfilledOrders">-</div>
          <p class="text-white/70 text-sm">Fulfilled Orders</p>
        </div>
      </div>
    </section>

    <!-- Quick Tools Section -->
    <section class="mt-10">
      <h2 class="text-2xl font-bold mb-6">Quick Tools</h2>
      <div class="glass p-6">
        <div class="grid sm:grid-cols-1 lg:grid-cols-3 gap-6">
          <!-- Employee Lookup -->
          <div>
            <h3 class="text-lg font-semibold mb-3">Employee Lookup</h3>
            <div class="flex gap-2">
              <input type="text" id="employeeSearch" placeholder="Search employee..." class="flex-1 rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <button id="searchEmployeeBtn" class="btn btn-primary">Search</button>
            </div>
            <div id="employeeResults" class="mt-2 text-sm"></div>
          </div>
          
          <!-- Order Search -->
          <div>
            <h3 class="text-lg font-semibold mb-3">Search Orders</h3>
            <div class="flex gap-2">
              <input type="text" id="orderSearch" placeholder="Order ID..." class="flex-1 rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <button id="searchOrderBtn" class="btn btn-primary">Search</button>
            </div>
            <div id="orderResults" class="mt-2 text-sm text-white/70">Feature coming soon...</div>
          </div>
          
          <!-- Quick Export -->
          <div>
            <h3 class="text-lg font-semibold mb-3">Quick Export</h3>
            <div class="flex gap-2">
              <select id="exportType" class="flex-1 rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
                <option value="attendance">Attendance Data</option>
                <option value="orders" disabled>Orders Data (Soon)</option>
              </select>
              <button id="quickExportBtn" class="btn btn-secondary">Export</button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Core Operations -->
    <section class="mt-10">
      <h2 class="text-2xl font-bold mb-6">Core Operations</h2>
      <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
      <a href="/orders" class="glass p-5 block hover:translate-y-[-2px] transition-all shadow-xl">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
               style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">🧭</div>
          <h3 class="text-xl font-semibold">Order Organizer</h3>
        </div>
        <p class="text-white/70 mt-3">Clean CSVs, download photos/polaroids, generate back messages & exports.</p>
          <div class="mt-2 text-xs text-blue-400">Ready to process</div>
      </a>

      <a href="/packing" class="glass p-5 block hover:translate-y-[-2px] transition-all shadow-xl">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
               style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">📦</div>
          <h3 class="text-xl font-semibold">Packing Management</h3>
        </div>
        <p class="text-white/70 mt-3">Visual picker table with thumbnails & engraving details.</p>
          <div class="mt-2 text-xs text-green-400">Items ready to pack</div>
      </a>

        <a href="/attendance" class="glass p-5 block hover:translate-y-[-2px] transition-all shadow-xl">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">🗓️</div>
            <h3 class="text-xl font-semibold">Employee Attendance</h3>
        </div>
          <p class="text-white/70 mt-3">Track employee check-ins, hours, and generate reports.</p>
          <div class="mt-2 text-xs text-yellow-400" id="attendanceStatus">Loading...</div>
      </a>

        <a href="/attendance/report_page" class="glass p-5 block hover:translate-y-[-2px] transition-all shadow-xl">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">📊</div>
            <h3 class="text-xl font-semibold">Reports & Analytics</h3>
        </div>
          <p class="text-white/70 mt-3">Comprehensive attendance reports with filtering options.</p>
          <div class="mt-2 text-xs text-purple-400">View detailed reports</div>
        </a>

        <a href="/chat" class="glass p-5 block hover:translate-y-[-2px] transition-all shadow-xl">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">💬</div>
            <h3 class="text-xl font-semibold">Team Chat</h3>
          </div>
          <p class="text-white/70 mt-3">Advanced team communication with channels, DMs, and reactions.</p>
          <div class="mt-2 text-xs text-blue-400">Real-time messaging</div>
        </a>
      </div>
    </section>

    <!-- Additional Modules -->
    <section class="mt-10">
      <h2 class="text-2xl font-bold mb-6">Additional Modules</h2>
      <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div class="glass p-5 opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">📝</div>
            <h3 class="text-xl font-semibold">Content</h3>
          </div>
          <p class="text-white/70 mt-3">Manage product descriptions, images, and marketing content.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </div>

        <div class="glass p-5 opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">📢</div>
            <h3 class="text-xl font-semibold">Marketing</h3>
          </div>
          <p class="text-white/70 mt-3">Campaign management, social media, and promotional tools.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </div>

        <div class="glass p-5 opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">🚚</div>
            <h3 class="text-xl font-semibold">Orders & Fulfillment</h3>
          </div>
          <p class="text-white/70 mt-3">Advanced order management and shipping coordination.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </div>

        <div class="glass p-5 opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">🎧</div>
            <h3 class="text-xl font-semibold">Customer Service</h3>
          </div>
          <p class="text-white/70 mt-3">Support tickets, customer communications, and issue tracking.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </div>

        <div class="glass p-5 opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">📦</div>
            <h3 class="text-xl font-semibold">Inventory & Supplies</h3>
          </div>
          <p class="text-white/70 mt-3">Stock management, supplier relations, and procurement.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </div>

        <div class="glass p-5 opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">👥</div>
            <h3 class="text-xl font-semibold">Team & Admin</h3>
          </div>
          <p class="text-white/70 mt-3">User management, permissions, and system administration.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </div>

        <div class="glass p-5 opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">✅</div>
            <h3 class="text-xl font-semibold">Daily Tasks</h3>
          </div>
          <p class="text-white/70 mt-3">Task management, checklists, and workflow automation.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </div>

        <a href="/pending" class="glass p-5 block hover:translate-y-[-2px] transition-all shadow-xl opacity-60">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center text-xl"
                 style="background:linear-gradient(135deg,var(--brand-strong),var(--accent));color:#0b0416)">⏳</div>
            <h3 class="text-xl font-semibold">Pending Orders</h3>
          </div>
          <p class="text-white/70 mt-3">Flag missing photo/variant/back-message.</p>
          <div class="mt-2 text-xs text-gray-400">Coming Soon</div>
        </a>
      </div>
    </section>

    <!-- Team Chat Widget -->
    <div id="chatWidget" class="fixed bottom-4 right-4 z-50">
      <div id="chatToggle" class="glass p-3 rounded-full cursor-pointer shadow-lg hover:scale-105 transition-transform">
        <div class="flex items-center gap-2">
          <span class="text-xl">💬</span>
          <span class="text-sm font-semibold">Team Chat</span>
          <div id="chatNotification" class="w-2 h-2 bg-red-500 rounded-full hidden"></div>
        </div>
      </div>
      
      <div id="chatPanel" class="hidden mt-2 glass rounded-lg shadow-xl" style="width: 300px; height: 400px;">
        <div class="p-3 border-b border-white/10">
          <div class="flex items-center justify-between">
            <h3 class="font-semibold">Team Chat</h3>
            <button id="chatClose" class="text-white/60 hover:text-white">✕</button>
          </div>
        </div>
        
        <div id="chatMessages" class="flex-1 p-3 overflow-y-auto" style="height: 280px;">
          <div class="text-center text-white/60 text-sm">Loading messages...</div>
        </div>
        
        <div class="p-3 border-t border-white/10">
          <div class="flex items-center gap-2">
            <select id="chatEmployeeSelect" class="flex-1 rounded bg-slate-900/60 border border-white/10 px-2 py-1 text-xs">
              <option value="">Select your name</option>
            </select>
          </div>
          <div class="flex items-center gap-2 mt-2">
            <input type="text" id="chatMessage" placeholder="Type message..." class="flex-1 rounded bg-slate-900/60 border border-white/10 px-2 py-1 text-sm" maxlength="200">
            <button id="chatSend" class="btn btn-primary text-xs px-3 py-1">Send</button>
          </div>
        </div>
      </div>
    </div>

    <script>
      // Fetch and display dashboard stats
      async function loadDashboardStats() {
        try {
          const response = await fetch('/api/dashboard/stats');
          const stats = await response.json();
          
          document.getElementById('ordersToday').textContent = stats.total_orders_today;
          document.getElementById('activeEmployees').textContent = stats.active_employees;
          document.getElementById('pendingOrders').textContent = stats.pending_orders;
          document.getElementById('ordersWeek').textContent = stats.total_orders_week;
          
          // Update Shopify revenue data
          const currency = stats.currency || 'USD';
          document.getElementById('todayRevenue').textContent = `${currency} ${stats.today_revenue || 0}`;
          document.getElementById('totalRevenue').textContent = `${currency} ${stats.total_revenue || 0}`;
          document.getElementById('fulfilledOrders').textContent = stats.fulfilled_orders || 0;
          
          // Update Shopify connection status
          const shopifyStatusEl = document.getElementById('shopifyStatus');
          if (stats.shopify_configured) {
            shopifyStatusEl.textContent = '🛒 Connected';
            shopifyStatusEl.className = 'mt-1 text-xs text-green-400';
          } else {
            shopifyStatusEl.innerHTML = '⚠️ <a href="/shopify/settings" class="text-yellow-400 hover:text-yellow-300">Setup Required</a>';
            shopifyStatusEl.className = 'mt-1 text-xs text-yellow-400';
          }
          
          // Update attendance status
          const attendanceStatusEl = document.getElementById('attendanceStatus');
          if (stats.active_employees > 0) {
            attendanceStatusEl.textContent = `${stats.active_employees} employees working`;
            attendanceStatusEl.className = 'mt-2 text-xs text-green-400';
          } else {
            attendanceStatusEl.textContent = 'No one checked in';
            attendanceStatusEl.className = 'mt-2 text-xs text-red-400';
          }
          
        } catch (error) {
          console.error('Error loading dashboard stats:', error);
        }
      }

      // Employee search functionality
      document.getElementById('searchEmployeeBtn').addEventListener('click', async function() {
        const query = document.getElementById('employeeSearch').value;
        const resultsEl = document.getElementById('employeeResults');
        
        if (!query.trim()) {
          resultsEl.innerHTML = '<p class="text-red-400">Please enter a search term.</p>';
          return;
        }
        
        try {
          const response = await fetch(`/api/search/employee?query=${encodeURIComponent(query)}`);
          const data = await response.json();
          
          if (data.results.length === 0) {
            resultsEl.innerHTML = '<p class="text-yellow-400">No employees found.</p>';
          } else {
            let html = '<div class="space-y-1">';
            data.results.forEach(emp => {
              const statusColor = emp.status === 'Checked In' ? 'text-green-400' : 'text-red-400';
              html += `<div class="flex justify-between items-center p-2 bg-slate-800/50 rounded">
                <span><strong>${emp.name}</strong> (${emp.employee_id})</span>
                <span class="${statusColor}">${emp.status}</span>
              </div>`;
            });
            html += '</div>';
            resultsEl.innerHTML = html;
          }
        } catch (error) {
          resultsEl.innerHTML = '<p class="text-red-400">Error searching employees.</p>';
        }
      });

      // Quick export functionality
      document.getElementById('quickExportBtn').addEventListener('click', async function() {
        const exportType = document.getElementById('exportType').value;
        
        if (exportType === 'attendance') {
          try {
            const response = await fetch('/api/attendance/export');
            if (!response.ok) {
              alert('No attendance data to export.');
              return;
            }
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'attendance_export.csv';
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
          } catch (error) {
            alert('Error exporting data.');
          }
        }
      });

      // Enter key support for searches
      document.getElementById('employeeSearch').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
          document.getElementById('searchEmployeeBtn').click();
        }
      });

      // Load dashboard stats on page load
      loadDashboardStats();
      
      // Refresh stats every 30 seconds
      setInterval(loadDashboardStats, 30000);

      // ==================== TEAM CHAT FUNCTIONALITY ====================
      const chatToggle = document.getElementById('chatToggle');
      const chatPanel = document.getElementById('chatPanel');
      const chatClose = document.getElementById('chatClose');
      const chatEmployeeSelect = document.getElementById('chatEmployeeSelect');
      const chatMessage = document.getElementById('chatMessage');
      const chatSend = document.getElementById('chatSend');
      const chatMessages = document.getElementById('chatMessages');
      const chatNotification = document.getElementById('chatNotification');

      let lastMessageCount = 0;
      let isChatOpen = false;

      // Populate chat employee dropdown
      const employees = {
          "Ritik": "EMP001",
          "Sunny": "EMP002",
          "Rahul": "EMP003",
          "Sumit": "EMP004",
          "Vishal": "EMP005",
          "Nishant": "EMP006",
      };

      // Role-based icon mapping for chat
      const chatRoleIcons = {
          'Super Admin': '👑', 'Admin': '🛡️', 'Manager': '🎯', 'Employee': '⭐'
      };
      
      const chatEmployeeRoles = {
          'EMP001': 'Super Admin', 'EMP002': 'Admin', 'EMP003': 'Manager',
          'EMP004': 'Employee', 'EMP005': 'Manager', 'EMP006': 'Employee'
      };

      for (const name in employees) {
          const empId = employees[name];
          const role = chatEmployeeRoles[empId] || 'Employee';
          const icon = chatRoleIcons[role] || '👤';
          const option = document.createElement('option');
          option.value = empId;
          option.textContent = `${icon} ${name}`;
          chatEmployeeSelect.appendChild(option);
      }

      // Toggle chat panel
      chatToggle.addEventListener('click', function() {
          isChatOpen = !isChatOpen;
          if (isChatOpen) {
              chatPanel.classList.remove('hidden');
              chatNotification.classList.add('hidden');
              loadChatMessages();
          } else {
              chatPanel.classList.add('hidden');
          }
      });

      chatClose.addEventListener('click', function() {
          isChatOpen = false;
          chatPanel.classList.add('hidden');
      });

      // Load chat messages
      async function loadChatMessages() {
          try {
              const response = await fetch('/api/chat/messages?limit=20');
              const data = await response.json();
              
              displayChatMessages(data.messages);
              
              // Show notification if new messages and chat is closed
              if (!isChatOpen && data.messages.length > lastMessageCount) {
                  chatNotification.classList.remove('hidden');
              }
              lastMessageCount = data.messages.length;
              
          } catch (error) {
              console.error('Error loading chat messages:', error);
              chatMessages.innerHTML = '<div class="text-center text-red-400 text-sm">Error loading messages</div>';
          }
      }

      // Display chat messages
      function displayChatMessages(messages) {
          if (messages.length === 0) {
              chatMessages.innerHTML = '<div class="text-center text-white/60 text-sm">No messages yet. Start the conversation!</div>';
              return;
          }

          // Role-based icon data for chat messages
          const chatMessageRoleIcons = {
              'Super Admin': {icon: '👑', icon_color: '#FFD700'},
              'Admin': {icon: '🛡️', icon_color: '#4F46E5'},
              'Manager': {icon: '🎯', icon_color: '#EF4444'},
              'Employee': {icon: '⭐', icon_color: '#10B981'}
          };
          
          const messageEmployeeRoles = {
              'EMP001': 'Super Admin', 'EMP002': 'Admin', 'EMP003': 'Manager',
              'EMP004': 'Employee', 'EMP005': 'Manager', 'EMP006': 'Employee'
          };

          let html = '';
          messages.forEach(msg => {
              const time = new Date(msg.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
              const role = messageEmployeeRoles[msg.employee_id] || 'Employee';
              const userIcon = chatMessageRoleIcons[role] || {icon: '👤', icon_color: '#6b7280'};
              
              html += `
                  <div class="mb-3">
                      <div class="flex items-center gap-2 mb-1">
                          <div class="w-5 h-5 rounded-full flex items-center justify-center text-xs profile-icon" 
                               style="background: ${userIcon.icon_color}; border: 1px solid rgba(255,255,255,0.5);">
                              ${userIcon.icon}
                          </div>
                          <span class="font-semibold text-sm text-blue-400">${msg.employee_name}</span>
                          <span class="text-xs text-white/50">${time}</span>
                      </div>
                      <div class="text-sm bg-slate-800/50 rounded-lg p-2 ml-7">${msg.message}</div>
                  </div>
              `;
          });
          
          chatMessages.innerHTML = html;
          // Scroll to bottom
          chatMessages.scrollTop = chatMessages.scrollHeight;
      }

      // Send message
      async function sendChatMessage() {
          const employeeId = chatEmployeeSelect.value;
          const message = chatMessage.value.trim();
          
          if (!employeeId) {
              alert('Please select your name first.');
              return;
          }
          
          if (!message) {
              alert('Please enter a message.');
              return;
          }
          
          try {
              const formData = new FormData();
              formData.append('employee_id', employeeId);
              formData.append('message', message);
              
              const response = await fetch('/api/chat/send', {
                  method: 'POST',
                  body: formData
              });
              
              if (response.ok) {
                  chatMessage.value = '';
                  loadChatMessages();
              } else {
                  alert('Error sending message.');
              }
              
          } catch (error) {
              console.error('Error sending message:', error);
              alert('Error sending message.');
          }
      }

      // Event listeners for sending messages
      chatSend.addEventListener('click', sendChatMessage);
      
      chatMessage.addEventListener('keypress', function(e) {
          if (e.key === 'Enter') {
              sendChatMessage();
          }
      });

      // Load messages initially and refresh every 10 seconds
      loadChatMessages();
      setInterval(loadChatMessages, 10000);
    </script>
    """
    # Prepare template context
    stats = {
        "orders_today": 12,
        "active_employees": 0,
        "pending_orders": 23,
        "orders_this_week": 156,
        "todays_revenue": "1234.56",
        "total_revenue": "45678.9",
        "fulfilled_orders": 133
    }
    
    return templates.TemplateResponse("hub.html", {
        "request": request,
        "time_greeting": time_greeting,
        "first_name": first_name,
        "day_message": day_message,
        "stats": stats
    })

# Redirect old /orders route to /order-organizer
@app.get("/orders")
def eraya_orders_page(current_user: Dict = Depends(require_roles("owner", "admin", "manager"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Order Management</h1>
      <p class="text-white/80 mt-2">Fetch and manage orders directly from your Shopify store.</p>
      
      <!-- Shopify Setup Notice -->
      <div id="shopifyNotice" class="bg-blue-500/20 border border-blue-500/30 rounded-xl p-4 mt-4" style="display: none;">
        <div class="flex items-center gap-3">
          <div class="text-2xl">ℹ️</div>
          <div>
            <div class="font-semibold text-blue-200">Shopify Setup Required</div>
            <div class="text-blue-300/80">Set environment variables: SHOPIFY_SHOP and SHOPIFY_TOKEN</div>
            <div class="text-xs text-blue-400 mt-1">
              Example: <code>set SHOPIFY_SHOP=your-store.myshopify.com</code> and <code>set SHOPIFY_TOKEN=your-token</code>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-6 grid gap-6">
        <div class="glass p-5">
          <div class="flex flex-wrap items-center gap-3">
            <button type="button" id="fetchOrders" class="btn btn-primary">Fetch from Shopify</button>
            <button type="button" id="fetchUnfulfilled" class="btn btn-primary">📦 Fetch ALL Unfulfilled (30 days)</button>
            <button type="button" id="fetchUnfulfilledCustom" class="btn btn-secondary">📅 Custom Date Range</button>
            <button type="button" id="fetchAllOrders" class="btn btn-accent">🚀 Fetch ALL Orders (All Pages)</button>
            <button type="button" id="exportOrders" class="btn btn-secondary">Export CSV (filtered)</button>
            <button type="button" id="exportSelected" class="btn btn-accent" disabled>Export Selected (<span id="selectedCount">0</span>)</button>
            <button type="button" id="downloadPhotos" class="btn btn-accent" disabled>Download Main Photos (<span id="selectedPhotos">0</span>)</button>
            <button type="button" id="downloadPolaroids" class="btn btn-accent" disabled>Download Polaroids (<span id="selectedPolaroids">0</span>)</button>
            <div id="status" class="text-white/70">🔄 Auto-fetching orders...</div>
          </div>
          <div class="flex flex-wrap items-center gap-3 mt-2">
            <button type="button" id="selectAll" class="btn btn-sm btn-secondary">Select All</button>
            <button type="button" id="selectNone" class="btn btn-sm btn-secondary">Select None</button>
            <button type="button" id="selectFiltered" class="btn btn-sm btn-secondary">Select Filtered</button>
            <div class="text-white/60 text-sm" id="selectionInfo">No items selected</div>
          </div>
          <div class="flex flex-wrap gap-3 mt-3">
            <input id="qOrder" placeholder="Search Order #" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <input id="qProd" placeholder="Search Product" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <input id="qVar" placeholder="Search Variant" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <select id="qStatus" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <option value="any">All Orders</option>
              <option value="open">Open</option>
              <option value="closed">Closed</option>
              <option value="cancelled">Cancelled</option>
            </select>
            <select id="qFulfillment" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <option value="any">All Fulfillment</option>
              <option value="fulfilled">Fulfilled</option>
              <option value="partial">Partially Fulfilled</option>
              <option value="unfulfilled">Unfulfilled</option>
              <option value="pending">Pending</option>
            </select>
            <input type="date" id="startDate" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm" title="Start Date">
            <input type="date" id="endDate" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm" title="End Date">
            <select id="pageSize" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <option value="25">25 / page</option>
              <option value="50">50 / page</option>
              <option value="100">100 / page</option>
            </select>
          </div>
        </div>

        <div class="glass p-0 overflow-auto" style="max-height:70vh">
          <table class="min-w-full text-sm" id="tbl">
            <thead class="sticky top-0 bg-slate-900/80 backdrop-blur" id="head"></thead>
            <tbody id="body"></tbody>
          </table>
        </div>
        
        <div class="flex items-center gap-3">
          <button id="prev" class="btn btn-secondary">Prev</button>
          <div id="pageinfo" class="text-white/70 text-sm"></div>
          <button id="next" class="btn btn-secondary">Next</button>
          <button id="loadMore" class="btn btn-primary" style="display: none;">Load More</button>
        </div>
      </div>

      <!-- Simple lightbox -->
      <div id="lb" class="fixed inset-0 hidden items-center justify-center bg-black/70 p-6">
        <div class="bg-slate-900/90 border border-white/10 rounded-2xl p-4 max-w-5xl w-full">
          <div class="flex justify-between items-center mb-3">
            <div class="text-lg font-semibold">Polaroids</div>
            <button id="lbClose" class="btn btn-secondary">Close</button>
          </div>
          <div id="lbBody" class="grid grid-cols-2 md:grid-cols-4 gap-3"></div>
        </div>
      </div>
    </section>

    <style>
      #body tr:nth-child(even){ background: rgba(255,255,255,0.03); }
      .badge-miss{ background:#ef4444; color:white; padding:2px 6px; border-radius:6px; font-size:12px; }
      #tbl tbody tr:hover { background-color: rgba(255,255,255,0.05); }
      #tbl th, #tbl td { padding: 0.75rem 0.5rem; text-align: left; vertical-align: top; }
      #tbl thead th { background-color: #0f172a; }
      
      /* Column Widths - adjusted for checkbox and fulfillment status */
      #tbl th:nth-child(1), #tbl td:nth-child(1) { width: 3%; /* Checkbox */ }
      #tbl th:nth-child(2), #tbl td:nth-child(2) { width: 9%; /* Order Number */ }
      #tbl th:nth-child(3), #tbl td:nth-child(3) { width: 14%; /* Product Name */ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
      #tbl th:nth-child(4), #tbl td:nth-child(4) { width: 9%; /* Variant */ }
      #tbl th:nth-child(5), #tbl td:nth-child(5) { width: 4%; /* Color */ }
      #tbl th:nth-child(6), #tbl td:nth-child(6) { width: 9%; /* Main Photo */ }
      #tbl th:nth-child(7), #tbl td:nth-child(7) { width: 9%; /* Polaroids */ }
      #tbl th:nth-child(8), #tbl td:nth-child(8) { width: 9%; /* Back Engraving Type */ }
      #tbl th:nth-child(9), #tbl td:nth-child(9) { width: 14%; /* Back Engraving Value */ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
      #tbl th:nth-child(10), #tbl td:nth-child(10) { width: 5%; /* Main Photo Status */ }
      #tbl th:nth-child(11), #tbl td:nth-child(11) { width: 4%; /* Polaroid Count */ }
      #tbl th:nth-child(12), #tbl td:nth-child(12) { width: 10%; /* Fulfillment Status */ }
      
      .truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .table-img { max-height: 80px; width: auto; }
      .btn-accent { background: linear-gradient(135deg, #8b5cf6, #a855f7); color: white; }
      .btn-accent:hover { background: linear-gradient(135deg, #7c3aed, #9333ea); }
      .btn-accent:disabled { opacity: 0.5; cursor: not-allowed; background: #6b7280; }
      .btn-sm { padding: 0.375rem 0.75rem; font-size: 0.875rem; }
      tr.selected { background-color: rgba(139, 92, 246, 0.2) !important; }
      .row-checkbox { transform: scale(1.2); }
      
      /* Fulfillment status badges */
      .badge-fulfillment { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; text-transform: capitalize; }
      .badge-fulfillment-fulfilled { background: #10b981; color: white; }
      .badge-fulfillment-unfulfilled { background: #f59e0b; color: white; }
      .badge-fulfillment-partial { background: #3b82f6; color: white; }
      .badge-fulfillment-pending { background: #6b7280; color: white; }
      .badge-fulfillment-null { background: #f59e0b; color: white; }
    </style>

    <script>
      // elements
      var fetchBtn=document.getElementById('fetchOrders'), fetchUnfulfilledBtn=document.getElementById('fetchUnfulfilled'), fetchUnfulfilledCustomBtn=document.getElementById('fetchUnfulfilledCustom'), fetchAllBtn=document.getElementById('fetchAllOrders'), exportBtn=document.getElementById('exportOrders'), status=document.getElementById('status');
      var exportSelectedBtn=document.getElementById('exportSelected'), downloadPhotosBtn=document.getElementById('downloadPhotos'), downloadPolaroidsBtn=document.getElementById('downloadPolaroids');
      var selectAllBtn=document.getElementById('selectAll'), selectNoneBtn=document.getElementById('selectNone'), selectFilteredBtn=document.getElementById('selectFiltered');
      var qOrder=document.getElementById('qOrder'), qProd=document.getElementById('qProd'), qVar=document.getElementById('qVar');
      var head=document.getElementById('head'), body=document.getElementById('body'), pageSizeEl=document.getElementById('pageSize');
      var prev=document.getElementById('prev'), next=document.getElementById('next'), pageinfo=document.getElementById('pageinfo');
      var loadMoreBtn=document.getElementById('loadMore');
      var lb=document.getElementById('lb'), lbBody=document.getElementById('lbBody'), lbClose=document.getElementById('lbClose');
      var qStatus=document.getElementById('qStatus'), qFulfillment=document.getElementById('qFulfillment');
      var startDateEl=document.getElementById('startDate'), endDateEl=document.getElementById('endDate');

      // state
      var rows=[], filt=[], page=1, sortBy=null, sortDir=1, nextPageInfo=null;
      var selectedRows = new Set(); // Track selected row indices
      
      // Set default date range (last 30 days to today)
      var today = new Date();
      var thirtyDaysAgo = new Date();
      thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
      
      startDateEl.value = thirtyDaysAgo.toISOString().split('T')[0];
      endDateEl.value = today.toISOString().split('T')[0];

      function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m];});}
      function td(h){return '<td class="border-t border-white/10 align-top">'+h+'</td>';}

      function imgFallback(el){el.onerror=null; el.src='https://via.placeholder.com/80?text=No+Img';}

      function openLB(urls){
        lbBody.innerHTML='';
        for(var i=0;i<urls.length;i++){
          var im=document.createElement('img'); im.loading='lazy'; im.src=urls[i];
          im.className='w-full h-40 object-cover rounded-xl border border-white/10';
          im.onerror=function(){ this.src='https://via.placeholder.com/160x160?text=No+Img'; };
          lbBody.appendChild(im);
        }
        lb.classList.remove('hidden'); lb.classList.add('flex');
      }
      lbClose.onclick=function(){lb.classList.add('hidden'); lb.classList.remove('flex');};
      lb.onclick=function(e){ if(e.target===lb) lbClose.onclick(); };

      function convertShopifyOrdersToRows(orders) {
        var converted = [];
        for(var i=0; i<orders.length; i++) {
          var order = orders[i];
          var lineItems = order.line_items || [];
          
          for(var j=0; j<lineItems.length; j++) {
            var item = lineItems[j];
            var properties = {};
            
            // Parse line item properties
            if(item.properties && Array.isArray(item.properties)) {
              for(var k=0; k<item.properties.length; k++) {
                var prop = item.properties[k];
                if(prop.name && prop.value) {
                  properties[prop.name.toLowerCase()] = prop.value;
                }
              }
            }
            
            // Extract data according to mapping rules
            var mainPhoto = properties['photo'] || properties['photo link'] || '';
            var polaroidStr = properties['polaroid'] || properties['your polaroid image'] || '';
            var polaroids = polaroidStr ? polaroidStr.split(/[,\\s]+/).map(function(s){return s.trim();}).filter(function(s){return s;}) : [];
            var backValue = properties['back message'] || properties['back engraving'] || '';
            
            var row = {
              'Order Number': order.name || ('#' + (order.order_number || order.id)),
              'Product Name': item.name || '',
              'Variant': item.variant_title || '',
              'Color': '', // Leave empty as requested
              'Main Photo': mainPhoto,
              'Polaroids': polaroids,
              'Back Engraving Type': backValue ? 'Back Message' : '',
              'Back Engraving Value': backValue,
              'Main Photo Status': mainPhoto ? 'Success' : '',
              'Polaroid Count': polaroids.length.toString(),
              'Fulfillment Status': order.fulfillment_status || 'unfulfilled',
              'Financial Status': order.financial_status || 'pending'
            };
            
            converted.push(row);
          }
        }
        return converted;
      }

      function buildHead(){
        var cols=['Order Number','Product Name','Variant','Color','Main Photo','Polaroids','Back Engraving Type','Back Engraving Value','Main Photo Status','Polaroid Count','Fulfillment Status'];
        var h='<tr>';
        
        // Add checkbox column header
        h+='<th class="text-left p-2 border-b border-white/10"><input type="checkbox" id="selectAllCheckbox" class="row-checkbox" title="Select All Visible"></th>';
        
        for(var i=0;i<cols.length;i++){
          var c=cols[i]; var arrow=(sortBy===c?(sortDir>0?' ▲':' ▼'):'');
          h+='<th class="text-left p-2 border-b border-white/10 cursor-pointer" data-col="'+esc(c)+'">'+esc(c)+arrow+'</th>';
        }
        h+='</tr>';
        head.innerHTML=h;
        
        // Add event listeners for sorting
        var ths=head.querySelectorAll('th[data-col]');
        for(var k=0;k<ths.length;k++){
          ths[k].onclick=function(){
            var c=this.getAttribute('data-col');
            if(sortBy===c) sortDir=-sortDir; else {sortBy=c; sortDir=1;}
            applyFilters();
          };
        }
        
        // Add event listener for select all checkbox
        document.getElementById('selectAllCheckbox').onchange = function() {
          if (this.checked) {
            selectAllVisible();
          } else {
            selectNoneVisible();
          }
        };
      }

      function applyFilters(){
        var o=qOrder.value.trim().toLowerCase(), p=qProd.value.trim().toLowerCase(), v=qVar.value.trim().toLowerCase();
        var fulfillmentFilter=qFulfillment.value;
        filt=rows.filter(function(r){
          var ok=true;
          if(o) ok = ok && String(r['Order Number']||'').toLowerCase().indexOf(o)>=0;
          if(p) ok = ok && String(r['Product Name']||'').toLowerCase().indexOf(p)>=0;
          if(v) ok = ok && String(r['Variant']||'').toLowerCase().indexOf(v)>=0;
          if(fulfillmentFilter && fulfillmentFilter !== 'any') {
            ok = ok && String(r['Fulfillment Status']||'').toLowerCase() === fulfillmentFilter.toLowerCase();
          }
          return ok;
        });
        if(sortBy){
          filt.sort(function(a,b){
            var av=String(a[sortBy]||'').toLowerCase(), bv=String(b[sortBy]||'').toLowerCase();
            if(av<bv) return -1*sortDir; if(av>bv) return 1*sortDir; return 0;
          });
        }
        page=1; render();
      }

      function render(){
        var per=parseInt(pageSizeEl.value,10)||25;
        var start=(page-1)*per, end=Math.min(start+per, filt.length);
        var out='';
        for(var i=start;i<end;i++){
          var r=filt[i];
          var globalIdx = rows.indexOf(r); // Get global index for selection tracking
          var isSelected = selectedRows.has(globalIdx);
          
          var main=r['Main Photo'] ? '<img loading="lazy" src="'+esc(r['Main Photo'])+'" class="w-20 h-20 object-cover rounded-lg border border-white/10 table-img" onerror="imgFallback(this)">' : '<span class="badge-miss">Missing photo</span>';
          var polys=r['Polaroids']||[]; var thumbs='';
          for(var t=0; t<Math.min(3,polys.length); t++){
            thumbs+='<img loading="lazy" src="'+esc(polys[t])+'" class="w-14 h-14 object-cover rounded-md border border-white/10 table-img" onerror="imgFallback(this)" style="margin-right:4px">';
          }
          var more=polys.length>3?('<div class="text-xs text-white/60">+'+(polys.length-3)+' more</div>'):'';
          var gallery='<a href="#" class="gal" data-idx="'+i+'"><div class="flex gap-2 flex-wrap">'+thumbs+more+'</div></a>';
          var engr=String(r['Back Engraving Value']||'').trim()?('<div class="truncate" style="white-space:pre-wrap">'+esc(r['Back Engraving Value'])+'</div>'):'<span class="badge-miss">Missing</span>';

          var fulfillmentStatus = r['Fulfillment Status'] || 'unfulfilled';
          var fulfillmentBadge = '<span class="badge-fulfillment badge-fulfillment-' + fulfillmentStatus + '">' + fulfillmentStatus + '</span>';

          out+='<tr class="'+(isSelected?'selected':'')+'" data-global-idx="'+globalIdx+'">'+
            td('<input type="checkbox" class="row-checkbox" data-idx="'+globalIdx+'" '+(isSelected?'checked':'')+'>')+
            td(esc(r['Order Number']))+td(esc(r['Product Name']))+td(esc(r['Variant']))+td(esc(r['Color']))+
            td(main)+td(gallery)+td(esc(r['Back Engraving Type']))+td(engr)+td(esc(r['Main Photo Status']))+td(esc(r['Polaroid Count']))+td(fulfillmentBadge)+
          '</tr>';
        }
        body.innerHTML=out;

        // Add event listeners for gallery links
        var links=body.querySelectorAll('a.gal');
        for(var g=0; g<links.length; g++){
          links[g].onclick=function(e){
            e.preventDefault();
            var idx=parseInt(this.getAttribute('data-idx')||'-1',10);
            if(idx>=0 && idx<filt.length){
              var urls=filt[idx]['Polaroids']||[];
              if(urls.length) openLB(urls);
            }
          };
        }
        
        // Add event listeners for checkboxes
        var checkboxes = body.querySelectorAll('.row-checkbox');
        for(var c=0; c<checkboxes.length; c++){
          checkboxes[c].onchange = function(){
            var idx = parseInt(this.getAttribute('data-idx'));
            var row = this.closest('tr');
            if(this.checked) {
              selectedRows.add(idx);
              row.classList.add('selected');
            } else {
              selectedRows.delete(idx);
              row.classList.remove('selected');
            }
            updateSelectionUI();
          };
        }

        var total=filt.length, pages=Math.max(1, Math.ceil(total/per));
        pageinfo.textContent='Page '+page+' / '+pages+' — '+total+' rows';
        prev.disabled=page<=1; next.disabled=page>=pages;
        
        // Show/hide load more button
        loadMoreBtn.style.display = nextPageInfo ? 'inline-block' : 'none';
        
        // Update selection UI
        updateSelectionUI();
      }

      prev.onclick=function(){ if(page>1){ page--; render(); } };
      next.onclick=function(){ var per=parseInt(pageSizeEl.value,10)||25; var pages=Math.max(1,Math.ceil(filt.length/per)); if(page<pages){ page++; render(); } };
      pageSizeEl.onchange=applyFilters;
      qOrder.oninput=qProd.oninput=qVar.oninput=qFulfillment.onchange=applyFilters;

      window.imgFallback = imgFallback; // make global for onerror attr
      
      // Selection functions
      function updateSelectionUI() {
        var selectedCount = selectedRows.size;
        var selectedWithPhotos = 0;
        var selectedWithPolaroids = 0;
        var totalPolaroids = 0;
        
        selectedRows.forEach(function(idx) {
          if (rows[idx]) {
            if (rows[idx]['Main Photo']) {
            selectedWithPhotos++;
            }
            if (rows[idx]['Polaroids'] && rows[idx]['Polaroids'].length > 0) {
              selectedWithPolaroids++;
              totalPolaroids += rows[idx]['Polaroids'].length;
            }
          }
        });
        
        document.getElementById('selectedCount').textContent = selectedCount;
        document.getElementById('selectedPhotos').textContent = selectedWithPhotos;
        document.getElementById('selectedPolaroids').textContent = totalPolaroids;
        
        exportSelectedBtn.disabled = selectedCount === 0;
        downloadPhotosBtn.disabled = selectedWithPhotos === 0;
        downloadPolaroidsBtn.disabled = totalPolaroids === 0;
        
        document.getElementById('selectionInfo').textContent = 
          selectedCount === 0 ? 'No items selected' : 
          selectedCount + ' items selected (' + selectedWithPhotos + ' with main photos, ' + totalPolaroids + ' polaroids)';
      }
      
      function selectAllVisible() {
        var per=parseInt(pageSizeEl.value,10)||25;
        var start=(page-1)*per, end=Math.min(start+per, filt.length);
        for(var i=start; i<end; i++) {
          var globalIdx = rows.indexOf(filt[i]);
          selectedRows.add(globalIdx);
        }
        render();
      }
      
      function selectNoneVisible() {
        var per=parseInt(pageSizeEl.value,10)||25;
        var start=(page-1)*per, end=Math.min(start+per, filt.length);
        for(var i=start; i<end; i++) {
          var globalIdx = rows.indexOf(filt[i]);
          selectedRows.delete(globalIdx);
        }
        render();
      }
      
      function selectAll() {
        selectedRows.clear();
        for(var i=0; i<rows.length; i++) {
          selectedRows.add(i);
        }
        render();
      }
      
      function selectNone() {
        selectedRows.clear();
        render();
      }
      
      function selectFiltered() {
        selectedRows.clear();
        for(var i=0; i<filt.length; i++) {
          var globalIdx = rows.indexOf(filt[i]);
          selectedRows.add(globalIdx);
        }
        render();
      }

      function fetchOrdersFromShopify() {
        status.textContent='Fetching from Shopify...'; 
        head.innerHTML=''; 
        body.innerHTML='';
        fetchBtn.disabled = true;
        fetchBtn.textContent = '🔄 Fetching...';
        
        var selectedStatus = qStatus.value;
        fetch('/api/shopify/orders?status='+encodeURIComponent(selectedStatus)+'&limit=100')
          .then(function(res){ 
            return res.text().then(function(t){ 
              return {ok:res.ok, status:res.status, text:t};
            }); 
          })
          .then(function(x){
            if(!x.ok){ 
              var errorMsg = 'Error: ';
              try {
                var errorData = JSON.parse(x.text);
                errorMsg += errorData.detail || x.text;
                
                // Show setup notice if it's a configuration error
                if (errorData.detail && (errorData.detail.includes('Shopify configuration missing') || errorData.detail.includes('configure via /shopify/settings'))) {
                  var notice = document.getElementById('shopifyNotice');
                  notice.style.display = 'block';
                  // Add link to Shopify settings
                  notice.innerHTML = notice.innerHTML.replace('</div></div>', 
                    '<div class="text-xs text-blue-400 mt-2">' +
                    '<a href="/shopify/settings" class="text-blue-300 hover:text-blue-200 underline">Or configure via Shopify Settings page →</a>' +
                    '</div></div></div>');
                }
              } catch(e) {
                errorMsg += x.text || ('HTTP ' + x.status);
              }
              status.textContent = errorMsg;
              return; 
            }
            
            // Hide setup notice on successful fetch
            document.getElementById('shopifyNotice').style.display = 'none';
            var data; 
            try{ 
              data=JSON.parse(x.text); 
            } catch(e){ 
              status.textContent='Bad JSON from server'; 
              return; 
            }
            var orders = data.orders || [];
            nextPageInfo = data.next_page_info;
            rows = convertShopifyOrdersToRows(orders);
            status.textContent='✅ Loaded '+orders.length+' orders ('+rows.length+' line items)';
            buildHead(); 
            applyFilters();
          })
          .catch(function(err){ 
            console.error('Fetch error:', err); 
            status.textContent='❌ Network error: ' + err.message; 
          })
          .finally(function(){
            fetchBtn.disabled = false;
            fetchBtn.textContent = 'Fetch from Shopify';
          });
      }

      fetchBtn.onclick = fetchOrdersFromShopify;
      
      // Fetch ALL unfulfilled orders with pagination
      function fetchUnfulfilledOrders() {
        status.textContent='Fetching ALL unfulfilled orders from Shopify (last 30 days)...'; 
        head.innerHTML=''; 
        body.innerHTML='';
        fetchUnfulfilledBtn.disabled = true;
        fetchUnfulfilledBtn.textContent = '🔄 Fetching...';
        
        // Calculate date range (last 30 days)
        var endDate = new Date();
        var startDate = new Date();
        startDate.setDate(startDate.getDate() - 30);
        
        var startDateStr = startDate.toISOString();
        var endDateStr = endDate.toISOString();
        
        // Start fetching with pagination
        fetchAllUnfulfilledWithPagination(startDateStr, endDateStr, null, []);
      }
      
      function fetchAllUnfulfilledWithPagination(startDate, endDate, pageInfo, allOrders) {
        var url = '/api/shopify/orders?status=open&fulfillment_status=unfulfilled&limit=250';
        url += '&created_at_min=' + encodeURIComponent(startDate);
        url += '&created_at_max=' + encodeURIComponent(endDate);
        if (pageInfo) {
          url += '&page_info=' + encodeURIComponent(pageInfo);
        }
        
        status.textContent = 'Fetching unfulfilled orders... (found ' + allOrders.length + ' so far)';
        
        fetch(url)
          .then(function(res){ 
            return res.text().then(function(t){ 
              return {ok:res.ok, status:res.status, text:t};
            }); 
          })
          .then(function(x){
            if(!x.ok){ 
              var errorMsg = 'Error: ';
              try {
                var errorData = JSON.parse(x.text);
                errorMsg += errorData.detail || x.text;
                
                // Show setup notice if it's a configuration error
                if (errorData.detail && (errorData.detail.includes('Shopify configuration missing') || errorData.detail.includes('configure via /shopify/settings'))) {
                  var notice = document.getElementById('shopifyNotice');
                  notice.style.display = 'block';
                  // Add link to Shopify settings
                  notice.innerHTML = notice.innerHTML.replace('</div></div>', 
                    '<div class="text-xs text-blue-400 mt-2">' +
                    '<a href="/shopify/settings" class="text-blue-300 hover:text-blue-200 underline">Or configure via Shopify Settings page →</a>' +
                    '</div></div></div>');
                }
              } catch(e) {
                errorMsg += x.text || ('HTTP ' + x.status);
              }
              status.textContent = errorMsg;
              fetchUnfulfilledBtn.disabled = false;
              fetchUnfulfilledBtn.textContent = '📦 Fetch ALL Unfulfilled (30 days)';
              return; 
            }
            
            // Hide setup notice on successful fetch
            document.getElementById('shopifyNotice').style.display = 'none';
            var data; 
            try{ 
              data=JSON.parse(x.text); 
            } catch(e){ 
              status.textContent='Bad JSON from server'; 
              fetchUnfulfilledBtn.disabled = false;
              fetchUnfulfilledBtn.textContent = '📦 Fetch ALL Unfulfilled (30 days)';
              return; 
            }
            
            var orders = data.orders || [];
            var nextPage = data.next_page_info;
            
            // Add to our collection
            allOrders = allOrders.concat(orders);
            
            // Check if there are more pages
            if (nextPage && orders.length === 250) {
              // Continue fetching next page
              fetchAllUnfulfilledWithPagination(startDate, endDate, nextPage, allOrders);
            } else {
              // We're done, process all orders
              rows = convertShopifyOrdersToRows(allOrders);
              
              // Auto-filter to show only unfulfilled orders
              qFulfillment.value = 'unfulfilled';
              
              var unfulfilledCount = allOrders.filter(function(o) { 
                return !o.fulfillment_status || o.fulfillment_status === 'unfulfilled'; 
              }).length;
              
              status.textContent='✅ Loaded ' + allOrders.length + ' unfulfilled orders (' + rows.length + ' line items) from last 30 days';
              buildHead(); 
              applyFilters();
              
              fetchUnfulfilledBtn.disabled = false;
              fetchUnfulfilledBtn.textContent = '📦 Fetch ALL Unfulfilled (30 days)';
              
              // Show success notification
              showNotification('Successfully loaded ' + allOrders.length + ' unfulfilled orders from the last 30 days!', 'success');
            }
          })
          .catch(function(err){ 
            console.error('Fetch error:', err); 
            status.textContent='❌ Network error: ' + err.message; 
            fetchUnfulfilledBtn.disabled = false;
            fetchUnfulfilledBtn.textContent = '📦 Fetch Unfulfilled Orders';
          });
      }
      
      fetchUnfulfilledBtn.onclick = fetchUnfulfilledOrders;
      
      // Custom date range unfulfilled orders fetch
      function fetchUnfulfilledCustomRange() {
        var startDate = startDateEl.value;
        var endDate = endDateEl.value;
        
        if (!startDate || !endDate) {
          alert('Please select both start and end dates');
          return;
        }
        
        if (new Date(startDate) > new Date(endDate)) {
          alert('Start date must be before end date');
          return;
        }
        
        status.textContent='Fetching ALL unfulfilled orders from ' + startDate + ' to ' + endDate + '...'; 
        head.innerHTML=''; 
        body.innerHTML='';
        fetchUnfulfilledCustomBtn.disabled = true;
        fetchUnfulfilledCustomBtn.textContent = '🔄 Fetching...';
        
        var startDateStr = new Date(startDate).toISOString();
        var endDateStr = new Date(endDate + 'T23:59:59').toISOString(); // Include full end date
        
        // Start fetching with pagination
        fetchAllUnfulfilledWithPaginationCustom(startDateStr, endDateStr, null, [], startDate, endDate);
      }
      
      function fetchAllUnfulfilledWithPaginationCustom(startDate, endDate, pageInfo, allOrders, displayStartDate, displayEndDate) {
        var url = '/api/shopify/orders?status=open&fulfillment_status=unfulfilled&limit=250';
        url += '&created_at_min=' + encodeURIComponent(startDate);
        url += '&created_at_max=' + encodeURIComponent(endDate);
        if (pageInfo) {
          url += '&page_info=' + encodeURIComponent(pageInfo);
        }
        
        status.textContent = 'Fetching unfulfilled orders from ' + displayStartDate + ' to ' + displayEndDate + '... (found ' + allOrders.length + ' so far)';
        
        fetch(url)
          .then(function(res){ 
            return res.text().then(function(t){ 
              return {ok:res.ok, status:res.status, text:t};
            }); 
          })
          .then(function(x){
            if(!x.ok){ 
              var errorMsg = 'Error: ';
              try {
                var errorData = JSON.parse(x.text);
                errorMsg += errorData.detail || x.text;
              } catch(e) {
                errorMsg += x.text || ('HTTP ' + x.status);
              }
              status.textContent = errorMsg;
              fetchUnfulfilledCustomBtn.disabled = false;
              fetchUnfulfilledCustomBtn.textContent = '📅 Custom Date Range';
              return; 
            }
            
            var data; 
            try{ 
              data=JSON.parse(x.text); 
            } catch(e){ 
              status.textContent='Bad JSON from server'; 
              fetchUnfulfilledCustomBtn.disabled = false;
              fetchUnfulfilledCustomBtn.textContent = '📅 Custom Date Range';
              return; 
            }
            
            var orders = data.orders || [];
            var nextPage = data.next_page_info;
            
            // Add to our collection
            allOrders = allOrders.concat(orders);
            
            // Check if there are more pages
            if (nextPage && orders.length === 250) {
              // Continue fetching next page
              fetchAllUnfulfilledWithPaginationCustom(startDate, endDate, nextPage, allOrders, displayStartDate, displayEndDate);
            } else {
              // We're done, process all orders
              rows = convertShopifyOrdersToRows(allOrders);
              
              // Auto-filter to show only unfulfilled orders
              qFulfillment.value = 'unfulfilled';
              
              var unfulfilledCount = allOrders.filter(function(o) { 
                return !o.fulfillment_status || o.fulfillment_status === 'unfulfilled'; 
              }).length;
              
              status.textContent='✅ Loaded ' + allOrders.length + ' unfulfilled orders (' + rows.length + ' line items) from ' + displayStartDate + ' to ' + displayEndDate;
              buildHead(); 
              applyFilters();
              
              fetchUnfulfilledCustomBtn.disabled = false;
              fetchUnfulfilledCustomBtn.textContent = '📅 Custom Date Range';
              
              // Show success notification
              showNotification('Successfully loaded ' + allOrders.length + ' unfulfilled orders from ' + displayStartDate + ' to ' + displayEndDate + '!', 'success');
            }
          })
          .catch(function(err){ 
            console.error('Fetch error:', err); 
            status.textContent='❌ Network error: ' + err.message; 
            fetchUnfulfilledCustomBtn.disabled = false;
            fetchUnfulfilledCustomBtn.textContent = '📅 Custom Date Range';
          });
      }
      fetchUnfulfilledCustomBtn.onclick = fetchUnfulfilledCustomRange;
      
      // Fetch ALL orders across all pages
      function fetchAllOrders() {
        status.textContent='🚀 Fetching ALL orders from all pages...'; 
        head.innerHTML=''; 
        body.innerHTML='';
        fetchAllBtn.disabled = true;
        fetchAllBtn.textContent = '🔄 Fetching All...';
        
        var selectedStatus = qStatus.value;
        var url = '/api/shopify/orders/all?status=' + encodeURIComponent(selectedStatus);
        
        // Add date filters if they exist
        if (startDateEl.value) {
          url += '&created_at_min=' + encodeURIComponent(new Date(startDateEl.value).toISOString());
        }
        if (endDateEl.value) {
          url += '&created_at_max=' + encodeURIComponent(new Date(endDateEl.value + 'T23:59:59').toISOString());
        }
        
        // Add fulfillment status filter if selected
        if (qFulfillment.value && qFulfillment.value !== 'any') {
          url += '&fulfillment_status=' + encodeURIComponent(qFulfillment.value);
        }
        
        fetch(url)
          .then(function(res){ 
            return res.text().then(function(t){ 
              return {ok:res.ok, status:res.status, text:t};
            }); 
          })
          .then(function(x){
            if(!x.ok){ 
              var errorMsg = 'Error: ';
              try {
                var errorData = JSON.parse(x.text);
                errorMsg += errorData.detail || x.text;
                
                // Show setup notice if it's a configuration error
                if (errorData.detail && (errorData.detail.includes('Shopify configuration missing') || errorData.detail.includes('configure via /shopify/settings'))) {
                  var notice = document.getElementById('shopifyNotice');
                  notice.style.display = 'block';
                }
              } catch(e) {
                errorMsg += x.text || ('HTTP ' + x.status);
              }
              status.textContent = errorMsg;
              return; 
            }
            
            // Hide setup notice on successful fetch
            document.getElementById('shopifyNotice').style.display = 'none';
            var data; 
            try{ 
              data=JSON.parse(x.text); 
            } catch(e){ 
              status.textContent='Bad JSON from server'; 
              return; 
            }
            
            var orders = data.orders || [];
            var count = data.count || 0;
            
            rows = convertShopifyOrdersToRows(orders);
            status.textContent='✅ Loaded ALL ' + count + ' orders (' + rows.length + ' line items) across all pages!';
            buildHead(); 
            applyFilters();
            
            // Show success notification
            showNotification('Successfully loaded ALL ' + count + ' orders from all pages!', 'success');
          })
          .catch(function(err){ 
            console.error('Fetch error:', err); 
            status.textContent='❌ Network error: ' + err.message; 
          })
          .finally(function(){
            fetchAllBtn.disabled = false;
            fetchAllBtn.textContent = '🚀 Fetch ALL Orders (All Pages)';
          });
      }
      fetchAllBtn.onclick = fetchAllOrders;
      
      loadMoreBtn.onclick=function(){
        if(!nextPageInfo) return;
        status.textContent='Loading more...';
        var selectedStatus = qStatus.value;
        fetch('/api/shopify/orders?status='+encodeURIComponent(selectedStatus)+'&limit=100&page_info='+encodeURIComponent(nextPageInfo))
          .then(function(res){ return res.text().then(function(t){ return {ok:res.ok, text:t};}); })
          .then(function(x){
            if(!x.ok){ status.textContent='Error: '+x.text; return; }
            var data; try{ data=JSON.parse(x.text); }catch(e){ status.textContent='Bad JSON from server'; return; }
            var orders = data.orders || [];
            nextPageInfo = data.next_page_info;
            var newRows = convertShopifyOrdersToRows(orders);
            rows = rows.concat(newRows);
            status.textContent='Loaded '+rows.length+' total line items';
            applyFilters(); // Refresh display with new data
          })
          .catch(function(err){ console.error(err); status.textContent='Unexpected error loading more'; });
      };

      exportBtn.onclick=function(){
        var cols=['Order Number','Product Name','Variant','Color','Main Photo','Polaroids','Back Engraving Type','Back Engraving Value','Main Photo Status','Polaroid Count'];
        var csv=cols.join(',')+'\\n';
        for(var i=0;i<filt.length;i++){
          var r=filt[i], line=[];
          for(var c=0;c<cols.length;c++){
            var v=r[cols[c]];
            if(Array.isArray(v)) v=v.join(' ');
            line.push('"'+String(v==null?'':v).replace(/"/g,'""')+'"');
          }
          csv+=line.join(',')+('\\n');
        }
        var blob=new Blob([csv],{type:'text/csv;charset=utf-8;'}), a=document.createElement('a');
        a.href=URL.createObjectURL(blob); a.download='shopify_orders_filtered.csv'; a.click(); URL.revokeObjectURL(a.href);
      };
      
      // Export selected orders
      exportSelectedBtn.onclick=function(){
        var selectedData = [];
        selectedRows.forEach(function(idx) {
          if (rows[idx]) {
            selectedData.push(rows[idx]);
          }
        });
        
        if (selectedData.length === 0) {
          alert('No orders selected for export');
          return;
        }
        
        var cols=['Order Number','Product Name','Variant','Color','Main Photo','Polaroids','Back Engraving Type','Back Engraving Value','Main Photo Status','Polaroid Count'];
        var csv=cols.join(',')+'\\n';
        for(var i=0;i<selectedData.length;i++){
          var r=selectedData[i], line=[];
          for(var c=0;c<cols.length;c++){
            var v=r[cols[c]];
            if(Array.isArray(v)) v=v.join(' ');
            line.push('"'+String(v==null?'':v).replace(/"/g,'""')+'"');
          }
          csv+=line.join(',')+('\\n');
        }
        var blob=new Blob([csv],{type:'text/csv;charset=utf-8;'}), a=document.createElement('a');
        a.href=URL.createObjectURL(blob); a.download='shopify_orders_selected.csv'; a.click(); URL.revokeObjectURL(a.href);
      };
      
      // Download photos in bulk with enhanced UI feedback
      downloadPhotosBtn.onclick=async function(){
        var photosToDownload = [];
        selectedRows.forEach(function(idx) {
          if (rows[idx] && rows[idx]['Main Photo'] && rows[idx]['Order Number']) {
            photosToDownload.push({
              url: rows[idx]['Main Photo'],
              order_number: rows[idx]['Order Number']
            });
          }
        });

        if (photosToDownload.length === 0) {
          alert('No photos with order numbers found for download.');
          return;
        }

        // Show progress indicator
        var originalText = downloadPhotosBtn.textContent;
        downloadPhotosBtn.disabled = true;
        downloadPhotosBtn.innerHTML = '🔄 Preparing download...';
        
        // Update status
        status.textContent = `📦 Preparing ${photosToDownload.length} photos for download...`;

        try {
          const response = await fetch('/api/orders/download-photos', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ photos: photosToDownload })
          });

          if (response.ok) {
            status.textContent = '📥 Downloading ZIP file...';
            
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            
            // Generate timestamp for unique filename
            const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
            a.download = `order_photos_${timestamp}.zip`;
            
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            status.textContent = `✅ Successfully downloaded ${photosToDownload.length} photos!`;
            
            // Show success notification
            showNotification(`Successfully downloaded ${photosToDownload.length} order photos as PNG files!`, 'success');
            
          } else {
            const errorData = await response.json();
            const errorMsg = 'Failed to download photos: ' + (errorData.detail || 'Unknown error');
            status.textContent = '❌ ' + errorMsg;
            showNotification(errorMsg, 'error');
          }
        } catch (error) {
          console.error('Error downloading photos:', error);
          const errorMsg = 'Network error occurred while downloading photos.';
          status.textContent = '❌ ' + errorMsg;
          showNotification(errorMsg, 'error');
        } finally {
          // Reset button state
          downloadPhotosBtn.disabled = selectedRows.size === 0 || Array.from(selectedRows).filter(idx => rows[idx] && rows[idx]['Main Photo']).length === 0;
          downloadPhotosBtn.innerHTML = originalText;
        }
      };
      
      // Download polaroids in bulk
      downloadPolaroidsBtn.onclick=async function(){
        var polaroidsToDownload = [];
        selectedRows.forEach(function(idx) {
          if (rows[idx] && rows[idx]['Polaroids'] && rows[idx]['Order Number']) {
            var polaroids = rows[idx]['Polaroids'];
            for (var i = 0; i < polaroids.length; i++) {
              polaroidsToDownload.push({
                url: polaroids[i],
                order_number: rows[idx]['Order Number'],
                polaroid_index: i + 1
              });
            }
          }
        });

        if (polaroidsToDownload.length === 0) {
          alert('No polaroid images found for download.');
          return;
        }

        // Show progress indicator
        var originalText = downloadPolaroidsBtn.textContent;
        downloadPolaroidsBtn.disabled = true;
        downloadPolaroidsBtn.innerHTML = '🔄 Preparing download...';
        
        // Update status
        status.textContent = `📦 Preparing ${polaroidsToDownload.length} polaroid images for download...`;

        try {
          const response = await fetch('/api/orders/download-polaroids', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ polaroids: polaroidsToDownload })
          });

          if (response.ok) {
            status.textContent = '📥 Downloading ZIP file...';
            
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            
            // Generate timestamp for unique filename
            const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
            a.download = `polaroid_images_${timestamp}.zip`;
            
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            status.textContent = `✅ Successfully downloaded ${polaroidsToDownload.length} polaroid images!`;
            
            // Show success notification
            showNotification(`Successfully downloaded ${polaroidsToDownload.length} polaroid images as PNG files!`, 'success');
            
          } else {
            const errorData = await response.json();
            const errorMsg = 'Failed to download polaroids: ' + (errorData.detail || 'Unknown error');
            status.textContent = '❌ ' + errorMsg;
            showNotification(errorMsg, 'error');
          }
        } catch (error) {
          console.error('Error downloading polaroids:', error);
          const errorMsg = 'Network error occurred while downloading polaroids.';
          status.textContent = '❌ ' + errorMsg;
          showNotification(errorMsg, 'error');
        } finally {
          // Reset button state
          var totalPolaroids = 0;
          selectedRows.forEach(function(idx) {
            if (rows[idx] && rows[idx]['Polaroids']) {
              totalPolaroids += rows[idx]['Polaroids'].length;
            }
          });
          downloadPolaroidsBtn.disabled = totalPolaroids === 0;
          downloadPolaroidsBtn.innerHTML = originalText;
        }
      };
      
      // Notification function for better user feedback
      function showNotification(message, type = 'info') {
        // Create notification element
        var notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 z-50 p-4 rounded-xl border max-w-md shadow-lg transition-all duration-300 transform translate-x-full`;
        
        if (type === 'success') {
          notification.className += ' bg-green-500/20 border-green-500/30 text-green-200';
        } else if (type === 'error') {
          notification.className += ' bg-red-500/20 border-red-500/30 text-red-200';
        } else {
          notification.className += ' bg-blue-500/20 border-blue-500/30 text-blue-200';
        }
        
        notification.innerHTML = `
          <div class="flex items-center gap-3">
            <div class="text-xl">${type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'}</div>
            <div class="flex-1">${message}</div>
            <button onclick="this.parentElement.parentElement.remove()" class="text-white/70 hover:text-white">✕</button>
          </div>
        `;
        
        document.body.appendChild(notification);
        
        // Animate in
        setTimeout(() => {
          notification.classList.remove('translate-x-full');
        }, 100);
        
        // Auto remove after 5 seconds
        setTimeout(() => {
          notification.classList.add('translate-x-full');
          setTimeout(() => notification.remove(), 300);
        }, 5000);
      }
      
      // Selection button event listeners
      selectAllBtn.onclick = selectAll;
      selectNoneBtn.onclick = selectNone;
      selectFilteredBtn.onclick = selectFiltered;
      
      // Auto-fetch orders when page loads
      document.addEventListener('DOMContentLoaded', function() {
        console.log('Page loaded, auto-fetching orders...');
        setTimeout(function() {
          fetchOrdersFromShopify();
        }, 500); // Small delay to ensure everything is initialized
      });
      
      // Also auto-fetch if DOM is already loaded
      if (document.readyState === 'loading') {
        // DOMContentLoaded listener above will handle this
      } else {
        // DOM is already loaded
        console.log('DOM already loaded, auto-fetching orders...');
        setTimeout(function() {
          fetchOrdersFromShopify();
        }, 100);
      }
    </script>
    """
    return _eraya_style_page("Order Management", body)

# -------------------- DASHBOARD STATS API --------------------
@app.get("/api/dashboard/stats")
def get_dashboard_stats(current_user: Dict = Depends(require_roles())):
    # Count active employees (currently checked in)
    active_employees = 0
    total_employees = 0
    employee_names = []
    
    for emp_id, records in ATTENDANCE_RECORDS.items():
        total_employees += 1
        # Get employee name
        emp_name = None
        for name, id_val in EMPLOYEES.items():
            if id_val == emp_id:
                emp_name = name
                break
        
        # Check if currently checked in (last record has no check_out_time)
        if records and "check_out_time" not in records[-1]:
            active_employees += 1
            employee_names.append(emp_name or emp_id)
    
    # Get Shopify data if configured
    shopify_data = {}
    if SHOPIFY_CONFIG["store_name"] and SHOPIFY_CONFIG["access_token"]:
        try:
            shopify_analytics = fetch_shopify_analytics()
            shopify_data = {
                "total_orders_today": shopify_analytics.get("today_orders", 0),
                "total_orders_week": shopify_analytics.get("total_orders", 0),
                "pending_orders": shopify_analytics.get("pending_orders", 0),
                "total_revenue": shopify_analytics.get("total_revenue", 0),
                "today_revenue": shopify_analytics.get("today_revenue", 0),
                "currency": shopify_analytics.get("currency", "USD"),
                "fulfilled_orders": shopify_analytics.get("fulfilled_orders", 0)
            }
        except Exception as e:
            print(f"Error fetching Shopify data for dashboard: {e}")
            shopify_data = {
                "total_orders_today": 0,
                "total_orders_week": 0,
                "pending_orders": 0,
                "total_revenue": 0,
                "today_revenue": 0,
                "currency": "USD",
                "fulfilled_orders": 0
            }
    else:
        # Placeholder data when Shopify not configured
        shopify_data = {
            "total_orders_today": 12,  # Placeholder
            "total_orders_week": 156,  # Placeholder
            "pending_orders": 23,  # Placeholder
            "total_revenue": 45678.90,  # Placeholder
            "today_revenue": 1234.56,  # Placeholder
            "currency": "USD",
            "fulfilled_orders": 133
        }

    stats = {
        **shopify_data,
        "active_employees": active_employees,
        "total_employees": len(EMPLOYEES),
        "active_employee_names": employee_names,
        "shopify_configured": bool(SHOPIFY_CONFIG["store_name"] and SHOPIFY_CONFIG["access_token"]),
        "recent_activity": []  # Can be enhanced later
    }
    
    return JSONResponse(content=stats)

@app.get("/api/search/employee")
def search_employee(query: str):
    results = []
    query_lower = query.lower()
    for name, emp_id in EMPLOYEES.items():
        if query_lower in name.lower() or query_lower in emp_id.lower():
            # Get current status
            status = "Unknown"
            if emp_id in ATTENDANCE_RECORDS and ATTENDANCE_RECORDS[emp_id]:
                last_record = ATTENDANCE_RECORDS[emp_id][-1]
                status = "Checked In" if "check_out_time" not in last_record else "Checked Out"
            
            results.append({
                "name": name,
                "employee_id": emp_id,
                "status": status
            })
    
    return JSONResponse(content={"results": results})

# -------------------- TEAM CHAT API --------------------
@app.post("/api/chat/send")
def send_message(employee_id: str = Form(...), message: str = Form(...)):
    if not employee_id or not message.strip():
        raise HTTPException(status_code=400, detail="Employee ID and message are required.")
    
    # Get employee name
    employee_name = None
    for name, emp_id in EMPLOYEES.items():
        if emp_id == employee_id:
            employee_name = name
            break
    
    if not employee_name:
        raise HTTPException(status_code=400, detail="Invalid employee ID.")
    
    # Create message object
    chat_message = {
        "id": len(CHAT_MESSAGES) + 1,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "message": message.strip(),
        "timestamp": get_timestamp()
    }
    
    CHAT_MESSAGES.append(chat_message)
    
    # Keep only last 100 messages to prevent memory issues
    if len(CHAT_MESSAGES) > 100:
        CHAT_MESSAGES.pop(0)
    
    return JSONResponse(content={"status": "success", "message": "Message sent successfully."})

@app.get("/api/chat/messages")
def get_messages(limit: int = 20):
    # Return the most recent messages
    recent_messages = CHAT_MESSAGES[-limit:] if len(CHAT_MESSAGES) > limit else CHAT_MESSAGES
    return JSONResponse(content={"messages": recent_messages})

# -------------------- ADVANCED CHAT API --------------------
@app.post("/api/chat/channel/send")
def send_channel_message(channel: str = Form(...), employee_id: str = Form(...), message: str = Form(...), file_info: str = Form(None)):
    if channel not in CHAT_CHANNELS:
        raise HTTPException(status_code=400, detail="Invalid channel.")
    
    if not employee_id or (not message.strip() and not file_info):
        raise HTTPException(status_code=400, detail="Employee ID and message or file are required.")
    
    # Get employee name
    employee_name = None
    for name, emp_id in EMPLOYEES.items():
        if emp_id == employee_id:
            employee_name = name
            break
    
    if not employee_name:
        raise HTTPException(status_code=400, detail="Invalid employee ID.")
    
    # Process links in message
    links = []
    if message.strip():
        found_links = extract_links_from_message(message)
        links = [get_link_preview(link) for link in found_links]
    
    # Parse file info if provided
    file_attachment = None
    if file_info:
        try:
            import json
            file_attachment = json.loads(file_info)
        except:
            pass
    
    # Create message object
    message_id = f"{channel}_{len(CHAT_CHANNELS[channel]['messages']) + 1}_{get_timestamp()}"
    chat_message = {
        "id": message_id,
        "channel": channel,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "message": message.strip(),
        "timestamp": get_timestamp(),
        "edited": False,
        "edited_at": None,
        "file_attachment": file_attachment,
        "links": links
    }
    
    CHAT_CHANNELS[channel]["messages"].append(chat_message)
    
    # Keep only last 200 messages per channel
    if len(CHAT_CHANNELS[channel]["messages"]) > 200:
        CHAT_CHANNELS[channel]["messages"].pop(0)
    
    return JSONResponse(content={"status": "success", "message": "Message sent successfully.", "message_id": message_id})

@app.get("/api/chat/channel/{channel_name}")
def get_channel_messages(channel_name: str, limit: int = 50):
    if channel_name not in CHAT_CHANNELS:
        raise HTTPException(status_code=404, detail="Channel not found.")
    
    messages = CHAT_CHANNELS[channel_name]["messages"]
    recent_messages = messages[-limit:] if len(messages) > limit else messages
    
    # Add reactions to messages
    for msg in recent_messages:
        msg["reactions"] = MESSAGE_REACTIONS.get(msg["id"], {})
    
    return JSONResponse(content={
        "channel": channel_name,
        "channel_name": CHAT_CHANNELS[channel_name]["name"],
        "messages": recent_messages
    })

@app.get("/api/chat/channels")
def get_channels():
    channels_info = []
    for channel_id, channel_data in CHAT_CHANNELS.items():
        unread_count = len(channel_data["messages"])  # Simplified - in real app, track per user
        channels_info.append({
            "id": channel_id,
            "name": channel_data["name"],
            "unread_count": min(unread_count, 99),  # Cap at 99
            "last_message": channel_data["messages"][-1] if channel_data["messages"] else None
        })
    
    return JSONResponse(content={"channels": channels_info})

@app.post("/api/chat/dm/send")
def send_direct_message(to_employee_id: str = Form(...), from_employee_id: str = Form(...), message: str = Form(...), file_info: str = Form(None)):
    if not to_employee_id or not from_employee_id or (not message.strip() and not file_info):
        raise HTTPException(status_code=400, detail="All fields are required.")
    
    # Validate employee IDs
    from_name = None
    to_name = None
    for name, emp_id in EMPLOYEES.items():
        if emp_id == from_employee_id:
            from_name = name
        if emp_id == to_employee_id:
            to_name = name
    
    if not from_name or not to_name:
        raise HTTPException(status_code=400, detail="Invalid employee ID.")
    
    # Create DM key (consistent ordering)
    dm_key = "_".join(sorted([from_employee_id, to_employee_id]))
    
    if dm_key not in DIRECT_MESSAGES:
        DIRECT_MESSAGES[dm_key] = []
    
    # Process links in message
    links = []
    if message.strip():
        found_links = extract_links_from_message(message)
        links = [get_link_preview(link) for link in found_links]
    
    # Parse file info if provided
    file_attachment = None
    if file_info:
        try:
            import json
            file_attachment = json.loads(file_info)
        except:
            pass
    
    # Create message object
    message_id = f"dm_{dm_key}_{len(DIRECT_MESSAGES[dm_key]) + 1}_{get_timestamp()}"
    dm_message = {
        "id": message_id,
        "from_employee_id": from_employee_id,
        "from_employee_name": from_name,
        "to_employee_id": to_employee_id,
        "to_employee_name": to_name,
        "message": message.strip(),
        "timestamp": get_timestamp(),
        "edited": False,
        "edited_at": None,
        "file_attachment": file_attachment,
        "links": links
    }
    
    DIRECT_MESSAGES[dm_key].append(dm_message)
    
    # Keep only last 500 DM messages
    if len(DIRECT_MESSAGES[dm_key]) > 500:
        DIRECT_MESSAGES[dm_key].pop(0)
    
    return JSONResponse(content={"status": "success", "message": "DM sent successfully.", "message_id": message_id})

# -------------------- SHOPIFY API ENDPOINTS --------------------

@app.get("/api/shopify/analytics")
def get_shopify_analytics():
    """Get analytics data from Shopify store."""
    try:
        analytics = fetch_shopify_analytics()
        
        # Cache the analytics
        SHOPIFY_CACHE["analytics"] = analytics
        SHOPIFY_CACHE["last_updated"] = get_timestamp()
        
        return JSONResponse(content=analytics)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching analytics: {str(e)}")

@app.post("/api/shopify/config")
def configure_shopify(store_name: str = Form(...), access_token: str = Form(...), current_user: Dict = Depends(require_roles("owner", "admin"))):
    """Configure Shopify store connection."""
    try:
        # Test the connection
        old_config = SHOPIFY_CONFIG.copy()
        SHOPIFY_CONFIG["store_name"] = store_name.strip()
        SHOPIFY_CONFIG["access_token"] = access_token.strip()
        
        # Test API call
        test_data = make_shopify_request("shop.json")
        shop_info = test_data.get("shop", {})
        
        return JSONResponse(content={
            "success": True,
            "message": "Shopify store connected successfully!",
            "shop_name": shop_info.get("name", store_name),
            "shop_domain": shop_info.get("domain", f"{store_name}.myshopify.com"),
            "currency": shop_info.get("currency", "USD")
        })
    except Exception as e:
        # Restore old config on error
        SHOPIFY_CONFIG.update(old_config)
        raise HTTPException(status_code=400, detail=f"Failed to connect to Shopify: {str(e)}")

@app.get("/api/shopify/config")
def get_shopify_config(current_user: Dict = Depends(require_roles("owner", "admin"))):
    """Get current Shopify configuration status."""
    return JSONResponse(content={
        "configured": bool(SHOPIFY_CONFIG["store_name"] and SHOPIFY_CONFIG["access_token"]),
        "store_name": SHOPIFY_CONFIG["store_name"],
        "api_version": SHOPIFY_CONFIG["api_version"],
        "last_updated": SHOPIFY_CACHE.get("last_updated")
    })

# -------------------- USER MANAGEMENT API --------------------
@app.get("/api/users/stats")
def get_users_stats(current_user: Dict = Depends(require_roles("owner", "admin"))):
    """Get user statistics for dashboard."""
    return JSONResponse(content=get_user_stats())

@app.get("/api/users")
def get_users(
    search: str = "",
    role: str = "",
    status: str = "",
    sort_by: str = "name",
    sort_dir: str = "asc",
    current_user: Dict = Depends(require_roles("owner", "admin"))
):
    """Get filtered and sorted user list."""
    users = list(USERS_DATABASE.values())
    
    # Add role-based icon data to each user
    for user in users:
        role_icon_data = get_role_icon(user["role"])
        user["icon"] = role_icon_data["icon"]
        user["icon_color"] = role_icon_data["icon_color"]
    
    # Apply filters
    if search:
        search = search.lower()
        users = [u for u in users if search in u["name"].lower() or search in u["email"].lower() or search in u["id"].lower()]
    
    if role:
        users = [u for u in users if u["role"] == role]
    
    if status:
        users = [u for u in users if u["status"] == status]
    
    # Apply sorting
    reverse = sort_dir == "desc"
    if sort_by == "name":
        users.sort(key=lambda x: x["name"], reverse=reverse)
    elif sort_by == "role":
        users.sort(key=lambda x: x["role"], reverse=reverse)
    elif sort_by == "status":
        users.sort(key=lambda x: x["status"], reverse=reverse)
    elif sort_by == "last_login":
        users.sort(key=lambda x: x["last_login"], reverse=reverse)
    elif sort_by == "login_count":
        users.sort(key=lambda x: x["login_count"], reverse=reverse)
    
    return JSONResponse(content={
        "users": users,
        "total": len(users),
        "roles": list(ROLE_DEFINITIONS.keys()),
        "permissions": PERMISSION_DEFINITIONS,
        "role_icons": ROLE_ICONS
    })

@app.post("/api/users/{user_id}/toggle-status")
def toggle_user_status(user_id: str, admin_user: str = "EMP001", current_user: Dict = Depends(require_roles("owner", "admin"))):
    """Toggle user active/inactive status."""
    if user_id not in USERS_DATABASE:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = USERS_DATABASE[user_id]
    old_status = user["status"]
    new_status = "inactive" if old_status == "active" else "active"
    
    user["status"] = new_status
    
    # Save changes to file
    save_users_database()
    
    # Clear session if deactivating and invalidate all user sessions
    if new_status == "inactive":
        user["session_id"] = None
        invalidate_user_sessions(user_id)
    
    # Log audit trail
    log_audit_trail(admin_user, user_id, "status_change", old_status, new_status)
    log_user_activity(user_id, "status_changed", f"Status changed from {old_status} to {new_status}")
    
    return JSONResponse(content={
        "success": True,
        "user_id": user_id,
        "old_status": old_status,
        "new_status": new_status
    })
@app.post("/api/users/{user_id}/change-role")
def change_user_role(user_id: str, role_data: dict, admin_user: str = "EMP001", current_user: Dict = Depends(require_roles("owner", "admin"))):
    """Change user role and permissions."""
    if user_id not in USERS_DATABASE:
        raise HTTPException(status_code=404, detail="User not found")
    
    new_role = role_data.get("role")
    if new_role not in ROLE_DEFINITIONS:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    user = USERS_DATABASE[user_id]
    old_role = user["role"]
    
    # Update USERS_DATABASE
    user["role"] = new_role
    user["permissions"] = ROLE_DEFINITIONS[new_role]["permissions"].copy()
    
    # IMPORTANT: Always update USERS authentication database
    if user_id in USERS:
        USERS[user_id]["role"] = new_role
    else:
        # Create user in USERS if doesn't exist
        USERS[user_id] = {
            "employee_id": user_id,
            "name": user["name"],
            "role": new_role,
            "password_hash": pwd_context.hash("default123")  # Default password
        }
    
    # Save changes to files
    save_users_database()
    save_users_auth()
    
    # Force synchronization to ensure consistency
    sync_user_databases()
    
    # Sync to task system
    try:
        sync_user_to_task_system(user_id, user, USERS.get(user_id, {}))
    except Exception as e:
        print(f"Warning: Failed to sync role change to task system: {e}")
    
    # Invalidate user sessions to force re-authentication with new role
    # This ensures immediate effect of role changes
    invalidate_user_sessions(user_id)
    
    # Log audit trail
    log_audit_trail(admin_user, user_id, "role_change", old_role, new_role)
    log_user_activity(user_id, "role_changed", f"Role changed from {old_role} to {new_role}")
    
    return JSONResponse(content={
        "success": True,
        "user_id": user_id,
        "old_role": old_role,
        "new_role": new_role,
        "new_permissions": user["permissions"]
    })

@app.post("/api/users/{user_id}/update-permissions")
def update_user_permissions(user_id: str, permission_data: dict, admin_user: str = "EMP001", current_user: Dict = Depends(require_roles("owner", "admin"))):
    """Update user permissions directly."""
    if user_id not in USERS_DATABASE:
        raise HTTPException(status_code=404, detail="User not found")
    
    new_permissions = permission_data.get("permissions", [])
    user = USERS_DATABASE[user_id]
    old_permissions = user["permissions"].copy()
    
    user["permissions"] = new_permissions
    
    # Log audit trail
    log_audit_trail(admin_user, user_id, "permissions_change", str(old_permissions), str(new_permissions))
    log_user_activity(user_id, "permissions_updated", f"Permissions updated")
    
    return JSONResponse(content={
        "success": True,
        "user_id": user_id,
        "old_permissions": old_permissions,
        "new_permissions": new_permissions
    })
@app.post("/api/users/{user_id}/change-password")
def change_user_password(user_id: str, password_data: dict, admin_user: str = "EMP001", current_user: Dict = Depends(require_roles("owner", "admin"))):
    """Change user password."""
    if user_id not in USERS_DATABASE:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user_id not in USERS:
        raise HTTPException(status_code=404, detail="User not found in authentication database")
    
    new_password = password_data.get("password", "").strip()
    if not new_password:
        raise HTTPException(status_code=400, detail="Password cannot be empty")
    
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")
    
    user_profile = USERS_DATABASE[user_id]
    user_auth = USERS[user_id]
    
    # Hash the new password
    new_password_hash = hash_password(new_password)
    old_password_hash = user_auth["password_hash"]
    
    # Update password in authentication database
    user_auth["password_hash"] = new_password_hash
    
    # Save authentication changes to file
    save_users_auth()
    
    # Invalidate all user sessions to force re-login with new password
    invalidate_user_sessions(user_id)
    
    # Log audit trail (don't log actual passwords, just that it was changed)
    log_audit_trail(admin_user, user_id, "password_change", "password_changed", "password_changed")
    log_user_activity(user_id, "password_changed", f"Password changed by {current_user.get('name', admin_user)}")
    
    return JSONResponse(content={
        "success": True, 
        "message": f"Password changed for {user_profile['name']}. User will need to login with the new password."
    })

@app.post("/api/users/create")
async def create_new_user(
    employee_id: str = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
    joining_date: str = Form(...),
    phone: str = Form(""),
    shift: str = Form(""),
    manager: str = Form(""),
    address: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    zip: str = Form(""),
    emergency_contact_name: str = Form(""),
    emergency_contact_relation: str = Form(""),
    emergency_contact_phone: str = Form(""),
    emergency_contact_email: str = Form(""),
    photo: UploadFile = File(None),
    current_user: Dict = Depends(require_roles("owner", "admin"))
):
    """Create a new user with complete profile information."""
    
    # Import datetime for use throughout the function
    from datetime import datetime as dt
    
    # Validate required fields
    if not employee_id.strip():
        raise HTTPException(status_code=400, detail="Employee ID is required")
    if not name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if not email.strip():
        raise HTTPException(status_code=400, detail="Email is required")
    if not role.strip():
        raise HTTPException(status_code=400, detail="Role is required")
    if not joining_date.strip():
        raise HTTPException(status_code=400, detail="Joining date is required")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")
    
    # Validate joining date format
    try:
        dt.strptime(joining_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid joining date format. Use YYYY-MM-DD")
    
    # Validate manager exists if provided
    if manager and manager not in USERS_DATABASE:
        raise HTTPException(status_code=400, detail="Selected manager does not exist")
    
    # Check if user already exists
    if employee_id in USERS_DATABASE or employee_id in USERS:
        raise HTTPException(status_code=400, detail="Employee ID already exists")
    
    # Validate role
    if role not in ROLE_DEFINITIONS:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    # Handle photo upload
    photo_url = f"https://via.placeholder.com/100/4F46E5/ffffff?text={name[0].upper()}"
    if photo:
        # In a real application, you would save this to a file storage service
        # For now, we'll create a data URL (in production, save to disk/cloud)
        try:
            photo_content = await photo.read()
            if len(photo_content) > 5 * 1024 * 1024:  # 5MB limit
                raise HTTPException(status_code=400, detail="Photo file size must be less than 5MB")
            
            # Create uploads directory if it doesn't exist
            uploads_dir = "uploads/profiles"
            os.makedirs(uploads_dir, exist_ok=True)
            
            # Save photo
            photo_filename = f"{employee_id}_{photo.filename}"
            photo_path = os.path.join(uploads_dir, photo_filename)
            with open(photo_path, "wb") as f:
                f.write(photo_content)
            
            photo_url = f"/uploads/profiles/{photo_filename}"
        except Exception as e:
            # If photo upload fails, use placeholder
            print(f"Photo upload failed: {e}")
    
    # Handle document uploads (from request.form)
    documents = []
    # Note: Documents would be handled similarly to photos in a real application
    
    # Create user in USERS_DATABASE
    user_data = {
        "id": employee_id,
        "name": name.strip(),
        "email": email.strip().lower(),
        "role": role,
        "status": "active",
        "photo": photo_url,
        "phone": phone.strip(),
        "joining_date": joining_date.strip(),
        "shift": shift.strip() if shift else "",
        "manager": manager.strip() if manager else "",
        "address": address.strip(),
        "city": city.strip(),
        "state": state.strip(),
        "zip": zip.strip(),
        "emergency_contact": {
            "name": emergency_contact_name.strip(),
            "relation": emergency_contact_relation.strip(),
            "phone": emergency_contact_phone.strip(),
            "email": emergency_contact_email.strip()
        },
        "documents": documents,
        "created_date": dt.now().strftime("%Y-%m-%d"),
        "last_login": None,
        "login_count": 0,
        "permissions": ROLE_DEFINITIONS.get(role, {}).get("permissions", []),
        "session_id": None
    }
    
    USERS_DATABASE[employee_id] = user_data
    
    # Save USERS_DATABASE to file
    save_users_database()
    
    # Create user in USERS (authentication database)
    auth_user_data = {
        "employee_id": employee_id,
        "name": name.strip(),
        "role": role,
        "password_hash": hash_password(password)
    }
    
    USERS[employee_id] = auth_user_data
    
    # Save USERS to file
    save_users_auth()
    
    # Auto-sync to task system
    try:
        sync_user_to_task_system(employee_id, user_data, auth_user_data)
    except Exception as e:
        # Log error but don't fail user creation
        print(f"Warning: Failed to sync user {employee_id} to task system: {e}")
    
    # Log audit trail
    log_audit_trail(current_user.get("employee_id", "system"), employee_id, "user_created", "", f"User {name} created with role {role}")
    log_user_activity(employee_id, "account_created", f"Account created by {current_user.get('name', 'admin')}")
    
    return JSONResponse(content={
        "success": True,
        "message": f"User {name} created successfully! They can now login with Employee ID: {employee_id}",
        "user_id": employee_id
    })

@app.post("/api/roles/create")
def create_role(role_data: dict, admin_user: str = "EMP001", current_user: Dict = Depends(require_roles("owner"))):
    """Create a new role with custom permissions."""
    role_name = role_data.get("name", "").strip()
    role_description = role_data.get("description", "").strip()
    role_permissions = role_data.get("permissions", [])
    role_color = role_data.get("color", "#6b7280")
    
    if not role_name:
        raise HTTPException(status_code=400, detail="Role name is required")
    
    if role_name in ROLE_DEFINITIONS:
        raise HTTPException(status_code=400, detail="Role already exists")
    
    # Validate permissions
    valid_permissions = set(PERMISSION_DEFINITIONS.keys())
    if not all(perm in valid_permissions for perm in role_permissions):
        raise HTTPException(status_code=400, detail="Invalid permissions specified")
    
    ROLE_DEFINITIONS[role_name] = {
        "name": role_name,
        "description": role_description,
        "permissions": role_permissions,
        "color": role_color,
        "custom": True  # Mark as custom role
    }
    
    # Log audit trail
    log_audit_trail(admin_user, "SYSTEM", "role_created", "", f"Created role: {role_name}")
    
    return JSONResponse(content={
        "success": True,
        "role": ROLE_DEFINITIONS[role_name]
    })

@app.put("/api/roles/{role_name}")
def update_role(role_name: str, role_data: dict, admin_user: str = "EMP001", current_user: Dict = Depends(require_roles("owner"))):
    """Update an existing role."""
    if role_name not in ROLE_DEFINITIONS:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Prevent editing system roles (only custom roles can be fully edited)
    role = ROLE_DEFINITIONS[role_name]
    if not role.get("custom", False):
        raise HTTPException(status_code=400, detail="Cannot modify system roles")
    
    old_role = role.copy()
    
    # Update role properties
    if "description" in role_data:
        role["description"] = role_data["description"].strip()
    if "permissions" in role_data:
        # Validate permissions
        valid_permissions = set(PERMISSION_DEFINITIONS.keys())
        if not all(perm in valid_permissions for perm in role_data["permissions"]):
            raise HTTPException(status_code=400, detail="Invalid permissions specified")
        role["permissions"] = role_data["permissions"]
    if "color" in role_data:
        role["color"] = role_data["color"]
    
    # Update all users with this role
    updated_users = []
    for user_id, user in USERS_DATABASE.items():
        if user["role"] == role_name:
            user["permissions"] = role["permissions"].copy()
            updated_users.append(user_id)
    
    # Log audit trail
    log_audit_trail(admin_user, "SYSTEM", "role_updated", str(old_role), str(role))
    
    return JSONResponse(content={
        "success": True,
        "role": role,
        "updated_users": updated_users
    })

@app.delete("/api/roles/{role_name}")
def delete_role(role_name: str, admin_user: str = "EMP001", current_user: Dict = Depends(require_roles("owner"))):
    """Delete a custom role."""
    if role_name not in ROLE_DEFINITIONS:
        raise HTTPException(status_code=404, detail="Role not found")
    
    role = ROLE_DEFINITIONS[role_name]
    if not role.get("custom", False):
        raise HTTPException(status_code=400, detail="Cannot delete system roles")
    
    # Check if any users have this role
    users_with_role = [user_id for user_id, user in USERS_DATABASE.items() if user["role"] == role_name]
    if users_with_role:
        raise HTTPException(status_code=400, detail=f"Cannot delete role: {len(users_with_role)} users still have this role")
    
    # Delete the role
    deleted_role = ROLE_DEFINITIONS.pop(role_name)
    
    # Log audit trail
    log_audit_trail(admin_user, "SYSTEM", "role_deleted", str(deleted_role), "")
    
    return JSONResponse(content={
        "success": True,
        "deleted_role": role_name
    })

@app.get("/api/roles")
def get_roles(current_user: Dict = Depends(require_roles("owner", "admin"))):
    """Get all available roles and their definitions."""
    return JSONResponse(content={
        "roles": ROLE_DEFINITIONS,
        "permissions": PERMISSION_DEFINITIONS
    })

@app.get("/api/shopify/orders")
def api_shopify_orders(
    status: str = "any",
    fulfillment_status: str = None,
    limit: int = 100,
    page_info: str = None,
    created_at_min: str = None,
    created_at_max: str = None,
    current_user: Dict = Depends(require_roles("owner", "admin", "manager"))
):
    """Fetch orders from Shopify with pagination support."""
    try:
        params = {
            "limit": min(limit, 250),  # Shopify max is 250
            "status": status,
            "fields": "id,name,order_number,created_at,financial_status,fulfillment_status,customer,email,order_status_url,line_items"
        }
        
        # Add optional parameters
        if fulfillment_status:
            params["fulfillment_status"] = fulfillment_status
        if page_info:
            params["page_info"] = page_info
        if created_at_min:
            params["created_at_min"] = created_at_min
        if created_at_max:
            params["created_at_max"] = created_at_max
            
        # Call Shopify API
        data = _shopify_get("/orders.json", params)
        
        return JSONResponse(content={
            "orders": data.get("orders", []),
            "next_page_info": data["_pagination"]["next_page_info"],
            "prev_page_info": data["_pagination"]["prev_page_info"]
        })
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Shopify orders: {str(e)}")

# -------------------- AUTHENTICATION API ENDPOINTS --------------------
@app.post("/api/auth/login")
def login(
    employee_id: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False)
):
    """Authenticate user and create session."""
    # Find user in authentication database
    user = USERS.get(employee_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid employee ID or password"
        )
    
    # Check if user is active in user management database
    user_profile = USERS_DATABASE.get(employee_id)
    if not user_profile:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found"
        )
    
    if user_profile["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated. Please contact your administrator."
        )
    
    # Verify password
    if not verify_password(password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid employee ID or password"
        )
    
    # Create session
    session_token = create_session(employee_id, remember_me)
    
    # Create response
    response = JSONResponse(content={
        "message": "Login successful",
        "user": {
            "employee_id": user["employee_id"],
            "name": user["name"],
            "role": user["role"]
        }
    })
    
    # Set session cookie
    max_age = (30 * 24 * 60 * 60) if remember_me else (7 * 24 * 60 * 60)  # seconds
    response.set_cookie(
        key="session_id",
        value=session_token,
        max_age=max_age,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax"
    )
    
    return response


@app.delete("/api/users/{user_id}")
def delete_user(
    user_id: str,
    delete_files: bool = True,
    current_user: Dict = Depends(require_roles("owner", "admin"))
):
    """Delete a user from both the profile database and authentication store.
    - Only owner/admin can delete
    - Cannot delete the owner account or self
    - Invalidates sessions and optionally removes uploaded profile photo
    """
    # Prevent self-deletion to avoid locking out the current admin
    if current_user.get("employee_id") == user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    # Ensure user exists
    if user_id not in USERS_DATABASE:
        raise HTTPException(status_code=404, detail="User not found")

    user_profile = USERS_DATABASE[user_id]

    # Disallow deleting owner accounts
    if user_profile.get("role") == "owner":
        raise HTTPException(status_code=403, detail="Owner accounts cannot be deleted")

    # Remove from auth if present
    if user_id in USERS:
        USERS.pop(user_id, None)

    # Invalidate sessions
    try:
        invalidate_user_sessions(user_id)
    except Exception:
        pass

    # Attempt to remove uploaded profile photo if local
    if delete_files:
        try:
            photo_url = user_profile.get("photo", "")
            if isinstance(photo_url, str) and photo_url.startswith("/uploads/"):
                uploads_root = Path("uploads").resolve()
                candidate = Path("." + photo_url).resolve()
                if uploads_root in candidate.parents and candidate.exists():
                    try:
                        candidate.unlink()
                    except Exception:
                        pass
        except Exception:
            pass

    # Remove from user database and persist
    USERS_DATABASE.pop(user_id, None)
    save_users_database()
    save_users_auth()

    return JSONResponse(content={
        "success": True,
        "message": f"User {user_id} deleted successfully"
    })

@app.post("/api/auth/logout")
def logout(session_id: str = Cookie(None, alias="session_id")):
    """Logout user and clear session."""
    if session_id and session_id in SESSIONS:
        del SESSIONS[session_id]
    
    response = JSONResponse(content={"message": "Logout successful"})
    response.delete_cookie("session_id")
    return response

@app.get("/api/auth/me")
def get_current_user_info(current_user: Dict = Depends(require_roles())):
    """Get current logged-in user information."""
    return {
        "employee_id": current_user["employee_id"],
        "name": current_user["name"],
        "role": current_user["role"]
    }

@app.get("/api/auth/navigation")
def get_current_user_navigation(current_user: Dict = Depends(require_roles())):
    """Get navigation menu for current authenticated user."""
    user_role = current_user["role"]
    menu_with_access = get_navigation_with_access(user_role)
    return JSONResponse(content={
        "role": user_role,
        "menu": menu_with_access
    })

@app.get("/api/shopify/orders/all")
def api_shopify_orders_all(
    status: str = "any",
    fulfillment_status: str = None,
    created_at_min: str = None,
    created_at_max: str = None,
    current_user: Dict = Depends(require_roles("owner", "admin", "manager"))
):
    """
    Fetch ALL orders from Shopify using cursor-based pagination.
    This endpoint will retrieve every order matching the criteria across all pages.
    
    Query Parameters:
    - status: Order status filter (any, open, closed, cancelled)
    - fulfillment_status: Fulfillment status filter (fulfilled, partial, unfulfilled, pending)
    - created_at_min: Start date filter (ISO format, e.g., 2024-01-01T00:00:00Z)
    - created_at_max: End date filter (ISO format, e.g., 2024-12-31T23:59:59Z)
    
    Returns:
    - count: Total number of orders retrieved
    - orders: Array of all orders matching the criteria
    """
    try:
        print(f"Starting fetch_all_orders_rest with filters: status={status}, fulfillment_status={fulfillment_status}, created_at_min={created_at_min}, created_at_max={created_at_max}")
        
        # Use the new helper function to get all orders
        all_orders = fetch_all_orders_rest(
            status=status,
            fulfillment_status=fulfillment_status,
            created_at_min=created_at_min,
            created_at_max=created_at_max,
            limit=250  # Use maximum page size for efficiency
        )
        
        print(f"Successfully retrieved {len(all_orders)} total orders")
        
        return JSONResponse(content={
            "count": len(all_orders),
            "orders": all_orders
        })
        
    except HTTPException as e:
        print(f"HTTPException in api_shopify_orders_all: {e.detail}")
        raise e
    except Exception as e:
        print(f"Unexpected error in api_shopify_orders_all: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching all Shopify orders: {str(e)}")

# -------------------- USER ROLES & NAVIGATION API --------------------
@app.get("/api/user/{employee_id}/role")
def get_user_role(employee_id: str):
    if employee_id not in USER_ROLES:
        raise HTTPException(status_code=404, detail="User not found.")
    
    user_info = USER_ROLES[employee_id]
    return JSONResponse(content={
        "employee_id": employee_id,
        "name": user_info["name"],
        "role": user_info["role"],
        "permissions": user_info["permissions"]
    })

@app.get("/api/navigation/{role}")
def get_navigation_menu(role: str, current_user: Dict = Depends(require_roles())):
    # Get menu with access information based on user's actual role
    user_role = current_user["role"]
    menu_with_access = get_navigation_with_access(user_role)
    return JSONResponse(content={"role": user_role, "menu": menu_with_access})

@app.get("/api/user/{employee_id}/navigation")
def get_user_navigation(employee_id: str, current_user: Dict = Depends(require_roles())):
    if employee_id not in USER_ROLES:
        raise HTTPException(status_code=404, detail="User not found.")
    
    user_role = USER_ROLES[employee_id]["role"]
    # Get menu with access information based on user's role
    menu_with_access = get_navigation_with_access(user_role)
    
    return JSONResponse(content={
        "employee_id": employee_id,
        "role": user_role,
        "menu": menu_with_access
    })

@app.get("/api/chat/dm/{other_employee_id}")
def get_direct_messages(other_employee_id: str, current_employee_id: str, limit: int = 50):
    # Create DM key
    dm_key = "_".join(sorted([current_employee_id, other_employee_id]))
    
    if dm_key not in DIRECT_MESSAGES:
        return JSONResponse(content={"messages": []})
    
    messages = DIRECT_MESSAGES[dm_key]
    recent_messages = messages[-limit:] if len(messages) > limit else messages
    
    # Add reactions to messages
    for msg in recent_messages:
        msg["reactions"] = MESSAGE_REACTIONS.get(msg["id"], {})
    
    return JSONResponse(content={"messages": recent_messages})

@app.post("/api/chat/reaction/add")
def add_reaction(message_id: str = Form(...), employee_id: str = Form(...), emoji: str = Form(...)):
    if not message_id or not employee_id or not emoji:
        raise HTTPException(status_code=400, detail="All fields are required.")
    
    if message_id not in MESSAGE_REACTIONS:
        MESSAGE_REACTIONS[message_id] = {}
    
    if emoji not in MESSAGE_REACTIONS[message_id]:
        MESSAGE_REACTIONS[message_id][emoji] = []
    
    if employee_id not in MESSAGE_REACTIONS[message_id][emoji]:
        MESSAGE_REACTIONS[message_id][emoji].append(employee_id)
    
    return JSONResponse(content={"status": "success", "message": "Reaction added."})

@app.post("/api/chat/reaction/remove")
def remove_reaction(message_id: str = Form(...), employee_id: str = Form(...), emoji: str = Form(...)):
    if not message_id or not employee_id or not emoji:
        raise HTTPException(status_code=400, detail="All fields are required.")
    
    if message_id in MESSAGE_REACTIONS and emoji in MESSAGE_REACTIONS[message_id]:
        if employee_id in MESSAGE_REACTIONS[message_id][emoji]:
            MESSAGE_REACTIONS[message_id][emoji].remove(employee_id)
            
            # Clean up empty reactions
            if not MESSAGE_REACTIONS[message_id][emoji]:
                del MESSAGE_REACTIONS[message_id][emoji]
            if not MESSAGE_REACTIONS[message_id]:
                del MESSAGE_REACTIONS[message_id]
    
    return JSONResponse(content={"status": "success", "message": "Reaction removed."})

@app.post("/api/chat/status/update")
def update_user_status(employee_id: str = Form(...), status: str = Form("online")):
    if not employee_id:
        raise HTTPException(status_code=400, detail="Employee ID is required.")
    
    USER_STATUS[employee_id] = {
        "status": status,
        "last_seen": get_timestamp()
    }
    
    return JSONResponse(content={"status": "success", "message": "Status updated."})

@app.get("/api/chat/users/online")
def get_online_users():
    online_users = []
    current_time = datetime.datetime.utcnow()
    
    for emp_id, status_info in USER_STATUS.items():
        last_seen = datetime.datetime.fromisoformat(status_info["last_seen"])
        # Consider user online if they were active in the last 5 minutes
        if (current_time - last_seen).total_seconds() < 300:
            # Get employee name
            emp_name = None
            for name, id_val in EMPLOYEES.items():
                if id_val == emp_id:
                    emp_name = name
                    break
            
            online_users.append({
                "employee_id": emp_id,
                "employee_name": emp_name or emp_id,
                "status": status_info["status"],
                "last_seen": status_info["last_seen"]
            })
    
    return JSONResponse(content={"online_users": online_users})

@app.post("/api/chat/upload")
async def upload_chat_file(file: UploadFile = File(...), employee_id: str = Form(...)):
    if not employee_id:
        raise HTTPException(status_code=400, detail="Employee ID is required.")
    
    # Validate file size (max 10MB)
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max size is 10MB.")
    
    # Generate unique filename
    file_extension = file.filename.split('.')[-1] if '.' in file.filename else ''
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = UPLOADS_DIR / unique_filename
    
    # Save file
    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Get file info
        file_type = get_file_type(file.filename)
        file_size = len(content)
        
        # Create file info object
        file_info = {
            "id": str(uuid.uuid4()),
            "filename": file.filename,
            "unique_filename": unique_filename,
            "file_type": file_type,
            "file_size": file_size,
            "uploaded_by": employee_id,
            "upload_time": get_timestamp(),
            "url": f"/uploads/chat/{unique_filename}"
        }
        
        return JSONResponse(content={"status": "success", "file": file_info})
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")
# -------------------- ATTENDANCE --------------------
@app.post("/api/attendance/check_in")
def check_in(employee_id: str = Form(...)):
    if employee_id not in ATTENDANCE_RECORDS:
        ATTENDANCE_RECORDS[employee_id] = []
    
    # Check if already checked in
    if ATTENDANCE_RECORDS[employee_id] and "check_out_time" not in ATTENDANCE_RECORDS[employee_id][-1]:
        raise HTTPException(status_code=400, detail="Already checked in.")

    ATTENDANCE_RECORDS[employee_id].append({"check_in_time": get_timestamp()})
    return JSONResponse(content={"status": "success", "message": "Checked in successfully."})

@app.post("/api/attendance/check_out")
def check_out(employee_id: str = Form(...)):
    if employee_id not in ATTENDANCE_RECORDS or not ATTENDANCE_RECORDS[employee_id]:
        raise HTTPException(status_code=400, detail="Not checked in yet.")
    
    last_record = ATTENDANCE_RECORDS[employee_id][-1]
    if "check_out_time" in last_record:
        raise HTTPException(status_code=400, detail="Already checked out.")

    last_record["check_out_time"] = get_timestamp()
    return JSONResponse(content={"status": "success", "message": "Checked out successfully."})

@app.get("/api/attendance/records")
def get_attendance_records(employee_id: str | None = None, date: str | None = None):
    filtered_records = {}
    for emp_id, records in ATTENDANCE_RECORDS.items():
        if employee_id and emp_id != employee_id:
            continue
        
        emp_filtered_records = []
        for record in records:
            if date:
                record_date = datetime.datetime.fromisoformat(record["check_in_time"]).strftime("%Y-%m-%d")
                if record_date != date:
                    continue
            emp_filtered_records.append(record)
        
        if emp_filtered_records:
            filtered_records[emp_id] = emp_filtered_records
            
    return JSONResponse(content=filtered_records)

@app.get("/api/attendance/report")
def get_attendance_report(employee_id: str | None = None, start_date: str | None = None, end_date: str | None = None):
    report = {}
    for emp_id, records in ATTENDANCE_RECORDS.items():
        if employee_id and emp_id != employee_id:
            continue
        
        total_hours = 0.0
        for record in records:
            if "check_in_time" in record and "check_out_time" in record:
                record_date = datetime.datetime.fromisoformat(record["check_in_time"]).date()
                if start_date and record_date < datetime.date.fromisoformat(start_date):
                    continue
                if end_date and record_date > datetime.date.fromisoformat(end_date):
                    continue
                total_hours += calculate_duration(record["check_in_time"], record["check_out_time"])
        if total_hours > 0 or not records: # Include employee even if 0 hours, but not if no records
             report[emp_id] = {"total_hours": round(total_hours, 2)}
    return JSONResponse(content=report)

@app.get("/api/attendance/overtime")
def get_overtime_report(threshold_hours: float = 8.0, employee_id: str | None = None, start_date: str | None = None, end_date: str | None = None):
    overtime_report = {}
    for emp_id, records in ATTENDANCE_RECORDS.items():
        if employee_id and emp_id != employee_id:
            continue

        total_hours = 0.0
        for record in records:
            if "check_in_time" in record and "check_out_time" in record:
                record_date = datetime.datetime.fromisoformat(record["check_in_time"]).date()
                if start_date and record_date < datetime.date.fromisoformat(start_date):
                    continue
                if end_date and record_date > datetime.date.fromisoformat(end_date):
                    continue
                total_hours += calculate_duration(record["check_in_time"], record["check_out_time"])
        
        if total_hours > 0 or not records:
            overtime = max(0.0, total_hours - threshold_hours)
            overtime_report[emp_id] = {"total_hours": round(total_hours, 2), "overtime_hours": round(overtime, 2)}
    return JSONResponse(content=overtime_report)
@app.get("/api/attendance/export")
def export_attendance_data(employee_id: str | None = None, start_date: str | None = None, end_date: str | None = None):
    data_for_df = []
    for emp_id, records in ATTENDANCE_RECORDS.items():
        if employee_id and emp_id != employee_id:
            continue
        for record in records:
            if "check_in_time" in record:
                record_date = datetime.datetime.fromisoformat(record["check_in_time"]).date()
                if start_date and record_date < datetime.date.fromisoformat(start_date):
                    continue
                if end_date and record_date > datetime.date.fromisoformat(end_date):
                    continue
            row = {"employee_id": emp_id}
            row.update(record)
            data_for_df.append(row)

    if not data_for_df:
        raise HTTPException(status_code=404, detail="No attendance data to export.")

    df = pd.DataFrame(data_for_df)
    
    # Convert timestamps to datetime objects for better formatting in CSV
    for col in ["check_in_time", "check_out_time"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])

    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    
    headers = {
        "Content-Disposition": "attachment; filename=\"attendance_data.csv\"".encode('latin-1').decode('utf-8'),
        "Content-Type": "text/csv",
    }
    return FileResponse(path=io.BytesIO(csv_buffer.getvalue().encode('utf-8')), media_type="text/csv", filename="attendance_data.csv", headers=headers)


# -------------------- PACKING MANAGEMENT — API --------------------
@app.post("/api/packing/preview")
async def packing_preview(file: UploadFile = File(...)):
    """Accept Organized Orders CSV/XLSX and return normalized rows for the table."""
    try:
        data = await file.read()
        if file.filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)
        elif file.filename.lower().endswith((".xls", ".xlsx")):
            df = pd.read_excel(io.BytesIO(data), dtype=str).fillna("")
        else:
            return JSONResponse({"error": "Unsupported file type"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"Failed to read file: {e}"}, status_code=400)

    cols = {c.strip(): c for c in df.columns}

    def col(name: str):
        return cols.get(name)

    rows = []
    for _, r in df.iterrows():
        order = r.get(col("Order Number") or "Order Number", r.get("Order Name", ""))
        product = (r.get(col("Product Name") or "Product Name", r.get("Lineitem Name", "")) or "").strip()
        variant = (r.get(col("Variant") or "Variant", r.get("Lineitem Variant Title", "")) or "").strip()
        main_link = (r.get(col("Main Photo Link") or "Main Photo Link", "") or "").strip()
        polaroid_raw = r.get(col("Polaroid Link(s)") or "Polaroid Link(s)", "")
        polaroids = [p.strip() for p in str(polaroid_raw).split(",") if p.strip()]
        back_type = r.get(col("Back Engraving Type") or "Back Engraving Type", "")
        back_value = r.get(col("Back Engraving Value") or "Back Engraving Value", "")
        status = r.get(col("Main Photo Status") or "Main Photo Status", "")
        polaroid_count = r.get(col("Polaroid Count") or "Polaroid Count", "")

        rows.append({
            "Order Number": order,
            "Product Name": product,
            "Variant": variant,

            "Main Photo": main_link,
            "Polaroids": polaroids,
            "Back Engraving Type": back_type,
            "Back Engraving Value": back_value,
        })

    return {
        "columns": [
            "Order Number", "Product Name", "Variant", "Color",
            "Main Photo", "Polaroids", "Back Engraving Type", "Back Engraving Value",
            "Main Photo Status", "Polaroid Count",
        ],
        "rows": rows,
    }


# -------------------- PACKING MANAGEMENT — PAGE --------------------
@app.get("/packing")
def eraya_packing_page(current_user: Dict = Depends(require_roles("owner", "admin", "manager", "packer"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Order Packing Management</h1>
      <p class="text-white/80 mt-2">Upload Organized Orders CSV/XLSX and preview as a table.</p>

      <div class="mt-6 grid gap-6">
        <div class="glass p-5">
          <div class="flex flex-wrap items-center gap-3">
            <input type="file" id="f" accept=".csv,.xlsx"
                   class="rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" />
            <button type="button" id="go" class="btn btn-primary">Preview</button>
            <button type="button" id="export" class="btn btn-secondary">Export CSV (filtered)</button>
            <div id="status" class="text-white/70">Waiting for file…</div>
          </div>
          <div class="flex flex-wrap gap-3 mt-3">
            <input id="qOrder" placeholder="Search Order #" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <input id="qProd"  placeholder="Search Product" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <input id="qVar"   placeholder="Search Variant" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <select id="qStatus" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <option value="">All Statuses</option>
              <option value="Packed">Packed</option>
              <option value="Dispute">Dispute</option>
              <option value="Bad photo">Bad photo</option>
              <option value="Missing photo">Missing photo</option>
            </select>
            <select id="pageSize" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <option value="25">25 / page</option>
              <option value="50">50 / page</option>
              <option value="100">100 / page</option>
              <option value="500">500 / page</option>
            </select>
          </div>
          <!-- Minimal faceted filters - same style as other filters -->
          <div class="flex flex-wrap gap-3 mt-3" id="facetedFilters">
            <select id="qSKU" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <option value="">All SKUs</option>
            </select>
            <select id="qVariant" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <option value="">All Variants</option>
            </select>
            <select id="qPacker" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <option value="">All Packers</option>
            </select>
          </div>
          <!-- Selected filters chips -->
          <div id="selectedFiltersChips" class="flex flex-wrap gap-2 mt-3 hidden">
            <div class="text-xs text-white/60">Active filters:</div>
          </div>
        </div>

        <div class="glass p-0 overflow-auto relative" style="max-height:70vh">
          <table class="min-w-full text-sm" id="tbl">
            <thead class="sticky top-0 bg-slate-900/80 backdrop-blur z-10" id="head"></thead>
            <tbody id="body"></tbody>
          </table>

        </div>
        <div class="flex items-center gap-3">
          <button id="prev" class="btn btn-secondary">Prev</button>
          <div id="pageinfo" class="text-white/70 text-sm"></div>
          <button id="next" class="btn btn-secondary">Next</button>
        </div>
      </div>

      <!-- Simple lightbox -->
      <div id="lb" class="fixed inset-0 hidden items-center justify-center bg-black/70 p-6">
        <div class="bg-slate-900/90 border border-white/10 rounded-2xl p-4 max-w-5xl w-full">
          <div class="flex justify-between items-center mb-3">
            <div class="text-lg font-semibold">Polaroids</div>
            <button id="lbClose" class="btn btn-secondary">Close</button>
          </div>
          <div id="lbBody" class="grid grid-cols-2 md:grid-cols-4 gap-3"></div>
        </div>
      </div>
    </section>

    <style>
      #body tr:nth-child(even){ background: rgba(255,255,255,0.03); }
      .badge-miss{ background:#ef4444; color:white; padding:2px 6px; border-radius:6px; font-size:12px; }
      .packed{ opacity:.6; text-decoration: line-through; }
      #tbl tbody tr:hover { background-color: rgba(255,255,255,0.05); }
      #tbl th, #tbl td { padding: 0.75rem 0.5rem; text-align: left; vertical-align: top; }
      #tbl thead th { background-color: #0f172a; }
      .status-select { background: rgba(255,255,255,0.08); color: white; border: 1px solid rgba(255,255,255,0.2); border-radius: 0.5rem; padding: 0.25rem 0.5rem; }

      /* Frozen columns - Order Number and Product Name (SKU) */
      #tbl th:nth-child(1), #tbl td:nth-child(1) { position: sticky; left: 0; z-index: 9; background: #0f172a; width: 5%; }
      #tbl th:nth-child(2), #tbl td:nth-child(2) { position: sticky; left: 5%; z-index: 9; background: #0f172a; width: 10%; border-right: 2px solid rgba(59,130,246,0.3); }
      #tbl td:nth-child(1), #tbl td:nth-child(2) { background: rgba(15,23,42,0.95); }
      
      /* Column Widths */
      #tbl th:nth-child(3), #tbl td:nth-child(3) { width: 15%; /* Product Name */ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
      #tbl th:nth-child(4), #tbl td:nth-child(4) { width: 10%; /* Variant */ }
      #tbl th:nth-child(5), #tbl td:nth-child(5) { width: 5%;  /* Color */ }
      #tbl th:nth-child(6), #tbl td:nth-child(6) { width: 10%; /* Main Photo */ }
      #tbl th:nth-child(7), #tbl td:nth-child(7) { width: 10%; /* Polaroids */ }
      #tbl th:nth-child(8), #tbl td:nth-child(8) { width: 10%; /* Back Engraving Type */ }
      #tbl th:nth-child(9), #tbl td:nth-child(9) { width: 15%; /* Back Engraving Value */ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
      #tbl th:nth-child(10), #tbl td:nth-child(10) { width: 5%; /* Main Photo Status */ }
      #tbl th:nth-child(11), #tbl td:nth-child(11) { width: 5%; /* Polaroid Count */ }
      #tbl th:nth-child(12), #tbl td:nth-child(12) { width: 10%; /* Status */ }
      
      .truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .table-img { max-height: 80px; width: auto; cursor: pointer; transition: transform 0.2s; }
      .table-img:hover { transform: scale(1.05); }
      
      /* Status badges with chips styling */
      .status-badge { display: inline-block; padding: 4px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: capitalize; border: 1px solid; }
      .status-badge-Packed { background: rgba(16,185,129,0.2); color: #10b981; border-color: #10b981; }
      .status-badge-Dispute { background: rgba(245,158,11,0.2); color: #f59e0b; border-color: #f59e0b; }
      .status-badge-Badphoto { background: rgba(239,68,68,0.2); color: #ef4444; border-color: #ef4444; }
      .status-badge-Missingphoto { background: rgba(239,68,68,0.2); color: #ef4444; border-color: #ef4444; }
      .status-badge- { background: rgba(107,114,128,0.2); color: #6b7280; border-color: #6b7280; }
      
      /* Error highlighting */
      .error-missing-photo { background: rgba(239,68,68,0.1) !important; border-left: 3px solid #ef4444; }
      .error-invalid-variant { background: rgba(245,158,11,0.1) !important; border-left: 3px solid #f59e0b; }
      .overdue-sla { background: rgba(239,68,68,0.05) !important; border-left: 3px solid #dc2626; }
      
      /* Filter chips */
      .filter-chip { 
        display: inline-flex; align-items: center; gap: 4px; 
        background: rgba(59,130,246,0.2); color: #3b82f6; 
        border: 1px solid #3b82f6; border-radius: 16px; 
        padding: 4px 8px; font-size: 12px; font-weight: 500; 
      }
      .filter-chip button { 
        background: none; border: none; color: inherit; 
        cursor: pointer; font-weight: bold; margin-left: 4px; 
      }
      
      /* Dropdown styling */
      .facet-option { 
        display: flex; align-items: center; gap: 8px; 
        padding: 4px 8px; border-radius: 6px; cursor: pointer; 
        font-size: 12px; transition: background-color 0.2s; 
      }
      .facet-option:hover { background: rgba(255,255,255,0.1); }
      .facet-option input[type="checkbox"] { margin: 0; }
    </style>

    <script>
      // elements
      var f=document.getElementById('f'), go=document.getElementById('go'), status=document.getElementById('status');
      var qOrder=document.getElementById('qOrder'), qProd=document.getElementById('qProd'), qVar=document.getElementById('qVar');
      var head=document.getElementById('head'), body=document.getElementById('body'), pageSizeEl=document.getElementById('pageSize');
      var prev=document.getElementById('prev'), next=document.getElementById('next'), pageinfo=document.getElementById('pageinfo');
      var exportBtn=document.getElementById('export');
      var lb=document.getElementById('lb'), lbBody=document.getElementById('lbBody'), lbClose=document.getElementById('lbClose');
      var qStatus=document.getElementById('qStatus');
      
      // New faceted filter elements - using select dropdowns like status
      var qSKU=document.getElementById('qSKU'), qVariant=document.getElementById('qVariant'), qPacker=document.getElementById('qPacker');
      var selectedFiltersChips=document.getElementById('selectedFiltersChips');

      // state
      var rows=[], filt=[], page=1, sortBy=null, sortDir=1, packed=JSON.parse(localStorage.getItem('packedMap')||'{}'), statuses=JSON.parse(localStorage.getItem('statusMap')||'{}');
      var selectedSKUs=new Set(), selectedVariants=new Set(), selectedPackers=new Set();
      var allSKUs=new Set(), allVariants=new Set(), allPackers=new Set();

      function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m];});}
      function td(h){return '<td class="border-t border-white/10 align-top">'+h+'</td>';}
      function savePacked(){localStorage.setItem('packedMap', JSON.stringify(packed)); localStorage.setItem('statusMap', JSON.stringify(statuses));}

      function imgFallback(el){el.onerror=null; el.src='https://via.placeholder.com/80?text=No+Img';}

      // Main photo lightbox - same as polaroids
      function openMainPhotoLB(photoUrl, orderNumber) {
        lbBody.innerHTML='';
        var im=document.createElement('img'); 
        im.loading='lazy'; 
        im.src=photoUrl;
        im.className='w-full h-auto object-contain rounded-xl border border-white/10 max-h-[80vh]';
        im.onerror=function(){ this.src='https://via.placeholder.com/400x400?text=No+Image'; };
        lbBody.appendChild(im);
        
        // Update lightbox title to show it's main photo
        var titleEl = lb.querySelector('.text-lg');
        if(titleEl) titleEl.textContent = 'Main Photo - Order #' + orderNumber;
        
        lb.classList.remove('hidden'); 
        lb.classList.add('flex');
      }

      // Faceted filter functions - populate select dropdowns
      function buildFacetedFilters() {
        allSKUs.clear(); allVariants.clear(); allPackers.clear();
        for(var i=0; i<rows.length; i++) {
          var r = rows[i];
          if(r['Product Name']) allSKUs.add(r['Product Name']);
          if(r['Variant']) allVariants.add(r['Variant']);
          // For packer, we'll use a dummy field since it's not in CSV - could be status-based
          allPackers.add('Packer A'); allPackers.add('Packer B'); allPackers.add('Packer C');
        }
        populateSelectDropdown(qSKU, allSKUs);
        populateSelectDropdown(qVariant, allVariants);
        populateSelectDropdown(qPacker, allPackers);
      }

      function populateSelectDropdown(selectEl, values) {
        // Keep the "All" option and add unique values - simple and clean
        var html = '<option value="">All ' + (selectEl.id === 'qSKU' ? 'SKUs' : selectEl.id === 'qVariant' ? 'Variants' : 'Packers') + '</option>';
        var sortedValues = Array.from(values).sort();
        
        sortedValues.forEach(function(value) {
          html += '<option value="' + esc(value) + '">' + esc(value) + '</option>';
        });
        selectEl.innerHTML = html;
      }



      function openLB(urls){
        lbBody.innerHTML='';
        for(var i=0;i<urls.length;i++){
          var im=document.createElement('img'); im.loading='lazy'; im.src=urls[i];
          im.className='w-full h-40 object-cover rounded-xl border border-white/10';
          im.onerror=function(){ this.src='https://via.placeholder.com/160x160?text=No+Img'; };
          lbBody.appendChild(im);
        }
        lb.classList.remove('hidden'); lb.classList.add('flex');
      }
      lbClose.onclick=function(){lb.classList.add('hidden'); lb.classList.remove('flex');};
      lb.onclick=function(e){ if(e.target===lb) lbClose.onclick(); };

      function buildHead(){
        var cols=['Packed','Order Number','Product Name','Variant','Color','Main Photo','Polaroids','Back Engraving Type','Back Engraving Value','Main Photo Status','Polaroid Count', 'Status'];
        var h='<tr>';
        for(var i=0;i<cols.length;i++){
          var c=cols[i]; var arrow=(sortBy===c?(sortDir>0?' ▲':' ▼'):'');
          h+='<th class="text-left p-2 border-b border-white/10 cursor-pointer" data-col="'+esc(c)+'">'+esc(c)+arrow+'</th>';
        }
        h+='</tr>';
        head.innerHTML=h;
        var ths=head.querySelectorAll('th[data-col]');
        for(var k=0;k<ths.length;k++){
          ths[k].onclick=function(){
            var c=this.getAttribute('data-col');
            if(c==='Packed') return;
            if(sortBy===c) sortDir=-sortDir; else {sortBy=c; sortDir=1;}
            applyFilters();
          };
        }
      }

      function applyFilters(){
        var o=qOrder.value.trim().toLowerCase(), p=qProd.value.trim().toLowerCase(), v=qVar.value.trim().toLowerCase();
        var s=qStatus.value; // Get the selected status
        
        // Get selected values from the new filter dropdowns - single select like status
        var selectedSKU = qSKU.value;
        var selectedVariant = qVariant.value;
        var selectedPacker = qPacker.value;
        
        filt=rows.filter(function(r){
          var ok=true;
          if(o) ok = ok && String(r['Order Number']||'').toLowerCase().indexOf(o)>=0;
          if(p) ok = ok && String(r['Product Name']||'').toLowerCase().indexOf(p)>=0;
          if(v) ok = ok && String(r['Variant']||'').toLowerCase().indexOf(v)>=0;
          if(s) ok = ok && statuses[String(r['Order Number']||'')] === s; // Filter by status
          
          // Faceted filters using single select dropdowns - simple like status filter
          if(selectedSKU) ok = ok && r['Product Name'] === selectedSKU;
          if(selectedVariant) ok = ok && r['Variant'] === selectedVariant;
          if(selectedPacker) {
            // For demo purposes, randomly assign packer based on order number hash
            var hash = r['Order Number'] ? r['Order Number'].charCodeAt(r['Order Number'].length-1) % 3 : 0;
            var packer = ['Packer A', 'Packer B', 'Packer C'][hash];
            ok = ok && packer === selectedPacker;
          }
          
          return ok;
        });
        if(sortBy){
          filt.sort(function(a,b){
            var av=String(a[sortBy]||'').toLowerCase(), bv=String(b[sortBy]||'').toLowerCase();
            if(av<bv) return -1*sortDir; if(av>bv) return 1*sortDir; return 0;
          });
        }
        page=1; render();
      }

      function render(){
        var per=parseInt(pageSizeEl.value,10)||25;
        var start=(page-1)*per, end=Math.min(start+per, filt.length);
        var out='';
        for(var i=start;i<end;i++){
          var r=filt[i], ord=r['Order Number'], isPacked=!!packed[ord];
          
          // Determine error classes for highlighting
          var errorClass = '';
          var hasPhoto = r['Main Photo'] && r['Main Photo'].trim();
          var hasVariant = r['Variant'] && r['Variant'].trim();
          if(!hasPhoto) errorClass += ' error-missing-photo';
          if(!hasVariant) errorClass += ' error-invalid-variant';
          // Simple SLA check - if no status set and created "today" (demo)
          if(!statuses[ord] && Math.random() > 0.8) errorClass += ' overdue-sla';
          
          var main = hasPhoto ? 
            '<img loading="lazy" src="'+esc(r['Main Photo'])+'" class="w-20 h-20 object-cover rounded-lg border border-white/10 table-img cursor-pointer hover:opacity-80 transition-opacity" onerror="imgFallback(this)" onclick="openMainPhotoLB(\\''+esc(r['Main Photo'])+'\\', \\''+esc(r['Order Number'])+'\\');">' : 
            '<span class="badge-miss">Missing photo</span>';
          
          var polys=r['Polaroids']||[]; var thumbs='';
          for(var t=0; t<Math.min(3,polys.length); t++){
            thumbs+='<img loading="lazy" src="'+esc(polys[t])+'" class="w-14 h-14 object-cover rounded-md border border-white/10 table-img cursor-pointer hover:opacity-80 transition-opacity" onerror="imgFallback(this)" style="margin-right:4px">';
          }
          var more=polys.length>3?('<div class="text-xs text-white/60">+'+(polys.length-3)+' more</div>'):'';
          var gallery='<a href="#" class="gal" data-idx="'+i+'"><div class="flex gap-2 flex-wrap">'+thumbs+more+'</div></a>';
          var engr=String(r['Back Engraving Value']||'').trim()?('<div class="truncate" style="white-space:pre-wrap">'+esc(r['Back Engraving Value'])+'</div>'):'<span class="badge-miss">Missing</span>';
          var currentStatus = statuses[ord] || '';

          out+='<tr class="'+(isPacked?'packed':'')+errorClass+'">'+
            td('<input type="checkbox" class="chk" data-ord="'+esc(ord)+'" '+(isPacked?'checked':'')+'>')+
            td(esc(ord))+td(esc(r['Product Name']))+td(esc(r['Variant']))+td(esc(r['Color']))+
            td(main)+td(gallery)+td(esc(r['Back Engraving Type']))+td(engr)+td(esc(r['Main Photo Status']))+td(esc(r['Polaroid Count']))+
            td('<select class="status-select status-badge status-badge-'+esc(currentStatus.replace(/ /g,''))+'" data-ord="'+esc(ord)+'">' +
              ['', 'Packed', 'Dispute', 'Bad photo', 'Missing photo'].map(function(opt) {
                return '<option value="'+opt+'" '+(currentStatus===opt?'selected':'')+'>'+(opt||'—')+'</option>';
              }).join('') +
            '</select>') +
          '</tr>';
        }
        body.innerHTML=out;


        // ADD THIS RIGHT AFTER: body.innerHTML=out;
(function addStatusColumn(){
  // 1) Add headers once
  if (!document.getElementById('extra-status-head')) {
    var hr = head.querySelector('tr');
    var th1 = document.createElement('th');
    th1.id = 'extra-status-head';
    th1.className = 'text-left p-2 border-b border-white/10';
    th1.textContent = 'Status';
    hr.appendChild(th1);
  }

  // 2) Add cells to each rendered row (skip if already added)
  var rowsEls = body.querySelectorAll('tr');
  rowsEls.forEach(function(tr){
    if (tr.querySelector('td.__extra_status')) return; // already enhanced

    // Status dropdown
    var tdS = document.createElement('td');
    tdS.className = 'border-t border-white/10 p-2 align-top __extra_status';
    var sel = tr.querySelector('.status-select'); // Select the existing dropdown
    tdS.appendChild(sel);
    tr.appendChild(tdS);
  });
})();


        var chks=body.querySelectorAll('.chk');
        for(var c=0;c<chks.length;c++){
          chks[c].onchange=function(){
            var ord=this.getAttribute('data-ord');
            if(this.checked) packed[ord]=true; else delete packed[ord];
            savePacked();
            this.closest('tr').classList.toggle('packed', this.checked);
          };
        }

        var statusSelects = body.querySelectorAll('.status-select');
        for(var s=0; s<statusSelects.length; s++){
          statusSelects[s].onchange = function(){
            var ord = this.getAttribute('data-ord');
            statuses[ord] = this.value;
            savePacked();
            this.className = 'status-select status-badge status-badge-' + this.value.replace(/ /g, '');
          };
        }
        var links=body.querySelectorAll('a.gal');
        for(var g=0; g<links.length; g++){
          links[g].onclick=function(e){
            e.preventDefault();
            var idx=parseInt(this.getAttribute('data-idx')||'-1',10);
            if(idx>=0 && idx<filt.length){
              var urls=filt[idx]['Polaroids']||[];
              if(urls.length) openLB(urls);
            }
          };
        }

        var total=filt.length, pages=Math.max(1, Math.ceil(total/per));
        pageinfo.textContent='Page '+page+' / '+pages+' — '+total+' rows';
        prev.disabled=page<=1; next.disabled=page>=pages;
      }

      prev.onclick=function(){ if(page>1){ page--; render(); } };
      next.onclick=function(){ var per=parseInt(pageSizeEl.value,10)||25; var pages=Math.max(1,Math.ceil(filt.length/per)); if(page<pages){ page++; render(); } };
      pageSizeEl.onchange=applyFilters;
      qOrder.oninput=qProd.oninput=qVar.oninput=applyFilters;
      qStatus.onchange=applyFilters;
      
      // Add event listeners for the new faceted filter dropdowns - simple like status filter
      qSKU.onchange=applyFilters;
      qVariant.onchange=applyFilters;
      qPacker.onchange=applyFilters;

      window.imgFallback = imgFallback; // make global for onerror attr

      go.onclick=function(){
        if(!f.files.length){ alert('Select a CSV/XLSX first.'); return; }
        status.textContent='Uploading…'; head.innerHTML=''; body.innerHTML='';
        var fd=new FormData(); fd.append('file', f.files[0]);
        fetch('/api/packing/preview', {method:'POST', body:fd})
          .then(function(res){ return res.text().then(function(t){ return {ok:res.ok, text:t};}); })
          .then(function(x){
            if(!x.ok){ status.textContent='Error: '+x.text; return; }
            var data; try{ data=JSON.parse(x.text); }catch(e){ status.textContent='Bad JSON from server'; return; }
            rows=data.rows||[]; status.textContent='Loaded '+rows.length+' orders';
            buildHead(); buildFacetedFilters(); applyFilters();
          })
          .catch(function(err){ console.error(err); status.textContent='Unexpected error'; });
      };

      exportBtn.onclick=function(){
        var cols=['Order Number','Product Name','Variant','Color','Main Photo','Polaroids','Back Engraving Type','Back Engraving Value','Main Photo Status','Polaroid Count', 'Status'];
        var csv=cols.join(',')+'\\n';
        for(var i=0;i<filt.length;i++){
          var r=filt[i], line=[];
          for(var c=0;c<cols.length;c++){
            var v=r[cols[c]];
            if(cols[c] === 'Status') v = statuses[r['Order Number']] || '';
            if(Array.isArray(v)) v=v.join(' ');
            line.push('"'+String(v==null?'':v).replace(/"/g,'""')+'"');
          }
          csv+=line.join(',')+'\\n';
        }
        var blob=new Blob([csv],{type:'text/csv;charset=utf-8;'}), a=document.createElement('a');
        a.href=URL.createObjectURL(blob); a.download='packing_filtered.csv'; a.click(); URL.revokeObjectURL(a.href);
      };
    </script>
    """
    return _eraya_style_page("Packing", body)
# -------------------- SHOPIFY SETTINGS PAGE --------------------
@app.get("/shopify/settings")
def shopify_settings_page(current_user: Dict = Depends(require_roles("owner", "admin"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold mb-2">🛒 Shopify Integration Settings</h1>
      <p class="text-white/80 mb-6">Connect your Shopify store to automatically sync orders and analytics with your dashboard.</p>
      
      <!-- Connection Status -->
      <div id="connectionStatus" class="mb-6">
        <!-- Will be populated by JavaScript -->
      </div>
      
      <!-- Configuration Form -->
      <div class="glass p-6 mb-6">
        <h3 class="text-xl font-semibold mb-4">Store Configuration</h3>
        <form id="shopifyForm" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-white/90 mb-2">Store Name</label>
            <input type="text" id="storeName" name="store_name" 
                   placeholder="your-store-name (without .myshopify.com)"
                   class="w-full bg-slate-800/60 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500">
            <p class="text-xs text-white/60 mt-1">Enter just the store name part (e.g., "my-store" for my-store.myshopify.com)</p>
          </div>
          
          <div>
            <label class="block text-sm font-medium text-white/90 mb-2">Private App Access Token</label>
            <input type="password" id="accessToken" name="access_token" 
                   placeholder="shppa_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                   class="w-full bg-slate-800/60 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500">
            <p class="text-xs text-white/60 mt-1">Get this from your Shopify Admin → Apps → Private Apps</p>
          </div>
          
          <div class="flex gap-3">
            <button type="submit" class="btn btn-primary">
              🔗 Connect Store
            </button>
            <button type="button" id="testConnection" class="btn btn-secondary">
              🧪 Test Connection
            </button>
          </div>
        </form>
      </div>
      
      <!-- How to Get Access Token -->
      <div class="glass p-6 mb-6">
        <h3 class="text-xl font-semibold mb-4">📋 How to Get Your Access Token</h3>
        <div class="space-y-3 text-sm text-white/80">
          <div class="flex items-start gap-3">
            <span class="bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">1</span>
            <div>
              <strong>Go to your Shopify Admin</strong><br>
              <span class="text-white/60">Navigate to Settings → Apps and sales channels</span>
            </div>
          </div>
          <div class="flex items-start gap-3">
            <span class="bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">2</span>
            <div>
              <strong>Create a Private App</strong><br>
              <span class="text-white/60">Click "Develop apps" → "Create an app" → Give it a name</span>
            </div>
          </div>
          <div class="flex items-start gap-3">
            <span class="bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">3</span>
            <div>
              <strong>Configure API Scopes</strong><br>
              <span class="text-white/60">Enable: read_orders, read_products, read_customers, read_analytics</span>
            </div>
          </div>
          <div class="flex items-start gap-3">
            <span class="bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">4</span>
            <div>
              <strong>Install & Copy Token</strong><br>
              <span class="text-white/60">Install the app and copy the "Admin API access token"</span>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Current Data Preview -->
      <div id="dataPreview" class="glass p-6" style="display: none;">
        <h3 class="text-xl font-semibold mb-4">📊 Live Data Preview</h3>
        <div id="previewContent">
          <!-- Will be populated by JavaScript -->
        </div>
      </div>
    </section>
    
    <script>
      const form = document.getElementById('shopifyForm');
      const testBtn = document.getElementById('testConnection');
      const statusDiv = document.getElementById('connectionStatus');
      const previewDiv = document.getElementById('dataPreview');
      const previewContent = document.getElementById('previewContent');
      
      // Load current configuration
      async function loadCurrentConfig() {
        try {
          const response = await fetch('/api/shopify/config');
          const data = await response.json();
          
          if (data.configured) {
            document.getElementById('storeName').value = data.store_name;
            showStatus('success', `✅ Connected to ${data.store_name}.myshopify.com`, data);
            loadDataPreview();
          } else {
            showStatus('warning', '⚠️ Shopify store not configured yet');
          }
        } catch (error) {
          showStatus('error', '❌ Error loading configuration');
        }
      }
      
      function showStatus(type, message, data = null) {
        const colors = {
          success: 'bg-green-500/20 border-green-500/30 text-green-200',
          warning: 'bg-yellow-500/20 border-yellow-500/30 text-yellow-200',
          error: 'bg-red-500/20 border-red-500/30 text-red-200'
        };
        
        let extraInfo = '';
        if (data && data.last_updated) {
          extraInfo = `<div class="text-xs mt-1 opacity-75">Last updated: ${new Date(data.last_updated).toLocaleString()}</div>`;
        }
        
        statusDiv.innerHTML = `
          <div class="border rounded-xl p-4 ${colors[type]}">
            <div class="font-medium">${message}</div>
            ${extraInfo}
          </div>
        `;
      }
      
      // Test connection
      testBtn.addEventListener('click', async () => {
        const storeName = document.getElementById('storeName').value.trim();
        const accessToken = document.getElementById('accessToken').value.trim();
        
        if (!storeName || !accessToken) {
          alert('Please fill in both store name and access token');
          return;
        }
        
        testBtn.disabled = true;
        testBtn.textContent = '🔄 Testing...';
        
        try {
          const formData = new FormData();
          formData.append('store_name', storeName);
          formData.append('access_token', accessToken);
          
          const response = await fetch('/api/shopify/config', {
            method: 'POST',
            body: formData
          });
          
          const result = await response.json();
          
          if (response.ok) {
            showStatus('success', `✅ ${result.message}`, result);
            loadDataPreview();
          } else {
            showStatus('error', `❌ ${result.detail}`);
          }
        } catch (error) {
          showStatus('error', '❌ Connection failed: ' + error.message);
        } finally {
          testBtn.disabled = false;
          testBtn.textContent = '🧪 Test Connection';
        }
      });
      
      // Form submission
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        testBtn.click(); // Reuse test connection logic
      });
      
      // Load data preview
      async function loadDataPreview() {
        try {
          const [ordersRes, analyticsRes] = await Promise.all([
            fetch('/api/shopify/orders?limit=5'),
            fetch('/api/shopify/analytics')
          ]);
          
          const orders = await ordersRes.json();
          const analytics = await analyticsRes.json();
          
          previewContent.innerHTML = `
            <div class="grid md:grid-cols-2 gap-6">
              <div>
                <h4 class="font-semibold mb-3">📈 Analytics Summary</h4>
                <div class="space-y-2 text-sm">
                  <div>Total Orders: <span class="font-mono">${analytics.total_orders || 0}</span></div>
                  <div>Today's Orders: <span class="font-mono">${analytics.today_orders || 0}</span></div>
                  <div>Total Revenue: <span class="font-mono">${analytics.currency} ${analytics.total_revenue || 0}</span></div>
                  <div>Today's Revenue: <span class="font-mono">${analytics.currency} ${analytics.today_revenue || 0}</span></div>
                  <div>Pending Orders: <span class="font-mono">${analytics.pending_orders || 0}</span></div>
                </div>
              </div>
              <div>
                <h4 class="font-semibold mb-3">🛍️ Recent Orders</h4>
                <div class="space-y-2 text-sm">
                  ${orders.orders ? orders.orders.slice(0, 3).map(order => `
                    <div class="bg-white/5 rounded p-2">
                      <div class="font-mono">#${order.name}</div>
                      <div class="text-white/60">${order.currency} ${order.total_price}</div>
                    </div>
                  `).join('') : '<div class="text-white/60">No orders found</div>'}
                </div>
              </div>
            </div>
          `;
          
          previewDiv.style.display = 'block';
        } catch (error) {
          console.error('Error loading preview:', error);
        }
      }
      
      // Load configuration on page load
      loadCurrentConfig();
    </script>
    """
    return _eraya_style_page("Shopify Settings", body)
@app.get("/admin/users")
def user_management_page(current_user: Dict = Depends(require_roles("owner", "admin"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold mb-2">👨‍💼 User Management</h1>
      <p class="text-white/80 mb-6">Manage user accounts, roles, permissions, and monitor activity across your system.</p>
      
      <!-- User Statistics Cards -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6" id="userStatsCards">
        <!-- Will be populated by JavaScript -->
      </div>
      
      <!-- Action Bar -->
      <div class="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div class="flex flex-wrap items-center gap-3">
          <input type="text" id="searchUsers" placeholder="Search users..." class="rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2 text-sm min-w-[200px]">
          <select id="filterRole" class="rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2 text-sm">
            <option value="">All Roles</option>
          </select>
          <select id="filterStatus" class="rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2 text-sm">
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </div>
        <div class="flex flex-wrap items-center gap-3">
          <button id="addNewUser" class="btn btn-sm btn-primary">👤 Add New User</button>
          <button id="bulkActivate" class="btn btn-sm btn-success" disabled>Activate Selected</button>
          <button id="bulkDeactivate" class="btn btn-sm btn-warning" disabled>Deactivate Selected</button>
          <button id="manageRoles" class="btn btn-sm btn-accent">🎭 Manage Roles</button>
          <button id="refreshUsers" class="btn btn-sm btn-secondary">🔄 Refresh</button>
        </div>
      </div>
      
      <!-- Selection Info -->
      <div id="selectionInfo" class="mb-4 text-sm text-white/60" style="display: none;">
        <span id="selectedCount">0</span> users selected
      </div>
      
      <!-- Users Table -->
      <div class="glass overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full" id="usersTable">
            <thead>
              <tr class="bg-slate-900/50">
                <th class="text-left p-4 border-b border-white/10">
                  <input type="checkbox" id="selectAllUsers" class="rounded">
                </th>
                <th class="text-left p-4 border-b border-white/10 cursor-pointer" data-sort="name">Name ↕️</th>
                <th class="text-left p-4 border-b border-white/10 cursor-pointer" data-sort="role">Role ↕️</th>
                <th class="text-left p-4 border-b border-white/10 cursor-pointer" data-sort="status">Status ↕️</th>
                <th class="text-left p-4 border-b border-white/10 cursor-pointer" data-sort="last_login">Last Login ↕️</th>
                <th class="text-left p-4 border-b border-white/10">Session</th>
                <th class="text-left p-4 border-b border-white/10">Actions</th>
              </tr>
            </thead>
            <tbody id="usersTableBody">
              <!-- Will be populated by JavaScript -->
            </tbody>
          </table>
        </div>
      </div>
      
      <!-- Loading State -->
      <div id="loadingUsers" class="text-center py-8">
        <div class="animate-spin inline-block w-6 h-6 border-[3px] border-current border-t-transparent text-blue-600 rounded-full"></div>
        <p class="mt-2 text-white/60">Loading users...</p>
      </div>
      
      <!-- No Users State -->
      <div id="noUsers" class="text-center py-8" style="display: none;">
        <p class="text-white/60">No users found matching your criteria.</p>
      </div>
    </section>

    <!-- User Details Modal -->
    <div id="userModal" class="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 hidden items-center justify-center p-4">
      <div class="glass max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div class="p-6">
          <div class="flex items-center justify-between mb-6">
            <h2 class="text-2xl font-bold" id="modalTitle">User Details</h2>
            <button id="closeModal" class="text-white/60 hover:text-white text-2xl">&times;</button>
          </div>
          
          <!-- User Profile Section -->
          <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <!-- User Info -->
            <div class="lg:col-span-1">
              <div class="text-center mb-6">
                <div class="relative inline-block">
                <img id="modalUserPhoto" src="" alt="User Photo" class="w-24 h-24 rounded-full mx-auto mb-4 border-4 border-white/20">
                  <div id="modalUserIcon" class="absolute -bottom-2 -right-2 w-8 h-8 rounded-full flex items-center justify-center text-lg profile-icon" 
                       style="border: 3px solid rgba(255,255,255,0.9);">
                  </div>
                </div>
                <h3 id="modalUserName" class="text-xl font-bold"></h3>
                <p id="modalUserEmail" class="text-white/60"></p>
                <div id="modalUserStatus" class="mt-2"></div>
              </div>
              
              <!-- Quick Actions -->
              <div class="space-y-3">
                <button id="toggleUserStatus" class="btn btn-primary w-full">Toggle Status</button>
                <select id="changeUserRole" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2">
                  <!-- Will be populated -->
                </select>
                <button id="changeUserPassword" class="btn btn-warning w-full">🔑 Change Password</button>
                <button id="deleteUserBtn" class="btn btn-danger w-full">🗑️ Delete User</button>
                <button id="viewUserActivity" class="btn btn-secondary w-full">View Activity Log</button>
              </div>
            </div>
            
            <!-- Permissions Matrix -->
            <div class="lg:col-span-2">
              <div class="flex items-center justify-between mb-4">
                <h4 class="text-lg font-semibold">Permissions</h4>
                <div class="flex gap-2">
                  <button id="editPermissions" class="btn btn-sm btn-accent">✏️ Edit Permissions</button>
                  <button id="savePermissions" class="btn btn-sm btn-success" style="display: none;">💾 Save Changes</button>
                  <button id="cancelPermissions" class="btn btn-sm btn-secondary" style="display: none;">❌ Cancel</button>
                </div>
              </div>
              
              <div id="permissionsMatrix" class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <!-- Will be populated by JavaScript -->
              </div>
              
              <!-- Permission Edit Mode Notice -->
              <div id="editModeNotice" class="mt-4 p-3 bg-blue-500/20 border border-blue-500/30 rounded-lg text-sm text-blue-200" style="display: none;">
                <strong>Edit Mode:</strong> Click on permission cards to toggle them on/off. Changes will override the user's role-based permissions.
              </div>
              
              <!-- User Activity Preview -->
              <div class="mt-6">
                <h4 class="text-lg font-semibold mb-4">Recent Activity</h4>
                <div id="recentActivity" class="space-y-2 max-h-40 overflow-y-auto">
                  <!-- Will be populated by JavaScript -->
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Role Management Modal -->
    <div id="roleModal" class="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 hidden items-center justify-center p-4">
      <div class="glass max-w-6xl w-full max-h-[90vh] overflow-y-auto">
        <div class="p-6">
          <div class="flex items-center justify-between mb-6">
            <h2 class="text-2xl font-bold">🎭 Role Management</h2>
            <button id="closeRoleModal" class="text-white/60 hover:text-white text-2xl">&times;</button>
          </div>
          
          <!-- Role Actions -->
          <div class="flex flex-wrap gap-3 mb-6">
            <button id="createNewRole" class="btn btn-success">➕ Create New Role</button>
            <button id="refreshRoles" class="btn btn-secondary">🔄 Refresh</button>
          </div>
          
          <!-- Roles Grid -->
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" id="rolesGrid">
            <!-- Will be populated by JavaScript -->
          </div>
        </div>
      </div>
    </div>

    <!-- Role Create/Edit Modal -->
    <div id="roleEditModal" class="fixed inset-0 bg-black/50 backdrop-blur-sm z-[60] hidden items-center justify-center p-4">
      <div class="glass max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div class="p-6">
          <div class="flex items-center justify-between mb-6">
            <h2 class="text-2xl font-bold" id="roleEditTitle">Create New Role</h2>
            <button id="closeRoleEditModal" class="text-white/60 hover:text-white text-2xl">&times;</button>
          </div>
          
          <!-- Role Form -->
          <form id="roleForm" class="space-y-4">
            <div>
              <label class="block text-sm font-semibold mb-2">Role Name</label>
              <input type="text" id="roleName" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="Enter role name" required>
            </div>
            
            <div>
              <label class="block text-sm font-semibold mb-2">Description</label>
              <textarea id="roleDescription" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" rows="3" placeholder="Describe this role's purpose"></textarea>
            </div>
            
            <div>
              <label class="block text-sm font-semibold mb-2">Role Color</label>
              <div class="flex items-center gap-3">
                <input type="color" id="roleColor" class="w-12 h-10 rounded border border-white/10" value="#6b7280">
                <span class="text-sm text-white/60">Choose a color to represent this role</span>
              </div>
            </div>
            
            <div>
              <label class="block text-sm font-semibold mb-2">Permissions</label>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-3" id="rolePermissionsGrid">
                <!-- Will be populated by JavaScript -->
              </div>
            </div>
            
            <div class="flex gap-3 pt-4">
              <button type="submit" class="btn btn-success flex-1">💾 Save Role</button>
              <button type="button" id="cancelRoleEdit" class="btn btn-secondary">❌ Cancel</button>
            </div>
          </form>
        </div>
      </div>
    </div>
    
    <!-- Password Change Modal -->
    <div id="passwordModal" class="fixed inset-0 bg-black/50 backdrop-blur-sm z-[60] hidden items-center justify-center p-4">
      <div class="glass max-w-md w-full">
        <div class="p-6">
          <div class="flex items-center justify-between mb-6">
            <h2 class="text-2xl font-bold">🔑 Change Password</h2>
            <button id="closePasswordModal" class="text-white/60 hover:text-white text-2xl">&times;</button>
          </div>
          
          <!-- Password Form -->
          <form id="passwordForm" class="space-y-4">
            <div class="text-center mb-4">
              <div class="w-16 h-16 rounded-full bg-gradient-to-r from-yellow-500 to-orange-500 flex items-center justify-center mx-auto mb-2">
                <span id="passwordModalIcon" class="text-2xl">🔑</span>
              </div>
              <h3 id="passwordModalUserName" class="text-lg font-semibold"></h3>
              <p class="text-white/60 text-sm">Enter a new password for this user</p>
            </div>
            
            <div>
              <label class="block text-sm font-semibold mb-2">New Password</label>
              <input type="password" id="newPassword" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="Enter new password" required minlength="6">
              <div class="text-xs text-white/60 mt-1">Minimum 6 characters</div>
            </div>
            
            <div>
              <label class="block text-sm font-semibold mb-2">Confirm Password</label>
              <input type="password" id="confirmPassword" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="Confirm new password" required minlength="6">
              <div id="passwordMatchError" class="text-xs text-red-400 mt-1 hidden">Passwords do not match</div>
            </div>
            
            <div class="bg-yellow-500/20 border border-yellow-500/30 rounded-lg p-3">
              <div class="flex items-center gap-2 text-yellow-400 text-sm">
                <span>⚠️</span>
                <span>The user will be logged out and must use the new password to login.</span>
              </div>
            </div>
            
            <div class="flex gap-3 pt-4">
              <button type="submit" class="btn btn-warning flex-1">🔑 Change Password</button>
              <button type="button" id="cancelPasswordChange" class="btn btn-secondary">❌ Cancel</button>
            </div>
          </form>
        </div>
      </div>
    </div>
    
    <!-- Add New User Modal -->
    <div id="addUserModal" class="fixed inset-0 bg-black/50 backdrop-blur-sm z-[60] hidden items-center justify-center p-4">
      <div class="glass max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div class="p-6">
          <div class="flex items-center justify-between mb-6">
            <h2 class="text-2xl font-bold">👤 Add New User</h2>
            <button id="closeAddUserModal" class="text-white/60 hover:text-white text-2xl">&times;</button>
          </div>
          
          <!-- Add User Form -->
          <form id="addUserForm" class="space-y-6">
            <!-- Basic Information -->
            <div class="glass p-4 rounded-xl">
              <h3 class="text-lg font-semibold mb-4">📋 Basic Information</h3>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-semibold mb-2">Employee ID *</label>
                  <input type="text" id="newEmployeeId" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="e.g., EMP007" required>
                </div>
                <div>
                  <label class="block text-sm font-semibold mb-2">Full Name *</label>
                  <input type="text" id="newEmployeeName" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="Enter full name" required>
                </div>
                <div>
                  <label class="block text-sm font-semibold mb-2">Email *</label>
                  <input type="email" id="newEmployeeEmail" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="employee@company.com" required>
                </div>
                <div>
                  <label class="block text-sm font-semibold mb-2">Phone Number</label>
                  <input type="tel" id="newEmployeePhone" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="+1 (555) 123-4567">
                </div>
                <div>
                  <label class="block text-sm font-semibold mb-2">Role *</label>
                  <select id="newEmployeeRole" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" required>
                    <option value="">Select Role</option>
                    <!-- Will be populated -->
                  </select>
                </div>
                <div>
                  <label class="block text-sm font-semibold mb-2">Initial Password *</label>
                  <input type="password" id="newEmployeePassword" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="Minimum 6 characters" required minlength="6">
                </div>
                <div>
                  <label class="block text-sm font-semibold mb-2">Joining Date *</label>
                  <input type="date" id="newEmployeeJoiningDate" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" required>
                </div>
                <div>
                  <label class="block text-sm font-semibold mb-2">Shift</label>
                  <select id="newEmployeeShift" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2">
                    <option value="">Select Shift</option>
                    <option value="morning">Morning (6 AM - 2 PM)</option>
                    <option value="afternoon">Afternoon (2 PM - 10 PM)</option>
                    <option value="night">Night (10 PM - 6 AM)</option>
                    <option value="flexible">Flexible</option>
                  </select>
                </div>
                <div>
                  <label class="block text-sm font-semibold mb-2">Manager</label>
                  <select id="newEmployeeManager" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2">
                    <option value="">Select Manager</option>
                    <!-- Will be populated with managers -->
                  </select>
                </div>
              </div>
            </div>
            
            <!-- Profile Photo -->
            <div class="glass p-4 rounded-xl">
              <h3 class="text-lg font-semibold mb-4">📷 Profile Photo</h3>
              <div class="flex items-center gap-4">
                <div id="photoPreview" class="w-20 h-20 rounded-full bg-gradient-to-r from-blue-500 to-purple-500 flex items-center justify-center text-2xl font-bold">
                  👤
                </div>
                <div class="flex-1">
                  <input type="file" id="profilePhotoInput" accept="image/*" class="hidden">
                  <button type="button" id="uploadPhotoBtn" class="btn btn-secondary mb-2">📷 Upload Photo</button>
                  <div class="text-xs text-white/60">Supported: JPG, PNG, GIF (Max 5MB)</div>
                </div>
              </div>
            </div>
            
            <!-- Contact Information -->
            <div class="glass p-4 rounded-xl">
              <h3 class="text-lg font-semibold mb-4">📍 Contact Information</h3>
              <div class="grid grid-cols-1 gap-4">
                <div>
                  <label class="block text-sm font-semibold mb-2">Address</label>
                  <textarea id="newEmployeeAddress" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" rows="2" placeholder="Enter full address"></textarea>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label class="block text-sm font-semibold mb-2">City</label>
                    <input type="text" id="newEmployeeCity" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="City">
                  </div>
                  <div>
                    <label class="block text-sm font-semibold mb-2">State/Province</label>
                    <input type="text" id="newEmployeeState" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="State">
                  </div>
                  <div>
                    <label class="block text-sm font-semibold mb-2">ZIP/Postal Code</label>
                    <input type="text" id="newEmployeeZip" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="ZIP Code">
                  </div>
                </div>
              </div>
            </div>
            
            <!-- Emergency Contact -->
            <div class="glass p-4 rounded-xl">
              <h3 class="text-lg font-semibold mb-4">🚨 Emergency Contact</h3>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-semibold mb-2">Emergency Contact Name</label>
                  <input type="text" id="emergencyContactName" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="Contact person name">
                </div>
                <div>
                  <label class="block text-sm font-semibold mb-2">Relationship</label>
                  <input type="text" id="emergencyContactRelation" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="e.g., Spouse, Parent, Sibling">
                </div>
                <div>
                  <label class="block text-sm font-semibold mb-2">Emergency Contact Phone</label>
                  <input type="tel" id="emergencyContactPhone" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="+1 (555) 123-4567">
                </div>
                <div>
                  <label class="block text-sm font-semibold mb-2">Emergency Contact Email</label>
                  <input type="email" id="emergencyContactEmail" class="w-full rounded-xl bg-slate-900/60 border border-white/10 px-4 py-2" placeholder="emergency@contact.com">
                </div>
              </div>
            </div>
            
            <!-- Document Upload -->
            <div class="glass p-4 rounded-xl">
              <h3 class="text-lg font-semibold mb-4">📎 Important Documents</h3>
              <div class="space-y-3">
                <div>
                  <input type="file" id="documentsInput" multiple accept=".pdf,.doc,.docx,.jpg,.jpeg,.png" class="hidden">
                  <button type="button" id="uploadDocumentsBtn" class="btn btn-secondary">📎 Upload Documents</button>
                  <div class="text-xs text-white/60 mt-1">Supported: PDF, DOC, DOCX, JPG, PNG (Max 10MB each)</div>
                </div>
                <div id="documentsPreview" class="space-y-2">
                  <!-- Uploaded documents will appear here -->
                </div>
              </div>
            </div>
            
            <div class="flex gap-3 pt-4">
              <button type="submit" class="btn btn-success flex-1">👤 Create User</button>
              <button type="button" id="cancelAddUser" class="btn btn-secondary">❌ Cancel</button>
            </div>
          </form>
        </div>
      </div>
    </div>
    
    <style>
      .user-card { transition: all 0.2s ease; }
      .user-card:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0,0,0,0.3); }
      .status-active { background: linear-gradient(135deg, #10b981, #059669); }
      .status-inactive { background: linear-gradient(135deg, #ef4444, #dc2626); }
      .role-badge { padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }
      .role-super-admin { background: #4f46e5; color: white; }
      .role-admin { background: #059669; color: white; }
      .role-manager { background: #dc2626; color: white; }
      .role-employee { background: #7c3aed; color: white; }
      .session-online { color: #10b981; }
      .session-offline { color: #6b7280; }
      .btn-success { background: linear-gradient(135deg, #10b981, #059669); }
      .btn-warning { background: linear-gradient(135deg, #f59e0b, #d97706); }
      .btn-danger { background: linear-gradient(135deg, #ef4444, #dc2626); }
      .permission-enabled { background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; }
      .permission-disabled { background: rgba(107, 114, 128, 0.2); border: 1px solid #6b7280; }
      .permission-editable { cursor: pointer; transition: all 0.2s ease; }
      .permission-editable:hover { transform: scale(1.02); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
      .role-card { transition: all 0.2s ease; cursor: pointer; }
      .role-card:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0,0,0,0.3); }
      .role-system { border: 2px solid #6b7280; }
      .role-custom { border: 2px solid #8b5cf6; }
      .permission-toggle { transition: all 0.2s ease; }
      .permission-toggle.active { background: rgba(16, 185, 129, 0.3); border-color: #10b981; }
      .permission-toggle.inactive { background: rgba(107, 114, 128, 0.2); border-color: #6b7280; }
      tbody tr:hover { background-color: rgba(255,255,255,0.05); }
      .selected-row { background-color: rgba(59, 130, 246, 0.2) !important; }
      
      /* Cute Profile Icon Styles */
      .profile-icon {
        animation: iconPulse 2s ease-in-out infinite alternate;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        transition: all 0.3s ease;
      }
      
      .profile-icon:hover {
        transform: scale(1.1);
        animation: iconBounce 0.6s ease-in-out;
      }
      
      @keyframes iconPulse {
        0% { transform: scale(1); opacity: 0.9; }
        100% { transform: scale(1.05); opacity: 1; }
      }
      
      @keyframes iconBounce {
        0%, 20%, 60%, 100% { transform: translateY(0) scale(1.1); }
        40% { transform: translateY(-4px) scale(1.15); }
        80% { transform: translateY(-2px) scale(1.12); }
      }
    </style>
    <script>
      // Global variables
      let allUsers = [];
      let selectedUsers = new Set();
      let currentSort = { field: 'name', direction: 'asc' };
      let currentModal = null;
      let editingPermissions = false;
      let originalPermissions = [];
      let allRoles = {};
      let allPermissions = {};
      let currentEditingRole = null;
      
      // DOM elements
      const searchInput = document.getElementById('searchUsers');
      const roleFilter = document.getElementById('filterRole');
      const statusFilter = document.getElementById('filterStatus');
      const usersTableBody = document.getElementById('usersTableBody');
      const loadingUsers = document.getElementById('loadingUsers');
      const noUsers = document.getElementById('noUsers');
      const selectAllCheckbox = document.getElementById('selectAllUsers');
      const bulkActivateBtn = document.getElementById('bulkActivate');
      const bulkDeactivateBtn = document.getElementById('bulkDeactivate');
      const refreshBtn = document.getElementById('refreshUsers');
      const selectionInfo = document.getElementById('selectionInfo');
      const selectedCount = document.getElementById('selectedCount');
      const userModal = document.getElementById('userModal');
      const closeModalBtn = document.getElementById('closeModal');
      const manageRolesBtn = document.getElementById('manageRoles');
      const roleModal = document.getElementById('roleModal');
      const closeRoleModalBtn = document.getElementById('closeRoleModal');
      const roleEditModal = document.getElementById('roleEditModal');
      const closeRoleEditModalBtn = document.getElementById('closeRoleEditModal');
      const passwordModal = document.getElementById('passwordModal');
      const closePasswordModalBtn = document.getElementById('closePasswordModal');
      const addUserModal = document.getElementById('addUserModal');
      const closeAddUserModalBtn = document.getElementById('closeAddUserModal');
      const editPermissionsBtn = document.getElementById('editPermissions');
      const savePermissionsBtn = document.getElementById('savePermissions');
      const cancelPermissionsBtn = document.getElementById('cancelPermissions');
      
      // Initialize page
      document.addEventListener('DOMContentLoaded', function() {
        loadUserStats();
        loadUsers();
        setupEventListeners();
      });
      
      function setupEventListeners() {
        // Search and filters
        searchInput.addEventListener('input', debounce(filterUsers, 300));
        roleFilter.addEventListener('change', filterUsers);
        statusFilter.addEventListener('change', filterUsers);
        
        // Bulk actions
        bulkActivateBtn.addEventListener('click', () => performBulkAction('activate'));
        bulkDeactivateBtn.addEventListener('click', () => performBulkAction('deactivate'));
        refreshBtn.addEventListener('click', loadUsers);
        
        // Select all checkbox
        selectAllCheckbox.addEventListener('change', toggleSelectAll);
        
        // Table sorting
        document.querySelectorAll('th[data-sort]').forEach(th => {
          th.addEventListener('click', () => sortUsers(th.dataset.sort));
        });
        
        // Modal
        closeModalBtn.addEventListener('click', closeModal);
        userModal.addEventListener('click', (e) => {
          if (e.target === userModal) closeModal();
        });
        
        // Role Management
        manageRolesBtn.addEventListener('click', openRoleModal);
        closeRoleModalBtn.addEventListener('click', closeRoleModal);
        roleModal.addEventListener('click', (e) => {
          if (e.target === roleModal) closeRoleModal();
        });
        
        // Permission Editing
        editPermissionsBtn.addEventListener('click', enterEditMode);
        savePermissionsBtn.addEventListener('click', savePermissions);
        cancelPermissionsBtn.addEventListener('click', cancelEditMode);
        
        // Role Edit Modal
        closeRoleEditModalBtn.addEventListener('click', closeRoleEditModal);
        document.getElementById('cancelRoleEdit').addEventListener('click', closeRoleEditModal);
        document.getElementById('roleForm').addEventListener('submit', saveRole);
        
        // Password Change Modal
        closePasswordModalBtn.addEventListener('click', closePasswordModal);
        passwordModal.addEventListener('click', (e) => {
          if (e.target === passwordModal) closePasswordModal();
        });
        document.getElementById('passwordForm').addEventListener('submit', changeUserPassword);
        document.getElementById('cancelPasswordChange').addEventListener('click', closePasswordModal);
        
        // Password validation
        document.getElementById('confirmPassword').addEventListener('input', validatePasswordMatch);
        
        // Add User Modal
        document.getElementById('addNewUser').addEventListener('click', openAddUserModal);
        closeAddUserModalBtn.addEventListener('click', closeAddUserModal);
        addUserModal.addEventListener('click', (e) => {
          if (e.target === addUserModal) closeAddUserModal();
        });
        document.getElementById('addUserForm').addEventListener('submit', createNewUser);
        document.getElementById('cancelAddUser').addEventListener('click', closeAddUserModal);
        
        // File upload handlers
        document.getElementById('uploadPhotoBtn').addEventListener('click', () => {
          document.getElementById('profilePhotoInput').click();
        });
        document.getElementById('profilePhotoInput').addEventListener('change', handlePhotoUpload);
        document.getElementById('uploadDocumentsBtn').addEventListener('click', () => {
          document.getElementById('documentsInput').click();
        });
        document.getElementById('documentsInput').addEventListener('change', handleDocumentsUpload);
      }
      
      async function loadUserStats() {
        try {
          const response = await fetch('/api/users/stats');
          const stats = await response.json();
          
          document.getElementById('userStatsCards').innerHTML = `
            <div class="glass p-4 text-center user-card">
              <div class="text-2xl font-bold text-blue-400">${stats.total_users}</div>
              <div class="text-sm text-white/60">Total Users</div>
            </div>
            <div class="glass p-4 text-center user-card">
              <div class="text-2xl font-bold text-green-400">${stats.active_users}</div>
              <div class="text-sm text-white/60">Active Users</div>
            </div>
            <div class="glass p-4 text-center user-card">
              <div class="text-2xl font-bold text-red-400">${stats.inactive_users}</div>
              <div class="text-sm text-white/60">Inactive Users</div>
            </div>
            <div class="glass p-4 text-center user-card">
              <div class="text-2xl font-bold text-purple-400">${stats.admin_count}</div>
              <div class="text-sm text-white/60">Administrators</div>
            </div>
          `;
        } catch (error) {
          console.error('Failed to load user stats:', error);
        }
      }
      
      async function loadUsers() {
        loadingUsers.style.display = 'block';
        usersTableBody.style.display = 'none';
        noUsers.style.display = 'none';
        
        try {
          const response = await fetch('/api/users');
          const data = await response.json();
          
          allUsers = data.users;
          
          // Populate role filter
          roleFilter.innerHTML = '<option value="">All Roles</option>';
          data.roles.forEach(role => {
            roleFilter.innerHTML += `<option value="${role}">${role}</option>`;
          });
          
          filterUsers();
          
        } catch (error) {
          console.error('Failed to load users:', error);
          loadingUsers.style.display = 'none';
          usersTableBody.innerHTML = '<tr><td colspan="7" class="text-center p-4 text-red-400">Failed to load users</td></tr>';
          usersTableBody.style.display = 'table-row-group';
        }
      }
      
      function filterUsers() {
        loadingUsers.style.display = 'none';
        
        const searchTerm = searchInput.value.toLowerCase();
        const roleFilterValue = roleFilter.value;
        const statusFilterValue = statusFilter.value;
        
        let filteredUsers = allUsers.filter(user => {
          const matchesSearch = !searchTerm || 
            user.name.toLowerCase().includes(searchTerm) ||
            user.email.toLowerCase().includes(searchTerm) ||
            user.id.toLowerCase().includes(searchTerm);
          
          const matchesRole = !roleFilterValue || user.role === roleFilterValue;
          const matchesStatus = !statusFilterValue || user.status === statusFilterValue;
          
          return matchesSearch && matchesRole && matchesStatus;
        });
        
        // Apply sorting
        filteredUsers.sort((a, b) => {
          let aVal = a[currentSort.field];
          let bVal = b[currentSort.field];
          
          if (currentSort.field === 'last_login') {
            aVal = new Date(aVal);
            bVal = new Date(bVal);
          }
          
          if (aVal < bVal) return currentSort.direction === 'asc' ? -1 : 1;
          if (aVal > bVal) return currentSort.direction === 'asc' ? 1 : -1;
          return 0;
        });
        
        renderUsers(filteredUsers);
      }
      
      function renderUsers(users) {
        if (users.length === 0) {
          usersTableBody.style.display = 'none';
          noUsers.style.display = 'block';
          return;
        }
        
        noUsers.style.display = 'none';
        usersTableBody.style.display = 'table-row-group';
        
        usersTableBody.innerHTML = users.map(user => {
          const isSelected = selectedUsers.has(user.id);
          const statusClass = user.status === 'active' ? 'status-active' : 'status-inactive';
          const roleClass = `role-${user.role.toLowerCase().replace(' ', '-')}`;
          const sessionStatus = user.session_id ? 'Online' : 'Offline';
          const sessionClass = user.session_id ? 'session-online' : 'session-offline';
          
          return `
            <tr class="${isSelected ? 'selected-row' : ''}" data-user-id="${user.id}">
              <td class="p-4 border-b border-white/10">
                <input type="checkbox" class="user-checkbox rounded" data-user-id="${user.id}" ${isSelected ? 'checked' : ''}>
              </td>
              <td class="p-4 border-b border-white/10">
                <div class="flex items-center gap-3">
                  <div class="relative">
                  <img src="${user.photo}" alt="${user.name}" class="w-10 h-10 rounded-full border-2 border-white/20">
                    <div class="absolute -bottom-1 -right-1 w-6 h-6 rounded-full flex items-center justify-center text-sm profile-icon" 
                         style="background: ${user.icon_color || '#6b7280'}; border: 2px solid rgba(255,255,255,0.8);">
                      ${user.icon || '👤'}
                    </div>
                  </div>
                  <div>
                    <div class="font-semibold">${user.name}</div>
                    <div class="text-sm text-white/60">${user.email}</div>
                    <div class="text-xs text-white/40">${user.id}</div>
                  </div>
                </div>
              </td>
              <td class="p-4 border-b border-white/10">
                <span class="role-badge ${roleClass}">${user.role}</span>
              </td>
              <td class="p-4 border-b border-white/10">
                <span class="px-3 py-1 rounded-full text-xs font-semibold text-white ${statusClass}">
                  ${user.status.charAt(0).toUpperCase() + user.status.slice(1)}
                </span>
              </td>
              <td class="p-4 border-b border-white/10">
                <div class="text-sm">${formatDateTime(user.last_login)}</div>
                <div class="text-xs text-white/60">${user.login_count} logins</div>
              </td>
              <td class="p-4 border-b border-white/10">
                <span class="text-sm ${sessionClass}">${sessionStatus}</span>
              </td>
              <td class="p-4 border-b border-white/10">
                <div class="flex gap-2">
                  <button class="btn btn-sm btn-primary" onclick="openUserModal('${user.id}')">Details</button>
                  <button class="btn btn-sm ${user.status === 'active' ? 'btn-warning' : 'btn-success'}" 
                          onclick="toggleUserStatus('${user.id}')">
                    ${user.status === 'active' ? 'Deactivate' : 'Activate'}
                  </button>
                </div>
              </td>
            </tr>
          `;
        }).join('');
        
        // Add event listeners to checkboxes
        document.querySelectorAll('.user-checkbox').forEach(checkbox => {
          checkbox.addEventListener('change', handleUserSelection);
        });
        
        updateSelectionUI();
      }
      
      function handleUserSelection(e) {
        const userId = e.target.dataset.userId;
        const row = e.target.closest('tr');
        
        if (e.target.checked) {
          selectedUsers.add(userId);
          row.classList.add('selected-row');
        } else {
          selectedUsers.delete(userId);
          row.classList.remove('selected-row');
        }
        
        updateSelectionUI();
      }
      
      function toggleSelectAll() {
        const visibleUsers = Array.from(document.querySelectorAll('.user-checkbox'));
        
        if (selectAllCheckbox.checked) {
          visibleUsers.forEach(checkbox => {
            checkbox.checked = true;
            selectedUsers.add(checkbox.dataset.userId);
            checkbox.closest('tr').classList.add('selected-row');
          });
        } else {
          visibleUsers.forEach(checkbox => {
            checkbox.checked = false;
            selectedUsers.delete(checkbox.dataset.userId);
            checkbox.closest('tr').classList.remove('selected-row');
          });
        }
        
        updateSelectionUI();
      }
      
      function updateSelectionUI() {
        const count = selectedUsers.size;
        selectedCount.textContent = count;
        
        if (count > 0) {
          selectionInfo.style.display = 'block';
          bulkActivateBtn.disabled = false;
          bulkDeactivateBtn.disabled = false;
        } else {
          selectionInfo.style.display = 'none';
          bulkActivateBtn.disabled = true;
          bulkDeactivateBtn.disabled = true;
        }
        
        // Update select all checkbox
        const visibleCheckboxes = document.querySelectorAll('.user-checkbox');
        const checkedCheckboxes = document.querySelectorAll('.user-checkbox:checked');
        selectAllCheckbox.indeterminate = checkedCheckboxes.length > 0 && checkedCheckboxes.length < visibleCheckboxes.length;
        selectAllCheckbox.checked = visibleCheckboxes.length > 0 && checkedCheckboxes.length === visibleCheckboxes.length;
      }
      
      async function toggleUserStatus(userId) {
        try {
                        const response = await fetch(`/api/users/${userId}/toggle-status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
          });
          
          if (response.ok) {
            await loadUsers();
            await loadUserStats();
          } else {
            throw new Error('Failed to toggle user status');
          }
        } catch (error) {
          alert('Failed to toggle user status: ' + error.message);
        }
      }
      
      async function performBulkAction(action) {
        if (selectedUsers.size === 0) return;
        
        const userIds = Array.from(selectedUsers);
        const actionText = action === 'activate' ? 'activate' : 'deactivate';
        
        if (!confirm(`Are you sure you want to ${actionText} ${userIds.length} user(s)?`)) {
          return;
        }
        
        try {
          const response = await fetch('/api/users/bulk-action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              user_ids: userIds,
              action: action
            })
          });
          
          if (response.ok) {
            selectedUsers.clear();
            await loadUsers();
            await loadUserStats();
          } else {
            throw new Error(`Failed to ${actionText} users`);
          }
        } catch (error) {
          alert(`Failed to ${actionText} users: ` + error.message);
        }
      }
      
      function sortUsers(field) {
        if (currentSort.field === field) {
          currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
        } else {
          currentSort.field = field;
          currentSort.direction = 'asc';
        }
        
        // Update sort indicators
        document.querySelectorAll('th[data-sort]').forEach(th => {
          th.innerHTML = th.innerHTML.replace(/[↑↓]/g, '') + ' ↕️';
        });
        
        const currentTh = document.querySelector(`th[data-sort="${field}"]`);
        currentTh.innerHTML = currentTh.innerHTML.replace('↕️', currentSort.direction === 'asc' ? '↑' : '↓');
        
        filterUsers();
      }
      
      async function openUserModal(userId) {
        const user = allUsers.find(u => u.id === userId);
        if (!user) return;
        
        currentModal = user;
        
        // Populate modal with user data
        document.getElementById('modalTitle').textContent = `User Details - ${user.name}`;
        document.getElementById('modalUserPhoto').src = user.photo;
        document.getElementById('modalUserName').textContent = user.name;
        document.getElementById('modalUserEmail').textContent = user.email;
        
        // Set the cute icon
        const modalUserIcon = document.getElementById('modalUserIcon');
        modalUserIcon.textContent = user.icon || '👤';
        modalUserIcon.style.background = user.icon_color || '#6b7280';
        
        const statusClass = user.status === 'active' ? 'status-active' : 'status-inactive';
        document.getElementById('modalUserStatus').innerHTML = `
          <span class="px-3 py-1 rounded-full text-xs font-semibold text-white ${statusClass}">
            ${user.status.charAt(0).toUpperCase() + user.status.slice(1)}
          </span>
        `;
        
        // Populate role dropdown
        try {
          const rolesResponse = await fetch('/api/roles');
          const rolesData = await rolesResponse.json();
          
          const roleSelect = document.getElementById('changeUserRole');
          roleSelect.innerHTML = Object.keys(rolesData.roles).map(role => 
            `<option value="${role}" ${user.role === role ? 'selected' : ''}>${role}</option>`
          ).join('');
          
          // Store permissions data globally
          allPermissions = rolesData.permissions;
          
          // Populate permissions matrix
          renderPermissionsMatrix(user, false);
          
        } catch (error) {
          console.error('Failed to load roles:', error);
        }
        
        // Show modal
        userModal.classList.remove('hidden');
        userModal.classList.add('flex');
        
        // Setup modal event listeners
        document.getElementById('toggleUserStatus').onclick = () => {
          toggleUserStatus(userId);
          closeModal();
        };
        
        document.getElementById('changeUserRole').onchange = async (e) => {
          const newRole = e.target.value;
          if (newRole !== user.role) {
            try {
              const response = await fetch(`/api/users/${userId}/change-role`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ role: newRole })
              });
              
              if (response.ok) {
                // Update the user's role and icon immediately
                user.role = newRole;
                updateUserIcon(user);
                
                await loadUsers();
                await loadUserStats();
                openUserModal(userId); // Refresh modal
                
                // Show success message
                alert(`Role updated successfully! ${user.name} is now a ${newRole}.`);
              }
            } catch (error) {
              alert('Failed to change user role: ' + error.message);
            }
          }
        };
        
        document.getElementById('changeUserPassword').onclick = () => {
          openPasswordModal(userId, user.name);
        };

        document.getElementById('deleteUserBtn').onclick = async () => {
          if (!confirm(`Are you sure you want to delete ${user.name} (${user.id})? This cannot be undone.`)) {
            return;
          }
          try {
            const response = await fetch(`/api/users/${userId}?delete_files=true`, { method: 'DELETE' });
            if (response.ok) {
              alert('User deleted successfully');
              closeModal();
              await loadUsers();
              await loadUserStats();
            } else {
              const err = await response.json().catch(() => ({ detail: 'Failed to delete user' }));
              alert(err.detail || 'Failed to delete user');
            }
          } catch (e) {
            alert('Error deleting user: ' + e.message);
          }
        };
      }
      
      function closeModal() {
        userModal.classList.add('hidden');
        userModal.classList.remove('flex');
        currentModal = null;
      }
      
      function openPasswordModal(userId, userName) {
        document.getElementById('passwordModalUserName').textContent = userName;
        document.getElementById('passwordModalIcon').textContent = '🔑';
        document.getElementById('newPassword').value = '';
        document.getElementById('confirmPassword').value = '';
        document.getElementById('passwordMatchError').classList.add('hidden');
        
        // Store current user ID for the password change
        passwordModal.dataset.userId = userId;
        
        // Show modal
        passwordModal.classList.remove('hidden');
        passwordModal.classList.add('flex');
        
        // Focus on password field
        setTimeout(() => {
          document.getElementById('newPassword').focus();
        }, 100);
      }
      
      function closePasswordModal() {
        passwordModal.classList.add('hidden');
        passwordModal.classList.remove('flex');
        
        // Clear form
        document.getElementById('newPassword').value = '';
        document.getElementById('confirmPassword').value = '';
        document.getElementById('passwordMatchError').classList.add('hidden');
      }
      
      function validatePasswordMatch() {
        const newPassword = document.getElementById('newPassword').value;
        const confirmPassword = document.getElementById('confirmPassword').value;
        const errorDiv = document.getElementById('passwordMatchError');
        
        if (confirmPassword && newPassword !== confirmPassword) {
          errorDiv.classList.remove('hidden');
          return false;
        } else {
          errorDiv.classList.add('hidden');
          return true;
        }
      }
      
      async function changeUserPassword(event) {
        event.preventDefault();
        
        const newPassword = document.getElementById('newPassword').value;
        const confirmPassword = document.getElementById('confirmPassword').value;
        const userId = passwordModal.dataset.userId;
        
        // Validate passwords
        if (newPassword.length < 6) {
          alert('Password must be at least 6 characters long');
          return;
        }
        
        if (newPassword !== confirmPassword) {
          alert('Passwords do not match');
          return;
        }
        
        try {
          const response = await fetch(`/api/users/${userId}/change-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: newPassword })
          });
          
          const result = await response.json();
          
          if (response.ok && result.success) {
            alert(result.message);
            closePasswordModal();
            closeModal(); // Close the user modal too
          } else {
            alert(result.message || 'Failed to change password');
          }
        } catch (error) {
          alert('Error changing password: ' + error.message);
        }
      }
      
      // Add User Modal Functions
      let uploadedPhoto = null;
      let uploadedDocuments = [];
      
      async function openAddUserModal() {
        // Clear form
        document.getElementById('addUserForm').reset();
        document.getElementById('photoPreview').innerHTML = '👤';
        document.getElementById('documentsPreview').innerHTML = '';
        uploadedPhoto = null;
        uploadedDocuments = [];
        
        // Set default joining date to today
        const today = new Date().toISOString().split('T')[0];
        document.getElementById('newEmployeeJoiningDate').value = today;
        
        // Load and populate roles dropdown
        await loadRolesForForm();
        
        // Populate managers dropdown
        populateManagersDropdown();
        
        // Show modal
        addUserModal.classList.remove('hidden');
        addUserModal.classList.add('flex');
        
        // Focus on employee ID field
        setTimeout(() => {
          document.getElementById('newEmployeeId').focus();
        }, 100);
      }
      
      function closeAddUserModal() {
        addUserModal.classList.add('hidden');
        addUserModal.classList.remove('flex');
        
        // Clear form and uploads
        document.getElementById('addUserForm').reset();
        uploadedPhoto = null;
        uploadedDocuments = [];
      }
      
      async function loadRolesForForm() {
        try {
          const response = await fetch('/api/roles');
          const data = await response.json();
          
          if (data.roles) {
            allRoles = data.roles;
            populateRolesDropdown();
          }
        } catch (error) {
          console.error('Failed to load roles:', error);
          // Fallback to hardcoded roles if API fails
          populateRolesDropdownFallback();
        }
      }
      
      function populateRolesDropdown() {
        const roleSelect = document.getElementById('newEmployeeRole');
        roleSelect.innerHTML = '<option value="">Select Role</option>';
        
        Object.keys(allRoles).forEach(roleKey => {
          const role = allRoles[roleKey];
          const option = document.createElement('option');
          option.value = roleKey;
          option.textContent = role.name;
          roleSelect.appendChild(option);
        });
      }
      
      function populateRolesDropdownFallback() {
        const roleSelect = document.getElementById('newEmployeeRole');
        roleSelect.innerHTML = `
          <option value="">Select Role</option>
          <option value="owner">Company Owner</option>
          <option value="admin">Admin</option>
          <option value="manager">Manager</option>
          <option value="packer">Packer</option>
        `;
      }
      
      function populateManagersDropdown() {
        const managerSelect = document.getElementById('newEmployeeManager');
        managerSelect.innerHTML = '<option value="">Select Manager</option>';
        
        // Get users who are managers, admins, or owners
        const managers = allUsers.filter(user => 
          ['owner', 'admin', 'manager'].includes(user.role) && user.status === 'active'
        );
        
        managers.forEach(manager => {
          const option = document.createElement('option');
          option.value = manager.id;
          option.textContent = `${manager.name} (${manager.role})`;
          managerSelect.appendChild(option);
        });
      }
      
      function handlePhotoUpload(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        // Validate file size (5MB limit)
        if (file.size > 5 * 1024 * 1024) {
          alert('File size must be less than 5MB');
          return;
        }
        
        // Validate file type
        if (!file.type.startsWith('image/')) {
          alert('Please select a valid image file');
          return;
        }
        
        // Create preview
        const reader = new FileReader();
        reader.onload = function(e) {
          const preview = document.getElementById('photoPreview');
          preview.innerHTML = `<img src="${e.target.result}" class="w-full h-full object-cover rounded-full">`;
          uploadedPhoto = {
            file: file,
            data: e.target.result
          };
        };
        reader.readAsDataURL(file);
      }
      
      function handleDocumentsUpload(event) {
        const files = Array.from(event.target.files);
        const preview = document.getElementById('documentsPreview');
        
        files.forEach(file => {
          // Validate file size (10MB limit per file)
          if (file.size > 10 * 1024 * 1024) {
            alert(`File ${file.name} is too large. Maximum size is 10MB`);
            return;
          }
          
          // Add to uploaded documents
          uploadedDocuments.push(file);
          
          // Create preview item
          const docItem = document.createElement('div');
          docItem.className = 'flex items-center justify-between bg-slate-800/50 rounded-lg p-3';
          docItem.innerHTML = `
            <div class="flex items-center gap-2">
              <span class="text-lg">${getFileIcon(file.type)}</span>
              <div>
                <div class="font-medium text-sm">${file.name}</div>
                <div class="text-xs text-white/60">${formatFileSize(file.size)}</div>
              </div>
            </div>
            <button type="button" onclick="removeDocument('${file.name}')" class="text-red-400 hover:text-red-300">✕</button>
          `;
          preview.appendChild(docItem);
        });
        
        // Clear input
        event.target.value = '';
      }
      
      function getFileIcon(fileType) {
        if (fileType.includes('pdf')) return '📄';
        if (fileType.includes('doc')) return '📝';
        if (fileType.includes('image')) return '🖼️';
        return '📎';
      }
      
      function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
      }
      
      function removeDocument(fileName) {
        uploadedDocuments = uploadedDocuments.filter(doc => doc.name !== fileName);
        
        // Refresh preview
        const preview = document.getElementById('documentsPreview');
        const items = preview.querySelectorAll('div');
        items.forEach(item => {
          if (item.textContent.includes(fileName)) {
            item.remove();
          }
        });
      }
      async function createNewUser(event) {
        event.preventDefault();
        
        // Get form data
        const formData = new FormData();
        formData.append('employee_id', document.getElementById('newEmployeeId').value);
        formData.append('name', document.getElementById('newEmployeeName').value);
        formData.append('email', document.getElementById('newEmployeeEmail').value);
        formData.append('phone', document.getElementById('newEmployeePhone').value);
        formData.append('role', document.getElementById('newEmployeeRole').value);
        formData.append('password', document.getElementById('newEmployeePassword').value);
        formData.append('joining_date', document.getElementById('newEmployeeJoiningDate').value);
        formData.append('shift', document.getElementById('newEmployeeShift').value);
        formData.append('manager', document.getElementById('newEmployeeManager').value);
        formData.append('address', document.getElementById('newEmployeeAddress').value);
        formData.append('city', document.getElementById('newEmployeeCity').value);
        formData.append('state', document.getElementById('newEmployeeState').value);
        formData.append('zip', document.getElementById('newEmployeeZip').value);
        formData.append('emergency_contact_name', document.getElementById('emergencyContactName').value);
        formData.append('emergency_contact_relation', document.getElementById('emergencyContactRelation').value);
        formData.append('emergency_contact_phone', document.getElementById('emergencyContactPhone').value);
        formData.append('emergency_contact_email', document.getElementById('emergencyContactEmail').value);
        
        // Add photo if uploaded
        if (uploadedPhoto) {
          formData.append('photo', uploadedPhoto.file);
        }
        
        // Add documents if uploaded
        uploadedDocuments.forEach((doc, index) => {
          formData.append(`document_${index}`, doc);
        });
        
        try {
          const response = await fetch('/api/users/create', {
            method: 'POST',
            body: formData
          });
          
          const result = await response.json();
          
          if (response.ok && result.success) {
            alert(result.message);
            closeAddUserModal();
            await loadUsers();
            await loadUserStats();
          } else {
            alert(result.message || 'Failed to create user');
          }
        } catch (error) {
          alert('Error creating user: ' + error.message);
        }
      }
      
      function formatDateTime(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
      }
      
      function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
          const later = () => {
            clearTimeout(timeout);
            func(...args);
          };
          clearTimeout(timeout);
          timeout = setTimeout(later, wait);
        };
      }
      
      // Permission Editing Functions
      function enterEditMode() {
        editingPermissions = true;
        originalPermissions = [...currentModal.permissions];
        
        // Update UI
        editPermissionsBtn.style.display = 'none';
        savePermissionsBtn.style.display = 'inline-block';
        cancelPermissionsBtn.style.display = 'inline-block';
        document.getElementById('editModeNotice').style.display = 'block';
        
        // Make permission cards clickable
        renderPermissionsMatrix(currentModal, true);
      }
      
      function cancelEditMode() {
        editingPermissions = false;
        currentModal.permissions = [...originalPermissions];
        
        // Update UI
        editPermissionsBtn.style.display = 'inline-block';
        savePermissionsBtn.style.display = 'none';
        cancelPermissionsBtn.style.display = 'none';
        document.getElementById('editModeNotice').style.display = 'none';
        
        // Restore original permissions display
        renderPermissionsMatrix(currentModal, false);
      }
      
      async function savePermissions() {
        try {
          const response = await fetch(`/api/users/${currentModal.id}/update-permissions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ permissions: currentModal.permissions })
          });
          
          if (response.ok) {
            editingPermissions = false;
            editPermissionsBtn.style.display = 'inline-block';
            savePermissionsBtn.style.display = 'none';
            cancelPermissionsBtn.style.display = 'none';
            document.getElementById('editModeNotice').style.display = 'none';
            
            await loadUsers();
            await loadUserStats();
            renderPermissionsMatrix(currentModal, false);
            
            alert('Permissions updated successfully!');
          } else {
            throw new Error('Failed to update permissions');
          }
        } catch (error) {
          alert('Failed to save permissions: ' + error.message);
        }
      }
      
      function renderPermissionsMatrix(user, editable = false) {
        const permissionsMatrix = document.getElementById('permissionsMatrix');
        
        permissionsMatrix.innerHTML = Object.entries(allPermissions).map(([key, perm]) => {
          const isEnabled = user.permissions.includes(key) || user.permissions.includes('all');
          const enabledClass = isEnabled ? 'permission-enabled' : 'permission-disabled';
          const editableClass = editable ? 'permission-editable' : '';
          const clickHandler = editable ? `onclick="togglePermission('${key}')"` : '';
          
          return `
            <div class="p-3 rounded-lg border ${enabledClass} ${editableClass}" ${clickHandler}>
              <div class="font-semibold text-sm">${perm.name}</div>
              <div class="text-xs text-white/60 mt-1">${perm.description}</div>
              <div class="text-xs mt-1 ${isEnabled ? 'text-green-400' : 'text-gray-400'}">
                ${isEnabled ? '✓ Enabled' : '✗ Disabled'}
              </div>
            </div>
          `;
        }).join('');
      }
      
      function togglePermission(permissionKey) {
        if (!editingPermissions) return;
        
        const permissions = currentModal.permissions;
        const index = permissions.indexOf(permissionKey);
        
        if (index > -1) {
          permissions.splice(index, 1);
        } else {
          permissions.push(permissionKey);
        }
        
        // Remove 'all' if it exists when toggling individual permissions
        const allIndex = permissions.indexOf('all');
        if (allIndex > -1 && permissionKey !== 'all') {
          permissions.splice(allIndex, 1);
        }
        
        renderPermissionsMatrix(currentModal, true);
      }
      
      // Role Management Functions
      async function openRoleModal() {
        try {
          const response = await fetch('/api/roles');
          const data = await response.json();
          
          allRoles = data.roles;
          allPermissions = data.permissions;
          
          renderRolesGrid();
          
          roleModal.classList.remove('hidden');
          roleModal.classList.add('flex');
          
          // Setup event listeners for role actions
          document.getElementById('createNewRole').onclick = () => openRoleEditModal();
          document.getElementById('refreshRoles').onclick = () => {
            openRoleModal(); // Refresh
          };
          
        } catch (error) {
          alert('Failed to load roles: ' + error.message);
        }
      }
      
      function closeRoleModal() {
        roleModal.classList.add('hidden');
        roleModal.classList.remove('flex');
      }
      
      function renderRolesGrid() {
        const rolesGrid = document.getElementById('rolesGrid');
        
        rolesGrid.innerHTML = Object.entries(allRoles).map(([roleName, role]) => {
          const isCustom = role.custom || false;
          const cardClass = isCustom ? 'role-custom' : 'role-system';
          const userCount = allUsers.filter(u => u.role === roleName).length;
          
          return `
            <div class="glass p-4 role-card ${cardClass}" style="border-left: 4px solid ${role.color}">
              <div class="flex items-center justify-between mb-3">
                <h3 class="font-bold text-lg">${role.name}</h3>
                <span class="text-xs px-2 py-1 rounded ${isCustom ? 'bg-purple-500/20 text-purple-300' : 'bg-gray-500/20 text-gray-300'}">
                  ${isCustom ? 'Custom' : 'System'}
                </span>
              </div>
              
              <p class="text-sm text-white/70 mb-3">${role.description}</p>
              
              <div class="text-xs text-white/60 mb-3">
                <strong>${role.permissions.length}</strong> permissions • <strong>${userCount}</strong> users
              </div>
              
              <div class="flex gap-2">
                <button class="btn btn-sm btn-primary flex-1" onclick="editRole('${roleName}')">
                  ${isCustom ? '✏️ Edit' : '👁️ View'}
                </button>
                ${isCustom ? `<button class="btn btn-sm btn-danger" onclick="deleteRole('${roleName}')">🗑️</button>` : ''}
              </div>
            </div>
          `;
        }).join('');
      }
      
      function openRoleEditModal(roleName = null) {
        currentEditingRole = roleName;
        const isEditing = roleName !== null;
        const role = isEditing ? allRoles[roleName] : null;
        
        // Update modal title
        document.getElementById('roleEditTitle').textContent = isEditing ? `Edit Role: ${roleName}` : 'Create New Role';
        
        // Populate form
        document.getElementById('roleName').value = role ? role.name : '';
        document.getElementById('roleName').disabled = isEditing && !role?.custom; // Can't rename system roles
        document.getElementById('roleDescription').value = role ? role.description : '';
        document.getElementById('roleColor').value = role ? role.color : '#6b7280';
        
        // Render permissions grid
        renderRolePermissionsGrid(role ? role.permissions : []);
        
        // Show modal
        roleEditModal.classList.remove('hidden');
        roleEditModal.classList.add('flex');
      }
      
      function closeRoleEditModal() {
        roleEditModal.classList.add('hidden');
        roleEditModal.classList.remove('flex');
        currentEditingRole = null;
      }
      
      function renderRolePermissionsGrid(selectedPermissions) {
        const grid = document.getElementById('rolePermissionsGrid');
        
        grid.innerHTML = Object.entries(allPermissions).map(([key, perm]) => {
          const isSelected = selectedPermissions.includes(key);
          const toggleClass = isSelected ? 'active' : 'inactive';
          
          return `
            <div class="permission-toggle ${toggleClass} p-3 rounded-lg border cursor-pointer" onclick="toggleRolePermission('${key}')">
              <div class="flex items-center gap-2">
                <input type="checkbox" ${isSelected ? 'checked' : ''} readonly>
                <div>
                  <div class="font-semibold text-sm">${perm.name}</div>
                  <div class="text-xs text-white/60">${perm.description}</div>
                </div>
              </div>
            </div>
          `;
        }).join('');
      }
      
      function toggleRolePermission(permissionKey) {
        const checkbox = event.target.closest('.permission-toggle').querySelector('input[type="checkbox"]');
        checkbox.checked = !checkbox.checked;
        
        const toggle = checkbox.closest('.permission-toggle');
        if (checkbox.checked) {
          toggle.classList.add('active');
          toggle.classList.remove('inactive');
        } else {
          toggle.classList.remove('active');
          toggle.classList.add('inactive');
        }
      }
      
      async function saveRole(event) {
        event.preventDefault();
        
        const roleName = document.getElementById('roleName').value.trim();
        const roleDescription = document.getElementById('roleDescription').value.trim();
        const roleColor = document.getElementById('roleColor').value;
        
        // Get selected permissions
        const selectedPermissions = Array.from(document.querySelectorAll('#rolePermissionsGrid input[type="checkbox"]:checked'))
          .map(checkbox => {
            const toggle = checkbox.closest('.permission-toggle');
            return toggle.onclick.toString().match(/'([^']+)'/)[1];
          });
        
        const roleData = {
          name: roleName,
          description: roleDescription,
          color: roleColor,
          permissions: selectedPermissions
        };
        
        try {
          let response;
          if (currentEditingRole) {
            // Update existing role
            response = await fetch(`/api/roles/${currentEditingRole}`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(roleData)
            });
          } else {
            // Create new role
            response = await fetch('/api/roles/create', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(roleData)
            });
          }
          
          if (response.ok) {
            closeRoleEditModal();
            await openRoleModal(); // Refresh roles
            await loadUsers(); // Refresh users
            alert(`Role ${currentEditingRole ? 'updated' : 'created'} successfully!`);
          } else {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save role');
          }
        } catch (error) {
          alert('Failed to save role: ' + error.message);
        }
      }
      
      async function editRole(roleName) {
        openRoleEditModal(roleName);
      }
      
      async function deleteRole(roleName) {
        if (!confirm(`Are you sure you want to delete the role "${roleName}"?`)) {
          return;
        }
        
        try {
          const response = await fetch(`/api/roles/${roleName}`, {
            method: 'DELETE'
          });
          
          if (response.ok) {
            await openRoleModal(); // Refresh roles
            alert('Role deleted successfully!');
          } else {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to delete role');
          }
        } catch (error) {
          alert('Failed to delete role: ' + error.message);
        }
      }
      
      // Helper function to update user icon based on role
      function updateUserIcon(user) {
        const roleIcons = {
          'Super Admin': {icon: '👑', icon_color: '#FFD700'},
          'Admin': {icon: '🛡️', icon_color: '#4F46E5'},
          'Manager': {icon: '🎯', icon_color: '#EF4444'},
          'Employee': {icon: '⭐', icon_color: '#10B981'}
        };
        
        const roleIconData = roleIcons[user.role] || {icon: '👤', icon_color: '#6b7280'};
        user.icon = roleIconData.icon;
        user.icon_color = roleIconData.icon_color;
        
        // Update modal icon if it's currently open
        const modalUserIcon = document.getElementById('modalUserIcon');
        if (modalUserIcon && currentModal && currentModal.id === user.id) {
          modalUserIcon.textContent = user.icon;
          modalUserIcon.style.background = user.icon_color;
        }
      }
      
      // Make functions global for onclick handlers
      window.togglePermission = togglePermission;
      window.editRole = editRole;
      window.deleteRole = deleteRole;
      window.toggleRolePermission = toggleRolePermission;
      window.updateUserIcon = updateUserIcon;
    </script>
    """
    
    return _eraya_style_page("User Management", body)

# -------------------- Pending & Attendance placeholders --------------------
@app.get("/pending")
def eraya_pending_page():
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Pending Orders</h1>
      <p class="text-white/80 mt-2">Coming next.</p>
    </section>
    """
    return _eraya_style_page("Pending Orders", body)


@app.get("/attendance")
def eraya_attendance_page(current_user: Dict = Depends(require_roles("owner", "admin", "manager", "packer"))):
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Employee Attendance</h1>
      <p class="text-white/80 mt-2">Simple check-in/out and attendance records.</p>

      <div class="mt-6 grid gap-6">
        <div class="glass p-5">
          <h2 class="text-2xl font-semibold mb-3">Check-in/Check-out</h2>
          <div class="flex items-center gap-3">
            <select id="employeeSelect" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm">
              <option value="">Select Employee</option>
            </select>
            <button type="button" id="checkInBtn" class="btn btn-primary">Check In</button>
            <button type="button" id="checkOutBtn" class="btn btn-secondary">Check Out</button>
            <div id="attendanceStatus" class="text-white/70"></div>
          </div>
        </div>

        <div class="glass p-5">
          <h2 class="text-2xl font-semibold mb-3">Real-time Employee Status</h2>
          <div id="realtimeStatus" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"></div>
        </div>

        <div class="glass p-5">
          <h2 class="text-2xl font-semibold mb-3">Attendance Records</h2>
          <div class="flex flex-wrap items-center gap-3 mb-4">
            <input type="text" id="filterEmployeeId" placeholder="Filter by Employee ID" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <input type="date" id="filterDate" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <button type="button" id="applyFilterBtn" class="btn btn-primary">Apply Filter</button>
            <button type="button" id="clearFilterBtn" class="btn btn-secondary">Clear Filter</button>
          </div>
          <table class="min-w-full text-sm" id="attendanceTable">
            <thead>
              <tr>
                <th class="text-left p-2 border-b border-white/10">Employee ID</th>
                <th class="text-left p-2 border-b border-white/10">Check In Time</th>
                <th class="text-left p-2 border-b border-white/10">Check Out Time</th>
                <th class="text-left p-2 border-b border-white/10">Duration (hours)</th>
              </tr>
            </thead>
            <tbody id="attendanceTableBody">
            </tbody>
          </table>
        </div>

        <div class="glass p-5 text-center">
          <h2 class="text-2xl font-semibold mb-3">View Comprehensive Reports</h2>
          <p class="text-white/70 mb-4">Access detailed total hours and overtime reports with advanced filtering options.</p>
          <a href="/attendance/report_page" class="btn btn-primary">Go to Reports Page</a>
        </div>

      </div>
    </section>

    <script>
      const employeeIdInput = document.getElementById('employeeId');
      const checkInBtn = document.getElementById('checkInBtn');
      const checkOutBtn = document.getElementById('checkOutBtn');
      const attendanceStatus = document.getElementById('attendanceStatus');
      const attendanceTableBody = document.getElementById('attendanceTableBody');
      const filterEmployeeIdInput = document.getElementById('filterEmployeeId');
      const filterDateInput = document.getElementById('filterDate');
      const applyFilterBtn = document.getElementById('applyFilterBtn');
      const clearFilterBtn = document.getElementById('clearFilterBtn');
      const realtimeStatusDiv = document.getElementById('realtimeStatus');
      const employeeSelect = document.getElementById('employeeSelect');

      // Populate employee dropdown
      const employees = {
          "Ritik": "EMP001",
          "Sunny": "EMP002",
          "Rahul": "EMP003",
          "Sumit": "EMP004",
          "Vishal": "EMP005",
          "Nishant": "EMP006",
      };
      const employeeIdToName = {};
      // Role-based icon mapping
      const roleIcons = {
          'Super Admin': '👑', 'Admin': '🛡️', 'Manager': '🎯', 'Employee': '⭐'
      };
      
      const employeeRoles = {
          'EMP001': 'Super Admin', 'EMP002': 'Admin', 'EMP003': 'Manager',
          'EMP004': 'Employee', 'EMP005': 'Manager', 'EMP006': 'Employee'
      };

      for (const name in employees) {
          const id = employees[name];
          employeeIdToName[id] = name;
          const role = employeeRoles[id] || 'Employee';
          const icon = roleIcons[role] || '👤';

          const option = document.createElement('option');
          option.value = id;
          option.textContent = `${icon} ${name}`;
          employeeSelect.appendChild(option);
      }

      async function fetchAttendanceRecords() {
        const employee_id_filter = filterEmployeeIdInput.value;
        const date_filter = filterDateInput.value;
        
        let url = '/api/attendance/records';
        const params = new URLSearchParams();
        if (employee_id_filter) {
            params.append('employee_id', employee_id_filter);
        }
        if (date_filter) {
            params.append('date', date_filter);
        }
        if (params.toString()) {
            url += `?${params.toString()}`;
        }

        const response = await fetch(url);
        const records = await response.json();
        attendanceTableBody.innerHTML = '';
        
        const realtimeStatus = {};

        for (const employee_id in records) {
          records[employee_id].forEach(record => {
            const row = document.createElement('tr');
            const checkInTime = record.check_in_time ? new Date(record.check_in_time).toLocaleString() : 'N/A';
            const checkOutTime = record.check_out_time ? new Date(record.check_out_time).toLocaleString() : 'N/A';
            let duration = 'N/A';
            if (record.check_in_time && record.check_out_time) {
                const start = new Date(record.check_in_time);
                const end = new Date(record.check_out_time);
                duration = ((end - start) / (1000 * 60 * 60)).toFixed(2);
            } else if (record.check_in_time && !record.check_out_time) {
                const start = new Date(record.check_in_time);
                const now = new Date();
                duration = ((now - start) / (1000 * 60 * 60)).toFixed(2) + ' (current)';
                realtimeStatus[employee_id] = {status: 'Checked In', duration: duration};
            }
            
            if (!realtimeStatus[employee_id]) {
                // If not currently checked in, show status from the last record
                const lastRecord = records[employee_id][records[employee_id].length - 1];
                if (lastRecord && lastRecord.check_out_time) {
                     const start = new Date(lastRecord.check_in_time);
                     const end = new Date(lastRecord.check_out_time);
                     const last_duration = ((end - start) / (1000 * 60 * 60)).toFixed(2);
                    realtimeStatus[employee_id] = {status: 'Checked Out', duration: `${last_duration} (last)`};
                } else {
                    realtimeStatus[employee_id] = {status: 'Unknown', duration: 'N/A'};
                }
            }

            row.innerHTML = `
              <td class="border-t border-white/10 p-2">${employee_id}</td>
              <td class="border-t border-white/10 p-2">${checkInTime}</td>
              <td class="border-t border-white/10 p-2">${checkOutTime}</td>
              <td class="border-t border-white/10 p-2">${duration}</td>
            `;
            attendanceTableBody.appendChild(row);
          });
        }
        
        // Display real-time status
        realtimeStatusDiv.innerHTML = '';
        if (Object.keys(realtimeStatus).length === 0) {
            realtimeStatusDiv.innerHTML = '<p class="text-white/70">No employee status to display.</p>';
        } else {
            for (const emp_id in realtimeStatus) {
                const statusCard = document.createElement('div');
                statusCard.className = "glass p-4 rounded-lg";
                const employeeName = employeeIdToName[emp_id] || emp_id; // Get name or fallback to ID
                // Get role-based icon data
                const roleIcons = {
                    'Super Admin': {icon: '👑', icon_color: '#FFD700'},
                    'Admin': {icon: '🛡️', icon_color: '#4F46E5'},
                    'Manager': {icon: '🎯', icon_color: '#EF4444'},
                    'Employee': {icon: '⭐', icon_color: '#10B981'}
                };
                
                // Map employee IDs to their roles (this could be fetched from API in real implementation)
                const employeeRoles = {
                    'EMP001': 'Super Admin',
                    'EMP002': 'Admin', 
                    'EMP003': 'Manager',
                    'EMP004': 'Employee',
                    'EMP005': 'Manager',
                    'EMP006': 'Employee'
                };
                
                const userRole = employeeRoles[emp_id] || 'Employee';
                const userIcon = roleIcons[userRole] || {icon: '👤', icon_color: '#6b7280'};
                
                statusCard.innerHTML = `
                    <div class="flex items-center gap-3 mb-3">
                        <div class="relative">
                            <div class="w-12 h-12 rounded-full bg-slate-700 flex items-center justify-center">
                                <span class="text-lg">👤</span>
                            </div>
                            <div class="absolute -bottom-1 -right-1 w-6 h-6 rounded-full flex items-center justify-center text-sm profile-icon" 
                                 style="background: ${userIcon.icon_color}; border: 2px solid rgba(255,255,255,0.8);">
                                ${userIcon.icon}
                            </div>
                        </div>
                        <div>
                            <h3 class="font-semibold text-lg">${employeeName}</h3>
                            <p class="text-sm text-white/60">${emp_id}</p>
                        </div>
                    </div>
                    <p>Status: <span class="font-bold ${realtimeStatus[emp_id].status === 'Checked In' ? 'text-green-400' : 'text-red-400'}">${realtimeStatus[emp_id].status}</span></p>
                    <p>Duration: ${realtimeStatus[emp_id].duration}</p>
                `;
                realtimeStatusDiv.appendChild(statusCard);
            }
        }

      }

      async function handleCheckIn() {
        const employee_id = employeeSelect.value;
        if (!employee_id) {
          attendanceStatus.textContent = 'Please select an Employee.';
          return;
        }
        const formData = new FormData();
        formData.append('employee_id', employee_id);
        const response = await fetch('/api/attendance/check_in', {
          method: 'POST',
          body: formData,
        });
        const result = await response.json();
        attendanceStatus.textContent = result.message;
        fetchAttendanceRecords();
      }

      async function handleCheckOut() {
        const employee_id = employeeSelect.value;
        if (!employee_id) {
          attendanceStatus.textContent = 'Please select an Employee.';
          return;
        }
        const formData = new FormData();
        formData.append('employee_id', employee_id);
        const response = await fetch('/api/attendance/check_out', {
          method: 'POST',
          body: formData,
        });
        const result = await response.json();
        attendanceStatus.textContent = result.message;
        fetchAttendanceRecords();
      }

      checkInBtn.addEventListener('click', handleCheckIn);
      checkOutBtn.addEventListener('click', handleCheckOut);
      applyFilterBtn.addEventListener('click', fetchAttendanceRecords);
      clearFilterBtn.addEventListener('click', () => {
          filterEmployeeIdInput.value = '';
          filterDateInput.value = '';
          fetchAttendanceRecords();
      });

      // Initial fetch and set up real-time refresh
      fetchAttendanceRecords();
      setInterval(fetchAttendanceRecords, 30000); // Refresh every 30 seconds

    </script>
    """
    return _eraya_style_page("Attendance", body)
@app.get("/attendance/report_page")
def eraya_attendance_report_page():
    body = """
    <section class="glass p-6">
      <h1 class="text-3xl font-bold">Attendance Reports</h1>
      <p class="text-white/80 mt-2">View total hours and overtime reports with filters.</p>

      <div class="mt-6 grid gap-6">
        <div class="glass p-5">
          <h2 class="text-2xl font-semibold mb-3">Filter Reports</h2>
          <div class="flex flex-wrap items-center gap-3 mb-4">
            <input type="text" id="reportEmployeeId" placeholder="Filter by Employee ID" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <input type="date" id="reportStartDate" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <input type="date" id="reportEndDate" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <button type="button" id="applyReportFilterBtn" class="btn btn-primary">Apply Filter</button>
            <button type="button" id="clearReportFilterBtn" class="btn btn-secondary">Clear Filter</button>
          </div>
        </div>

        <div class="glass p-5">
          <h2 class="text-2xl font-semibold mb-3">Basic Reporting</h2>
          <button type="button" id="exportReportDataBtn" class="btn btn-secondary">Export All Data (CSV)</button>
          <div class="mt-3" id="reportingData"></div>
        </div>

        <div class="glass p-5">
            <h2 class="text-2xl font-semibold mb-3">Overtime Report</h2>
            <label for="reportOvertimeThreshold" class="text-white/70 mr-2">Overtime Threshold (hours):</label>
            <input type="number" id="reportOvertimeThreshold" value="8" step="0.5" class="rounded-xl bg-slate-900/60 border border-white/10 px-3 py-2 text-sm"/>
            <button type="button" id="generateReportOvertimeBtn" class="btn btn-primary">Generate Overtime Report</button>
            <div class="mt-3" id="overtimeData"></div>
        </div>

      </div>
    </section>

    <script>
      const reportEmployeeIdInput = document.getElementById('reportEmployeeId');
      const reportStartDateInput = document.getElementById('reportStartDate');
      const reportEndDateInput = document.getElementById('reportEndDate');
      const applyReportFilterBtn = document.getElementById('applyReportFilterBtn');
      const clearReportFilterBtn = document.getElementById('clearReportFilterBtn');
      const exportReportDataBtn = document.getElementById('exportReportDataBtn');
      const reportingData = document.getElementById('reportingData');
      const reportOvertimeThresholdInput = document.getElementById('reportOvertimeThreshold');
      const generateReportOvertimeBtn = document.getElementById('generateReportOvertimeBtn');
      const overtimeData = document.getElementById('overtimeData');

      async function fetchReports() {
        const employee_id_filter = reportEmployeeIdInput.value;
        const start_date = reportStartDateInput.value;
        const end_date = reportEndDateInput.value;

        // Fetch Total Hours Report
        let reportUrl = '/api/attendance/report';
        let reportParams = new URLSearchParams();
        if (employee_id_filter) reportParams.append('employee_id', employee_id_filter);
        if (start_date) reportParams.append('start_date', start_date);
        if (end_date) reportParams.append('end_date', end_date);
        if (reportParams.toString()) reportUrl += `?${reportParams.toString()}`;

        const totalHoursResponse = await fetch(reportUrl);
        const totalHoursReport = await totalHoursResponse.json();
        let totalHoursHtml = '<h3>Total Hours Report</h3>';
        if (Object.keys(totalHoursReport).length === 0) {
            totalHoursHtml += '<p>No total hours data available.</p>';
        } else {
            totalHoursHtml += '<ul class="list-disc pl-5 mt-2">';
            for (const employee_id in totalHoursReport) {
                totalHoursHtml += `<li><strong>${employee_id}:</strong> Total Hours: ${totalHoursReport[employee_id].total_hours}</li>`;
            }
            totalHoursHtml += '</ul>';
        }
        reportingData.innerHTML = totalHoursHtml;

        // Fetch Overtime Report
        let overtimeUrl = '/api/attendance/overtime';
        let overtimeParams = new URLSearchParams();
        if (employee_id_filter) overtimeParams.append('employee_id', employee_id_filter);
        if (start_date) overtimeParams.append('start_date', start_date);
        if (end_date) overtimeParams.append('end_date', end_date);
        const threshold = reportOvertimeThresholdInput.value;
        if (threshold) overtimeParams.append('threshold_hours', threshold);
        if (overtimeParams.toString()) overtimeUrl += `?${overtimeParams.toString()}`;

        const overtimeResponse = await fetch(overtimeUrl);
        const overtimeReport = await overtimeResponse.json();
        let overtimeHtml = '<h3>Overtime Report</h3>';
        if (Object.keys(overtimeReport).length === 0) {
            overtimeHtml += '<p>No overtime data available.</p>';
        } else {
            overtimeHtml += '<ul class="list-disc pl-5 mt-2">';
            for (const employee_id in overtimeReport) {
                overtimeHtml += `<li><strong>${employee_id}:</strong> Total Hours: ${overtimeReport[employee_id].total_hours}, Overtime Hours: ${overtimeReport[employee_id].overtime_hours}</li>`;
            }
            overtimeHtml += '</ul>';
        }
        overtimeData.innerHTML = overtimeHtml;
      }

      async function handleExportReportData() {
          const employee_id_filter = reportEmployeeIdInput.value;
          const start_date = reportStartDateInput.value;
          const end_date = reportEndDateInput.value;

          let url = '/api/attendance/export';
          const params = new URLSearchParams();
          if (employee_id_filter) params.append('employee_id', employee_id_filter);
          if (start_date) params.append('start_date', start_date);
          if (end_date) params.append('end_date', end_date);
          if (params.toString()) url += `?${params.toString()}`;

          try {
              const response = await fetch(url);
              if (!response.ok) {
                  const errorText = await response.text();
                  alert(`Error exporting data: ${errorText}`);
                  return;
              }
              const blob = await response.blob();
              const urlBlob = window.URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = urlBlob;
              a.download = 'attendance_report.csv';
              document.body.appendChild(a);
              a.click();
              a.remove();
              window.URL.revokeObjectURL(urlBlob);
          } catch (error) {
              console.error('Export failed:', error);
              alert('Failed to export data.');
          }
      }

      applyReportFilterBtn.addEventListener('click', fetchReports);
      clearReportFilterBtn.addEventListener('click', () => {
          reportEmployeeIdInput.value = '';
          reportStartDateInput.value = '';
          reportEndDateInput.value = '';
          fetchReports();
      });
      exportReportDataBtn.addEventListener('click', handleExportReportData);
      generateReportOvertimeBtn.addEventListener('click', fetchReports);

      // Initial fetch
      fetchReports();

    </script>
    """
    return _eraya_style_page("Attendance Reports", body)

@app.get("/chat")
def eraya_chat_page():
    body = """
    <div class="flex h-screen bg-slate-900">
      <!-- Sidebar -->
      <div class="w-80 glass border-r border-white/10 flex flex-col">
        <!-- User Info -->
        <div class="p-4 border-b border-white/10">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-full bg-gradient-to-r from-blue-500 to-purple-500 flex items-center justify-center">
              <span class="text-white font-semibold" id="userInitials">?</span>
            </div>
            <div class="flex-1">
              <select id="currentUser" class="bg-slate-800 border border-white/10 rounded px-2 py-1 text-sm w-full">
                <option value="">Select your name</option>
              </select>
            </div>
            <div id="onlineIndicator" class="w-3 h-3 bg-gray-400 rounded-full"></div>
          </div>
        </div>

        <!-- Channels Section -->
        <div class="flex-1 overflow-y-auto">
          <div class="p-3">
            <h3 class="text-sm font-semibold text-white/60 uppercase tracking-wide mb-2">Channels</h3>
            <div id="channelsList" class="space-y-1">
              <div class="channel-item p-2 rounded cursor-pointer hover:bg-white/5 flex items-center justify-between" data-channel="general">
                <div class="flex items-center gap-2">
                  <span class="text-white/60">#</span>
                  <span class="text-sm">general</span>
                </div>
                <span class="unread-badge hidden bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full">0</span>
              </div>
              <div class="channel-item p-2 rounded cursor-pointer hover:bg-white/5 flex items-center justify-between" data-channel="packing">
                <div class="flex items-center gap-2">
                  <span class="text-white/60">#</span>
                  <span class="text-sm">packing</span>
                </div>
                <span class="unread-badge hidden bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full">0</span>
              </div>
              <div class="channel-item p-2 rounded cursor-pointer hover:bg-white/5 flex items-center justify-between" data-channel="management">
                <div class="flex items-center gap-2">
                  <span class="text-white/60">#</span>
                  <span class="text-sm">management</span>
                </div>
                <span class="unread-badge hidden bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full">0</span>
              </div>
              <div class="channel-item p-2 rounded cursor-pointer hover:bg-white/5 flex items-center justify-between" data-channel="announcements">
                <div class="flex items-center gap-2">
                  <span class="text-white/60">📢</span>
                  <span class="text-sm">announcements</span>
                </div>
                <span class="unread-badge hidden bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full">0</span>
              </div>
            </div>
          </div>

          <!-- Direct Messages Section -->
          <div class="p-3 border-t border-white/10">
            <h3 class="text-sm font-semibold text-white/60 uppercase tracking-wide mb-2">Direct Messages</h3>
            <div id="dmsList" class="space-y-1">
              <!-- DMs will be populated here -->
            </div>
          </div>

          <!-- Online Users -->
          <div class="p-3 border-t border-white/10">
            <h3 class="text-sm font-semibold text-white/60 uppercase tracking-wide mb-2">Online Now</h3>
            <div id="onlineUsersList" class="space-y-1">
              <div class="text-xs text-white/40">Loading...</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Main Chat Area -->
      <div class="flex-1 flex flex-col">
        <!-- Chat Header -->
        <div class="p-4 border-b border-white/10 glass">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <span id="chatTitle" class="text-xl font-semibold"># general</span>
              <span id="chatDescription" class="text-sm text-white/60">General team discussion</span>
            </div>
            <div class="flex items-center gap-2">
              <a href="/chat" class="btn btn-primary text-sm">💬 Full Chat</a>
              <button id="backToHub" class="btn btn-secondary text-sm">← Back to Hub</button>
            </div>
          </div>
        </div>

        <!-- Messages Area -->
        <div id="messagesContainer" class="flex-1 overflow-y-auto p-4 space-y-4">
          <div class="text-center text-white/60">Loading messages...</div>
        </div>

        <!-- Message Input -->
        <div class="p-4 border-t border-white/10 glass">
          <div class="flex items-end gap-3">
            <div class="flex-1">
              <textarea id="messageInput" 
                       placeholder="Type your message..." 
                       class="w-full bg-slate-800/60 border border-white/10 rounded-lg px-3 py-2 text-sm resize-none"
                       rows="1" maxlength="500"></textarea>
            </div>
            <div class="flex gap-2">
              <input type="file" id="fileInput" class="hidden" accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.txt">
              <button id="fileBtn" class="p-2 text-white/60 hover:text-white rounded" title="Upload file">📎</button>
              <button id="emojiBtn" class="p-2 text-white/60 hover:text-white rounded" title="Add emoji">😊</button>
              <button id="sendMessage" class="btn btn-primary">Send</button>
            </div>
          </div>
          <div id="filePreview" class="hidden mt-2 p-3 bg-slate-800 rounded-lg border border-white/10">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-3">
                <div id="fileIcon" class="text-2xl">📎</div>
                <div>
                  <div id="fileName" class="text-sm font-medium"></div>
                  <div id="fileSize" class="text-xs text-white/60"></div>
                </div>
              </div>
              <button id="removeFile" class="text-red-400 hover:text-red-300">✕</button>
            </div>
          </div>
          <div id="emojiPicker" class="hidden mt-2 p-3 bg-slate-800 rounded-lg border border-white/10">
            <div class="grid grid-cols-8 gap-2 text-lg">
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">👍</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">❤️</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">😂</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">😮</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">😢</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">😡</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">🎉</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">🔥</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">💯</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">✅</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">❌</span>
              <span class="emoji cursor-pointer hover:bg-white/10 p-1 rounded">⚠️</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <style>
      .channel-item.active {
        background-color: rgba(59, 130, 246, 0.2);
        border-left: 3px solid #3b82f6;
      }
      .message-bubble {
        max-width: 70%;
        word-wrap: break-word;
      }
      .message-reactions {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        margin-top: 4px;
      }
      .reaction-btn {
        background: rgba(255, 255, 255, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 12px;
        padding: 2px 6px;
        font-size: 12px;
        cursor: pointer;
        transition: all 0.2s;
      }
      .reaction-btn:hover {
        background: rgba(255, 255, 255, 0.2);
      }
      .reaction-btn.active {
        background: rgba(59, 130, 246, 0.3);
        border-color: #3b82f6;
      }
      .dm-item {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px;
        border-radius: 6px;
        cursor: pointer;
        transition: background-color 0.2s;
      }
      .dm-item:hover {
        background-color: rgba(255, 255, 255, 0.05);
      }
      .dm-item.active {
        background-color: rgba(59, 130, 246, 0.2);
        border-left: 3px solid #3b82f6;
      }
      .online-dot {
        width: 8px;
        height: 8px;
        background-color: #10b981;
        border-radius: 50%;
        display: inline-block;
      }
      .offline-dot {
        width: 8px;
        height: 8px;
        background-color: #6b7280;
        border-radius: 50%;
        display: inline-block;
      }
      .file-attachment {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 12px;
        margin-top: 8px;
        display: flex;
        align-items: center;
        gap: 12px;
        transition: background-color 0.2s;
      }
      .file-attachment:hover {
        background: rgba(255, 255, 255, 0.08);
      }
      .file-icon {
        font-size: 24px;
        width: 40px;
        height: 40px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(59, 130, 246, 0.2);
        border-radius: 8px;
      }
      .link-preview {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 12px;
        margin-top: 8px;
        transition: background-color 0.2s;
      }
      .link-preview:hover {
        background: rgba(255, 255, 255, 0.08);
      }
      .image-preview {
        max-width: 300px;
        max-height: 200px;
        border-radius: 8px;
        margin-top: 8px;
        cursor: pointer;
      }
    </style>
    <script>
      // Chat application state
      let currentUser = '';
      let currentChannel = 'general';
      let currentDM = null;
      let isTyping = false;
      let selectedFile = null;

      // DOM elements
      const currentUserSelect = document.getElementById('currentUser');
      const userInitials = document.getElementById('userInitials');
      const onlineIndicator = document.getElementById('onlineIndicator');
      const channelsList = document.getElementById('channelsList');
      const dmsList = document.getElementById('dmsList');
      const onlineUsersList = document.getElementById('onlineUsersList');
      const chatTitle = document.getElementById('chatTitle');
      const chatDescription = document.getElementById('chatDescription');
      const messagesContainer = document.getElementById('messagesContainer');
      const messageInput = document.getElementById('messageInput');
      const sendMessage = document.getElementById('sendMessage');
      const emojiBtn = document.getElementById('emojiBtn');
      const emojiPicker = document.getElementById('emojiPicker');
      const backToHub = document.getElementById('backToHub');
      const fileBtn = document.getElementById('fileBtn');
      const fileInput = document.getElementById('fileInput');
      const filePreview = document.getElementById('filePreview');
      const fileName = document.getElementById('fileName');
      const fileSize = document.getElementById('fileSize');
      const fileIcon = document.getElementById('fileIcon');
      const removeFile = document.getElementById('removeFile');

      // Employee data
      const employees = {
          "Ritik": "EMP001",
          "Sunny": "EMP002",
          "Rahul": "EMP003",
          "Sumit": "EMP004",
          "Vishal": "EMP005",
          "Nishant": "EMP006",
      };

      // Initialize
      function init() {
          // Populate user dropdown
          for (const name in employees) {
              const option = document.createElement('option');
              option.value = employees[name];
              option.textContent = name;
              currentUserSelect.appendChild(option);
          }

          // Event listeners
          currentUserSelect.addEventListener('change', handleUserChange);
          sendMessage.addEventListener('click', handleSendMessage);
          messageInput.addEventListener('keypress', handleKeyPress);
          emojiBtn.addEventListener('click', toggleEmojiPicker);
          backToHub.addEventListener('click', () => window.location.href = '/hub');
          fileBtn.addEventListener('click', () => fileInput.click());
          fileInput.addEventListener('change', handleFileSelect);
          removeFile.addEventListener('click', handleRemoveFile);

          // Channel clicks
          document.querySelectorAll('.channel-item').forEach(item => {
              item.addEventListener('click', () => {
                  const channel = item.dataset.channel;
                  switchToChannel(channel);
              });
          });

          // Emoji picker
          document.querySelectorAll('.emoji').forEach(emoji => {
              emoji.addEventListener('click', () => {
                  messageInput.value += emoji.textContent;
                  emojiPicker.classList.add('hidden');
                  messageInput.focus();
              });
          });

          // Auto-resize textarea
          messageInput.addEventListener('input', function() {
              this.style.height = 'auto';
              this.style.height = Math.min(this.scrollHeight, 120) + 'px';
          });

          // Load initial data
          loadOnlineUsers();
          loadChannelMessages();
          
          // Set up periodic updates
          setInterval(loadOnlineUsers, 10000);
          setInterval(loadChannelMessages, 5000);
      }

      function handleUserChange() {
          currentUser = currentUserSelect.value;
          if (currentUser) {
              const userName = Object.keys(employees).find(key => employees[key] === currentUser);
              userInitials.textContent = userName ? userName.charAt(0).toUpperCase() : '?';
              onlineIndicator.className = 'w-3 h-3 bg-green-400 rounded-full';
              
              // Update user status
              updateUserStatus('online');
              
              // Load DMs
              loadDirectMessages();
          }
      }

      function switchToChannel(channel) {
          currentChannel = channel;
          currentDM = null;
          
          // Update UI
          document.querySelectorAll('.channel-item').forEach(item => {
              item.classList.remove('active');
          });
          document.querySelector(`[data-channel="${channel}"]`).classList.add('active');
          
          document.querySelectorAll('.dm-item').forEach(item => {
              item.classList.remove('active');
          });

          // Update header
          const channelNames = {
              'general': 'General',
              'packing': 'Packing Team',
              'management': 'Management',
              'announcements': 'Announcements'
          };
          
          chatTitle.textContent = `# ${channel}`;
          chatDescription.textContent = `${channelNames[channel]} discussion`;
          
          loadChannelMessages();
      }

      function switchToDM(employeeId) {
          currentDM = employeeId;
          currentChannel = null;
          
          // Update UI
          document.querySelectorAll('.channel-item').forEach(item => {
              item.classList.remove('active');
          });
          document.querySelectorAll('.dm-item').forEach(item => {
              item.classList.remove('active');
          });
          document.querySelector(`[data-dm="${employeeId}"]`).classList.add('active');

          // Update header
          const employeeName = Object.keys(employees).find(key => employees[key] === employeeId);
          chatTitle.textContent = `@ ${employeeName}`;
          chatDescription.textContent = 'Direct message';
          
          loadDMMessages(employeeId);
      }

      async function loadChannelMessages() {
          if (!currentChannel) return;
          
          try {
              const response = await fetch(`/api/chat/channel/${currentChannel}`);
              const data = await response.json();
              displayMessages(data.messages);
          } catch (error) {
              console.error('Error loading channel messages:', error);
          }
      }

      async function loadDMMessages(employeeId) {
          if (!currentUser || !employeeId) return;
          
          try {
              const response = await fetch(`/api/chat/dm/${employeeId}?current_employee_id=${currentUser}`);
              const data = await response.json();
              displayMessages(data.messages, true);
          } catch (error) {
              console.error('Error loading DM messages:', error);
          }
      }

      function displayMessages(messages, isDM = false) {
          if (!messages || messages.length === 0) {
              messagesContainer.innerHTML = '<div class="text-center text-white/60">No messages yet. Start the conversation!</div>';
              return;
          }

          let html = '';
          messages.forEach(msg => {
              const time = new Date(msg.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
              const isOwnMessage = isDM ? msg.from_employee_id === currentUser : msg.employee_id === currentUser;
              
              const senderName = isDM ? msg.from_employee_name : msg.employee_name;
              
              html += `
                  <div class="message-item">
                      <div class="flex items-start gap-3">
                          <div class="w-8 h-8 rounded-full bg-gradient-to-r from-blue-500 to-purple-500 flex items-center justify-center flex-shrink-0">
                              <span class="text-white text-sm font-semibold">${senderName.charAt(0).toUpperCase()}</span>
                          </div>
                          <div class="flex-1 min-w-0">
                              <div class="flex items-center gap-2 mb-1">
                                  <span class="font-semibold text-sm ${isOwnMessage ? 'text-blue-400' : 'text-white'}">${senderName}</span>
                                  <span class="text-xs text-white/50">${time}</span>
                              </div>
                              <div class="text-sm bg-slate-800/50 rounded-lg p-3 message-bubble">
                                  ${msg.message}
                              </div>
                              ${renderFileAttachment(msg.file_attachment)}
                              ${renderLinkPreviews(msg.links)}
                              <div class="message-reactions" data-message-id="${msg.id}">
                                  ${renderReactions(msg.reactions || {}, msg.id)}
                              </div>
                          </div>
                      </div>
                  </div>
              `;
          });
          
          messagesContainer.innerHTML = html;
          messagesContainer.scrollTop = messagesContainer.scrollHeight;
          
          // Add reaction click handlers
          document.querySelectorAll('.reaction-btn').forEach(btn => {
              btn.addEventListener('click', handleReactionClick);
          });
      }

      function renderReactions(reactions, messageId) {
          let html = '';
          for (const emoji in reactions) {
              const users = reactions[emoji];
              if (users.length > 0) {
                  const isActive = users.includes(currentUser);
                  html += `
                      <span class="reaction-btn ${isActive ? 'active' : ''}" 
                            data-message-id="${messageId}" 
                            data-emoji="${emoji}">
                          ${emoji} ${users.length}
                      </span>
                  `;
              }
          }
          return html;
      }

      function renderFileAttachment(fileAttachment) {
          if (!fileAttachment) return '';
          
          const fileTypeIcons = {
              'image': '🖼️',
              'video': '🎥',
              'audio': '🎵',
              'pdf': '📄',
              'document': '📝',
              'file': '📎'
          };
          
          const icon = fileTypeIcons[fileAttachment.file_type] || '📎';
          
          if (fileAttachment.file_type === 'image') {
              return `
                  <div class="file-attachment">
                      <img src="${fileAttachment.url}" alt="${fileAttachment.filename}" class="image-preview" onclick="window.open('${fileAttachment.url}', '_blank')">
                  </div>
              `;
          } else {
              return `
                  <div class="file-attachment" onclick="window.open('${fileAttachment.url}', '_blank')">
                      <div class="file-icon">${icon}</div>
                      <div class="flex-1">
                          <div class="font-medium text-sm">${fileAttachment.filename}</div>
                          <div class="text-xs text-white/60">${formatFileSize(fileAttachment.file_size)}</div>
                      </div>
                      <div class="text-blue-400 text-sm">Download</div>
                  </div>
              `;
          }
      }

      function renderLinkPreviews(links) {
          if (!links || links.length === 0) return '';
          
          let html = '';
          links.forEach(link => {
              html += `
                  <div class="link-preview" onclick="window.open('${link.url}', '_blank')">
                      <div class="font-medium text-sm text-blue-400">${link.title}</div>
                      <div class="text-xs text-white/60 mt-1">${link.description}</div>
                      <div class="text-xs text-white/40 mt-1">${link.url}</div>
                  </div>
              `;
          });
          
          return html;
      }

      async function handleReactionClick(e) {
          if (!currentUser) return;
          
          const messageId = e.target.dataset.messageId;
          const emoji = e.target.dataset.emoji;
          const isActive = e.target.classList.contains('active');
          
          try {
              const formData = new FormData();
              formData.append('message_id', messageId);
              formData.append('employee_id', currentUser);
              formData.append('emoji', emoji);
              
              const endpoint = isActive ? '/api/chat/reaction/remove' : '/api/chat/reaction/add';
              await fetch(endpoint, { method: 'POST', body: formData });
              
              // Reload messages to show updated reactions
              if (currentChannel) {
                  loadChannelMessages();
              } else if (currentDM) {
                  loadDMMessages(currentDM);
              }
          } catch (error) {
              console.error('Error handling reaction:', error);
          }
      }

      async function handleSendMessage() {
          if (!currentUser) {
              alert('Please select your name first.');
              return;
          }
          
          const message = messageInput.value.trim();
          if (!message && !selectedFile) return;
          
          try {
              let fileInfo = null;
              
              // Upload file if selected
              if (selectedFile) {
                  fileInfo = await uploadFile(selectedFile, currentUser);
                  if (!fileInfo) return; // Upload failed
              }
              
              const formData = new FormData();
              formData.append('employee_id', currentUser);
              formData.append('message', message);
              
              if (fileInfo) {
                  formData.append('file_info', JSON.stringify(fileInfo));
              }
              
              if (currentChannel) {
                  formData.append('channel', currentChannel);
                  await fetch('/api/chat/channel/send', { method: 'POST', body: formData });
                  loadChannelMessages();
              } else if (currentDM) {
                  formData.append('from_employee_id', currentUser);
                  formData.append('to_employee_id', currentDM);
                  await fetch('/api/chat/dm/send', { method: 'POST', body: formData });
                  loadDMMessages(currentDM);
              }
              
              messageInput.value = '';
              messageInput.style.height = 'auto';
              handleRemoveFile(); // Clear file selection
              
          } catch (error) {
              console.error('Error sending message:', error);
          }
      }

      function handleKeyPress(e) {
          if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSendMessage();
          }
      }

      function toggleEmojiPicker() {
          emojiPicker.classList.toggle('hidden');
      }

      function handleFileSelect(e) {
          const file = e.target.files[0];
          if (!file) return;
          
          // Check file size (10MB limit)
          if (file.size > 10 * 1024 * 1024) {
              alert('File too large. Maximum size is 10MB.');
              return;
          }
          
          selectedFile = file;
          showFilePreview(file);
      }

      function showFilePreview(file) {
          fileName.textContent = file.name;
          fileSize.textContent = formatFileSize(file.size);
          
          // Set appropriate icon based on file type
          const ext = file.name.split('.').pop().toLowerCase();
          if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) {
              fileIcon.textContent = '🖼️';
          } else if (['mp4', 'avi', 'mov', 'wmv'].includes(ext)) {
              fileIcon.textContent = '🎥';
          } else if (['mp3', 'wav', 'ogg'].includes(ext)) {
              fileIcon.textContent = '🎵';
          } else if (ext === 'pdf') {
              fileIcon.textContent = '📄';
          } else if (['doc', 'docx', 'txt'].includes(ext)) {
              fileIcon.textContent = '📝';
          } else {
              fileIcon.textContent = '📎';
          }
          
          filePreview.classList.remove('hidden');
      }

      function handleRemoveFile() {
          selectedFile = null;
          fileInput.value = '';
          filePreview.classList.add('hidden');
      }

      function formatFileSize(bytes) {
          if (bytes === 0) return '0 Bytes';
          const k = 1024;
          const sizes = ['Bytes', 'KB', 'MB', 'GB'];
          const i = Math.floor(Math.log(bytes) / Math.log(k));
          return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
      }

      async function uploadFile(file, employeeId) {
          const formData = new FormData();
          formData.append('file', file);
          formData.append('employee_id', employeeId);
          
          try {
              const response = await fetch('/api/chat/upload', {
                  method: 'POST',
                  body: formData
              });
              
              if (response.ok) {
                  const result = await response.json();
                  return result.file;
              } else {
                  throw new Error('Upload failed');
              }
          } catch (error) {
              console.error('File upload error:', error);
              alert('Failed to upload file.');
              return null;
          }
      }

      async function loadOnlineUsers() {
          try {
              const response = await fetch('/api/chat/users/online');
              const data = await response.json();
              
              let html = '';
              if (data.online_users.length === 0) {
                  html = '<div class="text-xs text-white/40">No one online</div>';
              } else {
                  data.online_users.forEach(user => {
                      html += `
                          <div class="flex items-center gap-2 p-1 cursor-pointer hover:bg-white/5 rounded text-sm"
                               onclick="switchToDM('${user.employee_id}')">
                              <div class="online-dot"></div>
                              <span>${user.employee_name}</span>
                          </div>
                      `;
                  });
              }
              
              onlineUsersList.innerHTML = html;
          } catch (error) {
              console.error('Error loading online users:', error);
          }
      }

      async function loadDirectMessages() {
          if (!currentUser) return;
          
          let html = '';
          for (const [name, empId] of Object.entries(employees)) {
              if (empId !== currentUser) {
                  html += `
                      <div class="dm-item" data-dm="${empId}" onclick="switchToDM('${empId}')">
                          <div class="w-6 h-6 rounded-full bg-gradient-to-r from-green-500 to-blue-500 flex items-center justify-center">
                              <span class="text-white text-xs font-semibold">${name.charAt(0).toUpperCase()}</span>
                          </div>
                          <span class="text-sm">${name}</span>
                      </div>
                  `;
              }
          }
          
          dmsList.innerHTML = html;
      }

      async function updateUserStatus(status) {
          if (!currentUser) return;
          
          try {
              const formData = new FormData();
              formData.append('employee_id', currentUser);
              formData.append('status', status);
              await fetch('/api/chat/status/update', { method: 'POST', body: formData });
          } catch (error) {
              console.error('Error updating status:', error);
          }
      }

      // Initialize the app
      init();
    </script>
    """
    return _eraya_style_page("Team Chat", body)

@app.post("/api/orders/download-photos")
async def download_order_photos(request: Request):
    """
    Downloads selected order photos as a PNG zip file, named by order number.
    Expects a JSON body with a list of {'url': '...', 'order_number': '...'} objects.
    """
    try:
        data = await request.json()
        photos_to_download = data.get("photos", [])

        if not photos_to_download:
            raise HTTPException(status_code=400, detail="No photos provided for download.")

        def generate_zip():
            import requests
            import zipfile
            import tempfile
            
            # Create a temporary file for the ZIP
            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
            temp_zip.close()
            
            try:
                with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for photo_info in photos_to_download:
                        url = photo_info.get("url")
                        order_number = photo_info.get("order_number")

                        if not url or not order_number:
                            continue

                        # Clean order number for filename - preserve # and numbers, remove other special chars
                        clean_order = re.sub(r'[^\w#-]', '_', str(order_number))
                        filename = f"{clean_order}.png"

                        try:
                            response = requests.get(url, timeout=10)
                            response.raise_for_status()
                            image_data = response.content

                            img = Image.open(io.BytesIO(image_data))
                            
                            # Convert to PNG
                            img_byte_arr = io.BytesIO()
                            img.save(img_byte_arr, format='PNG')
                            
                            # Add to ZIP
                            zipf.writestr(filename, img_byte_arr.getvalue())
                            
                        except requests.RequestException as e:
                            print(f"Error fetching photo from {url}: {e}")
                        except Exception as e:
                            print(f"Error processing image {url}: {e}")
                
                # Read the ZIP file and yield its contents
                with open(temp_zip.name, 'rb') as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        yield chunk
                        
            finally:
                # Clean up temp file
                import os
                try:
                    os.unlink(temp_zip.name)
                except:
                    pass

        # Generate filename with timestamp for uniqueness
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"order_photos_{timestamp}.zip"

        headers = {
            "Content-Disposition": f"attachment; filename=\"{filename}\"",
            "Content-Type": "application/zip",
            "X-Total-Photos": str(len(photos_to_download)),
        }
        return StreamingResponse(generate_zip(), headers=headers)

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")


@app.post("/api/orders/download-polaroids")
async def download_order_polaroids(request: Request):
    """
    Download selected polaroid images as a ZIP file.
    Each polaroid is converted to PNG format and named with the order number and index.
    """
    try:
        data = await request.json()
        polaroids_to_download = data.get("polaroids", [])

        if not polaroids_to_download:
            raise HTTPException(status_code=400, detail="No polaroids provided for download.")

        def generate_zip():
            import requests
            import zipfile
            import tempfile
            
            # Create a temporary file for the ZIP
            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
            temp_zip.close()
            
            try:
                with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for polaroid_info in polaroids_to_download:
                        url = polaroid_info.get("url")
                        order_number = polaroid_info.get("order_number")
                        polaroid_index = polaroid_info.get("polaroid_index", 1)

                        if not url or not order_number:
                            continue

                        # Clean order number for filename - preserve # and numbers, remove other special chars
                        clean_order = re.sub(r'[^\w#-]', '_', str(order_number))
                        filename = f"{clean_order}_polaroid_{polaroid_index}.png"

                        try:
                            response = requests.get(url, timeout=10)
                            response.raise_for_status()
                            image_data = response.content

                            img = Image.open(io.BytesIO(image_data))
                            
                            # Convert to PNG
                            img_byte_arr = io.BytesIO()
                            img.save(img_byte_arr, format='PNG')
                            
                            # Add to ZIP
                            zipf.writestr(filename, img_byte_arr.getvalue())
                            
                        except requests.RequestException as e:
                            print(f"Error fetching polaroid from {url}: {e}")
                        except Exception as e:
                            print(f"Error processing polaroid image {url}: {e}")
                
                # Read the ZIP file and yield its contents
                with open(temp_zip.name, 'rb') as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        yield chunk
                        
            finally:
                # Clean up temp file
                import os
                try:
                    os.unlink(temp_zip.name)
                except:
                    pass

        # Generate filename with timestamp for uniqueness
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"polaroid_images_{timestamp}.zip"
        
        headers = {
            "Content-Disposition": f"attachment; filename=\"{filename}\"",
            "Content-Type": "application/zip",
            "X-Total-Polaroids": str(len(polaroids_to_download)),
        }
        return StreamingResponse(generate_zip(), headers=headers)

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")