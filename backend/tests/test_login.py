# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.routes.session import TOKEN_HEADER
from app.main import DEV_ORIGINS
from app.main import create_app
from app.users.login import session_key
from app.users.password import Password
from app.users.user_model import User
from tests.dev_redis import open_test_redis
from tests.mysql import open_test_database

_ANN = "ann-login"
_BOB = "bob-login"
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


def _clear_session(codes: Redis, token: str) -> None:
    """清掉本用例留下的会话。"""
    if token:
        codes.delete(session_key(token))


def _app() -> tuple[Engine, Redis, TestClient]:
    """连上测试库和测试 Redis。"""
    _settings, engine = open_test_database()
    codes = open_test_redis()
    User.create_table(engine)
    _delete(engine, _ANN)
    _delete(engine, _BOB)
    client = TestClient(create_app(engine, codes, _TTL_SECONDS))
    return engine, codes, client


def test_密码正确时返回_token_且_redis_只存哈希() -> None:
    """登录响应带 token。Redis 的键是哈希，值是用户名。"""
    engine, codes, client = _app()
    token = ""
    try:
        _create(engine, _ANN, "ann-secret")
        response = client.post("/session", json={"username": _ANN, "password": "ann-secret"})
        assert response.status_code == 200
        assert response.json()["message"] == "已登录"
        token = response.json()["token"]
        assert token
        assert "set-cookie" not in response.headers
        assert codes.get(session_key(token)) == _ANN
        assert codes.get(token) is None
        assert codes.ttl(session_key(token)) > 0
    finally:
        _clear_session(codes, token)
        _delete(engine, _ANN)


def test_密码错误或用户不存在时不签发_token() -> None:
    """两种失败都拒绝，并且响应里没有 token。"""
    engine, _codes, client = _app()
    try:
        _create(engine, _ANN, "ann-secret")
        wrong = client.post("/session", json={"username": _ANN, "password": "nope"})
        missing = client.post("/session", json={"username": "nobody-login", "password": "ann-secret"})
        assert wrong.status_code == 401
        assert missing.status_code == 401
        assert wrong.json()["detail"] == "用户名或密码不正确"
        assert missing.json()["detail"] == "用户名或密码不正确"
        assert "token" not in wrong.json()
        assert "token" not in missing.json()
    finally:
        _delete(engine, _ANN)


def test_当前用户只来自_token_退出后失效() -> None:
    """甲的 token 即使请求体写乙，也只能得到甲。退出后该 token 不能再用。"""
    engine, codes, client = _app()
    ann_token = ""
    bob_token = ""
    try:
        _create(engine, _ANN, "ann-secret")
        _create(engine, _BOB, "bob-secret")
        ann_token = client.post("/session", json={"username": _ANN, "password": "ann-secret"}).json()["token"]
        bob_token = client.post("/session", json={"username": _BOB, "password": "bob-secret"}).json()["token"]
        current = client.request(
            "GET",
            "/session",
            headers={TOKEN_HEADER: ann_token},
            json={"username": _BOB},
        )
        assert current.status_code == 200
        assert current.json()["username"] == _ANN
        bob_current = client.get("/session", headers={TOKEN_HEADER: bob_token})
        assert bob_current.json()["username"] == _BOB
        logged_out = client.delete("/session", headers={TOKEN_HEADER: ann_token})
        assert logged_out.status_code == 200
        assert codes.get(session_key(ann_token)) is None
        again = client.get("/session", headers={TOKEN_HEADER: ann_token})
        assert again.status_code == 401
        assert again.json()["detail"] == "未登录"
        assert client.get("/session", headers={TOKEN_HEADER: bob_token}).json()["username"] == _BOB
    finally:
        _clear_session(codes, ann_token)
        _clear_session(codes, bob_token)
        _delete(engine, _ANN)
        _delete(engine, _BOB)


def test_未知_token_或用户已删除时返回_401() -> None:
    """没有会话或用户已删除时一律 401。"""
    engine, codes, client = _app()
    token = ""
    try:
        assert client.get("/session").status_code == 401
        assert client.get("/session", headers={TOKEN_HEADER: "missing-token"}).status_code == 401
        _create(engine, _ANN, "ann-secret")
        token = client.post("/session", json={"username": _ANN, "password": "ann-secret"}).json()["token"]
        _delete(engine, _ANN)
        gone = client.get("/session", headers={TOKEN_HEADER: token})
        assert gone.status_code == 401
        assert gone.json()["detail"] == "未登录"
        assert codes.get(session_key(token)) is None
    finally:
        _clear_session(codes, token)
        _delete(engine, _ANN)


def test_读取当前用户会刷新过期时间() -> None:
    """空闲计时在成功读取后重新设满。"""
    engine, codes, client = _app()
    token = ""
    try:
        _create(engine, _ANN, "ann-secret")
        token = client.post("/session", json={"username": _ANN, "password": "ann-secret"}).json()["token"]
        codes.expire(session_key(token), 5)
        assert client.get("/session", headers={TOKEN_HEADER: token}).status_code == 200
        assert codes.ttl(session_key(token)) > 5
    finally:
        _clear_session(codes, token)
        _delete(engine, _ANN)


def test_开发来源可以带上_satoken_头() -> None:
    """前端开发来源允许 satoken 头，其他来源不允许。"""
    _engine, _codes, client = _app()
    origin = DEV_ORIGINS[0]
    allowed = client.options(
        "/session",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": TOKEN_HEADER,
        },
    )
    assert allowed.headers["access-control-allow-origin"] == origin
    assert TOKEN_HEADER in allowed.headers["access-control-allow-headers"].lower()
    denied = client.options(
        "/session",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": TOKEN_HEADER,
        },
    )
    assert denied.headers.get("access-control-allow-origin") != "https://evil.example"
