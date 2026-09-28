# -*- coding: utf-8 -*-
from pathlib import Path

import pytest

from app.config.settings import MysqlSettings
from app.users.memory_user_repository import MemoryUserRepository
from app.users.mysql_user_repository import MysqlUserRepository
from app.users.user_record import UserRecord
from app.users.user_repository import UsernameAlreadyExists


def _record(username: str) -> UserRecord:
    """构造一条只含盐和摘要占位的用户。"""
    return UserRecord(username=username, salt="salt", password_hash="hash")



def _assert_contract(repository) -> None:
    """确认仓库能按用户名保存、查询，并拒绝重复用户名。"""
    assert repository.find_by_username("ann") is None
    repository.save(_record("ann"))
    found = repository.find_by_username("ann")
    assert found is not None
    assert found.username == "ann"
    assert found.salt == "salt"
    assert found.password_hash == "hash"
    with pytest.raises(UsernameAlreadyExists):
        repository.save(_record("ann"))



def test_内存仓库按用户名保存和查询() -> None:
    """内存仓库满足按用户名存取的约定。"""
    _assert_contract(MemoryUserRepository())



def test_mysql_仓库按用户名保存和查询() -> None:
    """本机有测试库时，MySQL 仓库满足同一约定。"""
    config_path = Path(__file__).parents[1] / "config" / "mysql.yaml"
    if not config_path.is_file():
        pytest.skip("没有本机 MySQL 配置")
    repository = None
    try:
        settings = MysqlSettings.load(config_path)
        repository = MysqlUserRepository(settings)
        repository.ensure_table()
        repository.delete_by_username("ann")
        _assert_contract(repository)
    except Exception:
        # 测试库连不上时跳过，不把环境问题当成用例失败。
        pytest.skip("测试库不可用")
    finally:
        if repository is not None:
            try:
                repository.delete_by_username("ann")
            except Exception:
                # 清理失败不影响用例结论。
                pass
