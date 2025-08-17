from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy import JSON as SA_JSON

from models import Base, engine, SessionLocal, User  # reuse the main Base/engine/session


class ChatChannel(Base):
    __tablename__ = "chat_channels"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    name = Column(String, unique=True, nullable=False, index=True)
    is_private = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    messages = relationship("ChatMessage", back_populates="channel")


class DirectConversation(Base):
    __tablename__ = "chat_direct_conversations"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_a_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    user_b_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user_a = relationship("User", foreign_keys=[user_a_id])
    user_b = relationship("User", foreign_keys=[user_b_id])

    # Helpful index to speed up lookups by pair (unordered)
    __table_args__ = (
        Index("ix_chat_direct_pair", "user_a_id", "user_b_id"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    channel_id = Column(String, ForeignKey("chat_channels.id"), nullable=True, index=True)
    conversation_id = Column(String, ForeignKey("chat_direct_conversations.id"), nullable=True, index=True)
    sender_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    edited = Column(Boolean, default=False)
    edited_at = Column(DateTime, nullable=True)

    parent_message_id = Column(String, ForeignKey("chat_messages.id"), nullable=True, index=True)
    links = Column(SA_JSON, nullable=True)
    attachments = Column(SA_JSON, nullable=True)
    reactions = Column(SA_JSON, nullable=True)  # {"emoji": ["user_id", ...]}

    sender = relationship("User", foreign_keys=[sender_id])
    channel = relationship("ChatChannel", back_populates="messages", foreign_keys=[channel_id])
    conversation = relationship("DirectConversation", foreign_keys=[conversation_id])
    parent = relationship("ChatMessage", remote_side=[id], backref="thread_replies")


class MessageRead(Base):
    __tablename__ = "chat_message_reads"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    message_id = Column(String, ForeignKey("chat_messages.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    read_at = Column(DateTime, default=datetime.utcnow)


DEFAULT_CHANNELS = ["general", "packing", "management", "announcements", "support"]


def ensure_channels():
    """Ensure all default channels exist."""
    with SessionLocal() as db:
        existing = {c.name for c in db.query(ChatChannel).all()}
        for name in DEFAULT_CHANNELS:
            if name not in existing:
                db.add(ChatChannel(name=name))
        db.commit()


def ensure_channel_by_name(name: str) -> ChatChannel:
    """Get or create a channel by name."""
    with SessionLocal() as db:
        channel = db.query(ChatChannel).filter(ChatChannel.name == name).first()
        if not channel:
            channel = ChatChannel(name=name)
            db.add(channel)
            db.commit()
            db.refresh(channel)
        return channel


def _seed_default_channels():
    ensure_channels()


def init_chat_schema():
    Base.metadata.create_all(bind=engine)
    _seed_default_channels()


# Initialize schema on import to avoid touching app startup code
try:
    init_chat_schema()
except Exception:
    # Avoid hard-crashing during import; app can retry later
    pass


