# -*- coding: utf-8 -*-
"""各 agent 的上下文策略。

策略模式：变化点是「每个 agent 要什么上下文」。基类用模板方法固定组装流程（筛选、预算、排列），
子类只覆盖参数或钩子。默认策略和每个 agent 的策略都集中在本文件；新增 agent 时，在这里加一个
策略类并登记到 _STRATEGIES，不改组装流程，也不改其他 agent 的策略。
"""

import hashlib
import json
import math
from abc import ABC
from abc import abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.chats.history import HistoryTurn
from app.chats.span import Span
from app.chats.span import SpanStatus
from app.chats.span import SpanType
from app.chats.trace import TraceStatus

HISTORY_TOOLS = frozenset({"list_turns", "read_turn", "read_step"})

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ContextMessage:
    """与模型框架无关的一条上下文消息；接入 LangChain 时再转换成对应的消息类型。"""

    role: Role
    content: str


@dataclass(frozen=True)
class ContextWindow:
    """一次组装的结果：基础上下文消息和所用规则的版本。"""

    messages: tuple[ContextMessage, ...]
    rule_version: str

    @property
    def digest(self) -> str:
        """这组消息的输入指纹，用于事后核对重建结果是否与当时一致。"""
        return input_digest(self.messages)


def input_digest(messages: Sequence[ContextMessage]) -> str:
    """把消息按 [{"role","content"}] 以紧凑 JSON 序列化后取 SHA-256。"""
    payload = [{"role": message.role, "content": message.content} for message in messages]
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    """粗略估算 token：中日韩字符每字 1，其余字符每 4 个 1，向上取整。"""
    wide = sum(1 for char in text if _is_wide(char))
    return wide + math.ceil((len(text) - wide) / 4)


def _is_wide(char: str) -> bool:
    """是否为中日韩统一表意文字、假名、谚文或全角标点。"""
    code = ord(char)
    return (
        0x3000 <= code <= 0x30FF
        or 0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xAC00 <= code <= 0xD7AF
        or 0xFF00 <= code <= 0xFFEF
    )


class ContextStrategy(ABC):
    """上下文策略基类：最近若干轮放原文，更早的放目录，历史部分受 token 上限约束。"""

    recent_turns: int = 2
    include_index: bool = True
    history_tools: frozenset[str] = frozenset()
    upstream_span_types: frozenset[SpanType] = frozenset({SpanType.TEXT})
    token_budget: int = 8000

    @property
    @abstractmethod
    def version(self) -> str:
        """策略版本；组装规则或参数改动时递增，写进 llm Span 的 context_rule_version。"""

    def build(self, turns: Sequence[HistoryTurn], user_text: str) -> ContextWindow:
        """按路径上的历史轮次和本轮输入组装基础上下文：目录、最近原文、本轮输入。

        超出 token 上限时，先把最早的原文轮次降为目录行，直到原文放得下；再从最早的目录行丢起。
        """
        usable = [turn for turn in turns if turn.status == TraceStatus.COMPLETE]
        split = max(0, len(usable) - self.recent_turns)
        recent = usable[split:]
        indexed = usable[:split] if self.include_index else []
        while recent and self._cost([], recent) > self.token_budget:
            demoted = recent.pop(0)
            if self.include_index:
                indexed.append(demoted)
        while indexed and self._cost(indexed, recent) > self.token_budget:
            indexed.pop(0)
        messages: list[ContextMessage] = []
        if indexed:
            messages.append(ContextMessage("system", self.index_text(indexed)))
        for turn in recent:
            messages.extend(self.turn_messages(turn))
        messages.append(ContextMessage("user", user_text))
        return ContextWindow(messages=tuple(messages), rule_version=self.version)

    def select_upstream(self, spans: Sequence[Span]) -> list[Span]:
        """本轮之内，只把上游已完成、且类型在策略范围内的 Span 交给这个 agent。"""
        return [
            span for span in spans
            if span.type in self.upstream_span_types and span.status == SpanStatus.COMPLETE
        ]

    def turn_messages(self, turn: HistoryTurn) -> list[ContextMessage]:
        """一轮原文展开成用户、助手两条消息；子类可以覆盖以改变原文的呈现方式。"""
        return [ContextMessage("user", turn.user_text), ContextMessage("assistant", turn.reply)]

    def index_text(self, turns: Sequence[HistoryTurn]) -> str:
        """把更早的轮次写成目录；允许 read_turn 时提示模型按编号读取。"""
        lines = ["更早的对话目录（从早到晚）："]
        lines.extend(turn.index_line() for turn in turns)
        if "read_turn" in self.history_tools:
            lines.append("需要某一轮的细节时，用 read_turn 按轮次编号读取。")
        return "\n".join(lines)

    def _cost(self, indexed: Sequence[HistoryTurn], recent: Sequence[HistoryTurn]) -> int:
        """估算历史部分（不含本轮输入）的 token 数。"""
        cost = estimate_tokens(self.index_text(indexed)) if indexed else 0
        for turn in recent:
            cost += sum(estimate_tokens(message.content) for message in self.turn_messages(turn))
        return cost


class DefaultContextStrategy(ContextStrategy):
    """默认策略：最近 2 轮原文加目录，不允许取历史工具，本轮上游只看 text。"""

    version = "default-v1"


_DEFAULT = DefaultContextStrategy()

# agent 注册名 -> 策略对象。新增 agent 时在本文件定义它的策略类并登记在这里。
_STRATEGIES: dict[str, ContextStrategy] = {}


def strategy_for(agent_name: str | None) -> ContextStrategy:
    """按 agent 注册名取策略；未登记或没有名字时返回默认策略。"""
    if agent_name is None:
        return _DEFAULT
    return _STRATEGIES.get(agent_name, _DEFAULT)
