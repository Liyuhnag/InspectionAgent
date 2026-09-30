# -*- coding: utf-8 -*-
"""持久化聊天会话，并提供只涉及会话表的查询。"""

from datetime import UTC
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy import select
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import Session
from sqlalchemy.orm import mapped_column

from app.db.crud_model import CrudModel


class ChatSession(CrudModel):
    """聊天会话表；active_trace_id 记录当前显示的分支末端。继承 CrudModel 的 CRUD 实现并封装会话查询。"""

    __tablename__ = "chat_sessions"
    __table_args__ = (Index("ix_chat_sessions_username_updated_at", "username", "updated_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), ForeignKey("users.username"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # chat_sessions 先于 traces 建表，这里不建外键，由回复服务保证指向本会话的 Trace。
    active_trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    @classmethod
    def create_for_user(cls, session: Session, username: str) -> "ChatSession":
        """为已鉴权用户创建一条带默认标题的空会话。"""
        now = datetime.now(UTC)
        return cls.create(
            session,
            id=uuid4().hex,
            username=username,
            title="新会话",
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def list_for_user(cls, session: Session, username: str) -> list["ChatSession"]:
        """按更新时间从新到旧列出指定用户的会话。"""
        query = select(cls).where(cls.username == username).order_by(cls.updated_at.desc())
        return list(session.scalars(query))

    @classmethod
    def get_for_user(cls, session: Session, session_id: str, username: str) -> "ChatSession | None":
        """同时按会话编号和用户名读取，避免返回其他用户的会话。"""
        query = select(cls).where(cls.id == session_id, cls.username == username)
        return session.scalar(query)
