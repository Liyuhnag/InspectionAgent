# -*- coding: utf-8 -*-
"""Trace 持久化、会话归属和回复流生命周期。"""

import asyncio
import json
from contextlib import aclosing
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import anyio
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import text as sql_text
from sqlalchemy import update
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from app.api.auth import TOKEN_HEADER
from app.api.routes.traces import ClosingStreamingResponse
from app.chats.chat_reply import ChatReplyService
from app.chats.mock_reply import mock_reply
from app.chats.chat_session import ChatSession
from app.chats.span import SPAN_TEXT_LIMIT
from app.chats.span import Span
from app.chats.span import clip_text
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
        trace_ids = select(Trace.id).where(Trace.session_id.in_(session_ids))
        session.execute(delete(Span).where(Span.trace_id.in_(trace_ids)))
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
        assert events[-1][0] == "done"
        assert set(events[-1][1]) == {"trace_id", "span_id"}
        assert all(name == "chunk" for name, _payload in events[:-1])
        chunks = [payload["text"] for _name, payload in events[:-1]]
        assert all(isinstance(chunk, str) and 0 < len(chunk) <= 4 for chunk in chunks)
        assert "".join(chunks) == mock_reply(text)
        assert all("trace_id" not in payload for _name, payload in events[:-1])

        traces_response = client.get(f"/chat-sessions/{session_id}/traces", headers=owner_headers)
        assert traces_response.status_code == 200
        traces = traces_response.json()["traces"]
        assert len(traces) == 1
        assert traces[0]["user_text"] == text
        assert traces[0]["status"] == "complete"
        assert len(traces[0]["id"]) == 32
        spans_response = client.get(
            f"/chat-sessions/{session_id}/traces/{traces[0]['id']}/spans",
            headers=owner_headers,
        )
        assert spans_response.status_code == 200
        spans = spans_response.json()["spans"]
        assert len(spans) == 1
        started_at = spans[0].pop("started_at")
        ended_at = spans[0].pop("ended_at")
        assert started_at.endswith("Z")
        assert ended_at.endswith("Z")
        assert started_at <= ended_at
        assert spans == [{
            "id": events[-1][1]["span_id"],
            "sequence": 1,
            "type": "text",
            "status": "complete",
            "parent_span_id": None,
            "agent_name": None,
            "node": None,
            "visible": True,
            "model": None,
            "text": mock_reply(text),
            "truncated": False,
        }]
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
        forbidden_spans = client.get(
            f"/chat-sessions/{session_id}/traces/{traces[0]['id']}/spans",
            headers=other_headers,
        )
        assert (forbidden_spans.status_code, forbidden_spans.json()) == (missing.status_code, missing.json())
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


def _span_row(engine: Engine, span_id: str) -> Span:
    """用新的数据库会话读取 Span，避免读到本进程缓存的旧值。"""
    with Session(engine) as session:
        span = Span.get(session, span_id)
        assert span is not None
        session.expunge(span)
        return span


def _trace_status(engine: Engine, trace_id: str) -> str:
    """用新的数据库会话读取 Trace 状态。"""
    with Session(engine) as session:
        trace = Trace.get(session, trace_id)
        assert trace is not None
        return trace.status


def test_流被取消后将Trace与Span标记为失败并保留已推送正文() -> None:
    """推送期间不写正文；消费者停止读取后一次写入已推送部分并标为failed。"""
    engine, codes, client, tokens = _setup()
    try:
        session_id = client.post("/chat-sessions", headers={TOKEN_HEADER: tokens[_USERS[0]]}).json()["id"]
        service = ChatReplyService(engine)
        trace_id, span_id = service.begin_reply(session_id, _USERS[0], "中断场景")
        created = _span_row(engine, span_id)
        assert (created.status, created.text, created.visible, created.truncated) == ("running", "", True, False)
        assert created.started_at is not None
        assert created.ended_at is None

        async def close_after_two_chunks() -> tuple[list[str], Span]:
            """收到两段后读库，再关闭流，模拟客户端中断。"""
            stream = service.stream_reply(trace_id, span_id, "中断场景")
            events = [await anext(stream), await anext(stream)]
            streaming = _span_row(engine, span_id)
            await stream.aclose()
            return events, streaming

        events, streaming = asyncio.run(close_after_two_chunks())
        assert (streaming.status, streaming.text) == ("running", "")
        assert all(event.startswith("event: chunk") for event in events)
        sent = "".join(json.loads(event.split("data:", 1)[1])["text"] for event in events)
        span = _span_row(engine, span_id)
        assert _trace_status(engine, trace_id) == "failed"
        assert (span.status, span.text, span.truncated) == ("failed", sent, False)
        assert span.ended_at is not None
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()


def test_取消范围内关闭流仍完成失败状态写入() -> None:
    """anyio 取消会反复打断等待，最终写入需要屏蔽取消才能完成。"""
    engine, codes, client, tokens = _setup()
    try:
        session_id = client.post("/chat-sessions", headers={TOKEN_HEADER: tokens[_USERS[0]]}).json()["id"]
        service = ChatReplyService(engine)
        trace_id, span_id = service.begin_reply(session_id, _USERS[0], "取消场景")

        async def cancel_while_reading() -> None:
            """在任务组里读取事件，首段后取消整个任务组。"""
            started = anyio.Event()

            async def consume() -> None:
                """读取事件并在首段后挂起；退出时关闭生成器。"""
                async with aclosing(service.stream_reply(trace_id, span_id, "取消场景")) as stream:
                    async for _event in stream:
                        started.set()
                        await anyio.sleep(10)

            async with anyio.create_task_group() as group:
                group.start_soon(consume)
                await started.wait()
                group.cancel_scope.cancel()

        anyio.run(cancel_while_reading)
        span = _span_row(engine, span_id)
        assert _trace_status(engine, trace_id) == "failed"
        assert span.status == "failed"
        assert len(span.text) > 0
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()


def test_客户端断开时响应关闭生成器并写入失败状态() -> None:
    """发送失败时 Starlette 不关闭生成器，回复响应需要自己关闭，才能立即写库。"""
    engine, codes, client, tokens = _setup()
    try:
        session_id = client.post("/chat-sessions", headers={TOKEN_HEADER: tokens[_USERS[0]]}).json()["id"]
        service = ChatReplyService(engine)
        trace_id, span_id = service.begin_reply(session_id, _USERS[0], "断开场景")
        stream = service.stream_reply(trace_id, span_id, "断开场景")
        response = ClosingStreamingResponse(stream, media_type="text/event-stream")
        bodies: list[bytes] = []

        async def send(message: dict[str, object]) -> None:
            """收到第二段正文时模拟连接已断开。"""
            if message["type"] != "http.response.body":
                return
            if len(bodies) == 2:
                raise OSError("连接已断开")
            bodies.append(message["body"])

        async def run() -> str:
            """推送响应并吞掉模拟的断开错误；在事件循环关闭前读取状态。"""
            try:
                await response.stream_response(send)
            except OSError:
                pass
            return _trace_status(engine, trace_id)

        trace_status = anyio.run(run)
        sent = "".join(json.loads(body.decode().split("data:", 1)[1])["text"] for body in bodies)
        span = _span_row(engine, span_id)
        assert trace_status == "failed"
        assert span.status == "failed"
        assert span.text.startswith(sent)
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()


def test_类型和状态只接受枚举中定义的值() -> None:
    """写入或读出未定义的类型、状态都报错；MySQL 仍建 VARCHAR 列，不建 ENUM 或 CHECK。"""
    engine, codes, client, tokens = _setup()
    try:
        session_id = client.post("/chat-sessions", headers={TOKEN_HEADER: tokens[_USERS[0]]}).json()["id"]
        trace_id, span_id = ChatReplyService(engine).begin_reply(session_id, _USERS[0], "枚举场景")
        invalid_writes = ((Span, span_id, "type", "unknown"), (Span, span_id, "status", "paused"),
                          (Trace, trace_id, "status", "paused"))
        for model, row_id, column, value in invalid_writes:
            with Session(engine) as session:
                row = model.get(session, row_id)
                setattr(row, column, value)
                with pytest.raises(StatementError):
                    session.commit()

        with Session(engine) as session:
            session.execute(sql_text("UPDATE spans SET status = 'paused' WHERE id = :id"), {"id": span_id})
            session.execute(sql_text("UPDATE traces SET status = 'paused' WHERE id = :id"), {"id": trace_id})
            session.commit()
        for model, row_id in ((Span, span_id), (Trace, trace_id)):
            with Session(engine) as session:
                with pytest.raises(LookupError):
                    model.get(session, row_id)
        with Session(engine) as session:
            session.execute(sql_text("UPDATE spans SET status = 'running' WHERE id = :id"), {"id": span_id})
            session.execute(sql_text("UPDATE traces SET status = 'running' WHERE id = :id"), {"id": trace_id})
            session.commit()

        span_ddl = str(CreateTable(Span.__table__).compile(dialect=mysql.dialect()))
        trace_ddl = str(CreateTable(Trace.__table__).compile(dialect=mysql.dialect()))
        assert "type VARCHAR(32)" in span_ddl
        assert "status VARCHAR(16)" in span_ddl
        assert "status VARCHAR(16)" in trace_ddl
        assert all(word not in ddl for word in ("ENUM", "CHECK") for ddl in (span_ddl, trace_ddl))
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()


def test_正文按UTF8字节截断且不切开字符() -> None:
    """超过上限时截在字符边界并标记截断，未超过时原样返回。"""
    assert clip_text("阀门ab", 7) == ("阀门a", True)
    assert clip_text("阀门ab", 5) == ("阀", True)
    assert clip_text("阀门ab", 8) == ("阀门ab", False)
    assert clip_text("", 0) == ("", False)
    assert SPAN_TEXT_LIMIT == 64 * 1024


def test_超长正文写入时截断() -> None:
    """推送给客户端的是全文，写库的正文不超过上限并标记截断。"""
    engine, codes, client, tokens = _setup()
    try:
        session_id = client.post("/chat-sessions", headers={TOKEN_HEADER: tokens[_USERS[0]]}).json()["id"]
        service = ChatReplyService(engine, text_limit=10)
        trace_id, span_id = service.begin_reply(session_id, _USERS[0], "截断场景")

        async def read_all() -> list[str]:
            """读完整条事件流。"""
            return [event async for event in service.stream_reply(trace_id, span_id, "截断场景")]

        events = asyncio.run(read_all())
        sent = "".join(json.loads(event.split("data:", 1)[1])["text"] for event in events[:-1])
        assert sent == mock_reply("截断场景")
        span = _span_row(engine, span_id)
        assert span.status == "complete"
        assert span.truncated is True
        assert span.text == clip_text(sent, 10)[0]
        assert len(span.text.encode("utf-8")) <= 10
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()


def test_启动清理只把过期的running标为失败() -> None:
    """超过时限的 running Trace 和 Span 改为 failed，时限内的不变。"""
    engine, codes, client, tokens = _setup()
    try:
        session_id = client.post("/chat-sessions", headers={TOKEN_HEADER: tokens[_USERS[0]]}).json()["id"]
        service = ChatReplyService(engine)
        stale_trace, stale_span = service.begin_reply(session_id, _USERS[0], "过期")
        fresh_trace, fresh_span = service.begin_reply(session_id, _USERS[0], "新近")
        old = datetime.now(UTC) - timedelta(minutes=11)
        with Session(engine) as session:
            session.execute(update(Trace).where(Trace.id == stale_trace).values(created_at=old))
            session.execute(update(Span).where(Span.id == stale_span).values(started_at=old))
            session.commit()

        service.fail_stale_replies()

        assert _trace_status(engine, stale_trace) == "failed"
        assert _trace_status(engine, fresh_trace) == "running"
        swept = _span_row(engine, stale_span)
        assert swept.status == "failed"
        assert swept.ended_at is not None
        assert _span_row(engine, fresh_span).status == "running"
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
        spans = client.get(
            f"/chat-sessions/{session_id}/traces/{history[0]['id']}/spans",
            headers=headers,
        ).json()["spans"]
        assert len(spans) == 1
        assert spans[0]["type"] == "text"
        assert spans[0]["status"] == "complete"
        assert spans[0]["text"] == mock_reply("MySQL Trace")
        assert spans[0]["started_at"] <= spans[0]["ended_at"]
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()
