# -*- coding: utf-8 -*-
"""聊天会话接口的持久化、鉴权和用户隔离。"""

from datetime import UTC
from datetime import datetime
import re

from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import delete
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.auth import TOKEN_HEADER
from app.chats.chat_session import ChatSession
from app.main import create_app
from app.users.login import session_key
from app.users.password import Password
from app.users.user_model import User
from tests.dev_redis import open_test_redis
from tests.mysql import open_test_database

_USERS = ("chat-session-owner", "chat-session-other")
_PASSWORD = "session-secret"
_TTL_SECONDS = 60


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


def _clean(engine: Engine, codes: Redis | MemoryRedis, tokens: list[str]) -> None:
    """清掉会话、用户和本用例签发的 token。"""
    for token in tokens:
        codes.delete(session_key(token))
    with Session(engine) as session:
        session.execute(delete(ChatSession).where(ChatSession.username.in_(_USERS)))
        session.commit()
        for username in _USERS:
            row = User.get(session, username)
            if row is not None:
                row.delete(session)


def _create_user(engine: Engine, username: str) -> None:
    """写入本用例的登录用户。"""
    sealed = Password.encrypt(_PASSWORD)
    with Session(engine) as session:
        User.create(session, username=username, salt=sealed.salt, password_hash=sealed.password_hash)


def _setup() -> tuple[Engine, Redis, TestClient]:
    """连上测试依赖并创建会话接口客户端。"""
    _settings, engine = open_test_database()
    codes = open_test_redis()
    User.create_table(engine)
    ChatSession.create_table(engine)
    _clean(engine, codes, [])
    client = TestClient(create_app(engine, codes, _TTL_SECONDS))
    return engine, codes, client


def _sqlite_setup() -> tuple[Engine, MemoryRedis, TestClient]:
    """在共享内存数据库中创建接口客户端。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    codes = MemoryRedis()
    client = TestClient(create_app(engine, codes, _TTL_SECONDS))
    return engine, codes, client


def _login(client: TestClient, username: str) -> str:
    """用指定用户登录并返回 token。"""
    response = client.post("/session", json={"username": username, "password": _PASSWORD})
    assert response.status_code == 200
    return response.json()["token"]


def test_未登录时拒绝所有会话接口() -> None:
    """列表、创建和读取都受鉴权保护。"""
    engine, codes, client = _setup()
    try:
        responses = (
            client.get("/chat-sessions"),
            client.post("/chat-sessions"),
            client.get("/chat-sessions/unknown"),
        )
        assert all(response.status_code == 401 for response in responses)
        assert all(response.json()["detail"] == "未登录" for response in responses)
    finally:
        _clean(engine, codes, [])


def test_会话按当前用户创建读取并阻止伪造归属() -> None:
    """创建时只使用 token 用户，且他人编号与未知编号无法区分。"""
    engine, codes, client = _setup()
    tokens: list[str] = []
    try:
        for username in _USERS:
            _create_user(engine, username)
        owner_token = _login(client, _USERS[0])
        other_token = _login(client, _USERS[1])
        tokens.extend((owner_token, other_token))

        created = client.post(
            "/chat-sessions",
            json={"username": _USERS[1]},
            headers={TOKEN_HEADER: owner_token},
        )
        assert created.status_code == 201
        body = created.json()
        assert re.fullmatch(r"[0-9a-f]{32}", body["id"])
        assert body["title"] == "新会话"
        assert datetime.fromisoformat(body["updated_at"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0

        listed = client.get("/chat-sessions", headers={TOKEN_HEADER: owner_token})
        assert listed.status_code == 200
        assert listed.json()["sessions"] == [body]
        read = client.get(f"/chat-sessions/{body['id']}", headers={TOKEN_HEADER: owner_token})
        assert read.status_code == 200
        assert read.json() == body

        renamed = client.patch(
            f"/chat-sessions/{body['id']}",
            json={"title": "  巡检计划  "},
            headers={TOKEN_HEADER: owner_token},
        )
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "巡检计划"
        assert datetime.fromisoformat(renamed.json()["updated_at"].replace("Z", "+00:00")) >= datetime.fromisoformat(
            body["updated_at"].replace("Z", "+00:00")
        )
        assert client.get(f"/chat-sessions/{body['id']}", headers={TOKEN_HEADER: owner_token}).json() == renamed.json()

        foreign = client.get(f"/chat-sessions/{body['id']}", headers={TOKEN_HEADER: other_token})
        unknown = client.get("/chat-sessions/00000000000000000000000000000000", headers={TOKEN_HEADER: other_token})
        assert (foreign.status_code, foreign.json()) == (unknown.status_code, unknown.json())
        assert foreign.status_code == 404
        assert foreign.json()["detail"] == "会话不存在"

        other_list = client.get("/chat-sessions", headers={TOKEN_HEADER: other_token})
        assert other_list.status_code == 200
        assert other_list.json() == {"sessions": []}
    finally:
        _clean(engine, codes, tokens)


def test_会话列表按更新时间倒序排列() -> None:
    """同一用户的会话按更新时间由新到旧返回。"""
    engine, codes, client = _setup()
    tokens: list[str] = []
    try:
        _create_user(engine, _USERS[0])
        token = _login(client, _USERS[0])
        tokens.append(token)
        headers = {TOKEN_HEADER: token}
        older = client.post("/chat-sessions", headers=headers).json()
        newer = client.post("/chat-sessions", headers=headers).json()

        with Session(engine) as session:
            old_row = ChatSession.get(session, older["id"])
            new_row = ChatSession.get(session, newer["id"])
            assert old_row is not None
            assert new_row is not None
            old_row.update(session, updated_at=datetime(2026, 1, 1, tzinfo=UTC))
            new_row.update(session, updated_at=datetime(2026, 1, 2, tzinfo=UTC))

        listed = client.get("/chat-sessions", headers=headers)
        assert [item["id"] for item in listed.json()["sessions"]] == [newer["id"], older["id"]]
    finally:
        _clean(engine, codes, tokens)


def test_模型创建会话并按用户和更新时间查询() -> None:
    """在轻量数据库中验证默认字段、用户过滤和倒序查询。"""
    engine = create_engine("sqlite://")
    User.create_table(engine)
    ChatSession.create_table(engine)
    with Session(engine) as session:
        for username in _USERS:
            User.create(session, username=username, salt="salt", password_hash="hash")
        earlier = ChatSession.create_for_user(session, _USERS[0])
        later = ChatSession.create_for_user(session, _USERS[0])
        ChatSession.create_for_user(session, _USERS[1])
        assert earlier.created_at == earlier.updated_at
        earlier.update(session, updated_at=datetime(2026, 1, 1, tzinfo=UTC))
        later.update(session, updated_at=datetime(2026, 1, 2, tzinfo=UTC))

        rows = ChatSession.list_for_user(session, _USERS[0])
        assert [row.id for row in rows] == [later.id, earlier.id]
        assert all(row.username == _USERS[0] for row in rows)
        assert rows[0].title == "新会话"
        assert re.fullmatch(r"[0-9a-f]{32}", rows[0].id)
        assert ChatSession.get_for_user(session, rows[0].id, _USERS[0]) is not None
        assert ChatSession.get_for_user(session, rows[0].id, _USERS[1]) is None


def test_会话接口隔离用户并对未知编号返回相同错误() -> None:
    """端到端验证会话接口从 satoken 取归属并隐藏他人会话。"""
    engine, codes, client = _sqlite_setup()
    tokens: list[str] = []
    try:
        unauthorized = (
            client.get("/chat-sessions"),
            client.post("/chat-sessions"),
            client.get("/chat-sessions/unknown"),
            client.patch("/chat-sessions/unknown", json={"title": "新标题"}),
        )
        assert all(response.status_code == 401 for response in unauthorized)

        for username in _USERS:
            _create_user(engine, username)
        owner_token = _login(client, _USERS[0])
        other_token = _login(client, _USERS[1])
        tokens.extend((owner_token, other_token))

        created = client.post(
            "/chat-sessions",
            json={"username": _USERS[1]},
            headers={TOKEN_HEADER: owner_token},
        )
        assert created.status_code == 201
        assert created.json()["title"] == "新会话"
        assert created.json()["updated_at"].endswith("Z")
        session_id = created.json()["id"]
        owner_list = client.get("/chat-sessions", headers={TOKEN_HEADER: owner_token})
        assert [item["id"] for item in owner_list.json()["sessions"]] == [session_id]
        assert client.get(f"/chat-sessions/{session_id}", headers={TOKEN_HEADER: owner_token}).status_code == 200

        foreign = client.get(f"/chat-sessions/{session_id}", headers={TOKEN_HEADER: other_token})
        missing = client.get("/chat-sessions/not-a-session", headers={TOKEN_HEADER: other_token})
        assert (foreign.status_code, foreign.json()) == (missing.status_code, missing.json())
        assert foreign.status_code == 404
        assert foreign.json() == {"detail": "会话不存在"}

        renamed = client.patch(
            f"/chat-sessions/{session_id}",
            json={"title": "  每日设备巡检  "},
            headers={TOKEN_HEADER: owner_token},
        )
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "每日设备巡检"
        assert client.get(f"/chat-sessions/{session_id}", headers={TOKEN_HEADER: owner_token}).json() == renamed.json()
        assert client.patch(
            f"/chat-sessions/{session_id}",
            json={"title": "   "},
            headers={TOKEN_HEADER: owner_token},
        ).status_code == 422
        assert client.patch(
            f"/chat-sessions/{session_id}",
            json={"title": "x" * 256},
            headers={TOKEN_HEADER: owner_token},
        ).status_code == 422
        assert client.patch(
            f"/chat-sessions/{session_id}",
            json={"title": "改名", "username": _USERS[1]},
            headers={TOKEN_HEADER: owner_token},
        ).status_code == 422

        foreign_rename = client.patch(
            f"/chat-sessions/{session_id}",
            json={"title": "不能改别人的"},
            headers={TOKEN_HEADER: other_token},
        )
        missing_rename = client.patch(
            "/chat-sessions/not-a-session",
            json={"title": "不存在"},
            headers={TOKEN_HEADER: other_token},
        )
        assert (foreign_rename.status_code, foreign_rename.json()) == (
            missing_rename.status_code,
            missing_rename.json(),
        )
        assert foreign_rename.status_code == 404
    finally:
        _clean(engine, codes, tokens)
        engine.dispose()
