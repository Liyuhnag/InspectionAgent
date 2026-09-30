# -*- coding: utf-8 -*-
"""由一个会话的全部 Trace 计算对话路径、兄弟版本和分支末端。"""

from collections.abc import Sequence

from app.chats.trace import Trace


class ConversationTree:
    """会话内的 Trace 按 parent_trace_id 组成一棵树；同父的 Trace 互为版本，只在内存里计算，不查库。"""

    def __init__(self, traces: Sequence[Trace]) -> None:
        """按创建时间给每个父级下的子 Trace 排序，便于取版本序号和最新分支。"""
        ordered = sorted(traces, key=lambda trace: (trace.created_at, trace.id))
        self._by_id = {trace.id: trace for trace in ordered}
        self._children: dict[str | None, list[Trace]] = {}
        for trace in ordered:
            self._children.setdefault(trace.parent_trace_id, []).append(trace)

    def get(self, trace_id: str) -> Trace | None:
        """按编号取本会话的 Trace，不属于本会话时返回空。"""
        return self._by_id.get(trace_id)

    def path_to(self, leaf_id: str | None) -> list[Trace]:
        """从末端沿父级上溯到首轮，返回从早到晚的路径；末端为空或不在本会话时返回空列表。"""
        path: list[Trace] = []
        current = self._by_id.get(leaf_id) if leaf_id else None
        while current is not None:
            path.append(current)
            current = self._by_id.get(current.parent_trace_id) if current.parent_trace_id else None
        path.reverse()
        return path

    def siblings(self, trace: Trace) -> list[Trace]:
        """返回与该 Trace 同父的全部版本（含自身），按创建时间排列。"""
        return list(self._children.get(trace.parent_trace_id, []))

    def branch_end(self, trace_id: str) -> str:
        """从该 Trace 出发反复走到最新的子 Trace，返回这条分支的末端编号。"""
        current = trace_id
        while self._children.get(current):
            current = self._children[current][-1].id
        return current
