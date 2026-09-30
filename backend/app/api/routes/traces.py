# -*- coding: utf-8 -*-
"""Trace 查询和会话回复接口。"""

from datetime import UTC
from datetime import datetime

import anyio
from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from starlette.types import Send

from app.chats.chat_reply import ChatReplyService
from app.chats.chat_reply import ChatSessionNotFound
from app.chats.chat_session import ChatSession
from app.chats.span import Span
from app.chats.trace import Trace


class ReplyBody(BaseModel):
    """发送一轮回复的请求体。"""

    text: str = ""


class ClosingStreamingResponse(StreamingResponse):
    """推送结束、客户端断开或被取消时都关闭内容生成器，让它写完最终结果。"""

    async def stream_response(self, send: Send) -> None:
        """Starlette 不会主动关闭生成器，这里在屏蔽取消的范围内显式关闭。"""
        try:
            await super().stream_response(send)
        finally:
            close = getattr(self.body_iterator, "aclose", None)
            if close is not None:
                with anyio.CancelScope(shield=True):
                    await close()


def traces_router(engine: Engine, replies: ChatReplyService) -> APIRouter:
    """挂上会话内 Trace 列表和 SSE 回复接口。"""
    router = APIRouter()

    @router.get("/chat-sessions/{session_id}/traces")
    def list_traces(session_id: str, request: Request) -> dict[str, list[dict[str, str]]]:
        """返回当前用户会话中的 Trace，按创建时间升序排列。"""
        username = _current_username(request)
        with Session(engine) as session:
            chat_session = ChatSession.get_for_user(session, session_id, username)
            if chat_session is None:
                raise HTTPException(status_code=404, detail="会话不存在")
            traces = Trace.list_for_session(session, session_id)
            return {"traces": [_trace_payload(trace) for trace in traces]}

    @router.get("/chat-sessions/{session_id}/traces/{trace_id}/spans")
    def list_spans(
        session_id: str,
        trace_id: str,
        request: Request,
    ) -> dict[str, list[dict[str, str | int | bool | None]]]:
        """返回指定 Trace 的 Span，未知或越权编号均按不存在处理。"""
        username = _current_username(request)
        with Session(engine) as session:
            chat_session = ChatSession.get_for_user(session, session_id, username)
            if chat_session is None:
                raise HTTPException(status_code=404, detail="会话不存在")
            trace = Trace.get(session, trace_id)
            if trace is None or trace.session_id != session_id:
                raise HTTPException(status_code=404, detail="会话不存在")
            spans = Span.list_for_trace(session, trace_id)
            return {"spans": [_span_payload(span) for span in spans]}

    @router.post("/chat-sessions/{session_id}/replies")
    def create_reply(session_id: str, body: ReplyBody, request: Request) -> StreamingResponse:
        """先记录用户请求，再流式发送模拟回复。"""
        username = _current_username(request)
        user_text = body.text.strip()
        if not user_text:
            raise HTTPException(status_code=400, detail="不能为空")
        try:
            trace_id, span_id = replies.begin_reply(session_id, username, user_text)
        except ChatSessionNotFound as error:
            raise HTTPException(status_code=404, detail="会话不存在") from error
        return ClosingStreamingResponse(
            replies.stream_reply(trace_id, span_id, user_text),
            media_type="text/event-stream",
        )

    return router


def _current_username(request: Request) -> str:
    """读取鉴权中间件解析出的用户名。"""
    username = getattr(request.state, "username", "")
    if not isinstance(username, str) or not username:
        raise HTTPException(status_code=401, detail="未登录")
    return username


def _trace_payload(trace: Trace) -> dict[str, str]:
    """把 Trace 模型转换为公开响应字段。"""
    return {
        "id": trace.id,
        "user_text": trace.user_text,
        "status": trace.status,
        "created_at": _iso_utc(trace.created_at),
    }


def _span_payload(span: Span) -> dict[str, str | int | bool | None]:
    """把 Span 模型转换为公开响应字段；摘要和 token 数只供模型上下文使用，不返回。"""
    return {
        "id": span.id,
        "sequence": span.sequence,
        "type": span.type,
        "status": span.status,
        "parent_span_id": span.parent_span_id,
        "agent_name": span.agent_name,
        "node": span.node,
        "visible": span.visible,
        "model": span.model,
        "text": span.text,
        "truncated": span.truncated,
        "started_at": _iso_utc(span.started_at),
        "ended_at": None if span.ended_at is None else _iso_utc(span.ended_at),
    }


def _iso_utc(value: datetime) -> str:
    """将数据库时间统一序列化为带 Z 后缀的 UTC 时间。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat().replace("+00:00", "Z")
