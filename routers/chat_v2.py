from datetime import datetime
from typing import Optional, List
import os
import json

from fastapi import APIRouter, HTTPException, Depends, Form, Query, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from models import get_db, User
from chat_models import ChatChannel, ChatMessage, DirectConversation, MessageRead

router = APIRouter()


@router.get("/api/chat/channels")
def list_channels(db: Session = Depends(get_db)):
    channels = db.query(ChatChannel).order_by(ChatChannel.name).all()
    return {"channels": [{"id": c.id, "name": c.name, "is_private": c.is_private} for c in channels]}


@router.get("/api/chat/channel/{name}")
def get_channel_messages(name: str, limit: int = Query(50, ge=1, le=200), before: Optional[str] = None, db: Session = Depends(get_db)):
    channel = db.query(ChatChannel).filter(ChatChannel.name == name).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    q = db.query(ChatMessage).filter(ChatMessage.channel_id == channel.id)
    if before:
        # before is message_id; fetch messages older than that message's created_at
        anchor = db.query(ChatMessage).filter(ChatMessage.id == before).first()
        if anchor:
            q = q.filter(ChatMessage.created_at < anchor.created_at)

    messages = (
        q.order_by(ChatMessage.created_at.desc())
         .limit(limit)
         .all()
    )

    items = []
    for m in reversed(messages):
        sender = db.query(User).filter(User.id == m.sender_id).first()
        items.append({
            "id": m.id,
            "employee_id": m.sender_id,
            "employee_name": sender.name if sender else "Unknown",
            "message": m.content,
            "timestamp": m.created_at.isoformat(),
            "edited": m.edited,
            "edited_at": m.edited_at.isoformat() if m.edited_at else None,
            "links": m.links,
            "attachments": m.attachments,
            "reactions": m.reactions,
        })

    next_before = messages[-1].id if messages else None
    return {"channel": name, "messages": items, "next_before": next_before}


@router.post("/api/chat/channel/send")
def send_channel_message(
    channel: str = Form(...),
    employee_id: str = Form(...),
    message: str = Form(""),
    attachments: Optional[str] = Form(None),  # JSON string
    db: Session = Depends(get_db),
):
    if not message.strip():
        raise HTTPException(status_code=400, detail="Message is required")

    user = db.query(User).filter(User.id == employee_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid user")

    ch = db.query(ChatChannel).filter(ChatChannel.name == channel).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    atts = None
    if attachments:
        try:
            atts = json.loads(attachments)
        except Exception:
            atts = None

    msg = ChatMessage(
        channel_id=ch.id,
        sender_id=user.id,
        content=message.strip(),
        attachments=atts,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return JSONResponse(content={
        "status": "success",
        "message_id": msg.id,
        "data": {
            "id": msg.id,
            "employee_id": user.id,
            "employee_name": user.name,
            "message": msg.content,
            "timestamp": msg.created_at.isoformat(),
            "attachments": msg.attachments,
        }
    })


@router.post("/api/chat/message/react")
def react_message(message_id: str = Form(...), employee_id: str = Form(...), emoji: str = Form(...), db: Session = Depends(get_db)):
    m = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Message not found")
    reactions = m.reactions or {}
    users = reactions.get(emoji, [])
    if employee_id in users:
        users.remove(employee_id)
    else:
        users.append(employee_id)
    if users:
        reactions[emoji] = users
    elif emoji in reactions:
        del reactions[emoji]
    m.reactions = reactions
    db.add(m)
    db.commit()
    return {"ok": True, "reactions": reactions}


@router.post("/api/chat/thread/reply")
def thread_reply(parent_message_id: str = Form(...), employee_id: str = Form(...), message: str = Form(...), db: Session = Depends(get_db)):
    if not message.strip():
        raise HTTPException(status_code=400, detail="Message required")
    parent = db.query(ChatMessage).filter(ChatMessage.id == parent_message_id).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent not found")
    user = db.query(User).filter(User.id == employee_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid user")
    reply = ChatMessage(
        parent_message_id=parent_message_id,
        sender_id=employee_id,
        content=message.strip(),
        channel_id=parent.channel_id,
        conversation_id=parent.conversation_id,
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return {"ok": True, "reply": {
        "id": reply.id,
        "parent_id": parent_message_id,
        "employee_id": employee_id,
        "employee_name": user.name,
        "message": reply.content,
        "timestamp": reply.created_at.isoformat()
    }}


@router.get("/api/chat/thread/{parent_message_id}")
def get_thread(parent_message_id: str, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    q = (db.query(ChatMessage)
            .filter(ChatMessage.parent_message_id == parent_message_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit))
    rows = q.all()
    items = []
    for m in rows:
        sender = db.query(User).filter(User.id == m.sender_id).first()
        items.append({
            "id": m.id,
            "employee_id": m.sender_id,
            "employee_name": sender.name if sender else "Unknown",
            "message": m.content,
            "timestamp": m.created_at.isoformat(),
        })
    return {"replies": items}


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


@router.post("/api/chat/dm/send")
def dm_send(
    to_employee_id: str = Form(...),
    from_employee_id: str = Form(...),
    message: str = Form(""),
    attachments: Optional[str] = Form(None),  # JSON string
    db: Session = Depends(get_db),
):
    if not message.strip():
        raise HTTPException(status_code=400, detail="Message required")
    u_from = db.query(User).filter(User.id == from_employee_id).first()
    u_to = db.query(User).filter(User.id == to_employee_id).first()
    if not u_from or not u_to:
        raise HTTPException(status_code=400, detail="Invalid user")
    a, b = _pair(from_employee_id, to_employee_id)
    conv = (db.query(DirectConversation)
               .filter(or_(and_(DirectConversation.user_a_id == a, DirectConversation.user_b_id == b),
                           and_(DirectConversation.user_a_id == b, DirectConversation.user_b_id == a)))
               .first())
    if not conv:
        conv = DirectConversation(user_a_id=a, user_b_id=b)
        db.add(conv)
        db.commit()
        db.refresh(conv)
    atts = None
    if attachments:
        try:
            atts = json.loads(attachments)
        except Exception:
            atts = None

    msg = ChatMessage(
        conversation_id=conv.id,
        sender_id=from_employee_id,
        content=message.strip(),
        attachments=atts,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"status": "success", "message_id": msg.id, "data": {
        "id": msg.id,
        "from_employee_id": from_employee_id,
        "to_employee_id": to_employee_id,
        "message": msg.content,
        "timestamp": msg.created_at.isoformat(),
        "attachments": msg.attachments,
    }}


@router.get("/api/chat/dm")
def dm_messages(user_a: str, user_b: str, limit: int = Query(50, ge=1, le=200), before: Optional[str] = None, db: Session = Depends(get_db)):
    a, b = _pair(user_a, user_b)
    conv = (db.query(DirectConversation)
               .filter(or_(and_(DirectConversation.user_a_id == a, DirectConversation.user_b_id == b),
                           and_(DirectConversation.user_a_id == b, DirectConversation.user_b_id == a)))
               .first())
    if not conv:
        return {"messages": [], "next_before": None}
    q = db.query(ChatMessage).filter(ChatMessage.conversation_id == conv.id)
    if before:
        anchor = db.query(ChatMessage).filter(ChatMessage.id == before).first()
        if anchor:
            q = q.filter(ChatMessage.created_at < anchor.created_at)
    rows = q.order_by(ChatMessage.created_at.desc()).limit(limit).all()
    rows.reverse()
    items = []
    for m in rows:
        sender = db.query(User).filter(User.id == m.sender_id).first()
        items.append({
            "id": m.id,
            "from_employee_id": m.sender_id,
            "employee_name": sender.name if sender else "Unknown",
            "message": m.content,
            "timestamp": m.created_at.isoformat(),
            "reactions": m.reactions,
        })
    next_before = rows[0].id if rows else None
    return {"messages": items, "next_before": next_before}


@router.post("/api/chat/message/read")
def mark_read(message_id: str = Form(...), user_id: str = Form(...), db: Session = Depends(get_db)):
    exists = (db.query(MessageRead)
                .filter(MessageRead.message_id == message_id, MessageRead.user_id == user_id)
                .first())
    if not exists:
        db.add(MessageRead(message_id=message_id, user_id=user_id))
        db.commit()
    return {"ok": True}


@router.get("/api/chat/unread_counts")
def unread_counts(user_id: str, db: Session = Depends(get_db)):
    # Per-channel unread counts
    channels = db.query(ChatChannel).all()
    channel_counts = {}
    for ch in channels:
        total = db.query(ChatMessage).filter(ChatMessage.channel_id == ch.id).count()
        read = (db.query(MessageRead)
                  .join(ChatMessage, ChatMessage.id == MessageRead.message_id)
                  .filter(MessageRead.user_id == user_id, ChatMessage.channel_id == ch.id)
                  .count())
        channel_counts[ch.name] = max(total - read, 0)

    # Per-DM unread count (total)
    # Count messages sent to user that user hasn't read
    dm_unread = (db.query(ChatMessage)
                   .join(DirectConversation, DirectConversation.id == ChatMessage.conversation_id)
                   .filter(ChatMessage.sender_id != user_id)
                   .filter(or_(DirectConversation.user_a_id == user_id, DirectConversation.user_b_id == user_id))
                   .count()
                 - db.query(MessageRead)
                      .join(ChatMessage, ChatMessage.id == MessageRead.message_id)
                      .join(DirectConversation, DirectConversation.id == ChatMessage.conversation_id)
                      .filter(MessageRead.user_id == user_id)
                      .filter(ChatMessage.sender_id != user_id)
                      .filter(or_(DirectConversation.user_a_id == user_id, DirectConversation.user_b_id == user_id))
                      .count())
    return {"channels": channel_counts, "dm_unread": max(dm_unread, 0)}


UPLOAD_DIR = os.path.join("uploads", "chat")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/api/chat/upload")
def upload_attachment(file: UploadFile = File(...)):
    # Basic validation
    filename = file.filename or "upload.bin"
    safe_name = filename.replace("..", "+").replace("/", "_")
    path = os.path.join(UPLOAD_DIR, safe_name)
    with open(path, "wb") as f:
        f.write(file.file.read())
    return {
        "name": safe_name,
        "path": f"/uploads/chat/{safe_name}",
        "mime_type": file.content_type,
        "size": os.path.getsize(path)
    }

@router.post("/api/chat/message/edit")
def edit_message(message_id: str = Form(...), employee_id: str = Form(...), new_text: str = Form(...), db: Session = Depends(get_db)):
    m = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Message not found")
    if m.sender_id != employee_id:
        raise HTTPException(status_code=403, detail="Not allowed")
    m.content = new_text
    m.edited = True
    m.edited_at = datetime.utcnow()
    db.add(m)
    db.commit()
    return {"ok": True}


@router.post("/api/chat/message/delete")
def delete_message(message_id: str = Form(...), employee_id: str = Form(...), db: Session = Depends(get_db)):
    m = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Message not found")
    if m.sender_id != employee_id:
        raise HTTPException(status_code=403, detail="Not allowed")
    m.content = "(message deleted)"
    m.edited = True
    m.edited_at = datetime.utcnow()
    db.add(m)
    db.commit()
    return {"ok": True}


@router.get("/api/chat/search")
def search_messages(
    q: Optional[str] = None,
    channel: Optional[str] = None,
    user_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(ChatMessage)
    if channel:
        ch = db.query(ChatChannel).filter(ChatChannel.name == channel).first()
        if ch:
            query = query.filter(ChatMessage.channel_id == ch.id)
        else:
            return {"results": []}
    if user_id:
        query = query.filter(ChatMessage.sender_id == user_id)
    if q:
        like = f"%{q}%"
        query = query.filter(ChatMessage.content.like(like))
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(ChatMessage.created_at >= dt_from)
        except Exception:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.filter(ChatMessage.created_at <= dt_to)
        except Exception:
            pass
    rows = query.order_by(ChatMessage.created_at.desc()).limit(200).all()
    results = []
    for m in rows:
        sender = db.query(User).filter(User.id == m.sender_id).first()
        results.append({
            "id": m.id,
            "channel_id": m.channel_id,
            "conversation_id": m.conversation_id,
            "employee_id": m.sender_id,
            "employee_name": sender.name if sender else "Unknown",
            "message": m.content,
            "timestamp": m.created_at.isoformat(),
        })
    return {"results": results}


