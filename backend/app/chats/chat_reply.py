# -*- coding: utf-8 -*-
"""协调 Trace 与 Span 的创建、会话标题更新和回复结束时的一次写入。"""

import json
from collections.abc import AsyncIterator
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from uuid import uuid4

import anyio
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.chats.chat_session import ChatSession
from app.chats.mock_reply import iter_chunks
from app.chats.mock_reply import mock_reply
from app.chats.span import SPAN_TEXT_LIMIT
from app.chats.span import Span
from app.chats.span import SpanStatus
from app.chats.span import SpanType
from app.chats.span import clip_text
from app.chats.trace import Trace
from app.chats.trace import TraceStatus

_DEFAULT_TITLE = "新会话"
_TITLE_LENGTH = 16
_STALE_AFTER = timedelta(minutes=10)


class ChatSessionNotFound(Exception):
    """会话不存在，或当前用户无权访问。"""


class ChatReplyService:
    """原子创建 Trace 和 Span；推送期间只在内存累积正文，结束时一次写库。"""

    def __init__(self, engine: Engine, text_limit: int = SPAN_TEXT_LIMIT) -> None:
        """保存数据库引擎和单条 Span 正文的字节上限。"""
        self._engine = engine
        self._text_limit = text_limit

    def begin_reply(self, session_id: str, username: str, user_text: str) -> tuple[str, str]:
        """创建 running Trace 和空 text Span，并更新会话标题和时间。"""
        with Session(self._engine) as session:
            chat_session = ChatSession.get_for_user(session, session_id, username)
            if chat_session is None:
                raise ChatSessionNotFound(session_id)
            created_at = datetime.now(UTC)
            trace_id = uuid4().hex
            trace = Trace(
                id=trace_id,
                session_id=chat_session.id,
                user_text=user_text,
                status=TraceStatus.RUNNING,
                created_at=created_at,
            )
            span_id = uuid4().hex
            span = Span(
                id=span_id,
                trace_id=trace_id,
                sequence=1,
                type=SpanType.TEXT,
                status=SpanStatus.RUNNING,
                visible=True,
                text="",
                truncated=False,
                started_at=created_at,
            )
            session.add(trace)
            session.flush()
            session.add(span)
            chat_session.updated_at = created_at
            if chat_session.title == _DEFAULT_TITLE:
                chat_session.title = _title_from(user_text)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise
            return trace_id, span_id

    async def stream_reply(self, trace_id: str, span_id: str, user_text: str) -> AsyncIterator[str]:
        """推送回复片段；正常结束、出错或被中断时把已推送正文和状态写入一次。"""
        accumulated: list[str] = []
        finished = False
        try:
            reply = mock_reply(user_text)
            for chunk in iter_chunks(reply):
                accumulated.append(chunk)
                payload = json.dumps({"text": chunk}, ensure_ascii=False)
                yield f"event: chunk\ndata: {payload}\n\n"
            await self._finish(trace_id, span_id, "".join(accumulated), completed=True)
            finished = True
            payload = json.dumps({"trace_id": trace_id, "span_id": span_id})
            yield f"event: done\ndata: {payload}\n\n"
        except Exception:
            # 回复生成或发送边界异常只返回固定错误，不向客户端暴露内部信息。
            if not finished:
                await self._finish(trace_id, span_id, "".join(accumulated), completed=False)
                finished = True
            payload = json.dumps({"detail": "回复失败"}, ensure_ascii=False)
            yield f"event: error\ndata: {payload}\n\n"
        finally:
            if not finished:
                await self._finish(trace_id, span_id, "".join(accumulated), completed=False)

    def fail_stale_replies(self) -> None:
        """把超过时限仍为 running 的 Trace 和 Span 标为 failed，供进程启动时清理残留。"""
        now = datetime.now(UTC)
        before = now - _STALE_AFTER
        with Session(self._engine) as session:
            Trace.fail_running_before(session, before)
            Span.fail_running_before(session, before, now)
            session.commit()

    async def _finish(self, trace_id: str, span_id: str, text: str, completed: bool) -> None:
        """在线程池中写入最终结果；屏蔽取消，保证客户端断开时也能写完。"""
        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(self._write_result, trace_id, span_id, text, completed)

    def _write_result(self, trace_id: str, span_id: str, text: str, completed: bool) -> None:
        """在一个事务里写入 Span 正文与状态，以及 Trace 状态；completed 为假时两者都标为失败。"""
        stored, truncated = clip_text(text, self._text_limit)
        with Session(self._engine) as session:
            trace = Trace.get(session, trace_id)
            span = Span.get(session, span_id)
            if trace is not None:
                trace.status = TraceStatus.COMPLETE if completed else TraceStatus.FAILED
            if span is not None:
                span.text = stored
                span.truncated = truncated
                span.status = SpanStatus.COMPLETE if completed else SpanStatus.FAILED
                span.ended_at = datetime.now(UTC)
            session.commit()


def _title_from(user_text: str) -> str:
    """从首轮用户输入截取默认标题，超出长度时添加省略号。"""
    if len(user_text) <= _TITLE_LENGTH:
        return user_text
    return f"{user_text[:_TITLE_LENGTH]}…"
