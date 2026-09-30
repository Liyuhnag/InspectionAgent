# -*- coding: utf-8 -*-
"""持久化 Trace 中的有序执行片段，并提供只涉及 Span 表的查询。"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import Session
from sqlalchemy.orm import mapped_column

from app.db.crud_model import CrudModel
from app.db.enum_column import string_enum

SPAN_TEXT_LIMIT = 64 * 1024

_LongText = Text().with_variant(MEDIUMTEXT(), "mysql")
_PreciseTime = DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql")


class SpanType(StrEnum):
    """一步执行的类型。"""

    AGENT = "agent"
    LLM = "llm"
    TOOL_CALL = "tool_call"
    MCP_CALL = "mcp_call"
    THINKING = "thinking"
    TEXT = "text"
    HUMAN_INPUT = "human_input"


class SpanStatus(StrEnum):
    """一步执行的运行状态。"""

    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class Span(CrudModel):
    """一个 Span 记录 Trace 中某一步的类型、归属、输出原文和摘要；llm 类型另记提示词、组装规则版本和输入指纹，供审计核对。"""

    __tablename__ = "spans"
    __table_args__ = (
        UniqueConstraint("trace_id", "sequence", name="uq_spans_trace_sequence"),
        Index("ix_spans_status_started_at", "status", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(32), ForeignKey("traces.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[SpanType] = mapped_column(string_enum(SpanType, 32), nullable=False)
    status: Mapped[SpanStatus] = mapped_column(string_enum(SpanStatus, 16), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("spans.id"), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context_rule_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text: Mapped[str] = mapped_column(_LongText, nullable=False)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    summary: Mapped[str | None] = mapped_column(_LongText, nullable=True)
    summarized_at: Mapped[datetime | None] = mapped_column(_PreciseTime, nullable=True)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(_PreciseTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(_PreciseTime, nullable=True)

    @classmethod
    def list_for_trace(cls, session: Session, trace_id: str) -> list["Span"]:
        """按顺序从小到大列出 Trace 的 Span。"""
        query = select(cls).where(cls.trace_id == trace_id).order_by(cls.sequence.asc())
        return list(session.scalars(query))

    @classmethod
    def list_visible_text(cls, session: Session, trace_ids: list[str]) -> list["Span"]:
        """一次查询取出多条 Trace 中进入用户气泡的 text Span，按 Trace 和顺序排列。"""
        if not trace_ids:
            return []
        query = (
            select(cls)
            .where(cls.trace_id.in_(trace_ids), cls.visible.is_(True), cls.type == SpanType.TEXT)
            .order_by(cls.trace_id.asc(), cls.sequence.asc())
        )
        return list(session.scalars(query))

    @classmethod
    def fail_running_before(cls, session: Session, before: datetime, ended_at: datetime) -> None:
        """把开始时间早于给定时刻、仍为 running 的 Span 标为 failed，不提交。"""
        query = (
            update(cls)
            .where(cls.status == SpanStatus.RUNNING, cls.started_at < before)
            .values(status=SpanStatus.FAILED, ended_at=ended_at)
        )
        session.execute(query)


def clip_text(text: str, limit: int = SPAN_TEXT_LIMIT) -> tuple[str, bool]:
    """按 UTF-8 字节数截断正文，截断点落在字符边界；返回正文和是否截断。"""
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text, False
    return encoded[:limit].decode("utf-8", errors="ignore"), True
