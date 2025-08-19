"""
Chat router for team communication and file sharing
"""
from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Optional, Any, List
import os
import uuid
from datetime import datetime
from pathlib import Path

from app.deps import require_employee
from app.services import supa

router = APIRouter()

# Get templates from app state
def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates

@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Chat page"""
    return templates.TemplateResponse("chat.html", {
        "request": request,
        "title": "Team Chat",
        "header": "Team Chat"
    })

@router.post("/api/chat/send")
async def send_message(
    request: Request,
    current_user: Dict = Depends(require_employee),
    message: str = Form(...),
    channel_id: Optional[str] = Form(None),
    reply_to: Optional[str] = Form(None)
):
    """Send a chat message"""
    try:
        # TODO: Implement actual message storage in Supabase
        # For now, return placeholder response
        
        message_data = {
            "id": str(uuid.uuid4()),
            "user_id": current_user["id"],
            "user_name": current_user["name"],
            "message": message,
            "channel_id": channel_id or "general",
            "reply_to": reply_to,
            "timestamp": datetime.now().isoformat(),
            "type": "text"
        }
        
        # TODO: Save message to Supabase
        # result = supa.create_chat_message(message_data)
        
        return JSONResponse(content={
            "message": "Message sent successfully",
            "data": message_data
        })
        
    except Exception as e:
        print(f"Error sending message: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to send message"
        )

@router.get("/api/chat/messages")
async def get_chat_messages(
    request: Request,
    current_user: Dict = Depends(require_employee),
    channel_id: str = "general",
    limit: int = 50,
    before_id: Optional[str] = None
):
    """Get chat messages for a channel"""
    try:
        # TODO: Implement actual message retrieval from Supabase
        # For now, return placeholder data
        
        messages = [
            {
                "id": "msg-1",
                "user_id": "user-1",
                "user_name": "John Doe",
                "message": "Hello team!",
                "channel_id": channel_id,
                "timestamp": "2024-01-15T10:30:00Z",
                "type": "text"
            },
            {
                "id": "msg-2",
                "user_id": "user-2",
                "user_name": "Jane Smith",
                "message": "Hi John! How's the project going?",
                "channel_id": channel_id,
                "timestamp": "2024-01-15T10:32:00Z",
                "type": "text"
            }
        ]
        
        return JSONResponse(content={
            "messages": messages,
            "channel_id": channel_id,
            "total": len(messages),
            "has_more": False
        })
        
    except Exception as e:
        print(f"Error getting chat messages: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve chat messages"
        )

@router.get("/api/chat/messages/{message_id}")
async def get_chat_message(
    request: Request,
    message_id: str,
    current_user: Dict = Depends(require_employee)
):
    """Get a specific chat message"""
    try:
        # TODO: Implement actual message retrieval from Supabase
        # For now, return placeholder data
        
        message = {
            "id": message_id,
            "user_id": "user-1",
            "user_name": "John Doe",
            "message": "Sample message",
            "channel_id": "general",
            "timestamp": "2024-01-15T10:30:00Z",
            "type": "text"
        }
        
        return JSONResponse(content=message)
        
    except Exception as e:
        print(f"Error getting chat message: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve chat message"
        )

@router.post("/api/chat/upload")
async def upload_chat_file(
    request: Request,
    current_user: Dict = Depends(require_employee),
    file: UploadFile = File(...),
    channel_id: str = Form("general"),
    message: Optional[str] = Form("")
):
    """Upload a file to chat"""
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Create uploads directory if it doesn't exist
        upload_dir = Path("uploads/chat")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        file_extension = Path(file.filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = upload_dir / unique_filename
        
        # Save file
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # TODO: Save file metadata to Supabase
        file_data = {
            "id": str(uuid.uuid4()),
            "user_id": current_user["id"],
            "user_name": current_user["name"],
            "filename": file.filename,
            "file_path": str(file_path),
            "file_size": len(content),
            "channel_id": channel_id,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "type": "file"
        }
        
        # TODO: Create chat message for file
        # result = supa.create_chat_message(file_data)
        
        return JSONResponse(content={
            "message": "File uploaded successfully",
            "data": file_data
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error uploading file: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to upload file"
        )

@router.get("/api/chat/channels")
async def get_chat_channels(
    request: Request,
    current_user: Dict = Depends(require_employee)
):
    """Get available chat channels"""
    try:
        # TODO: Implement actual channel retrieval from Supabase
        # For now, return placeholder data
        
        channels = [
            {
                "id": "general",
                "name": "General",
                "description": "General team discussions",
                "member_count": 15,
                "last_message": "2024-01-15T10:32:00Z"
            },
            {
                "id": "project-a",
                "name": "Project A",
                "description": "Project A specific discussions",
                "member_count": 8,
                "last_message": "2024-01-15T09:15:00Z"
            },
            {
                "id": "announcements",
                "name": "Announcements",
                "description": "Important team announcements",
                "member_count": 15,
                "last_message": "2024-01-14T16:00:00Z"
            }
        ]
        
        return JSONResponse(content={
            "channels": channels,
            "total": len(channels)
        })
        
    except Exception as e:
        print(f"Error getting chat channels: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve chat channels"
        )
