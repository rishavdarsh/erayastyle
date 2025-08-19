"""
Chat channels router for team chat functionality
"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Optional, Any

router = APIRouter()

# Get templates from app state
def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates

@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Team chat page"""
    return templates.TemplateResponse("chat.html", {
        "request": request,
        "title": "Team Chat",
        "header": "Team Chat"
    })

@router.get("/api/chat/channels")
async def list_channels_api(request: Request):
    """List chat channels"""
    try:
        # TODO: Implement channel listing logic
        result = {
            "items": [],
            "total": 0
        }
        
        return JSONResponse(
            content=result,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    except Exception as e:
        print(f"Error in list_channels_api: {e}")
        raise HTTPException(status_code=500, detail=str(e))
