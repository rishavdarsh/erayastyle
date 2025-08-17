from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models import get_db
from chat_models import ChatChannel

router = APIRouter()


@router.get("/api/chat/channels")
def list_channels(db: Session = Depends(get_db)):
    """List all available chat channels."""
    channels = db.query(ChatChannel).order_by(ChatChannel.name).all()
    return [{"id": c.id, "name": c.name} for c in channels]
