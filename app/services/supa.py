"""
Single Supabase client and helper functions for the application
"""
import os
import uuid
from typing import Dict, List, Optional, Any
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import re
from datetime import datetime

from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

# Initialize Supabase client with service role key for admin operations
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Password hasher
ph = PasswordHasher()

print(f"🔧 Supabase client initialized:")
print(f"   URL: {SUPABASE_URL}")
print(f"   Service Key: {SUPABASE_SERVICE_ROLE_KEY[:20] if SUPABASE_SERVICE_ROLE_KEY else 'None'}...")

def hash_password(password: str) -> str:
    """Hash password using Argon2"""
    return ph.hash(password)

def verify_password(password: str, hash: str) -> bool:
    """Verify password against hash"""
    try:
        if not hash:
            return False
        ph.verify(hash, password)
        return True
    except VerifyMismatchError:
        return False
    except Exception as e:
        print(f"Password verification error: {e}")
        return False

def validate_email(email: str) -> bool:
    """Basic email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def normalize_email(email: str) -> str:
    """Normalize email (lowercase, strip whitespace)"""
    return email.strip().lower()

# User Management Functions
def list_users(query: str = "", page: int = 1, limit: int = 10, sort: str = "created_at", order: str = "desc", role_filter: str = "all", status_filter: str = "all") -> Dict[str, Any]:
    """
    List users with search, pagination, and filtering
    Returns: {items: List[Dict], total: int, page: int, pages: int}
    """
    try:
        # Base query - exclude password_hash from selection
        base_query = supabase.table("users").select(
            "id, name, email, role, status, phone, city, state, joining_date, last_login, login_count, created_at, updated_at",
            count="exact"
        )
        
        # Apply search filter
        if query:
            # Enhanced search across multiple fields
            base_query = base_query.or_(f"name.ilike.%{query}%,email.ilike.%{query}%,phone.ilike.%{query}%")
        
        # Apply role filter
        if role_filter and role_filter != "all":
            base_query = base_query.eq("role", role_filter)
        
        # Apply status filter
        if status_filter and status_filter != "all":
            base_query = base_query.eq("status", status_filter)
        
        # Apply sorting
        desc = order.lower() == "desc"
        base_query = base_query.order(sort, desc=desc)
        
        # Apply pagination
        offset = (page - 1) * limit
        base_query = base_query.range(offset, offset + limit - 1)
        
        # Execute query
        print(f"🔍 Supabase Debug: Executing query with params: page={page}, limit={limit}, sort={sort}, order={order}")
        response = base_query.execute()
        print(f"🔍 Supabase Debug: Response data length: {len(response.data) if response.data else 0}")
        print(f"🔍 Supabase Debug: Response count: {response.count}")
        
        # Calculate pagination info
        total = response.count if response.count else 0
        pages = (total + limit - 1) // limit if total > 0 else 1
        
        result = {
            "items": response.data or [],
            "total": total,
            "page": page,
            "pages": pages,
            "limit": limit
        }
        
        print(f"🔍 Supabase Debug: Returning result: {result}")
        return result
        
    except Exception as e:
        print(f"Error listing users: {e}")
        return {"items": [], "total": 0, "page": 1, "pages": 1, "limit": limit}

def get_user(user_id: str) -> Optional[Dict]:
    """Get user by ID (exclude password_hash)"""
    try:
        response = supabase.table("users").select(
            "id, name, email, role, status, phone, city, state, joining_date, last_login, login_count, created_at, updated_at"
        ).eq("id", user_id).execute()
        
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error getting user {user_id}: {e}")
        return None

def check_email_unique(email: str, exclude_id: str = None) -> bool:
    """Check if email is unique (optionally excluding a specific user ID)"""
    try:
        query = supabase.table("users").select("id").eq("email", email)
        if exclude_id:
            query = query.neq("id", exclude_id)
        
        response = query.execute()
        return len(response.data) == 0
    except Exception as e:
        print(f"Error checking email uniqueness: {e}")
        return False

def create_user(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create new user
    Returns: {ok: bool, data: Dict, error: str}
    """
    try:
        # Generate ID if not provided
        if "id" not in payload or not payload["id"]:
            payload["id"] = str(uuid.uuid4())
        
        # Validate required fields
        if not payload.get("name") or not payload.get("email"):
            return {"ok": False, "error": "Name and email are required"}
        
        # Validate and normalize email
        email = normalize_email(payload["email"])
        if not validate_email(email):
            return {"ok": False, "error": "Invalid email format"}
        
        payload["email"] = email
        
        # Check email uniqueness
        if not check_email_unique(email):
            return {"ok": False, "error": "Email already exists"}
        
        # Validate password (required for creation)
        if not payload.get("password"):
            return {"ok": False, "error": "Password is required"}
        
        # Hash password
        payload["password_hash"] = hash_password(payload["password"])
        del payload["password"]  # Remove plain password
        
        # Set defaults
        payload.setdefault("role", "employee")
        payload.setdefault("status", "active")
        payload.setdefault("login_count", 0)
        payload["created_at"] = datetime.now().isoformat()
        payload["updated_at"] = datetime.now().isoformat()
        
        # Validate role and status
        valid_roles = ["owner", "admin", "manager", "employee", "packer"]
        valid_statuses = ["active", "inactive", "suspended"]
        
        if payload["role"] not in valid_roles:
            return {"ok": False, "error": f"Invalid role. Must be one of: {', '.join(valid_roles)}"}
        
        if payload["status"] not in valid_statuses:
            return {"ok": False, "error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}
        
        # Trim string fields
        for field in ["name", "phone", "city", "state"]:
            if field in payload and payload[field]:
                payload[field] = payload[field].strip()
        
        # Insert user
        response = supabase.table("users").insert(payload).execute()
        
        if response.data:
            # Return user data without password_hash
            user_data = response.data[0].copy()
            user_data.pop("password_hash", None)
            return {"ok": True, "data": user_data}
        else:
            return {"ok": False, "error": "Failed to create user"}
            
    except Exception as e:
        print(f"Error creating user: {e}")
        return {"ok": False, "error": str(e)}

def update_user(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update user
    Returns: {ok: bool, data: Dict, error: str}
    """
    try:
        # Check if user exists
        existing_user = get_user(user_id)
        if not existing_user:
            return {"ok": False, "error": "User not found"}
        
        # Remove fields that shouldn't be updated
        update_data = payload.copy()
        update_data.pop("id", None)
        update_data.pop("created_at", None)
        
        # Handle email update
        if "email" in update_data:
            email = normalize_email(update_data["email"])
            if not validate_email(email):
                return {"ok": False, "error": "Invalid email format"}
            
            # Check email uniqueness (excluding current user)
            if not check_email_unique(email, user_id):
                return {"ok": False, "error": "Email already exists"}
            
            update_data["email"] = email
        
        # Handle password update (only if provided and not empty)
        if "password" in update_data and update_data["password"]:
            update_data["password_hash"] = hash_password(update_data["password"])
            del update_data["password"]
        else:
            update_data.pop("password", None)
        
        # Validate role and status if provided
        valid_roles = ["owner", "admin", "manager", "employee", "packer"]
        valid_statuses = ["active", "inactive", "suspended"]
        
        if "role" in update_data and update_data["role"] not in valid_roles:
            return {"ok": False, "error": f"Invalid role. Must be one of: {', '.join(valid_roles)}"}
        
        if "status" in update_data and update_data["status"] not in valid_statuses:
            return {"ok": False, "error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}
        
        # Trim string fields
        for field in ["name", "phone", "city", "state"]:
            if field in update_data and update_data[field]:
                update_data[field] = update_data[field].strip()
        
        # Set updated timestamp
        update_data["updated_at"] = datetime.now().isoformat()
        
        # Update user
        response = supabase.table("users").update(update_data).eq("id", user_id).execute()
        
        if response.data:
            # Return updated user data without password_hash
            user_data = response.data[0].copy()
            user_data.pop("password_hash", None)
            return {"ok": True, "data": user_data}
        else:
            return {"ok": False, "error": "Failed to update user"}
            
    except Exception as e:
        print(f"Error updating user {user_id}: {e}")
        return {"ok": False, "error": str(e)}

def delete_user(user_id: str) -> Dict[str, Any]:
    """
    Delete user
    Returns: {ok: bool, error: str}
    """
    try:
        # Check if user exists
        existing_user = get_user(user_id)
        if not existing_user:
            return {"ok": False, "error": "User not found"}
        
        # Delete user
        response = supabase.table("users").delete().eq("id", user_id).execute()
        
        if response.data:
            return {"ok": True}
        else:
            return {"ok": False, "error": "Failed to delete user"}
            
    except Exception as e:
        print(f"Error deleting user {user_id}: {e}")
        return {"ok": False, "error": str(e)}

# Authentication Functions
def get_user_by_session(session_id: str) -> Optional[Dict]:
    """Get user by session ID"""
    try:
        # This would need to be implemented based on your session management
        # For now, we'll return a mock user for testing
        return {"id": "test_user", "role": "admin", "name": "Test User"}
    except Exception as e:
        print(f"Error getting user by session: {e}")
        return None

# Order Management Functions (placeholder - implement based on your needs)
def list_orders(query: str = "", page: int = 1, limit: int = 10) -> Dict[str, Any]:
    """List orders with pagination and filtering"""
    # TODO: Implement order listing
    return {"items": [], "total": 0, "page": page, "pages": 1, "limit": limit}

def get_order(order_id: str) -> Optional[Dict]:
    """Get order by ID"""
    # TODO: Implement order retrieval
    return None

def upsert_orders(orders: List[Dict]) -> Dict[str, Any]:
    """Upsert orders (create or update)"""
    # TODO: Implement order upsert
    return {"ok": True, "message": "Orders processed"}

def delete_order(order_id: str) -> Dict[str, Any]:
    """Delete order by ID"""
    # TODO: Implement order deletion
    return {"ok": True, "message": "Order deleted"}

print("✅ Supabase service initialized with all helper functions")
