# -*- coding: utf-8 -*-
"""密码的加盐单向加密。"""

import hashlib
import hmac
import secrets

_ITERATIONS = 600_000


class Password:
    """一条已经加密的密码。只保留盐和加密结果。"""

    def __init__(self, salt: str, password_hash: str) -> None:
        """保存盐和单向加密结果。"""
        self.salt = salt
        self.password_hash = password_hash

    @classmethod
    def encrypt(cls, plain: str) -> "Password":
        """为这条明文单独生成盐，并做单向加密。"""
        salt = secrets.token_hex(16)
        return cls(salt=salt, password_hash=_digest(plain, salt))

    def matches(self, plain: str) -> bool:
        """用保存的盐和同一算法核对明文。"""
        actual = _digest(plain, self.salt)
        return hmac.compare_digest(actual, self.password_hash)


def _digest(plain: str, salt: str) -> str:
    """用 PBKDF2 计算单向结果。"""
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS)
    return digest.hex()
