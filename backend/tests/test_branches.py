# -*- coding: utf-8 -*-
"""对话分支：编辑、重新生成、切换版本、历史分页和旧数据回填。"""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.auth import TOKEN_HEADER
from app.chats.branch_migration import BranchMigration
from app.chats.chat_session import ChatSession
from app.chats.mock_reply import mock_reply
from app.chats.span import Span
from app.chats.span import SpanStatus
from app.chats.span import SpanType
from app.chats.trace import Trace
from app.chats.trace import TraceStatus
from tests.test_traces import _USERS
from tests.test_traces import _cleanup
from tests.test_traces import _setup


def _send(client: TestClient, headers: dict[str, str], session_id: str, text: str,
          sibling_of: str | None = None) -> None:
    """发送一轮并读完事件流。"""
    body: dict[str, str] = {"text": text}
    if sibling_of is not None:
        body["sibling_of"] = sibling_of
    response = client.post(f"/chat-sessions/{session_id}/replies", json=body, headers=headers)
    assert response.status_code == 200
    assert "event: done" in response.text


def _history(client: TestClient, headers: dict[str, str], session_id: str, **params: object) -> dict:
    """读取当前分支的历史。"""
    response = client.get(f"/chat-sessions/{session_id}/history", params=params, headers=headers)
    assert response.status_code == 200
    return response.json()


def _texts(page: dict) -> list[str]:
    """取出一页里各轮的用户输入。"""
    return [turn["user_text"] for turn in page["turns"]]


def test_重新生成编辑和切换版本按树更新当前分支() -> None:
    """重新生成和编辑与原轮同父；切换版本落到该分支最新的末端。"""
    engine, codes, client, tokens = _setup()
    headers = {TOKEN_HEADER: tokens[_USERS[0]]}
    try:
        session_id = client.post("/chat-sessions", headers=headers).json()["id"]
        assert _history(client, headers, session_id) == {"turns": [], "has_more": False}
        for text in ("第一轮", "第二轮", "第三轮"):
            _send(client, headers, session_id, text)
        linear = _history(client, headers, session_id)
        assert _texts(linear) == ["第一轮", "第二轮", "第三轮"]
        first, second, third = [turn["trace_id"] for turn in linear["turns"]]
        assert all(turn["reply"] == mock_reply(turn["user_text"]) for turn in linear["turns"])
        assert all(turn["versions"] == {"index": 1, "total": 1, "trace_ids": [turn["trace_id"]]}
                   for turn in linear["turns"])

        _send(client, headers, session_id, "第二轮", sibling_of=second)
        regenerated = _history(client, headers, session_id)
        assert _texts(regenerated) == ["第一轮", "第二轮"]
        new_second = regenerated["turns"][1]
        assert new_second["trace_id"] != second
        assert new_second["versions"] == {"index": 2, "total": 2, "trace_ids": [second, new_second["trace_id"]]}

        switched = client.put(f"/chat-sessions/{session_id}/active-trace", json={"trace_id": second},
                              headers=headers)
        assert switched.status_code == 200
        assert [turn["trace_id"] for turn in switched.json()["turns"]] == [first, second, third]
        assert switched.json() == _history(client, headers, session_id)

        _send(client, headers, session_id, "改写的第一轮", sibling_of=first)
        edited = _history(client, headers, session_id)
        assert _texts(edited) == ["改写的第一轮"]
        assert edited["turns"][0]["versions"]["index"] == 2

        back = client.put(f"/chat-sessions/{session_id}/active-trace", json={"trace_id": first},
                          headers=headers).json()
        assert [turn["trace_id"] for turn in back["turns"]] == [first, new_second["trace_id"]]
        with Session(engine) as session:
            parents = {trace.id: trace.parent_trace_id for trace in Trace.list_for_session(session, session_id)}
            assert parents[first] is None
            assert parents[second] == first
            assert parents[third] == second
            assert parents[new_second["trace_id"]] == first
            assert parents[edited["turns"][0]["trace_id"]] is None
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()


def test_跨会话或不存在的版本编号按会话不存在处理() -> None:
    """sibling_of 和切换目标不属于该会话时返回 404，且不新建 Trace。"""
    engine, codes, client, tokens = _setup()
    owner = {TOKEN_HEADER: tokens[_USERS[0]]}
    other = {TOKEN_HEADER: tokens[_USERS[1]]}
    try:
        own_session = client.post("/chat-sessions", headers=owner).json()["id"]
        other_session = client.post("/chat-sessions", headers=other).json()["id"]
        _send(client, other, other_session, "别人的一轮")
        foreign_trace = _history(client, other, other_session)["turns"][0]["trace_id"]

        for sibling_of in (foreign_trace, "not-a-trace"):
            response = client.post(f"/chat-sessions/{own_session}/replies",
                                   json={"text": "借用", "sibling_of": sibling_of}, headers=owner)
            assert (response.status_code, response.json()) == (404, {"detail": "会话不存在"})
            switched = client.put(f"/chat-sessions/{own_session}/active-trace",
                                  json={"trace_id": sibling_of}, headers=owner)
            assert (switched.status_code, switched.json()) == (404, {"detail": "会话不存在"})
        assert _history(client, owner, own_session)["turns"] == []
        assert client.get(f"/chat-sessions/{other_session}/history", headers=owner).status_code == 404
        assert client.get(f"/chat-sessions/{own_session}/history").status_code == 401
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()


def test_历史按before和limit分页并校验参数() -> None:
    """返回 before 之前最近的 limit 轮，has_more 表示更早是否还有。"""
    engine, codes, client, tokens = _setup()
    headers = {TOKEN_HEADER: tokens[_USERS[0]]}
    try:
        session_id = client.post("/chat-sessions", headers=headers).json()["id"]
        texts = [f"第{index}轮" for index in range(1, 6)]
        for text in texts:
            _send(client, headers, session_id, text)

        latest = _history(client, headers, session_id, limit=2)
        assert (_texts(latest), latest["has_more"]) == (texts[3:], True)
        middle = _history(client, headers, session_id, limit=2, before=latest["turns"][0]["trace_id"])
        assert (_texts(middle), middle["has_more"]) == (texts[1:3], True)
        oldest = _history(client, headers, session_id, limit=2, before=middle["turns"][0]["trace_id"])
        assert (_texts(oldest), oldest["has_more"]) == (texts[:1], False)
        empty = _history(client, headers, session_id, before=oldest["turns"][0]["trace_id"])
        assert empty == {"turns": [], "has_more": False}
        assert _texts(_history(client, headers, session_id)) == texts

        invalid = client.get(f"/chat-sessions/{session_id}/history", params={"before": "nope"}, headers=headers)
        assert (invalid.status_code, invalid.json()) == (400, {"detail": "分页位置无效"})
        for limit in (0, 101):
            response = client.get(f"/chat-sessions/{session_id}/history", params={"limit": limit}, headers=headers)
            assert response.status_code == 422
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()


def test_历史只拼可见text正文且查询次数不随轮数增长() -> None:
    """不可见或非 text 的 Span 不进入回答；3 轮和 6 轮的查询次数相同。"""
    engine, codes, client, tokens = _setup()
    headers = {TOKEN_HEADER: tokens[_USERS[0]]}
    try:
        session_id = client.post("/chat-sessions", headers=headers).json()["id"]
        _send(client, headers, session_id, "第一轮")
        trace_id = _history(client, headers, session_id)["turns"][0]["trace_id"]
        now = datetime.now(UTC)
        with Session(engine) as session:
            for sequence, span_type, visible, text in ((2, SpanType.THINKING, True, "思考"),
                                                       (3, SpanType.TEXT, False, "内部文本"),
                                                       (4, SpanType.TEXT, True, "，补充")):
                session.add(Span(id=uuid4().hex, trace_id=trace_id, sequence=sequence, type=span_type,
                                 status=SpanStatus.COMPLETE, visible=visible, text=text, truncated=False,
                                 started_at=now, ended_at=now))
            session.commit()
        assert _history(client, headers, session_id)["turns"][0]["reply"] == f"{mock_reply('第一轮')}，补充"

        for text in ("第二轮", "第三轮"):
            _send(client, headers, session_id, text)
        three = _count_queries(engine, lambda: _history(client, headers, session_id))
        for text in ("第四轮", "第五轮", "第六轮"):
            _send(client, headers, session_id, text)
        six = _count_queries(engine, lambda: _history(client, headers, session_id))
        assert three == six
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()


def test_回填把旧会话按时间串成一条链且可重复执行() -> None:
    """没有分支信息的会话回填后成一条链，末端为最后一轮；再次执行不改变结果。"""
    engine, codes, client, tokens = _setup()
    headers = {TOKEN_HEADER: tokens[_USERS[0]]}
    try:
        session_id = client.post("/chat-sessions", headers=headers).json()["id"]
        start = datetime.now(UTC) - timedelta(minutes=5)
        ids = [uuid4().hex for _ in range(3)]
        with Session(engine) as session:
            for offset, trace_id in enumerate(ids):
                session.add(Trace(id=trace_id, session_id=session_id, user_text=f"旧的第{offset + 1}轮",
                                  status=TraceStatus.COMPLETE, created_at=start + timedelta(seconds=offset)))
            session.commit()

        migration = BranchMigration(engine)
        with Session(engine) as session:
            assert migration.backfill(session) == 1
            session.commit()
        with Session(engine) as session:
            assert migration.backfill(session) == 0
            chat_session = ChatSession.get(session, session_id)
            assert chat_session is not None
            assert chat_session.active_trace_id == ids[-1]
            parents = [Trace.get(session, trace_id).parent_trace_id for trace_id in ids]
            assert parents == [None, ids[0], ids[1]]
        assert _texts(_history(client, headers, session_id)) == ["旧的第1轮", "旧的第2轮", "旧的第3轮"]
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()


def _count_queries(engine: Engine, action) -> int:
    """统计执行 action 期间发往数据库的 SQL 条数。"""
    statements: list[str] = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        """记下每条 SQL。"""
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        action()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return len(statements)
