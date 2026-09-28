# -*- coding: utf-8 -*-
from app.users.password import Password


def test_同一密码两次加密结果不同() -> None:
    """每条密码使用自己的盐，所以同样的明文不会得到同样的结果。"""
    first = Password.encrypt("secret-pass")
    second = Password.encrypt("secret-pass")
    assert first.salt != second.salt
    assert first.password_hash != second.password_hash


def test_用原盐可以核对明文() -> None:
    """保存盐和加密结果后，同一套算法能认出原来的明文。"""
    sealed = Password.encrypt("secret-pass")
    assert sealed.matches("secret-pass")
    assert not sealed.matches("other-pass")


def test_不能从结果还原明文() -> None:
    """加密结果里没有明文，也没有还原方法。"""
    sealed = Password.encrypt("secret-pass")
    assert sealed.password_hash != "secret-pass"
    assert "secret-pass" not in sealed.salt
    assert "secret-pass" not in sealed.password_hash
    assert not hasattr(sealed, "decrypt")
