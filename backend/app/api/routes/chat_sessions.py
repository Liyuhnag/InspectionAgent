# -*- coding: utf-8 -*-
"""聊天会话接口。只读取鉴权身份、调用模型并整理响应。"""

from datetime import UTC
from datetime import datetime

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import field_validator
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.chats.chat_session import ChatSession


class RenameChatSessionBody(BaseModel):
    """手动修改会话标题的请求体。"""

    model_config = ConfigDict(extra="forbid")

    title: str

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        """裁剪标题首尾空白，并拒绝空标题或超长标题。"""
        title = value.strip()
        if not title:
            raise ValueError("标题不能为空")
        if len(title) > 255:
            raise ValueError("标题不能超过 255 个字符")
        return title


def chat_sessions_router(engine: Engine) -> APIRouter:
    """挂上会话列表、创建、读取和改名接口。"""
    router = APIRouter()

    @router.get("/chat-sessions")
    def list_sessions(request: Request) -> dict[str, list[dict[str, str]]]:
        """返回当前用户按更新时间倒序排列的会话。"""
        username = _current_username(request)
        with Session(engine) as session:
            rows = ChatSession.list_for_user(session, username)
            return {"sessions": [_session_payload(row) for row in rows]}

    @router.post("/chat-sessions", status_code=201)
    def create_session(request: Request) -> dict[str, str]:
        """为当前用户创建并返回一条空会话。"""
        username = _current_username(request)
        with Session(engine) as session:
            row = ChatSession.create_for_user(session, username)
            return _session_payload(row)

    @router.get("/chat-sessions/{session_id}")
    def get_session(session_id: str, request: Request) -> dict[str, str]:
        """返回当前用户的会话，未知或越权编号均按不存在处理。"""
        username = _current_username(request)
        with Session(engine) as session:
            row = ChatSession.get_for_user(session, session_id, username)
            if row is None:
                raise HTTPException(status_code=404, detail="会话不存在")
            return _session_payload(row)

    @router.patch("/chat-sessions/{session_id}")
    def rename_session(
        session_id: str,
        body: RenameChatSessionBody,
        request: Request,
    ) -> dict[str, str]:
        """修改当前用户会话的标题并更新会话时间。"""
        username = _current_username(request)
        with Session(engine) as session:
            row = ChatSession.get_for_user(session, session_id, username)
            if row is None:
                raise HTTPException(status_code=404, detail="会话不存在")
            row.update(session, title=body.title, updated_at=datetime.now(UTC))
            return _session_payload(row)

    return router


def _current_username(request: Request) -> str:
    """读取鉴权中间件解析出的用户名。"""
    username = getattr(request.state, "username", "")
    if not isinstance(username, str) or not username:
        raise HTTPException(status_code=401, detail="未登录")
    return username


def _session_payload(row: ChatSession) -> dict[str, str]:
    """把会话模型转换为公开响应字段。"""
    return {
        "id": row.id,
        "title": row.title,
        "updated_at": _iso_utc(row.updated_at),
    }


def _iso_utc(value: datetime) -> str:
    """将数据库时间统一序列化为带 Z 后缀的 UTC 时间。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat().replace("+00:00", "Z")
