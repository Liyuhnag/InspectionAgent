# 可替换的文本流

## 要解决的变化点

助手回复可以由本地定时切段产生，也可以由后端 SSE 产生。页面不能因为来源变化而改成“每段新建一条消息”。

## 使用的设计

策略。`TextChunkSource` 负责产出文本段，`ChatSession` 只把段追加到当前助手消息。

## 关键类

- `frontend/src/domain/chat/types.ts` 中的 `TextChunkSource`
- `frontend/src/domain/chat/ChatSession.ts` 中的 `send`、`appendChunk`
- `frontend/src/domain/chat/LocalTimedChunkSource.ts`
- `frontend/src/domain/chat/SseChunkSource.ts`：聊天页默认使用的后端事件流

## 以后怎么扩展

新增一种来源时，实现 `start` 和 `stop`，并把实例传给 `ChatSession`。不要在 `ChatSession.send` 里判断来源类型，也不要在视图里直接拼接流式协议。
