# -*- coding: utf-8 -*-
import pytest

from app.users.jwt_token import JwtError
from app.users.jwt_token import JwtToken

_SECRET = "test-secret-key-at-least-32-bytes"
_OTHER_SECRET = "another-test-secret-key-32-bytes!"


def test_签发后只能解析出用户名() -> None:
    """令牌能还原签发时的用户名，解析结果只有用户名。"""
    token = JwtToken(_SECRET, expires_minutes=60).sign("ann")
    assert JwtToken(_SECRET, expires_minutes=60).parse(token) == "ann"


def test_签名不对时解析失败() -> None:
    """密钥不一致或令牌被改过时，不能得到用户名。"""
    token = JwtToken(_SECRET, expires_minutes=60).sign("ann")
    with pytest.raises(JwtError):
        JwtToken(_OTHER_SECRET, expires_minutes=60).parse(token)
    changed = token[:-1] + ("a" if token[-1] != "a" else "b")
    with pytest.raises(JwtError):
        JwtToken(_SECRET, expires_minutes=60).parse(changed)


def test_过期后解析失败() -> None:
    """过期令牌不能解析出用户名。"""
    token = JwtToken(_SECRET, expires_minutes=-1).sign("ann")
    with pytest.raises(JwtError):
        JwtToken(_SECRET, expires_minutes=60).parse(token)
