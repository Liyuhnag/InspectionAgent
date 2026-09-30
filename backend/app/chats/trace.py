# -*- coding: utf-8 -*-
"""持久化一轮用户请求及其运行状态。"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import Session
from sqlalchemy.orm import mapped_column

from app.db.crud_model import CrudModel
from app.db.enum_column import string_enum


class TraceStatus(StrEnum):
    """一轮请求的运行状态。"""

    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


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
    status: Mapped[TraceStatus] = mapped_column(string_enum(TraceStatus, 16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    @classmethod
    def list_for_session(cls, session: Session, session_id: str) -> list["Trace"]:
        """按创建时间从早到晚列出会话的所有 Trace。"""
        query = select(cls).where(cls.session_id == session_id).order_by(cls.created_at.asc())
        return list(session.scalars(query))

    @classmethod
    def fail_running_before(cls, session: Session, before: datetime) -> None:
        """把创建时间早于给定时刻、仍为 running 的 Trace 标为 failed，不提交。"""
        query = (
            update(cls)
            .where(cls.status == TraceStatus.RUNNING, cls.created_at < before)
            .values(status=TraceStatus.FAILED)
        )
        session.execute(query)
