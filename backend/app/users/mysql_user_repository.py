# -*- coding: utf-8 -*-
"""MySQL 用户仓库。"""

import pymysql

from app.config.settings import MysqlSettings
from app.users.user_record import UserRecord
from app.users.user_repository import UserRepository
from app.users.user_repository import UsernameAlreadyExists


class MysqlUserRepository(UserRepository):
    """把用户写入 MySQL。用户名是唯一标识。"""

    def __init__(self, settings: MysqlSettings) -> None:
        """保存连接参数，不在构造时访问数据库。"""
        self._settings = settings

    def ensure_table(self) -> None:
        """保证用户表存在。"""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        username VARCHAR(64) NOT NULL PRIMARY KEY,
                        salt VARCHAR(255) NOT NULL,
                        password_hash VARCHAR(255) NOT NULL
                    )
                    """
                )
            connection.commit()

    def save(self, record: UserRecord) -> None:
        """保存一个新用户。用户名已存在时失败。"""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                try:
                    cursor.execute(
                        "INSERT INTO users (username, salt, password_hash) VALUES (%s, %s, %s)",
                        (record.username, record.salt, record.password_hash),
                    )
                except pymysql.IntegrityError as error:
                    raise UsernameAlreadyExists(record.username) from error
            connection.commit()

    def find_by_username(self, username: str) -> UserRecord | None:
        """按用户名查找。没有这个用户时返回空。"""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT username, salt, password_hash FROM users WHERE username = %s",
                    (username,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return UserRecord(username=row[0], salt=row[1], password_hash=row[2])

    def delete_by_username(self, username: str) -> None:
        """删除指定用户。没有这个用户时不做任何事。"""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM users WHERE username = %s", (username,))
            connection.commit()

    def _connect(self):
        """按配置打开一个连接。"""
        return pymysql.connect(
            host=self._settings.host,
            port=self._settings.port,
            user=self._settings.user,
            password=self._settings.password,
            database=self._settings.database,
            charset="utf8mb4",
            autocommit=False,
        )
