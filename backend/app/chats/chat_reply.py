# -*- coding: utf-8 -*-
"""协调 Trace 创建、会话标题更新和模拟回复状态。"""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC
from datetime import datetime
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.chats.chat_session import ChatSession
from app.chats.mock_reply import iter_chunks
from app.chats.mock_reply import mock_reply
from app.chats.trace import Trace

_DEFAULT_TITLE = "新会话"
_TITLE_LENGTH = 16


class ChatSessionNotFound(Exception):
    """会话不存在，或当前用户无权访问。"""


class ChatReplyService:
    """原子创建 Trace 和会话标题，再按 SSE 流程更新 Trace 状态。"""

    def __init__(self, engine: Engine) -> None:
        """保存用于读取会话和更新 Trace 状态的数据库引擎。"""
        self._engine = engine

    def begin_reply(self, session_id: str, username: str, user_text: str) -> str:
        """创建 running Trace，并同步更新会话时间和首轮默认标题。"""
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
                status="running",
                created_at=created_at,
            )
            session.add(trace)
            chat_session.updated_at = created_at
            if chat_session.title == _DEFAULT_TITLE:
                chat_session.title = _title_from(user_text)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise
            return trace_id

    async def stream_reply(self, trace_id: str, user_text: str) -> AsyncIterator[str]:
        """推送回复片段，正常完成或中断时保存 Trace 状态。"""
        completed = False
        failed = False
        try:
            reply = mock_reply(user_text)
            for chunk in iter_chunks(reply):
                payload = json.dumps({"text": chunk}, ensure_ascii=False)
                yield f"event: chunk\ndata: {payload}\n\n"
            self._set_status(trace_id, "complete")
            yield "event: done\ndata: {}\n\n"
            completed = True
        except asyncio.CancelledError:
            self._set_status(trace_id, "failed")
            failed = True
            raise
        except GeneratorExit:
            self._set_status(trace_id, "failed")
            failed = True
            raise
        except Exception:
            # 回复生成或发送边界异常只返回固定错误，不向客户端暴露内部信息。
            self._set_status(trace_id, "failed")
            failed = True
            payload = json.dumps({"detail": "回复失败"}, ensure_ascii=False)
            yield f"event: error\ndata: {payload}\n\n"
        finally:
            if not completed and not failed:
                self._set_status(trace_id, "failed")

    def _set_status(self, trace_id: str, status: str) -> None:
        """持久化 Trace 的最终状态。"""
        with Session(self._engine) as session:
            trace = Trace.get(session, trace_id)
            if trace is not None:
                trace.update(session, status=status)


def _title_from(user_text: str) -> str:
    """从首轮用户输入截取默认标题，超出长度时添加省略号。"""
    if len(user_text) <= _TITLE_LENGTH:
        return user_text
    return f"{user_text[:_TITLE_LENGTH]}…"
