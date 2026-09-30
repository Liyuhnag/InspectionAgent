# -*- coding: utf-8 -*-
"""把当前分支路径上的 Trace 和可见正文组装成「轮次」，供历史接口、上下文策略和取历史工具共用。"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.chats.conversation_tree import ConversationTree
from app.chats.span import Span
from app.chats.trace import Trace
from app.chats.trace import TraceStatus


_INDEX_USER_CHARS = 40
_INDEX_REPLY_CHARS = 60


def _head(text: str, length: int) -> str:
    """取开头若干字并压成一行，超出时加省略号。"""
    flat = " ".join(text.split())
    return flat if len(flat) <= length else f"{flat[:length]}…"


class InvalidCursor(Exception):
    """分页位置不在当前路径上。"""


@dataclass(frozen=True)
class HistoryTurn:
    """一轮对话：用户输入、可见回答、可选摘要，以及它在同父版本中的位置。"""

    trace_id: str
    user_text: str
    status: TraceStatus
    created_at: datetime
    reply: str
    summary: str | None
    version_ids: tuple[str, ...]

    @property
    def version_index(self) -> int:
        """该轮在同父版本中的序号，从 1 开始。"""
        return self.version_ids.index(self.trace_id) + 1

    def index_line(self) -> str:
        """给模型看的目录行：编号、用户输入开头、摘要（没有摘要时用回答开头）。"""
        answer = self.summary if self.summary else _head(self.reply, _INDEX_REPLY_CHARS)
        return f"- [轮次 {self.trace_id}] 用户：{_head(self.user_text, _INDEX_USER_CHARS)} ｜ 回答：{answer}"


@dataclass(frozen=True)
class HistoryPage:
    """历史接口的一页：从早到晚的轮次，以及更早是否还有轮次。"""

    turns: list[HistoryTurn]
    has_more: bool


class ConversationHistory:
    """读取一个会话的对话树：Trace 元数据一次查询，所需轮次的可见正文一次查询。"""

    def __init__(self, session: Session, session_id: str) -> None:
        """取出会话的全部 Trace 并建树；调用方负责先校验会话归属。"""
        self._session = session
        self.tree = ConversationTree(Trace.list_for_session(session, session_id))

    def page(self, leaf_id: str | None, limit: int, before: str | None = None) -> HistoryPage:
        """返回路径上位于 before 之前（省略时为末尾）最近的 limit 轮。"""
        path = self.tree.path_to(leaf_id)
        end = len(path)
        if before is not None:
            positions = [index for index, trace in enumerate(path) if trace.id == before]
            if not positions:
                raise InvalidCursor(before)
            end = positions[0]
        start = max(0, end - limit)
        return HistoryPage(turns=self.turns(path[start:end]), has_more=start > 0)

    def path_turns(self, leaf_id: str | None) -> list[HistoryTurn]:
        """返回整条路径上的轮次，供上下文组装和取历史工具使用。"""
        return self.turns(self.tree.path_to(leaf_id))

    def turns(self, traces: Sequence[Trace]) -> list[HistoryTurn]:
        """一次查询取出这些 Trace 的可见 text Span，拼成回答和摘要。"""
        spans_by_trace: dict[str, list[Span]] = {}
        for span in Span.list_visible_text(self._session, [trace.id for trace in traces]):
            spans_by_trace.setdefault(span.trace_id, []).append(span)
        return [self._turn(trace, spans_by_trace.get(trace.id, [])) for trace in traces]

    def _turn(self, trace: Trace, spans: list[Span]) -> HistoryTurn:
        """组装一轮；只有每段可见正文都有摘要时才给出整轮摘要，避免摘要只覆盖一部分。"""
        summaries = [span.summary for span in spans if span.summary]
        summary = "".join(summaries) if spans and len(summaries) == len(spans) else None
        return HistoryTurn(
            trace_id=trace.id,
            user_text=trace.user_text,
            status=trace.status,
            created_at=trace.created_at,
            reply="".join(span.text for span in spans),
            summary=summary,
            version_ids=tuple(sibling.id for sibling in self.tree.siblings(trace)),
        )
