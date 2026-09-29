# -*- coding: utf-8 -*-
"""模拟回复的 SSE。未登录拒绝，空文本拒绝，登录后按段推送固定文案。"""

import json

from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.auth import TOKEN_HEADER
from app.chats.mock_reply import mock_reply
from app.main import create_app
from app.users.login import session_key
from app.users.password import Password
from app.users.user_model import User
from tests.dev_redis import open_test_redis
from tests.mysql import open_test_database

_USER = "reply-user"
_PASSWORD = "reply-secret"
_TTL_SECONDS = 60


def _delete(engine: Engine, username: str) -> None:
    """清掉本用例使用的用户。"""
    with Session(engine) as session:
        row = User.get(session, username)
        if row is not None:
            row.delete(session)


def _create(engine: Engine, username: str, password: str) -> None:
    """写入一个已加密密码的用户。"""
    sealed = Password.encrypt(password)
    with Session(engine) as session:
        User.create(session, username=username, salt=sealed.salt, password_hash=sealed.password_hash)


def _app() -> tuple[Engine, Redis, TestClient]:
    """连上测试库和测试 Redis。"""
    _settings, engine = open_test_database()
    codes = open_test_redis()
    User.create_table(engine)
    _delete(engine, _USER)
    client = TestClient(create_app(engine, codes, _TTL_SECONDS))
    return engine, codes, client


def _login(client: TestClient) -> str:
    """用本用例用户登录并返回 token。"""
    response = client.post("/session", json={"username": _USER, "password": _PASSWORD})
    assert response.status_code == 200
    token = response.json()["token"]
    assert isinstance(token, str)
    return token


def _events(body: str) -> list[tuple[str, dict[str, object]]]:
    """按空行拆开 SSE，读出事件名和 data。"""
    found: list[tuple[str, dict[str, object]]] = []
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
        found.append((name, json.loads(data)))
    return found


def test_未登录时拒绝回复() -> None:
    """没有 satoken 时不建立事件流。"""
    engine, _codes, client = _app()
    try:
        response = client.post("/replies", json={"text": "阀门"})
        assert response.status_code == 401
        assert response.json()["detail"] == "未登录"
        assert "text/event-stream" not in response.headers.get("content-type", "")
    finally:
        _delete(engine, _USER)


def test_空文本返回_400_且不是事件流() -> None:
    """空白和缺少 text 都拒绝，响应是 JSON。"""
    engine, codes, client = _app()
    token = ""
    try:
        _create(engine, _USER, _PASSWORD)
        token = _login(client)
        headers = {TOKEN_HEADER: token}
        blank = client.post("/replies", json={"text": "  "}, headers=headers)
        missing = client.post("/replies", json={}, headers=headers)
        assert blank.status_code == 400
        assert blank.json()["detail"] == "不能为空"
        assert "text/event-stream" not in blank.headers.get("content-type", "")
        assert missing.status_code == 400
        assert missing.json()["detail"] == "不能为空"
    finally:
        if token:
            codes.delete(session_key(token))
        _delete(engine, _USER)


def test_登录后按段推送固定回复并以_done_结束() -> None:
    """chunk 按顺序拼回固定回复，done 不带 trace 编号。"""
    engine, codes, client = _app()
    token = ""
    try:
        _create(engine, _USER, _PASSWORD)
        token = _login(client)
        with client.stream(
            "POST",
            "/replies",
            json={"text": "  阀门  "},
            headers={TOKEN_HEADER: token},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = "".join(response.iter_text())
        events = _events(body)
        assert events[-1] == ("done", {})
        chunks = [item[1] for item in events[:-1]]
        assert chunks
        assert all(item[0] == "chunk" for item in events[:-1])
        texts = [chunk["text"] for chunk in chunks]
        assert all(isinstance(text, str) and text and len(text) <= 4 for text in texts)
        expected = mock_reply("阀门")
        assert len(expected) >= 400
        assert "1 号线压力" in expected
        assert "3 号泵房阀门" in expected
        assert "".join(texts) == expected
        assert "trace_id" not in body
    finally:
        if token:
            codes.delete(session_key(token))
        _delete(engine, _USER)
