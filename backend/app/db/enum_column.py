# -*- coding: utf-8 -*-
"""把 StrEnum 映射为按枚举值存储的 VARCHAR 列。"""

from enum import StrEnum

from sqlalchemy import Enum


def string_enum(enum_type: type[StrEnum], length: int) -> Enum:
    """生成 VARCHAR 枚举列：写入和读出非法值都报错，数据库不建 ENUM 或 CHECK，新增取值不用改表。"""
    return Enum(
        enum_type,
        native_enum=False,
        create_constraint=False,
        length=length,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )
