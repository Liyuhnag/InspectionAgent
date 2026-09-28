# -*- coding: utf-8 -*-
"""MySQL 用户仓库。"""

from sqlalchemy import URL
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import MysqlSettings
from app.users.user_model import User
from app.users.user_record import UserRecord
from app.users.user_repository import UserRepository
from app.users.user_repository import UsernameAlreadyExists


class MysqlUserRepository(UserRepository):
    """把用户写入 MySQL。存取都走用户模型上的增删改查。"""

    def __init__(self, settings: MysqlSettings) -> None:
        """按配置准备连接，不在构造时访问数据库。"""
        url = URL.create(
            drivername="mysql+pymysql",
            username=settings.user,
            password=settings.password,
            host=settings.host,
            port=settings.port,
            database=settings.database,
            query={"charset": "utf8mb4"},
        )
        self._engine = create_engine(url)

    def ensure_table(self) -> None:
        """按用户模型建表。"""
        User.create_table(self._engine)

    def save(self, record: UserRecord) -> None:
        """保存一个新用户。用户名已存在时失败。"""
        with Session(self._engine) as session:
            try:
                User.create(
                    session,
                    username=record.username,
                    salt=record.salt,
                    password_hash=record.password_hash,
                )
            except IntegrityError as error:
                raise UsernameAlreadyExists(record.username) from error

    def find_by_username(self, username: str) -> UserRecord | None:
        """按用户名查找。没有这个用户时返回空。"""
        with Session(self._engine) as session:
            row = User.get(session, username)
            if row is None:
                return None
            return UserRecord(username=row.username, salt=row.salt, password_hash=row.password_hash)

    def delete_by_username(self, username: str) -> None:
        """删除指定用户。没有这个用户时不做任何事。"""
        with Session(self._engine) as session:
            row = User.get(session, username)
            if row is None:
                return
            row.delete(session)
