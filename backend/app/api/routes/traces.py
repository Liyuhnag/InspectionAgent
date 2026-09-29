# -*- coding: utf-8 -*-
"""Trace 查询和会话回复接口。"""

from datetime import UTC
from datetime import datetime

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.chats.chat_reply import ChatReplyService
from app.chats.chat_reply import ChatSessionNotFound
from app.chats.chat_session import ChatSession
from app.chats.trace import Trace


class ReplyBody(BaseModel):
    """发送一轮回复的请求体。"""

    text: str = ""


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

    @router.post("/chat-sessions/{session_id}/replies")
    def create_reply(session_id: str, body: ReplyBody, request: Request) -> StreamingResponse:
        """先记录用户请求，再流式发送模拟回复。"""
        username = _current_username(request)
        user_text = body.text.strip()
        if not user_text:
            raise HTTPException(status_code=400, detail="不能为空")
        try:
            trace_id = replies.begin_reply(session_id, username, user_text)
        except ChatSessionNotFound as error:
            raise HTTPException(status_code=404, detail="会话不存在") from error
        return StreamingResponse(
            replies.stream_reply(trace_id, user_text),
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


def _iso_utc(value: datetime) -> str:
    """将数据库时间统一序列化为带 Z 后缀的 UTC 时间。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat().replace("+00:00", "Z")
