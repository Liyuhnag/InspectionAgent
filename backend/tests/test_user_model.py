# -*- coding: utf-8 -*-
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import MysqlSettings
from app.users.mysql_user_repository import MysqlUserRepository
from app.users.user_model import User
from app.users.user_record import UserRecord
from app.users.user_repository import UsernameAlreadyExists


def test_定义用户模型后即可增删改查() -> None:
    """用户模型不写 SQL，也能完成创建、读取、更新和删除。"""
    engine = create_engine("sqlite://")
    User.create_table(engine)
    with Session(engine) as session:
        User.create(session, username="ann", salt="salt", password_hash="hash")
        found = User.get(session, "ann")
        assert found is not None
        assert found.salt == "salt"
        found.update(session, salt="next")
        again = User.get(session, "ann")
        assert again is not None
        assert again.salt == "next"
        again.delete(session)
        assert User.get(session, "ann") is None


def test_重复用户名不能再次创建() -> None:
    """主键冲突时创建失败，并回滚这一次插入。"""
    engine = create_engine("sqlite://")
    User.create_table(engine)
    with Session(engine) as session:
        User.create(session, username="ann", salt="salt", password_hash="hash")
        with pytest.raises(IntegrityError):
            User.create(session, username="ann", salt="other", password_hash="hash")
        found = User.get(session, "ann")
        assert found is not None
        assert found.salt == "salt"


def test_仓库通过模型拒绝重复用户名() -> None:
    """仓库把模型的唯一约束冲突转成用户名已存在。"""
    settings = MysqlSettings(
        host="127.0.0.1",
        port=3306,
        database="inspection",
        user="root",
        password="secret",
    )
    repository = MysqlUserRepository(settings)
    repository._engine = create_engine("sqlite://")
    repository.ensure_table()
    repository.save(UserRecord(username="ann", salt="salt", password_hash="hash"))
    with pytest.raises(UsernameAlreadyExists):
        repository.save(UserRecord(username="ann", salt="other", password_hash="hash"))
    found = repository.find_by_username("ann")
    assert found is not None
    assert found.salt == "salt"
