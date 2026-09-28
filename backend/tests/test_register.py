# -*- coding: utf-8 -*-
import logging

import pytest
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.main import create_app
from app.users.password import Password
from app.users.registration import verification_code_key
from app.users.user_model import User
from tests.mysql import open_test_database
from tests.dev_redis import open_test_redis

_USERNAME = "ann-register"


def _delete_user(engine: Engine) -> None:
    """清掉本用例使用的用户。"""
    with Session(engine) as session:
        row = User.get(session, _USERNAME)
        if row is not None:
            row.delete(session)


def _open() -> tuple[Engine, Redis, TestClient]:
    """连上测试库和测试 Redis，并清掉本用例留下的用户和验证码。"""
    _settings, engine = open_test_database()
    codes = open_test_redis()
    User.create_table(engine)
    _delete_user(engine)
    codes.delete(verification_code_key(_USERNAME))
    return engine, codes, TestClient(create_app(engine, codes))


def _code_from_log(text: str) -> str:
    """从日志里取出验证码。"""
    for line in text.splitlines():
        if "注册验证码" in line and _USERNAME in line:
            return line.rsplit(" ", 1)[-1]
    raise AssertionError("日志中没有验证码")


def test_验证码只出现在日志中并且可以完成注册(caplog: pytest.LogCaptureFixture) -> None:
    """发送验证码的响应不含验证码。验证码在 Redis 中，用它可以注册。"""
    engine, codes, client = _open()
    try:
        with caplog.at_level(logging.INFO):
            sent = client.post("/verification-codes", json={"username": _USERNAME})
        assert sent.status_code == 200
        assert sent.json()["message"] == "已发送"
        code = _code_from_log(caplog.text)
        assert code not in sent.text
        assert codes.get(verification_code_key(_USERNAME)) == code
        assert codes.ttl(verification_code_key(_USERNAME)) > 0
        created = client.post(
            "/users",
            json={"username": _USERNAME, "password": "secret-pass", "code": code},
        )
        assert created.status_code == 200
        assert created.json()["message"] == "用户已创建"
        with Session(engine) as session:
            row = User.get(session, _USERNAME)
            assert row is not None
            assert Password(salt=row.salt, password_hash=row.password_hash).matches("secret-pass")
        assert codes.get(verification_code_key(_USERNAME)) is None
    finally:
        _delete_user(engine)
        codes.delete(verification_code_key(_USERNAME))


def test_空用户名不能发送验证码() -> None:
    """空白用户名在入参校验时拒绝，不生成验证码。"""
    _engine, _codes, client = _open()
    sent = client.post("/verification-codes", json={"username": "  "})
    assert sent.status_code == 422


def test_用户名已存在不能发送验证码() -> None:
    """已经注册的用户名不能再要验证码。"""
    engine, codes, client = _open()
    with Session(engine) as session:
        User.create(session, username=_USERNAME, salt="salt", password_hash="hash")
    try:
        sent = client.post("/verification-codes", json={"username": _USERNAME})
        assert sent.status_code == 400
        assert sent.json()["detail"] == "用户名已存在"
        assert codes.get(verification_code_key(_USERNAME)) is None
    finally:
        _delete_user(engine)
        codes.delete(verification_code_key(_USERNAME))


def test_验证码错误或用户名已存在不能注册(caplog: pytest.LogCaptureFixture) -> None:
    """验证码不对不写入。用户名已存在时拒绝，且不改已有记录。"""
    engine, codes, client = _open()
    try:
        with caplog.at_level(logging.INFO):
            sent = client.post("/verification-codes", json={"username": _USERNAME})
        assert sent.status_code == 200
        code = _code_from_log(caplog.text)
        wrong = "000000" if code != "000000" else "000001"
        rejected = client.post(
            "/users",
            json={"username": _USERNAME, "password": "secret-pass", "code": wrong},
        )
        assert rejected.status_code == 400
        assert rejected.json()["detail"] == "验证码错误"
        with Session(engine) as session:
            assert User.get(session, _USERNAME) is None
            User.create(session, username=_USERNAME, salt="salt", password_hash="hash")
        exists = client.post(
            "/users",
            json={"username": _USERNAME, "password": "secret-pass", "code": code},
        )
        assert exists.status_code == 400
        assert exists.json()["detail"] == "用户名已存在"
        with Session(engine) as session:
            row = User.get(session, _USERNAME)
            assert row is not None
            assert row.salt == "salt"
        assert codes.get(verification_code_key(_USERNAME)) == code
    finally:
        _delete_user(engine)
        codes.delete(verification_code_key(_USERNAME))
