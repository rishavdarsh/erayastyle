from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session

from models import get_db, User
from chat_models import ChatChannel, ChatMessage
from routers.tasks import current_user

router = APIRouter()


@router.get("/api/chat/messages/{channel_id}")
def list_messages(
    channel_id: str,
    limit: int = 50,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Get last N messages from a channel."""
    channel = db.query(ChatChannel).filter(ChatChannel.id == channel_id).first()
    if not channel:
        raise HTTPException(404, "Channel not found")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.channel_id == channel_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": m.id,
            "channel_id": m.channel_id,
            "author": m.sender.name,
            "text": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.post("/api/chat/messages")
def create_message(
    channel_id: str = Form(...),
    text: str = Form(...),
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Create a new message in a channel."""
    channel = db.query(ChatChannel).filter(ChatChannel.id == channel_id).first()
    if not channel:
        raise HTTPException(404, "Channel not found")

    message = ChatMessage(
        channel_id=channel_id,
        sender_id=u.id,
        content=f"{u.name}: {text}",
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    return {
        "id": message.id,
        "channel_id": message.channel_id,
        "author": u.name,
        "text": message.content,
        "created_at": message.created_at.isoformat(),
    }
