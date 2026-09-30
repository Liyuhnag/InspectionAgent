# -*- coding: utf-8 -*-
"""把已有的会话数据升级到对话分支结构：补列、补外键和索引，并把旧 Trace 串成一条链。"""

from sqlalchemy import Table
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.chats.chat_session import ChatSession
from app.chats.span import Span
from app.chats.trace import Trace

_PARENT_FOREIGN_KEY = "fk_traces_parent_trace_id"


class BranchMigration:
    """幂等迁移：只补缺少的可空列、外键和索引；只回填还没有 active_trace_id 的会话。"""

    def __init__(self, engine: Engine) -> None:
        """保存要迁移的数据库引擎。"""
        self._engine = engine

    def run(self) -> int:
        """执行结构升级和数据回填，返回回填的会话数。"""
        self.upgrade_schema()
        with Session(self._engine) as session:
            count = self.backfill(session)
            session.commit()
        return count

    def upgrade_schema(self) -> None:
        """给三张表补上模型里新增、库里还没有的列，再补 Trace 父级外键和索引。"""
        for table in (ChatSession.__table__, Trace.__table__, Span.__table__):
            self._add_missing_columns(table)
        inspector = inspect(self._engine)
        foreign_keys = {key["name"] for key in inspector.get_foreign_keys(Trace.__tablename__)}
        if _PARENT_FOREIGN_KEY not in foreign_keys and self._engine.dialect.name == "mysql":
            with self._engine.begin() as connection:
                connection.execute(text(
                    f"ALTER TABLE traces ADD CONSTRAINT {_PARENT_FOREIGN_KEY} "
                    "FOREIGN KEY (parent_trace_id) REFERENCES traces (id)"
                ))
        indexes = {index["name"] for index in inspector.get_indexes(Trace.__tablename__)}
        for index in Trace.__table__.indexes:
            if index.name not in indexes:
                index.create(self._engine)

    @staticmethod
    def backfill(session: Session) -> int:
        """把没有分支信息的会话按创建时间串成一条链，并把最后一轮设为当前分支末端；不提交。"""
        pending = session.scalars(select(ChatSession).where(ChatSession.active_trace_id.is_(None)))
        count = 0
        for chat_session in pending:
            traces = Trace.list_for_session(session, chat_session.id)
            if not traces:
                continue
            for previous, current in zip(traces, traces[1:]):
                if current.parent_trace_id is None:
                    current.parent_trace_id = previous.id
            chat_session.active_trace_id = traces[-1].id
            count += 1
        return count

    def _add_missing_columns(self, table: Table) -> None:
        """补上库里缺少的列；新增列都必须可空，否则已有行无法填值。"""
        existing = {column["name"] for column in inspect(self._engine).get_columns(table.name)}
        missing = [column for column in table.columns if column.name not in existing]
        with self._engine.begin() as connection:
            for column in missing:
                if not column.nullable:
                    raise ValueError(f"{table.name}.{column.name} 不可空，不能直接加到已有表")
                column_type = column.type.compile(dialect=self._engine.dialect)
                connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column_type} NULL"))
