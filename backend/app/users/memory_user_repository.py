# -*- coding: utf-8 -*-
"""不连接数据库的用户仓库，供不依赖 MySQL 的测试使用。"""

from app.users.user_record import UserRecord
from app.users.user_repository import UserRepository
from app.users.user_repository import UsernameAlreadyExists


class MemoryUserRepository(UserRepository):
    """把用户放在内存字典里。"""

    def __init__(self) -> None:
        """从空集合开始。"""
        self._records: dict[str, UserRecord] = {}

    def save(self, record: UserRecord) -> None:
        """保存一个新用户。用户名已存在时失败。"""
        if record.username in self._records:
            raise UsernameAlreadyExists(record.username)
        self._records[record.username] = record

    def find_by_username(self, username: str) -> UserRecord | None:
        """按用户名查找。没有这个用户时返回空。"""
        return self._records.get(username)

    def delete_by_username(self, username: str) -> None:
        """删除指定用户。没有这个用户时不做任何事。"""
        self._records.pop(username, None)
