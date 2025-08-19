from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Form, UploadFile, File, WebSocket, WebSocketDisconnect
from pathlib import Path
from uuid import uuid4
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from models import (
    get_db,
    init_db,
    User,
    Task,
    Comment,
    # CommentMention,  # Temporarily disabled for dashboard access
    Attachment,
    ActivityLog,
    Announcement,
    RecurringTemplate,
    Subtask,
)

# Templates (directory initialized in app.py; we re-create here if imported directly in tests)
templates = Jinja2Templates(directory="templates")

router = APIRouter()

# Note: NAV_ITEMS will be set by app.py when it imports this router


# ---- Utilities: auth integration ----
def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    # Reuse existing app session cookie workflow if present
    from app import get_current_user_from_session, USERS_DATABASE  # type: ignore

    session_id = request.cookies.get("session_id")
    user_payload = None
    if session_id:
        try:
            user_payload = get_current_user_from_session(session_id)
        except Exception:
            user_payload = None

    if not user_payload:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Sync user from main app to task system
    employee_id = user_payload['employee_id']
    
    # Get full user profile from main app
    main_user = USERS_DATABASE.get(employee_id)
    if not main_user:
        raise HTTPException(status_code=401, detail="User not found in main system")
    
    # Create email for task system (using actual email if available)
    email = main_user.get('email', f"{employee_id}@company.com")
    
    # CRITICAL FIX: Clean up duplicate users and ensure correct ID mapping
    # First, get all users with the same email
    all_users_with_email = db.query(User).filter(User.email == email).all()
    
    # Find the user with correct employee_id or identify duplicates to clean
    u = None
    duplicates_to_remove = []
    
    for user in all_users_with_email:
        if user.id == employee_id:
            u = user  # This is the correct user
        else:
            duplicates_to_remove.append(user)
    
    # Clean up duplicates and reassign their tasks to correct user
    for duplicate in duplicates_to_remove:
        print(f"Cleaning up duplicate user: {duplicate.id} -> {employee_id}")
        # Reassign tasks from duplicate to correct user
        db.query(Task).filter(Task.assigned_to_id == duplicate.id).update({"assigned_to_id": employee_id})
        db.query(Task).filter(Task.created_by_id == duplicate.id).update({"created_by_id": employee_id})
        db.delete(duplicate)
    
    # If no user with correct ID exists, check if we need to create one
    if not u:
        u = db.query(User).filter(User.id == employee_id).first()
    
    if not u:
        # Create a new user in task system
        role_map = {
            "owner": "ADMIN", 
            "admin": "ADMIN", 
            "manager": "MANAGER",
            "packer": "EMPLOYEE",
            "employee": "EMPLOYEE"
        }
        mapped_role = role_map.get(user_payload.get("role", "").lower(), "EMPLOYEE")
        
        u = User(
            id=employee_id,  # Use employee_id as primary key for consistency
            email=email, 
            name=user_payload.get("name", employee_id), 
            password_hash="synced_from_main_app", 
            role=mapped_role,
            team=main_user.get('team', None)
        )
        db.add(u)
        db.commit()
        db.refresh(u)
    else:
        # Update existing user to ensure sync
        role_map = {
            "owner": "ADMIN", 
            "admin": "ADMIN", 
            "manager": "MANAGER",
            "packer": "EMPLOYEE",
            "employee": "EMPLOYEE"
        }
        mapped_role = role_map.get(user_payload.get("role", "").lower(), "EMPLOYEE")
        
        # Update user info if changed
        updated = False
        if u.name != user_payload.get("name", employee_id):
            u.name = user_payload.get("name", employee_id)
            updated = True
        if u.role != mapped_role:
            u.role = mapped_role
            updated = True
        if u.email != email:
            u.email = email
            updated = True
        if u.team != main_user.get('team', None):
            u.team = main_user.get('team', None)
            updated = True
            
        if updated:
            db.commit()
            db.refresh(u)
    
    return u


def require_roles(*roles: str):
    def dep(u: User = Depends(current_user)) -> User:
        if roles and u.role not in roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return u
    return dep


# ---- Pages ----
@router.get("/task", response_class=HTMLResponse)
def dashboard(request: Request, u: User = Depends(current_user), db: Session = Depends(get_db)):
    today = datetime.utcnow().date()
    
    # Debug: Print current user info
    print(f"Dashboard - Current user: {u.id} ({u.name}) - Role: {u.role}")
    
    # Get tasks assigned to current user
    my_daily = (
        db.query(Task)
        .filter(Task.assigned_to_id == u.id, Task.board == "DAILY")
        .order_by(Task.priority.desc(), Task.updated_at.desc())
        .all()
    )
    my_other = (
        db.query(Task)
        .filter(Task.assigned_to_id == u.id, Task.board == "OTHER")
        .order_by(Task.priority.desc(), Task.updated_at.desc())
        .all()
    )
    
    # Debug: Print task counts
    all_tasks = db.query(Task).all()
    print(f"Total tasks in DB: {len(all_tasks)}")
    print(f"Tasks assigned to {u.id}: Daily={len(my_daily)}, Other={len(my_other)}")
    
    # Print all task assignments for debugging
    for task in all_tasks:
        print(f"Task '{task.title}' assigned to: {task.assigned_to_id} (created by: {task.created_by_id})")

    counts = {
        "due_today": db.query(Task).filter(Task.assigned_to_id == u.id, Task.due_date != None).count(),
        "in_progress": db.query(Task).filter(Task.assigned_to_id == u.id, Task.status == "IN_PROGRESS").count(),
        "review": db.query(Task).filter(Task.assigned_to_id == u.id, Task.status == "REVIEW").count(),
        "overdue": db.query(Task).filter(Task.assigned_to_id == u.id, Task.due_date != None).count(),
    }

    # Users for filters/views and modal assignee picker
    all_users = db.query(User).order_by(User.name).all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": u,
        "my_daily": my_daily,
        "my_other": my_other,
        "counts": counts,
        "now": datetime.utcnow(),  # Add current time for template
        "all_users": all_users,
    })


# ---- WebSocket: real-time notifications ----
class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self.user_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        self.user_connections[user_id] = websocket
        print(f"🔗 User {user_id} connected to WebSocket")

    def disconnect(self, websocket: WebSocket, user_id: Optional[str] = None) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if user_id and user_id in self.user_connections:
            del self.user_connections[user_id]
        print(f"📡 User {user_id} disconnected from WebSocket")

    async def send_personal_message(self, message: dict, user_id: str) -> None:
        ws = self.user_connections.get(user_id)
        if not ws:
            return
        try:
            await ws.send_json(message)
        except Exception:
            self.disconnect(ws, user_id)

    async def broadcast(self, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self.active_connections):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self.active_connections:
                self.active_connections.remove(ws)


manager = ConnectionManager()


@router.websocket("/ws/notifications")
async def websocket_endpoint(websocket: WebSocket):
    # Authenticate via session cookie like HTTP routes
    try:
        from app import get_current_user_from_session  # type: ignore
        session_id = websocket.cookies.get("session_id") if websocket.cookies else None
        if not session_id:
            # Try query param fallback ?session_id=
            session_id = websocket.query_params.get("session_id")
        if not session_id:
            await websocket.close(code=4001)
            return
        user_payload = get_current_user_from_session(session_id)
        if not user_payload:
            await websocket.close(code=4003)
            return
        user_id = user_payload["employee_id"]
        await manager.connect(websocket, user_id)

        await websocket.send_json({"type": "CONNECTED", "user_id": user_id})

        try:
            while True:
                _ = await websocket.receive_text()  # keepalive/echo ignored
        except WebSocketDisconnect:
            manager.disconnect(websocket, user_id)
        except Exception:
            manager.disconnect(websocket, user_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.close(code=4000)
        except Exception:
            pass


async def notify_task_update(task_id: str, message: str, affected_users: Optional[List[str]] = None) -> None:
    payload = {"type": "TASK_UPDATED", "task_id": task_id, "message": message, "ts": datetime.utcnow().isoformat()}
    if affected_users:
        for uid in affected_users:
            if uid:
                await manager.send_personal_message(payload, uid)
    else:
        await manager.broadcast(payload)


@router.get("/team", response_class=HTMLResponse)
def team_page(request: Request, u: User = Depends(require_roles("ADMIN", "MANAGER")), db: Session = Depends(get_db)):
    # Auto-sync users before showing team page to ensure all users are available
    try:
        from app import USERS_DATABASE, USERS  # type: ignore
        
        # Quick sync of all active users to task system
        role_map = {
            "owner": "ADMIN", 
            "admin": "ADMIN", 
            "manager": "MANAGER",
            "packer": "EMPLOYEE",
            "employee": "EMPLOYEE"
        }
        
        for employee_id, main_user in USERS_DATABASE.items():
            if main_user.get('status') != 'active':
                continue
                
            # Check if user exists in task system
            task_user = db.query(User).filter(User.id == employee_id).first()
            if not task_user:
                # Create user in task system
                mapped_role = role_map.get(main_user.get("role", "").lower(), "EMPLOYEE")
                email = main_user.get('email', f"{employee_id}@company.com")
                
                task_user = User(
                    id=employee_id,
                    email=email,
                    name=main_user.get("name", employee_id),
                    password_hash="synced_from_main_app",
                    role=mapped_role,
                    team=main_user.get('team', None)
                )
                db.add(task_user)
        
        db.commit()
    except Exception as e:
        print(f"Warning: Failed to auto-sync users: {e}")
    
    # Get team users based on role
    if u.role == "MANAGER":
        team_users = db.query(User).filter(User.team == u.team).all()
    else:
        # For ADMIN, show all active users
        team_users = db.query(User).all()
    
    return templates.TemplateResponse("team.html", {"request": request, "user": u, "team_users": team_users})


@router.get("/admin/tasks", response_class=HTMLResponse)
def admin_tasks_page(request: Request, u: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    # Auto-sync users to ensure all users are available for task assignment
    try:
        from app import USERS_DATABASE, USERS  # type: ignore
        
        role_map = {
            "owner": "ADMIN", 
            "admin": "ADMIN", 
            "manager": "MANAGER",
            "packer": "EMPLOYEE",
            "employee": "EMPLOYEE"
        }
        
        for employee_id, main_user in USERS_DATABASE.items():
            if main_user.get('status') != 'active':
                continue
                
            task_user = db.query(User).filter(User.id == employee_id).first()
            if not task_user:
                mapped_role = role_map.get(main_user.get("role", "").lower(), "EMPLOYEE")
                email = main_user.get('email', f"{employee_id}@company.com")
                
                task_user = User(
                    id=employee_id,
                    email=email,
                    name=main_user.get("name", employee_id),
                    password_hash="synced_from_main_app",
                    role=mapped_role,
                    team=main_user.get('team', None)
                )
                db.add(task_user)
        
        db.commit()
    except Exception as e:
        print(f"Warning: Failed to auto-sync users in admin: {e}")
    
    templates_list = db.query(RecurringTemplate).order_by(RecurringTemplate.created_at.desc()).all()
    announcements = db.query(Announcement).order_by(Announcement.created_at.desc()).all()
    all_users = db.query(User).order_by(User.name).all()
    
    return templates.TemplateResponse("admin_tasks.html", {
        "request": request, 
        "user": u, 
        "templates": templates_list, 
        "announcements": announcements,
        "all_users": all_users
    })


# ---- APIs ----
@router.get("/api/tasks/{task_id}")
def get_task(task_id: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    """Get a single task by ID."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check if user has access to this task
    # Allow access if: user is assignee, creator, or admin/manager
    has_access = False
    if task.assigned_to_id == u.id or task.created_by_id == u.id:
        has_access = True
    elif u.role in ["ADMIN", "MANAGER"]:
        has_access = True
        if u.role == "MANAGER":
            # Manager can see tasks assigned to their team members
            if task.assigned_to and task.assigned_to.team == u.team:
                has_access = True
    
    if not has_access:
        raise HTTPException(status_code=403, detail="Not authorized to view this task")
    
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "board": task.board,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "tags": task.tags or [],
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "assigned_to": {
            "id": task.assigned_to.id,
            "name": task.assigned_to.name,
            "email": task.assigned_to.email
        } if task.assigned_to else None,
        "created_by": {
            "id": task.created_by.id,
            "name": task.created_by.name,
            "email": task.created_by.email
        } if task.created_by else None
    }


@router.get("/api/tasks")
def list_tasks(scope: str = "my", board: Optional[str] = None, status: Optional[str] = None, q: str = "", u: User = Depends(current_user), db: Session = Depends(get_db)):
    query = db.query(Task)
    if scope == "my":
        query = query.filter(Task.assigned_to_id == u.id)
    elif scope == "team":
        if u.role not in ("ADMIN", "MANAGER"):
            raise HTTPException(status_code=403, detail="Forbidden")
        if u.role == "MANAGER":
            user_ids = [x.id for x in db.query(User).filter(User.team == u.team).all()]
            query = query.filter(Task.assigned_to_id.in_(user_ids))
    if board:
        query = query.filter(Task.board == board)
    if status:
        query = query.filter(Task.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(Task.title.ilike(like))
    tasks = query.order_by(Task.updated_at.desc()).all()
    return tasks


@router.post("/api/tasks")
def create_task(
    title: str = Form(...),
    board: str = Form(...),
    assigned_to_id: str = Form(...),
    description: str = Form(""),
    priority: str = Form("MEDIUM"),
    due_date: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    u: User = Depends(require_roles("ADMIN", "MANAGER")),
    db: Session = Depends(get_db),
):
    if board not in ("DAILY", "OTHER"):
        raise HTTPException(400, "Invalid board")
    
    # Debug: Print task creation details
    print(f"Creating task: '{title}'")
    print(f"Created by: {u.id} ({u.name})")
    print(f"Assigned to: {assigned_to_id}")
    print(f"Board: {board}")
    
    # Verify the assigned user exists
    assigned_user = db.query(User).filter(User.id == assigned_to_id).first()
    if not assigned_user:
        print(f"ERROR: User {assigned_to_id} not found in task system!")
        raise HTTPException(400, f"User {assigned_to_id} not found")
    
    print(f"Assigned user found: {assigned_user.name} ({assigned_user.id})")
    
    t = Task(
        title=title,
        board=board,
        status="TODO" if board == "DAILY" else "BACKLOG",
        description=description or None,
        priority=priority,
        due_date=datetime.fromisoformat(due_date) if due_date else None,
        tags=[tag.strip() for tag in tags.split(',')] if tags else [],
        attachments=[],
        created_by_id=u.id,
        assigned_to_id=assigned_to_id,
    )
    db.add(t)
    db.add(ActivityLog(task_id=t.id, actor_id=u.id, action="CREATE", meta={"title": title}))
    db.commit()
    db.refresh(t)
    
    print(f"Task created successfully with ID: {t.id}")
    return t


@router.patch("/api/tasks/{task_id}")
def update_task(task_id: str, payload: dict, u: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.query(Task).filter(Task.id == task_id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    # Permissions: employees may update limited fields if assigned; admin/manager may also reassign
    allowed_fields = {"title", "description", "priority", "tags", "due_date"}
    if u.role == "EMPLOYEE":
        if t.assigned_to_id != u.id:
            raise HTTPException(403, "Forbidden")
        allowed_fields = {"description", "priority", "tags", "due_date"}
    else:
        allowed_fields.add("assigned_to_id")
    for k, v in payload.items():
        if k in allowed_fields:
            if k == "due_date" and v:
                setattr(t, k, datetime.fromisoformat(v))
            else:
                setattr(t, k, v)
    t.updated_at = datetime.utcnow()
    db.add(ActivityLog(task_id=t.id, actor_id=u.id, action="UPDATE", meta=payload))
    db.commit()
    db.refresh(t)
    return t


@router.delete("/api/tasks/{task_id}")
def delete_task(
    task_id: str,
    u: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    """Delete a task."""
    t = db.query(Task).filter(Task.id == task_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check permissions - only creator, assignee, or admin/manager can delete
    if t.created_by_id != u.id and t.assigned_to_id != u.id and u.role not in ["ADMIN", "MANAGER"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete this task")
    
    # Delete related records first
    db.query(Comment).filter(Comment.task_id == task_id).delete()
    db.query(ActivityLog).filter(ActivityLog.task_id == task_id).delete()
    
    # Delete the task
    db.delete(t)
    db.commit()
    
    return {"message": "Task deleted successfully"}


@router.get("/api/tasks/{task_id}/attachments")
def get_task_attachments(
    task_id: str,
    u: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    """Get all attachments for a task (simplified version)."""
    
    # Verify task exists and user has access
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check access
    if (task.assigned_to_id != u.id and task.created_by_id != u.id and 
        u.role not in ["ADMIN", "MANAGER"]):
        raise HTTPException(status_code=403, detail="Not authorized to view this task")
    
    attachments = db.query(Attachment).filter(Attachment.task_id == task_id).order_by(Attachment.created_at.desc()).all()
    return [
        {
            "id": a.id,
            "filename": a.original_filename,
            "size": a.file_size,
            "mime_type": a.mime_type,
            "is_image": a.is_image,
            "uploaded_by": a.uploaded_by.name if a.uploaded_by else "Unknown",
            "created_at": a.created_at.isoformat(),
        }
        for a in attachments
    ]


UPLOAD_DIR = Path("uploads/attachments")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {
    'txt','pdf','png','jpg','jpeg','gif','doc','docx','xls','xlsx','ppt','pptx','zip','rar','7z','mp4','avi','mov','mp3','wav','csv','json','xml'
}

def _ext(name: str) -> str:
    return name.rsplit('.', 1)[-1].lower() if '.' in name else ''


@router.post("/api/tasks/{task_id}/upload")
async def upload_file(task_id: str, file: UploadFile = File(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if (task.assigned_to_id != u.id and task.created_by_id != u.id and u.role not in ["ADMIN", "MANAGER"]):
        raise HTTPException(403, "Forbidden")
    if not file or not file.filename:
        raise HTTPException(400, "No file selected")
    if _ext(file.filename) not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "File type not allowed")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large")
    unique = f"{uuid4()}.{_ext(file.filename)}"
    path = UPLOAD_DIR / unique
    with open(path, 'wb') as f:
        f.write(content)
    att = Attachment(
        task_id=task_id,
        uploaded_by_id=u.id,
        filename=unique,
        original_filename=file.filename,
        file_path=str(path),
        file_size=len(content),
        mime_type=file.content_type or "application/octet-stream",
        is_image=_ext(file.filename) in {"png","jpg","jpeg","gif","webp","svg"}
    )
    db.add(att)
    db.add(ActivityLog(task_id=task_id, actor_id=u.id, action="ADD_ATTACHMENT", meta={"filename": file.filename}))
    db.commit()
    return {"id": att.id, "filename": att.original_filename, "size": att.file_size, "mime_type": att.mime_type, "uploaded_by": u.name}


@router.get("/api/attachments/{attachment_id}/download")
def download_attachment(attachment_id: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att:
        raise HTTPException(404, "Attachment not found")
    task = db.query(Task).filter(Task.id == att.task_id).first()
    if (task.assigned_to_id != u.id and task.created_by_id != u.id and u.role not in ["ADMIN","MANAGER"]):
        raise HTTPException(403, "Forbidden")
    p = Path(att.file_path)
    if not p.exists():
        raise HTTPException(404, "File missing")
    return FileResponse(path=str(p), filename=att.original_filename, media_type=att.mime_type)


@router.delete("/api/attachments/{attachment_id}")
def delete_attachment(attachment_id: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att:
        raise HTTPException(404, "Attachment not found")
    task = db.query(Task).filter(Task.id == att.task_id).first()
    if (att.uploaded_by_id != u.id and task.created_by_id != u.id and u.role not in ["ADMIN","MANAGER"]):
        raise HTTPException(403, "Forbidden")
    p = Path(att.file_path)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass
    db.delete(att)
    db.add(ActivityLog(task_id=task.id, actor_id=u.id, action="DELETE_ATTACHMENT", meta={"filename": att.original_filename}))
    db.commit()
    return {"message": "Attachment deleted"}


@router.get("/api/tasks/{task_id}/comments")
def get_task_comments(
    task_id: str,
    u: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    """Get all comments for a task."""
    
    # Verify task exists and user has access
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if (task.assigned_to_id != u.id and task.created_by_id != u.id and 
        u.role not in ["ADMIN", "MANAGER"]):
        raise HTTPException(status_code=403, detail="Not authorized to view this task")
    
    comments = db.query(Comment).filter(Comment.task_id == task_id).order_by(Comment.created_at.asc()).all()
    
    return [
        {
            "id": comment.id,
            "content": comment.content,
            "author": comment.author.name if comment.author else "Unknown",
            "author_id": comment.author_id,
            "created_at": comment.created_at.isoformat(),
            "can_delete": comment.author_id == u.id or u.role in ["ADMIN", "MANAGER"]
        }
        for comment in comments
    ]


# ---- Subtasks ----
@router.get("/api/tasks/{task_id}/subtasks")
def list_subtasks(task_id: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.query(Task).filter(Task.id == task_id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    if (t.assigned_to_id != u.id and t.created_by_id != u.id and u.role not in ["ADMIN", "MANAGER"]):
        raise HTTPException(403, "Forbidden")
    subs = db.query(Subtask).filter(Subtask.task_id == task_id).order_by(Subtask.created_at.asc()).all()
    return [{"id": s.id, "title": s.title, "is_completed": s.is_completed} for s in subs]


@router.post("/api/tasks/{task_id}/subtasks")
def create_subtask(task_id: str, title: str = Form(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.query(Task).filter(Task.id == task_id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    if (t.assigned_to_id != u.id and t.created_by_id != u.id and u.role not in ["ADMIN", "MANAGER"]):
        raise HTTPException(403, "Forbidden")
    s = Subtask(task_id=task_id, title=title.strip())
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "title": s.title, "is_completed": s.is_completed}


@router.patch("/api/subtasks/{subtask_id}")
def update_subtask(subtask_id: str, is_completed: Optional[bool] = Form(None), title: Optional[str] = Form(None), u: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.query(Subtask).filter(Subtask.id == subtask_id).first()
    if not s:
        raise HTTPException(404, "Subtask not found")
    t = db.query(Task).filter(Task.id == s.task_id).first()
    if (t.assigned_to_id != u.id and t.created_by_id != u.id and u.role not in ["ADMIN","MANAGER"]):
        raise HTTPException(403, "Forbidden")
    if is_completed is not None:
        s.is_completed = bool(is_completed)
    if title is not None and title.strip():
        s.title = title.strip()
    db.commit()
    return {"id": s.id, "title": s.title, "is_completed": s.is_completed}


@router.delete("/api/subtasks/{subtask_id}")
def delete_subtask(subtask_id: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.query(Subtask).filter(Subtask.id == subtask_id).first()
    if not s:
        raise HTTPException(404, "Subtask not found")
    t = db.query(Task).filter(Task.id == s.task_id).first()
    if (t.assigned_to_id != u.id and t.created_by_id != u.id and u.role not in ["ADMIN","MANAGER"]):
        raise HTTPException(403, "Forbidden")
    db.delete(s)
    db.commit()
    return {"message": "Subtask deleted"}


# ---- Users (for assignee picker) ----
@router.get("/api/users")
def list_users(u: User = Depends(current_user), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.name).all()
    return [{"id": usr.id, "name": usr.name, "team": usr.team, "role": usr.role} for usr in users]


@router.patch("/api/tasks/{task_id}/move")
def move_task(task_id: str, payload: dict, u: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.query(Task).filter(Task.id == task_id).first()
    if not t:
        raise HTTPException(404, "Task not found")

    to_status = payload.get("to_status")
    to_board = payload.get("to_board")

    if to_board and to_board not in ("DAILY", "OTHER"):
        raise HTTPException(422, "Invalid board")
    if t.board == "DAILY":
        allowed = {"TODO", "IN_PROGRESS", "DONE"}
    else:
        allowed = {"BACKLOG", "IN_PROGRESS", "REVIEW", "DONE"}
    if to_status not in allowed:
        raise HTTPException(422, "Invalid status for board")

    tags = t.tags or []
    if to_status == "DONE" and ("requireProof" in tags) and not t.proof_url:
        raise HTTPException(422, detail="Proof required to mark as DONE")

    if to_board and to_board != t.board:
        t.board = to_board
    t.status = to_status
    t.updated_at = datetime.utcnow()
    db.add(ActivityLog(task_id=t.id, actor_id=u.id, action="UPDATE_STATUS", meta={"to_status": to_status, "to_board": to_board}))
    db.commit()
    db.refresh(t)
    return t


@router.post("/api/debug/clear-tasks")
def clear_all_tasks(u: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    """Clear all tasks for debugging."""
    db.query(Task).delete()
    db.query(ActivityLog).delete()
    db.commit()
    return {"message": "All tasks cleared"}


@router.post("/api/debug/fix-user-assignments")
def fix_user_assignments(u: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    """Fix task assignments by cleaning up duplicate users."""
    from app import USERS_DATABASE  # type: ignore
    
    fixed_count = 0
    
    # Go through all active users in main system
    for employee_id, main_user in USERS_DATABASE.items():
        if main_user.get('status') != 'active':
            continue
            
        email = main_user.get('email', f"{employee_id}@company.com")
        
        # Find all users with this email in task system
        users_with_email = db.query(User).filter(User.email == email).all()
        
        if len(users_with_email) > 1:
            # Multiple users found - clean up
            correct_user = None
            duplicates = []
            
            for user in users_with_email:
                if user.id == employee_id:
                    correct_user = user
                else:
                    duplicates.append(user)
            
            # If no user with correct ID, use the first one and update its ID
            if not correct_user and duplicates:
                correct_user = duplicates[0]
                old_id = correct_user.id
                correct_user.id = employee_id
                
                # Update tasks
                db.query(Task).filter(Task.assigned_to_id == old_id).update({"assigned_to_id": employee_id})
                db.query(Task).filter(Task.created_by_id == old_id).update({"created_by_id": employee_id})
                
                duplicates = duplicates[1:]  # Remove the one we're keeping
                fixed_count += 1
            
            # Remove remaining duplicates
            for duplicate in duplicates:
                # Reassign tasks to correct user
                task_count = db.query(Task).filter(Task.assigned_to_id == duplicate.id).count()
                if task_count > 0:
                    db.query(Task).filter(Task.assigned_to_id == duplicate.id).update({"assigned_to_id": employee_id})
                    fixed_count += task_count
                
                db.query(Task).filter(Task.created_by_id == duplicate.id).update({"created_by_id": employee_id})
                db.delete(duplicate)
    
    db.commit()
    return {"message": f"Fixed {fixed_count} task assignments and cleaned up duplicate users"}


@router.get("/api/debug/users")
def debug_users(u: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    """Debug endpoint to see what users exist in task system."""
    from app import USERS_DATABASE  # type: ignore
    
    task_users = db.query(User).all()
    main_users = list(USERS_DATABASE.keys())
    
    # Get all tasks and their assignments
    all_tasks = db.query(Task).all()
    
    return {
        "current_user": {"id": u.id, "name": u.name, "email": u.email, "role": u.role},
        "task_system_users": [{"id": user.id, "name": user.name, "email": user.email, "role": user.role, "team": user.team} for user in task_users],
        "main_system_users": main_users,
        "task_count": len(task_users),
        "main_count": len([user for user in USERS_DATABASE.values() if user.get('status') == 'active']),
        "all_tasks": [{"id": task.id, "title": task.title, "assigned_to_id": task.assigned_to_id, "created_by_id": task.created_by_id, "board": task.board} for task in all_tasks],
        "tasks_for_current_user": len([task for task in all_tasks if task.assigned_to_id == u.id])
    }


@router.post("/api/sync-users")
def sync_users_from_main_app(u: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    """Sync all users from main app to task system."""
    from app import USERS_DATABASE, USERS  # type: ignore
    
    synced_count = 0
    created_count = 0
    updated_count = 0
    
    role_map = {
        "owner": "ADMIN", 
        "admin": "ADMIN", 
        "manager": "MANAGER",
        "packer": "EMPLOYEE",
        "employee": "EMPLOYEE"
    }
    
    for employee_id, main_user in USERS_DATABASE.items():
        # Skip inactive users
        if main_user.get('status') != 'active':
            continue
            
        # Get auth info
        auth_user = USERS.get(employee_id, {})
        
        # Create email
        email = main_user.get('email', f"{employee_id}@company.com")
        
        # Find or create user in task system
        task_user = db.query(User).filter(User.id == employee_id).first()
        
        if not task_user:
            # Create new user
            mapped_role = role_map.get(main_user.get("role", "").lower(), "EMPLOYEE")
            
            task_user = User(
                id=employee_id,
                email=email,
                name=main_user.get("name", employee_id),
                password_hash="synced_from_main_app",
                role=mapped_role,
                team=main_user.get('team', None)
            )
            db.add(task_user)
            created_count += 1
        else:
            # Update existing user
            mapped_role = role_map.get(main_user.get("role", "").lower(), "EMPLOYEE")
            
            updated = False
            if task_user.name != main_user.get("name", employee_id):
                task_user.name = main_user.get("name", employee_id)
                updated = True
            if task_user.role != mapped_role:
                task_user.role = mapped_role
                updated = True
            if task_user.email != email:
                task_user.email = email
                updated = True
            if task_user.team != main_user.get('team', None):
                task_user.team = main_user.get('team', None)
                updated = True
                
            if updated:
                updated_count += 1
        
        synced_count += 1
    
    db.commit()
    
    return {
        "message": "User sync completed",
        "synced": synced_count,
        "created": created_count,
        "updated": updated_count
    }


@router.delete("/api/tasks/{task_id}")
def delete_task(task_id: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.query(Task).filter(Task.id == task_id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    if u.role not in ("ADMIN", "MANAGER") and t.created_by_id != u.id:
        raise HTTPException(403, "Forbidden")
    db.query(Comment).filter(Comment.task_id == t.id).delete()
    db.query(ActivityLog).filter(ActivityLog.task_id == t.id).delete()
    db.delete(t)
    db.commit()
    return {"success": True}


@router.get("/api/tasks/{task_id}/comments")
def list_comments(task_id: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.query(Task).filter(Task.id == task_id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    if u.role == "EMPLOYEE" and t.assigned_to_id != u.id:
        raise HTTPException(403, "Forbidden")
    
    comments = db.query(Comment).filter(Comment.task_id == task_id).order_by(Comment.created_at.desc()).limit(50).all()
    
    result = []
    for comment in comments:
        # mentions = db.query(CommentMention).filter(CommentMention.comment_id == comment.id).all()  # Temporarily disabled
        result.append({
            "id": comment.id,
            "task_id": comment.task_id,
            "author_id": comment.author_id,
            "author_name": comment.author.name,
            "text": comment.content,
            "mentions": [],  # [m.mentioned_user_id for m in mentions],  # Temporarily disabled
            "created_at": comment.created_at.isoformat(),
            "can_delete": comment.author_id == u.id or u.role in ["ADMIN", "MANAGER"]
        })
    
    return result


@router.post("/api/tasks/{task_id}/comments")
def add_comment(task_id: str, content: str = Form(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.query(Task).filter(Task.id == task_id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    if u.role == "EMPLOYEE" and t.assigned_to_id != u.id:
        raise HTTPException(403, "Forbidden")
    # Create comment
    c = Comment(task_id=task_id, author_id=u.id, content=content)
    db.add(c)
    db.flush()  # Get comment ID
    
    # Extract mentions
    import re
    mention_pattern = r'@(\w+)'
    mentioned_usernames = re.findall(mention_pattern, content)
    mentioned_user_ids = []
    
    for username in mentioned_usernames:
        mentioned_user = db.query(User).filter(User.id == username).first()
        if mentioned_user:
            # mention = CommentMention(comment_id=c.id, mentioned_user_id=mentioned_user.id)  # Temporarily disabled
            # db.add(mention)  # Temporarily disabled
            mentioned_user_ids.append(mentioned_user.id)
    
    db.add(ActivityLog(task_id=task_id, actor_id=u.id, action="ADD_COMMENT", meta={"length": len(content)}))
    db.commit()
    
    return {
        "id": c.id,
        "task_id": c.task_id,
        "author_id": c.author_id,
        "author_name": u.name,
        "text": c.content,
        "mentions": mentioned_user_ids,
        "created_at": c.created_at.isoformat()
    }


@router.get("/api/announcements")
def get_announcements(db: Session = Depends(get_db)):
    return db.query(Announcement).order_by(Announcement.created_at.desc()).all()


@router.post("/api/announcements")
def create_announcement(title: str = Form(...), body: str = Form(""), u: User = Depends(require_roles("ADMIN", "MANAGER")), db: Session = Depends(get_db)):
    a = Announcement(title=title, body=body, created_by_id=u.id)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def spawn_recurring_tasks(now_utc: Optional[datetime], db: Session, actor: Optional[User] = None):
    now = now_utc or datetime.utcnow()
    templates = db.query(RecurringTemplate).all()
    created = 0
    for tpl in templates:
        if tpl.freq == "DAILY":
            pass_check = now.hour == tpl.hour and now.minute >= tpl.minute
        elif tpl.freq == "WEEKLY":
            weekday = now.isoweekday()  # 1..7
            pass_check = (weekday == (tpl.weekday or 1)) and (now.hour == tpl.hour and now.minute >= tpl.minute)
        else:
            pass_check = False
        if not pass_check:
            continue

        # idempotency: same title + assignee + date
        start = datetime(now.year, now.month, now.day)
        exists = (
            db.query(Task)
            .filter(Task.title == tpl.title, Task.assigned_to_id == tpl.assigned_to_id, Task.created_at >= start)
            .first()
        )
        if exists:
            continue

        t = Task(
            title=tpl.title,
            description=tpl.description,
            board=tpl.board,
            status=tpl.default_status or ("TODO" if tpl.board == "DAILY" else "BACKLOG"),
            priority=tpl.priority or "MEDIUM",
            is_recurring=True,
            tags=tpl.tags or [],
            created_by_id=(actor.id if actor else tpl.created_by_id),
            assigned_to_id=tpl.assigned_to_id,
        )
        db.add(t)
        db.add(ActivityLog(task_id=t.id, actor_id=(actor.id if actor else tpl.created_by_id), action="CREATE", meta={"recurring": True}))
        created += 1
    if created:
        db.commit()
    return {"spawned": created}


@router.post("/cron/run-recurring")
def run_recurring(u: User = Depends(require_roles("ADMIN", "MANAGER")), db: Session = Depends(get_db)):
    return spawn_recurring_tasks(None, db, actor=u)


