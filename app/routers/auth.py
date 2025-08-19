"""
Authentication router for login, logout, and user management
"""
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Optional, Any
import time

from app.deps import get_current_user, require_auth, create_session
from app.services import supa

router = APIRouter()

# Get templates from app state
def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Login page"""
    # Check if user is already logged in
    current_user = get_current_user(request.cookies.get("session_id"))
    if current_user:
        return RedirectResponse(url="/hub", status_code=302)
    
    return templates.TemplateResponse("login.html", {
        "request": request,
        "title": "Login",
        "header": "Login"
    })

@router.post("/api/auth/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False)
):
    """Authenticate user and create session - TEMPORARILY DISABLED"""
    try:
        print(f"🔓 TEMPORARY LOGIN: Username '{username}' with password '{password}' - AUTHENTICATION DISABLED")
        
        # TEMPORARILY: Create a mock user for any login
        mock_user = {
            "id": "temp_user_123",
            "name": username,
            "role": "ADMIN",  # Give admin access temporarily
            "status": "active"
        }
        
        print(f"✅ Creating mock session for: {mock_user['name']} (Role: {mock_user['role']})")
        
        # Create session
        session_token = create_session(mock_user["id"], remember_me)
        
        # Create response
        response = JSONResponse(content={
            "message": "Login successful (AUTHENTICATION TEMPORARILY DISABLED)",
            "user": {
                "id": mock_user["id"],
                "name": mock_user["name"],
                "username": mock_user["name"],
                "role": mock_user["role"]
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
        
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed. Please try again."
        )

@router.post("/api/auth/logout")
async def logout(request: Request):
    """Logout user and clear session"""
    response = JSONResponse(content={"message": "Logout successful"})
    response.delete_cookie("session_id")
    return response

@router.get("/api/auth/me")
async def get_current_user_info():  # current_user: Dict = Depends(require_auth) - TEMPORARILY DISABLED
    """Get current logged-in user information - TEMPORARILY DISABLED"""
    # TEMPORARILY: Return mock user data
    return {
        "id": "temp_user_123",
        "name": "Temporary User",
        "role": "ADMIN",
        "email": "temp@example.com",
        "status": "active"
    }

@router.get("/api/auth/navigation")
async def get_current_user_navigation():  # current_user: Dict = Depends(require_auth) - TEMPORARILY DISABLED
    """Get navigation menu for current authenticated user - TEMPORARILY DISABLED"""
    from app.factory import NAV_ITEMS
    
    # TEMPORARILY: Return all navigation items for admin
    return JSONResponse(content={
        "role": "admin",
        "menu": NAV_ITEMS
    })

@router.get("/api/user/{user_id}/role")
async def get_user_role(user_id: str):  # current_user: Dict = Depends(require_auth) - TEMPORARILY DISABLED
    """Get role for a specific user (admin only) - TEMPORARILY DISABLED"""
    # TEMPORARILY: Return mock role data
    return {"role": "ADMIN"}
