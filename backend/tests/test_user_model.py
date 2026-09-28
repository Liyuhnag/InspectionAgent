# -*- coding: utf-8 -*-
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.users.user_model import User
from tests.mysql import open_test_database


def _reset(session: Session) -> None:
    """清掉本用例使用的用户，避免留在测试库里。"""
    row = User.get(session, "ann")
    if row is not None:
        row.delete(session)


def test_定义用户模型后即可增删改查() -> None:
    """用户模型在测试库上完成创建、读取、更新和删除。"""
    _settings, engine = open_test_database()
    User.create_table(engine)
    with Session(engine) as session:
        _reset(session)
        try:
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
        finally:
            _reset(session)


def test_重复用户名不能再次创建() -> None:
    """主键冲突时创建失败，测试库里仍保留原来的盐。"""
    _settings, engine = open_test_database()
    User.create_table(engine)
    with Session(engine) as session:
        _reset(session)
        try:
            User.create(session, username="ann", salt="salt", password_hash="hash")
            with pytest.raises(IntegrityError):
                User.create(session, username="ann", salt="other", password_hash="hash")
            found = User.get(session, "ann")
            assert found is not None
            assert found.salt == "salt"
        finally:
            _reset(session)
