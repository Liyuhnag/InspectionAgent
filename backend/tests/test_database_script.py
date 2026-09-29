# -*- coding: utf-8 -*-
"""数据库初始化脚本的目标选择要求。"""

import sys

import pytest

from scripts.create_database import _arguments


def test_初始化脚本必须显式指定数据库目标(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有目标参数时脚本打印用法并以参数错误退出。"""
    monkeypatch.setattr(sys, "argv", ["create_database.py"])

    with pytest.raises(SystemExit) as error:
        _arguments()

    assert error.value.code == 2
