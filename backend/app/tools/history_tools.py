# -*- coding: utf-8 -*-
"""供模型按需读取历史的工具：目录翻页、读一轮、读一步。只读当前分支路径上已完成的轮次。"""

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.chats.chat_session import ChatSession
from app.chats.history import ConversationHistory
from app.chats.history import HistoryTurn
from app.chats.span import Span
from app.chats.trace import TraceStatus

_NOT_FOUND = "没有找到。"
_EXHAUSTED = "本轮取回的历史已达上限。"


class HistoryTools:
    """一轮执行内使用的一组取历史工具。

    可见范围在创建时确定：当前用户、当前会话里 current_trace_id 的祖先中已完成的轮次。
    范围外的编号一律返回「没有找到」，不抛异常，也不区分「不存在」和「无权访问」。
    """

    def __init__(
        self,
        engine: Engine,
        username: str,
        session_id: str,
        current_trace_id: str,
        call_limit: int = 4000,
        total_limit: int = 16000,
        preview_limit: int = 1000,
    ) -> None:
        """读取可见范围，并记下单次、累计和预览的字数上限。"""
        self._engine = engine
        self._call_limit = call_limit
        self._remaining = total_limit
        self._preview_limit = preview_limit
        self._turns = self._load_turns(username, session_id, current_trace_id)
        self._by_id = {turn.trace_id: turn for turn in self._turns}

    def list_turns(self, before: str | None = None, limit: int = 10) -> str:
        """返回范围内位于 before 之前（省略时为最近）的 limit 条目录行。"""
        end = len(self._turns)
        if before is not None:
            if before not in self._by_id:
                return self._emit(_NOT_FOUND)
            end = [turn.trace_id for turn in self._turns].index(before)
        page = self._turns[max(0, end - max(1, limit)):end]
        if not page:
            return self._emit("没有更早的轮次。")
        return self._emit("\n".join(turn.index_line() for turn in page))

    def read_turn(self, turn_id: str, full: bool = False) -> str:
        """返回一轮的用户输入和回答；回答过长且未要求 full 时返回摘要或开头，并提示可取原文。"""
        turn = self._by_id.get(turn_id)
        if turn is None:
            return self._emit(_NOT_FOUND)
        answer = turn.reply
        if not full and len(answer) > self._preview_limit:
            shortened = turn.summary if turn.summary else answer[:self._preview_limit]
            answer = f"{shortened}\n（回答较长，已省略。需要原文时用 full=True 再读一次。）"
        return self._emit(f"用户：{turn.user_text}\n回答：{answer}")

    def read_step(self, span_id: str) -> str:
        """返回范围内某一步的输出原文，例如一次工具调用的结果。"""
        with Session(self._engine) as session:
            span = Span.get(session, span_id)
            if span is None or span.trace_id not in self._by_id:
                return self._emit(_NOT_FOUND)
            return self._emit(span.text)

    def _emit(self, text: str) -> str:
        """按单次上限截断，并从累计额度里扣除；额度用完后只返回上限提示。"""
        if self._remaining <= 0:
            return _EXHAUSTED
        limit = min(self._call_limit, self._remaining)
        if len(text) > limit:
            text = f"{text[:limit]}\n（内容过长，已截断。）"
        self._remaining -= min(len(text), limit)
        return text

    def _load_turns(self, username: str, session_id: str, current_trace_id: str) -> list[HistoryTurn]:
        """取出 current_trace_id 的祖先中已完成的轮次；会话或 Trace 不属于当前用户时范围为空。"""
        with Session(self._engine) as session:
            if ChatSession.get_for_user(session, session_id, username) is None:
                return []
            history = ConversationHistory(session, session_id)
            path = history.tree.path_to(current_trace_id)
            if not path or path[-1].id != current_trace_id:
                return []
            ancestors = [trace for trace in path[:-1] if trace.status == TraceStatus.COMPLETE]
            return history.turns(ancestors)
