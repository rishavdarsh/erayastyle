"""
Admin Users Router - User Management functionality
"""
from fastapi import APIRouter, Request, Form, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, Dict
import secrets
import time

# Import from main app
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import supa

router = APIRouter(tags=["admin-users"])

# We'll import these inside the functions to avoid circular imports
# TEMPORARILY: Create a mock auth function for testing
def mock_auth():
    """Temporary mock authentication for testing"""
    return {"id": "test_user", "role": "admin", "name": "Test User"}

@router.get("/test")
def test_endpoint():
    """Test endpoint to verify router is working"""
    return {"message": "Router is working!", "timestamp": time.time()}

# CSRF token storage (simple in-memory for demo - use Redis/DB in production)
csrf_tokens = {}  # token -> timestamp

def generate_csrf_token() -> str:
    """Generate CSRF token with expiration"""
    token = secrets.token_urlsafe(32)
    csrf_tokens[token] = time.time()
    return token

def verify_csrf_token(token: str) -> bool:
    """Verify CSRF token (don't consume it immediately)"""
    if token in csrf_tokens:
        # Check if token is expired (1 hour)
        if time.time() - csrf_tokens[token] < 3600:
            return True
        else:
            # Remove expired token
            del csrf_tokens[token]
    return False

def cleanup_expired_csrf_tokens():
    """Clean up expired CSRF tokens"""
    current_time = time.time()
    expired_tokens = [token for token, timestamp in csrf_tokens.items() 
                     if current_time - timestamp > 3600]
    for token in expired_tokens:
        del csrf_tokens[token]

@router.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(
    request: Request,
    current_user: Dict = Depends(mock_auth)  # Use mock auth for testing
):
    """Render admin users page"""
    # Import locally to avoid circular imports
    from app import templates, NAV_ITEMS
    
    # Make NAV_ITEMS available to templates
    templates.env.globals["NAV_ITEMS"] = NAV_ITEMS
    
    cleanup_expired_csrf_tokens()  # Clean up old tokens
    csrf_token = generate_csrf_token()
    print(f"🔑 CSRF Debug: Generated new token: {csrf_token[:10]}...")
    print(f"🔑 CSRF Debug: Total tokens in memory: {len(csrf_tokens)}")
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "current_user": current_user,
        "csrf_token": csrf_token
    })

@router.get("/api/users")
def list_users_api(
    request: Request,
    query: str = "",
    page: int = 1,
    limit: int = 10,
    sort: str = "created_at",
    order: str = "desc",
    role_filter: str = "all",
    status_filter: str = "all",
    current_user: Dict = Depends(mock_auth)  # Use mock auth for testing
):
    """Get users list with pagination and filtering"""
    try:
        print(f"📡 API Debug: Calling supa.list_users with: query='{query}', page={page}, limit={limit}, sort='{sort}', order='{order}'")
        result = supa.list_users(
            query=query,
            page=page,
            limit=limit,
            sort=sort,
            order=order,
            role_filter=role_filter,
            status_filter=status_filter
        )
        print(f"📡 API Debug: supa.list_users returned: {result}")
        
        # TEMPORARY DIAGNOSTIC LOGGING (as requested)
        print(f"🔍 DIAGNOSTIC: Final Supabase query params: page={page}, limit={limit}, sort={sort}, order={order}")
        print(f"🔍 DIAGNOSTIC: Response items length: {len(result.get('items', []))}")
        print(f"🔍 DIAGNOSTIC: Response total: {result.get('total', 0)}")
        
        # Add cache-busting metadata
        result['_timestamp'] = time.time()
        result['_cache_bust'] = f"v{int(time.time())}"
        
        # Return with no-cache headers to prevent browser caching
        return JSONResponse(
            content=result,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    except Exception as e:
        print(f"Error in list_users_api: {e}")
        return JSONResponse(
            content={"ok": False, "error": "Failed to fetch users"},
            status_code=500
        )

@router.post("/api/users")
def create_user_api(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    role: str = Form("employee"),
    status: str = Form("active"),
    phone: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    joining_date: str = Form(""),
    csrf_token: str = Form(...),
    current_user: Dict = Depends(mock_auth)  # Use mock auth for testing
):
    """Create new user"""
    try:
        # Verify CSRF token
        print(f"🔒 CSRF Debug: Received token: {csrf_token[:10]}...")
        print(f"🔒 CSRF Debug: Available tokens: {list(csrf_tokens.keys())[:3]}")
        if not verify_csrf_token(csrf_token):
            print(f"❌ CSRF Debug: Token verification failed for: {csrf_token[:10]}...")
            return JSONResponse(
                content={"ok": False, "error": "Invalid CSRF token"},
                status_code=403
            )
        print(f"✅ CSRF Debug: Token verified successfully")
        
        # Validate password confirmation
        if password != password_confirm:
            return JSONResponse(
                content={"ok": False, "error": "Passwords do not match"},
                status_code=400
            )
        
        # Validate password strength
        if len(password) < 6:
            return JSONResponse(
                content={"ok": False, "error": "Password must be at least 6 characters"},
                status_code=400
            )
        
        # Prepare user data
        user_data = {
            "name": name,
            "email": email,
            "password": password,
            "role": role,
            "status": status,
            "phone": phone,
            "city": city,
            "state": state,
        }
        
        if joining_date:
            user_data["joining_date"] = joining_date
        
        # Create user
        result = supa.create_user(user_data)
        
        if result["ok"]:
            return JSONResponse(content=result, status_code=201)
        else:
            return JSONResponse(content=result, status_code=400)
            
    except Exception as e:
        print(f"Error creating user: {e}")
        return JSONResponse(
            content={"ok": False, "error": "Failed to create user"},
            status_code=500
        )

@router.patch("/api/users/{user_id}")
def update_user_api(
    user_id: str,
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(""),
    password_confirm: str = Form(""),
    role: str = Form(...),
    status: str = Form(...),
    phone: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    joining_date: str = Form(""),
    csrf_token: str = Form(...),
    current_user: Dict = Depends(mock_auth)  # Use mock auth for testing
):
    """Update existing user"""
    try:
        # Verify CSRF token
        print(f"🔒 CSRF Debug: Received token: {csrf_token[:10]}...")
        print(f"🔒 CSRF Debug: Available tokens: {list(csrf_tokens.keys())[:3]}")
        if not verify_csrf_token(csrf_token):
            print(f"❌ CSRF Debug: Token verification failed for: {csrf_token[:10]}...")
            return JSONResponse(
                content={"ok": False, "error": "Invalid CSRF token"},
                status_code=403
            )
        print(f"✅ CSRF Debug: Token verified successfully")
        
        # Validate password confirmation if password is provided
        if password and password != password_confirm:
            return JSONResponse(
                content={"ok": False, "error": "Passwords do not match"},
                status_code=400
            )
        
        # Validate password strength if provided
        if password and len(password) < 6:
            return JSONResponse(
                content={"ok": False, "error": "Password must be at least 6 characters"},
                status_code=400
            )
        
        # Prepare update data
        update_data = {
            "name": name,
            "email": email,
            "role": role,
            "status": status,
            "phone": phone,
            "city": city,
            "state": state,
        }
        
        # Only include password if provided
        if password:
            update_data["password"] = password
        
        if joining_date:
            update_data["joining_date"] = joining_date
        
        # Update user
        result = supa.update_user(user_id, update_data)
        
        if result["ok"]:
            return JSONResponse(content=result)
        else:
            return JSONResponse(content=result, status_code=400)
            
    except Exception as e:
        print(f"Error updating user {user_id}: {e}")
        return JSONResponse(
            content={"ok": False, "error": "Failed to update user"},
            status_code=500
        )

@router.delete("/api/users/{user_id}")
def delete_user_api(
    user_id: str,
    request: Request,
    csrf_token: str = Form(...),
    current_user: Dict = Depends(mock_auth)  # Use mock auth for testing
):
    """Delete user"""
    try:
        # Verify CSRF token
        print(f"🔒 CSRF Debug: Received token: {csrf_token[:10]}...")
        print(f"🔒 CSRF Debug: Available tokens: {list(csrf_tokens.keys())[:3]}")
        if not verify_csrf_token(csrf_token):
            print(f"❌ CSRF Debug: Token verification failed for: {csrf_token[:10]}...")
            return JSONResponse(
                content={"ok": False, "error": "Invalid CSRF token"},
                status_code=403
            )
        print(f"✅ CSRF Debug: Token verified successfully")
        
        # Prevent self-deletion (temporarily disabled for testing)
        # if user_id == current_user.get("id") or user_id == current_user.get("employee_id"):
        #     return JSONResponse(
        #         content={"ok": False, "error": "Cannot delete your own account"},
        #         status_code=400
        #     )
        
        # Delete user
        result = supa.delete_user(user_id)
        
        if result["ok"]:
            # Return 204 No Content on successful deletion with no-cache headers
            return JSONResponse(
                content=result,
                status_code=204,
                headers={
                    "Cache-Control": "no-store",
                    "Pragma": "no-cache"
                }
            )
        else:
            # Return appropriate status code based on error
            if "User not found" in result.get("error", ""):
                return JSONResponse(
                    content=result, 
                    status_code=404,
                    headers={
                        "Cache-Control": "no-store",
                        "Pragma": "no-cache"
                    }
                )
            else:
                return JSONResponse(
                    content=result, 
                    status_code=400,
                    headers={
                        "Cache-Control": "no-store",
                        "Pragma": "no-cache"
                    }
                )
            
    except Exception as e:
        print(f"Error deleting user {user_id}: {e}")
        return JSONResponse(
            content={"ok": False, "error": "Failed to delete user"},
            status_code=500
        )

@router.get("/api/users/{user_id}")
def get_user_api(
    user_id: str,
    current_user: Dict = Depends(mock_auth)  # Use mock auth for testing
):
    """Get single user details"""
    try:
        user = supa.get_user(user_id)
        if user:
            return JSONResponse(content={"ok": True, "data": user})
        else:
            return JSONResponse(
                content={"ok": False, "error": "User not found"},
                status_code=404
            )
    except Exception as e:
        print(f"Error getting user {user_id}: {e}")
        return JSONResponse(
            content={"ok": False, "error": "Failed to get user"},
            status_code=500
        )
