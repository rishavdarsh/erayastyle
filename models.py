from __future__ import annotations

import os
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Text,
    DateTime,
    Enum,
    Boolean,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy import JSON as SA_JSON


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./eraya_ops.db")
POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")


engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def _json_column():
    # Use SQLAlchemy's generic JSON; on SQLite it stores as TEXT/JSON depending on build
    return SA_JSON


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=False)
    role = Column(Enum("ADMIN", "MANAGER", "EMPLOYEE", name="role_enum"), default="EMPLOYEE", index=True)
    team = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    title = Column(String, nullable=False)
    description = Column(Text)
    board = Column(Enum("DAILY", "OTHER", name="board_enum"), nullable=False, index=True)
    status = Column(Enum("TODO", "IN_PROGRESS", "REVIEW", "DONE", "BACKLOG", name="status_enum"), index=True)
    priority = Column(Enum("LOW", "MEDIUM", "HIGH", "URGENT", name="priority_enum"), default="MEDIUM", index=True)
    type = Column(Enum("DAILY", "PROJECT", name="tasktype_enum"), default="PROJECT")
    due_date = Column(DateTime, nullable=True)
    is_recurring = Column(Boolean, default=False)
    recurring_rule = Column(_json_column(), nullable=True)  # {"freq": "DAILY"|"WEEKLY", ...}
    tags = Column(_json_column())  # list of strings
    attachments = Column(_json_column())  # list of {name,url}
    proof_url = Column(String)

    created_by_id = Column(String, ForeignKey("users.id"), nullable=False)
    assigned_to_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_by = relationship("User", foreign_keys=[created_by_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Comment(Base):
    __tablename__ = "comments"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String, ForeignKey("tasks.id"), index=True)
    author_id = Column(String, ForeignKey("users.id"), index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("Task")
    author = relationship("User")


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String, ForeignKey("tasks.id"), index=True)
    uploaded_by_id = Column(String, ForeignKey("users.id"), index=True)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)  # in bytes
    mime_type = Column(String, nullable=False)
    is_image = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("Task")
    uploaded_by = relationship("User")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String, ForeignKey("tasks.id"), index=True)
    actor_id = Column(String, ForeignKey("users.id"), index=True)
    action = Column(String)  # CREATE, UPDATE_STATUS, ADD_COMMENT, ADD_ATTACHMENT, MARK_DONE
    meta = Column(_json_column())
    created_at = Column(DateTime, default=datetime.utcnow)


class Subtask(Base):
    __tablename__ = "subtasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String, ForeignKey("tasks.id"), index=True)
    title = Column(String, nullable=False)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("Task")


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    title = Column(String, nullable=False)
    body = Column(Text)
    created_by_id = Column(String, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)


class RecurringTemplate(Base):
    __tablename__ = "recurring_templates"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    title = Column(String, nullable=False)
    description = Column(Text)
    board = Column(Enum("DAILY", "OTHER", name="board_enum_copy"), nullable=False)
    default_status = Column(String, default="TODO")
    priority = Column(String, default="MEDIUM")
    freq = Column(Enum("DAILY", "WEEKLY", name="freq_enum"), default="DAILY")
    hour = Column(Integer, default=6)
    minute = Column(Integer, default=30)
    weekday = Column(Integer, nullable=True)  # 1..7
    assigned_to_id = Column(String, ForeignKey("users.id"))
    created_by_id = Column(String, ForeignKey("users.id"))
    tags = Column(_json_column())
    created_at = Column(DateTime, default=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)


