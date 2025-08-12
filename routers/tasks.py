from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from models import (
    get_db,
    init_db,
    User,
    Task,
    Comment,
    ActivityLog,
    Announcement,
    RecurringTemplate,
)

# Templates (directory initialized in app.py; we re-create here if imported directly in tests)
templates = Jinja2Templates(directory="templates")

router = APIRouter()


# ---- Utilities: auth integration ----
def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    # Reuse existing app session cookie workflow if present
    # We expect an existing session middleware/cookie in the main app with `session_id` mapped to an employee id
    # Fallback: check for our own minimal session (request.session.get("user_id")) if added later
    from app import get_current_user_from_session  # type: ignore

    session_id = request.cookies.get("session_id")
    user_payload = None
    if session_id:
        try:
            user_payload = get_current_user_from_session(session_id)
        except Exception:
            user_payload = None

    if not user_payload:
        # fallback minimal session
        uid = getattr(request, "session", {}).get("user_id") if hasattr(request, "session") else None
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")
        # Minimal lookup by email for our SQL users table
        u = db.query(User).filter((User.id == uid) | (User.email == uid)).first()
        if not u:
            raise HTTPException(status_code=401, detail="Invalid session")
        return u

    # Map existing employee payload to a SQL user. If not present, create a shadow user using email/id.
    email = f"{user_payload['employee_id']}@example.local"
    u = db.query(User).filter(User.email == email).first()
    if not u:
        # Create a shadow record with role mapping
        role_map = {"owner": "ADMIN", "admin": "ADMIN", "manager": "MANAGER"}
        mapped_role = role_map.get(user_payload.get("role"), "EMPLOYEE")
        u = User(email=email, name=user_payload.get("name", user_payload["employee_id"]), password_hash="x", role=mapped_role)
        db.add(u)
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
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, u: User = Depends(current_user), db: Session = Depends(get_db)):
    today = datetime.utcnow().date()
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

    counts = {
        "due_today": db.query(Task).filter(Task.assigned_to_id == u.id, Task.due_date != None).count(),
        "in_progress": db.query(Task).filter(Task.assigned_to_id == u.id, Task.status == "IN_PROGRESS").count(),
        "review": db.query(Task).filter(Task.assigned_to_id == u.id, Task.status == "REVIEW").count(),
        "overdue": db.query(Task).filter(Task.assigned_to_id == u.id, Task.due_date != None).count(),
    }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": u,
        "my_daily": my_daily,
        "my_other": my_other,
        "counts": counts,
    })


@router.get("/team", response_class=HTMLResponse)
def team_page(request: Request, u: User = Depends(require_roles("ADMIN", "MANAGER")), db: Session = Depends(get_db)):
    team_users = db.query(User).filter(User.team == u.team).all() if u.role == "MANAGER" else db.query(User).all()
    return templates.TemplateResponse("team.html", {"request": request, "user": u, "team_users": team_users})


@router.get("/admin/tasks", response_class=HTMLResponse)
def admin_tasks_page(request: Request, u: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    templates_list = db.query(RecurringTemplate).order_by(RecurringTemplate.created_at.desc()).all()
    announcements = db.query(Announcement).order_by(Announcement.created_at.desc()).all()
    return templates.TemplateResponse("admin_tasks.html", {"request": request, "user": u, "templates": templates_list, "announcements": announcements})


# ---- APIs ----
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
    t = Task(
        title=title,
        board=board,
        status="TODO" if board == "DAILY" else "BACKLOG",
        description=description or None,
        priority=priority,
        due_date=datetime.fromisoformat(due_date) if due_date else None,
        tags=json.loads(tags) if tags else [],
        attachments=[],
        created_by_id=u.id,
        assigned_to_id=assigned_to_id,
    )
    db.add(t)
    db.add(ActivityLog(task_id=t.id, actor_id=u.id, action="CREATE", meta={"title": title}))
    db.commit()
    db.refresh(t)
    return t


@router.patch("/api/tasks/{task_id}")
def update_task(task_id: str, payload: dict, u: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.query(Task).filter(Task.id == task_id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    # Permissions: employees may update limited fields if assigned
    allowed_fields = {"title", "description", "priority", "tags", "due_date"}
    if u.role == "EMPLOYEE":
        if t.assigned_to_id != u.id:
            raise HTTPException(403, "Forbidden")
        allowed_fields = {"description", "priority", "tags", "due_date"}
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
    comments = db.query(Comment).filter(Comment.task_id == task_id).order_by(Comment.created_at.asc()).all()
    return comments


@router.post("/api/tasks/{task_id}/comments")
def add_comment(task_id: str, content: str = Form(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.query(Task).filter(Task.id == task_id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    if u.role == "EMPLOYEE" and t.assigned_to_id != u.id:
        raise HTTPException(403, "Forbidden")
    c = Comment(task_id=task_id, author_id=u.id, content=content)
    db.add(c)
    db.add(ActivityLog(task_id=task_id, actor_id=u.id, action="ADD_COMMENT", meta={"length": len(content)}))
    db.commit()
    db.refresh(c)
    return c


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


