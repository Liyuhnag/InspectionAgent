# -*- coding: utf-8 -*-
"""Trace 持久化、会话归属和回复流生命周期。"""

import asyncio
import json

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.auth import TOKEN_HEADER
from app.chats.chat_reply import ChatReplyService
from app.chats.mock_reply import mock_reply
from app.chats.chat_session import ChatSession
from app.chats.trace import Trace
from app.main import create_app
from app.users.login import session_key
from app.users.password import Password
from app.users.user_model import User
from tests.mysql import open_test_database

_USERS = ("trace-owner", "trace-other")
_PASSWORD = "trace-secret"


class MemoryRedis:
    """为接口测试提供无需外部服务的 token 存储。"""

    def __init__(self) -> None:
        """创建空的键值集合。"""
        self.values: dict[str, str] = {}

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """保存 token 值并忽略测试中的过期时间。"""
        self.values[key] = value
        return True

    def get(self, key: str) -> str | None:
        """读取指定键对应的 token 用户名。"""
        return self.values.get(key)

    def expire(self, key: str, seconds: int) -> bool:
        """模拟更新 token 过期时间。"""
        return key in self.values

    def delete(self, key: str) -> int:
        """删除指定 token 并返回删除数量。"""
        return int(self.values.pop(key, None) is not None)


def _setup(use_mysql: bool = False) -> tuple[Engine, MemoryRedis, TestClient, dict[str, str]]:
    """创建测试数据库、清理测试记录并建立登录态。"""
    if use_mysql:
        _settings, engine = open_test_database()
    else:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    codes = MemoryRedis()
    client = TestClient(create_app(engine, codes, 60))
    _cleanup(engine, codes, {})
    tokens: dict[str, str] = {}
    for username in _USERS:
        sealed = Password.encrypt(_PASSWORD)
        with Session(engine) as session:
            User.create(session, username=username, salt=sealed.salt, password_hash=sealed.password_hash)
        response = client.post("/session", json={"username": username, "password": _PASSWORD})
        assert response.status_code == 200
        tokens[username] = response.json()["token"]
    return engine, codes, client, tokens


def _cleanup(engine: Engine, codes: MemoryRedis, tokens: dict[str, str]) -> None:
    """删除本用例创建的会话、trace、用户和 token。"""
    for token in tokens.values():
        codes.delete(session_key(token))
    with Session(engine) as session:
        session_ids = select(ChatSession.id).where(ChatSession.username.in_(_USERS))
        session.execute(delete(Trace).where(Trace.session_id.in_(session_ids)))
        session.execute(delete(ChatSession).where(ChatSession.username.in_(_USERS)))
        session.commit()
        for username in _USERS:
            row = User.get(session, username)
            if row is not None:
                row.delete(session)


def _events(body: str) -> list[tuple[str, dict[str, object]]]:
    """解析 SSE 文本中的事件名和 JSON 数据。"""
    events: list[tuple[str, dict[str, object]]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        name = ""
        data = ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
        events.append((name, json.loads(data)))
    return events


def test_每轮回复创建Trace并在结束后保存状态与首轮标题() -> None:
    """按会话流式回复，持久化每轮输入和状态，并保留手动标题。"""
    engine, codes, client, tokens = _setup()
    owner_token = tokens[_USERS[0]]
    other_token = tokens[_USERS[1]]
    owner_headers = {TOKEN_HEADER: owner_token}
    other_headers = {TOKEN_HEADER: other_token}
    try:
        unauthenticated = client.get("/chat-sessions/unknown/traces")
        assert unauthenticated.status_code == 401
        assert client.post("/replies", json={"text": "旧接口"}, headers=owner_headers).status_code == 404

        created = client.post("/chat-sessions", headers=owner_headers)
        assert created.status_code == 201
        session_id = created.json()["id"]
        blank = client.post(
            f"/chat-sessions/{session_id}/replies",
            json={"text": "  "},
            headers=owner_headers,
        )
        assert blank.status_code == 400
        assert blank.json()["detail"] == "不能为空"
        assert client.get(f"/chat-sessions/{session_id}/traces", headers=owner_headers).json() == {"traces": []}

        text = "检查东区1号线高压水泵阀门运行状况"
        with client.stream(
            "POST",
            f"/chat-sessions/{session_id}/replies",
            json={"text": f"  {text}  ", "username": _USERS[1]},
            headers=owner_headers,
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = "".join(response.iter_text())
        events = _events(body)
        assert events[-1] == ("done", {})
        assert all(name == "chunk" for name, _payload in events[:-1])
        chunks = [payload["text"] for _name, payload in events[:-1]]
        assert all(isinstance(chunk, str) and 0 < len(chunk) <= 4 for chunk in chunks)
        assert "".join(chunks) == mock_reply(text)
        assert all("trace_id" not in payload for _name, payload in events)

        traces_response = client.get(f"/chat-sessions/{session_id}/traces", headers=owner_headers)
        assert traces_response.status_code == 200
        traces = traces_response.json()["traces"]
        assert len(traces) == 1
        assert traces[0]["user_text"] == text
        assert traces[0]["status"] == "complete"
        assert len(traces[0]["id"]) == 32
        session = client.get(f"/chat-sessions/{session_id}", headers=owner_headers).json()
        assert session["title"] == f"{text[:16]}…"

        renamed = client.patch(
            f"/chat-sessions/{session_id}",
            json={"title": "人工命名"},
            headers=owner_headers,
        )
        assert renamed.status_code == 200
        second = client.post(
            f"/chat-sessions/{session_id}/replies",
            json={"text": "复核备用泵"},
            headers=owner_headers,
        )
        assert second.status_code == 200
        history = client.get(f"/chat-sessions/{session_id}/traces", headers=owner_headers).json()["traces"]
        assert [trace["user_text"] for trace in history] == [text, "复核备用泵"]
        assert [trace["status"] for trace in history] == ["complete", "complete"]
        assert client.get(f"/chat-sessions/{session_id}", headers=owner_headers).json()["title"] == "人工命名"

        forbidden_list = client.get(f"/chat-sessions/{session_id}/traces", headers=other_headers)
        forbidden_reply = client.post(
            f"/chat-sessions/{session_id}/replies",
            json={"text": "越权"},
            headers=other_headers,
        )
        missing = client.get("/chat-sessions/not-a-session/traces", headers=other_headers)
        assert (forbidden_list.status_code, forbidden_list.json()) == (missing.status_code, missing.json())
        assert (forbidden_reply.status_code, forbidden_reply.json()) == (missing.status_code, missing.json())
        assert missing.status_code == 404
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()


def test_未登录时拒绝Trace接口() -> None:
    """读取trace和发送回复都需要登录。"""
    engine, codes, client, tokens = _setup()
    try:
        session_id = client.post("/chat-sessions", headers={TOKEN_HEADER: tokens[_USERS[0]]}).json()["id"]
        responses = (
            client.get(f"/chat-sessions/{session_id}/traces"),
            client.post(f"/chat-sessions/{session_id}/replies", json={"text": "检查"}),
        )
        assert all(response.status_code == 401 for response in responses)
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()


def test_流被取消后将Trace标记为失败() -> None:
    """消费者停止读取事件流时保留输入并把trace状态改为failed。"""
    engine, codes, client, tokens = _setup()
    try:
        session_id = client.post("/chat-sessions", headers={TOKEN_HEADER: tokens[_USERS[0]]}).json()["id"]
        service = ChatReplyService(engine)
        trace_id = service.begin_reply(session_id, _USERS[0], "中断场景")

        async def close_after_first_chunk() -> str:
            """收到首段后关闭流，模拟客户端中断。"""
            stream = service.stream_reply(trace_id, "中断场景")
            first = await anext(stream)
            await stream.aclose()
            return first

        first_event = asyncio.run(close_after_first_chunk())
        assert first_event.startswith("event: chunk")
        with Session(engine) as session:
            trace = Trace.get(session, trace_id)
            assert trace is not None
            assert trace.status == "failed"
            assert trace.user_text == "中断场景"
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()


def test_mysql数据库可以持久化完整Trace状态流转() -> None:
    """在项目测试库验证 Trace 外键、排序和完成状态。"""
    engine, codes, client, tokens = _setup(use_mysql=True)
    try:
        headers = {TOKEN_HEADER: tokens[_USERS[0]]}
        session_id = client.post("/chat-sessions", headers=headers).json()["id"]
        response = client.post(
            f"/chat-sessions/{session_id}/replies",
            json={"text": "MySQL Trace"},
            headers=headers,
        )
        assert response.status_code == 200
        assert "event: done" in response.text
        history = client.get(f"/chat-sessions/{session_id}/traces", headers=headers).json()["traces"]
        assert len(history) == 1
        assert history[0]["user_text"] == "MySQL Trace"
        assert history[0]["status"] == "complete"
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()
