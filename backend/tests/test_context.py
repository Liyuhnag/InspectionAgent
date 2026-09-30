# -*- coding: utf-8 -*-
"""上下文策略的组装规则，以及取历史工具的可见范围和额度。"""

from datetime import UTC
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.agents import context_strategies
from app.agents.context_strategies import ContextMessage
from app.agents.context_strategies import ContextStrategy
from app.agents.context_strategies import DefaultContextStrategy
from app.agents.context_strategies import estimate_tokens
from app.agents.context_strategies import input_digest
from app.agents.context_strategies import strategy_for
from app.api.auth import TOKEN_HEADER
from app.chats.chat_reply import ChatReplyService
from app.chats.history import HistoryTurn
from app.chats.mock_reply import mock_reply
from app.chats.span import Span
from app.chats.span import SpanStatus
from app.chats.span import SpanType
from app.chats.trace import Trace
from app.chats.trace import TraceStatus
from app.tools.history_tools import HistoryTools
from tests.test_branches import _history
from tests.test_branches import _send
from tests.test_traces import _USERS
from tests.test_traces import _cleanup
from tests.test_traces import _setup


def _turn(number: int, status: TraceStatus = TraceStatus.COMPLETE, reply: str | None = None,
          summary: str | None = None) -> HistoryTurn:
    """构造一轮历史，编号 t<number>。"""
    return HistoryTurn(
        trace_id=f"t{number}",
        user_text=f"问题{number}",
        status=status,
        created_at=datetime.now(UTC),
        reply=reply if reply is not None else f"回答{number}",
        summary=summary,
        version_ids=(f"t{number}",),
    )


def _roles(window) -> list[str]:
    """取出消息角色序列。"""
    return [message.role for message in window.messages]


def test_默认策略放最近两轮原文和更早轮次的目录() -> None:
    """顺序为目录、最近两轮原文、本轮输入；目录不提示取历史工具。"""
    window = DefaultContextStrategy().build([_turn(1), _turn(2), _turn(3), _turn(4)], "本轮")

    assert _roles(window) == ["system", "user", "assistant", "user", "assistant", "user"]
    index = window.messages[0].content
    assert "[轮次 t1] 用户：问题1 ｜ 回答：回答1" in index
    assert "[轮次 t2]" in index
    assert "t3" not in index
    assert "read_turn" not in index
    assert [message.content for message in window.messages[1:]] == ["问题3", "回答3", "问题4", "回答4", "本轮"]
    assert window.rule_version == "default-v1"


def test_失败和进行中的轮次直接跳过() -> None:
    """不完成的轮次既不进原文，也不进目录。"""
    turns = [_turn(1), _turn(2, TraceStatus.FAILED), _turn(3), _turn(4, TraceStatus.RUNNING)]
    window = DefaultContextStrategy().build(turns, "本轮")

    assert [message.content for message in window.messages] == ["问题1", "回答1", "问题3", "回答3", "本轮"]


def test_超出token上限时原文降为目录行再从最早的目录行丢弃() -> None:
    """预算不足时先把最早的原文轮次写成目录行，仍不足再丢最早的目录行。"""

    class Tight(DefaultContextStrategy):
        """原文放不下两轮的策略。"""

        version = "tight"
        token_budget = 80

    long_reply = "阀门压力" * 10
    turns = [_turn(1), _turn(2, reply=long_reply, summary="压力正常"), _turn(3, reply=long_reply)]
    window = Tight().build(turns, "本轮")
    assert _roles(window) == ["system", "user", "assistant", "user"]
    assert "[轮次 t2] 用户：问题2 ｜ 回答：压力正常" in window.messages[0].content
    assert "t1" not in window.messages[0].content
    assert window.messages[1].content == "问题3"

    class Tighter(DefaultContextStrategy):
        """只放得下本轮输入的策略。"""

        version = "tighter"
        token_budget = 5

    window = Tighter().build([_turn(1), _turn(2)], "本轮")
    assert [message.content for message in window.messages] == ["本轮"]


def test_子类只覆盖需要不同的部分() -> None:
    """不放目录、不放原文、允许取历史工具时，目录提示按编号读取。"""

    class NoHistory(DefaultContextStrategy):
        """只看本轮输入。"""

        version = "no-history"
        recent_turns = 0
        include_index = False

    assert [message.content for message in NoHistory().build([_turn(1)], "本轮").messages] == ["本轮"]

    class Reader(DefaultContextStrategy):
        """只放目录，并允许读取历史。"""

        version = "reader"
        recent_turns = 0
        history_tools = frozenset({"read_turn"})

    window = Reader().build([_turn(1, summary="一句摘要")], "本轮")
    assert "回答：一句摘要" in window.messages[0].content
    assert "用 read_turn 按轮次编号读取" in window.messages[0].content

    with pytest.raises(TypeError):
        ContextStrategy()


def test_未登记的agent使用默认策略(monkeypatch: pytest.MonkeyPatch) -> None:
    """登记表里有的返回对应策略，其余返回默认策略。"""

    class Planner(DefaultContextStrategy):
        """测试用的登记策略。"""

        version = "planner-v1"

    planner = Planner()
    monkeypatch.setitem(context_strategies._STRATEGIES, "planner", planner)
    assert strategy_for("planner") is planner
    assert isinstance(strategy_for("unknown"), DefaultContextStrategy)
    assert isinstance(strategy_for(None), DefaultContextStrategy)


def test_输入指纹稳定且随内容变化() -> None:
    """同样的消息得到同样的指纹，内容或角色变了指纹也变。"""
    messages = (ContextMessage("user", "巡检"), ContextMessage("assistant", "好的"))
    window = DefaultContextStrategy().build([], "巡检")

    assert input_digest(messages) == input_digest(list(messages))
    assert len(input_digest(messages)) == 64
    assert input_digest(messages) != input_digest((ContextMessage("user", "巡检"),))
    assert input_digest(messages) != input_digest((ContextMessage("system", "巡检"), messages[1]))
    assert window.digest == input_digest((ContextMessage("user", "巡检"),))
    assert estimate_tokens("巡检ab") == 3
    assert estimate_tokens("") == 0


def test_本轮上游只交给策略范围内已完成的Span() -> None:
    """默认只看 text；类型不符或未完成的不交给 agent。"""
    now = datetime.now(UTC)

    def span(span_type: SpanType, status: SpanStatus) -> Span:
        """构造一个不入库的 Span。"""
        return Span(id=uuid4().hex, trace_id="t", sequence=1, type=span_type, status=status, visible=True,
                    text="", truncated=False, started_at=now)

    spans = [span(SpanType.TEXT, SpanStatus.COMPLETE), span(SpanType.TOOL_CALL, SpanStatus.COMPLETE),
             span(SpanType.TEXT, SpanStatus.RUNNING)]
    assert DefaultContextStrategy().select_upstream(spans) == spans[:1]


def test_取历史工具只读当前路径上已完成的轮次() -> None:
    """失败轮次、其他分支、其他会话、本轮自身和其他用户都读不到。"""
    engine, codes, client, tokens = _setup()
    owner = {TOKEN_HEADER: tokens[_USERS[0]]}
    other = {TOKEN_HEADER: tokens[_USERS[1]]}
    try:
        session_id = client.post("/chat-sessions", headers=owner).json()["id"]
        for text in ("第一轮", "第二轮", "第三轮"):
            _send(client, owner, session_id, text)
        first, second, third = [turn["trace_id"] for turn in _history(client, owner, session_id)["turns"]]
        _send(client, owner, session_id, "第三轮", sibling_of=third)
        other_session = client.post("/chat-sessions", headers=other).json()["id"]
        _send(client, other, other_session, "别人的一轮")
        foreign = _history(client, other, other_session)["turns"][0]["trace_id"]
        with Session(engine) as session:
            session.execute(update(Trace).where(Trace.id == second).values(status=TraceStatus.FAILED))
            session.commit()
            first_span = Span.list_for_trace(session, first)[0].id

        current, current_span = ChatReplyService(engine).begin_reply(session_id, _USERS[0], "第四轮")
        tools = HistoryTools(engine, _USERS[0], session_id, current, preview_limit=100)

        listing = tools.list_turns()
        assert "问题" not in listing
        assert f"[轮次 {first}]" in listing
        assert second not in listing
        assert f"[轮次 {third}]" not in listing
        assert tools.list_turns(before=first) == "没有更早的轮次。"
        for hidden in (second, third, foreign, current, "nope"):
            assert tools.read_turn(hidden) == "没有找到。"
        preview = tools.read_turn(first)
        assert preview.startswith("用户：第一轮\n回答：")
        assert "full=True" in preview
        assert tools.read_turn(first, full=True) == f"用户：第一轮\n回答：{mock_reply('第一轮')}"
        assert tools.read_step(first_span) == mock_reply("第一轮")
        assert tools.read_step(current_span) == "没有找到。"

        stranger = HistoryTools(engine, _USERS[1], session_id, current)
        assert stranger.read_turn(first) == "没有找到。"
        assert stranger.list_turns() == "没有更早的轮次。"
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()


def test_取历史工具有单次和累计上限() -> None:
    """单次超长时截断；累计额度用完后只返回上限提示。"""
    engine, codes, client, tokens = _setup()
    owner = {TOKEN_HEADER: tokens[_USERS[0]]}
    try:
        session_id = client.post("/chat-sessions", headers=owner).json()["id"]
        _send(client, owner, session_id, "第一轮")
        first = _history(client, owner, session_id)["turns"][0]["trace_id"]
        current, _span_id = ChatReplyService(engine).begin_reply(session_id, _USERS[0], "第二轮")
        tools = HistoryTools(engine, _USERS[0], session_id, current, call_limit=50, total_limit=120)

        clipped = tools.read_turn(first, full=True)
        assert clipped.endswith("（内容过长，已截断。）")
        assert len(clipped) <= 50 + len("\n（内容过长，已截断。）")
        tools.read_turn(first, full=True)
        tools.read_turn(first, full=True)
        assert tools.read_turn(first, full=True) == "本轮取回的历史已达上限。"
    finally:
        _cleanup(engine, codes, tokens)
        engine.dispose()
