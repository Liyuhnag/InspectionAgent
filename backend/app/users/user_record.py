# -*- coding: utf-8 -*-
"""用户账号在库中的形态。"""


class UserRecord:
    """已保存的用户。密码只保留盐和加密结果。"""

    def __init__(self, username: str, salt: str, password_hash: str) -> None:
        """保存用户名和密码材料。"""
        self.username = username
        self.salt = salt
        self.password_hash = password_hash
