# -*- coding: utf-8 -*-
"""用户仓库。用仓库模式把存取和具体数据库分开，以后 session 只按用户名读取。"""

from abc import ABC
from abc import abstractmethod

from app.users.user_record import UserRecord


class UsernameAlreadyExists(Exception):
    """用户名已经被占用。"""


class UserRepository(ABC):
    """按用户名保存和查询用户。"""

    @abstractmethod
    def save(self, record: UserRecord) -> None:
        """保存一个新用户。用户名已存在时失败。"""

    @abstractmethod
    def find_by_username(self, username: str) -> UserRecord | None:
        """按用户名查找。没有这个用户时返回空。"""

    @abstractmethod
    def delete_by_username(self, username: str) -> None:
        """删除指定用户。没有这个用户时不做任何事。"""
