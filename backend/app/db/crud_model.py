# -*- coding: utf-8 -*-
"""模型基类。子类只声明表和列，创建、读取、更新、删除由这里实现。变化点是以后每张新表。"""

from typing import Self

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Session


class CrudModel(DeclarativeBase):
    """声明式模型。表结构由子类给出，增删改查沿用这一套。"""

    @classmethod
    def create_table(cls, engine: Engine) -> None:
        """按模型声明建表。表已存在时不重复创建。"""
        cls.metadata.create_all(engine, tables=[cls.__table__])

    @classmethod
    def create(cls, session: Session, **values: object) -> Self:
        """插入一行并提交。唯一约束冲突时回滚并抛出。"""
        row = cls(**values)
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise
        return row

    @classmethod
    def get(cls, session: Session, primary_key: object) -> Self | None:
        """按主键读取一行。没有则返回空。"""
        return session.get(cls, primary_key)

    def update(self, session: Session, **values: object) -> None:
        """修改当前行已有字段并提交。"""
        for name, value in values.items():
            if name not in self.__table__.columns:
                raise AttributeError(name)
            setattr(self, name, value)
        session.commit()

    def delete(self, session: Session) -> None:
        """删除当前行并提交。"""
        session.delete(self)
        session.commit()
