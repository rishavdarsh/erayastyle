"""
Users router for user management (admin interface)
"""
from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Optional, Any
import time

from app.services import supa

router = APIRouter()

# Get templates from app state
def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates

# Mock authentication for testing (replace with real auth later)
def mock_auth():
    """Temporary mock authentication for testing"""
    return {"id": "test_user", "role": "admin", "name": "Test User"}

@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """User management page"""
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "title": "User Management",
        "header": "User Management"
    })

@router.get("/api/users")
async def list_users_api(
    request: Request,
    query: str = "",
    page: int = 1,
    limit: int = 10,
    sort: str = "created_at",
    order: str = "desc",
    role_filter: str = "all",
    status_filter: str = "all"
):
    """List users with search, pagination, and filtering"""
    try:
        # Call Supabase helper
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
        print(f"📡 API Debug: list_users_api: Returning {len(result['items'])} items, Total: {result['total']}")
        
        # Return with no-cache headers
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
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/users")
async def create_user_api(request: Request):
    """Create a new user"""
    try:
        payload = await request.json()
        result = supa.create_user(payload)
        
        if result["ok"]:
            return JSONResponse(
                content={"ok": True, "id": result["data"]["id"]},
                status_code=201
            )
        else:
            return JSONResponse(
                content={"ok": False, "error": result["error"]},
                status_code=400
            )
    except Exception as e:
        print(f"Error in create_user_api: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/api/users/{user_id}")
async def update_user_api(user_id: str, request: Request):
    """Update an existing user"""
    try:
        payload = await request.json()
        result = supa.update_user(user_id, payload)
        
        if result["ok"]:
            return JSONResponse(content={"ok": True, "data": result["data"]})
        else:
            return JSONResponse(
                content={"ok": False, "error": result["error"]},
                status_code=400
            )
    except Exception as e:
        print(f"Error in update_user_api: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/users/{user_id}")
async def delete_user_api(user_id: str):
    """Delete a user"""
    try:
        result = supa.delete_user(user_id)
        
        if result["ok"]:
            return JSONResponse(
                content={"ok": True},
                status_code=204,
                headers={
                    "Cache-Control": "no-store",
                    "Pragma": "no-cache"
                }
            )
        else:
            if result["error"] == "User not found":
                return JSONResponse(
                    content={"ok": False, "error": "User not found"},
                    status_code=404,
                    headers={
                        "Cache-Control": "no-store",
                        "Pragma": "no-cache"
                    }
                )
            else:
                return JSONResponse(
                    content={"ok": False, "error": result["error"]},
                    status_code=500
                )
    except Exception as e:
        print(f"Error in delete_user_api: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/test")
def test_endpoint():
    """Test endpoint to verify router is working"""
    return {"message": "Users router is working!", "timestamp": time.time()}
