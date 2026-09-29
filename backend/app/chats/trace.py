# -*- coding: utf-8 -*-
"""持久化一轮用户请求及其运行状态。"""

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import select
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import Session
from sqlalchemy.orm import mapped_column

from app.db.crud_model import CrudModel


class Trace(CrudModel):
    """一条 Trace 代表一个会话中的单轮用户请求。"""

    __tablename__ = "traces"
    __table_args__ = (Index("ix_traces_session_created_at", "session_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("chat_sessions.id"),
        nullable=False,
    )
    user_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    @classmethod
    def list_for_session(cls, session: Session, session_id: str) -> list["Trace"]:
        """按创建时间从早到晚列出会话的所有 Trace。"""
        query = select(cls).where(cls.session_id == session_id).order_by(cls.created_at.asc())
        return list(session.scalars(query))
