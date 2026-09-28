# 可替换的文本流

## 要解决的变化点

助手回复现在由本地定时切段产生，以后会改成接口返回的数据块。页面不能因为来源变化而改成“每段新建一条消息”。

## 使用的设计

策略。`TextChunkSource` 负责产出文本段，`ChatSession` 只把段追加到当前助手消息。

## 关键类

- `frontend/src/domain/chat/types.ts` 中的 `TextChunkSource`
- `frontend/src/domain/chat/ChatSession.ts` 中的 `send`、`appendChunk`
- `frontend/src/domain/chat/LocalTimedChunkSource.ts`

## 以后怎么扩展

新增一种来源时，实现 `start` 和 `stop`，并把实例传给 `ChatSession`。不要在 `ChatSession.send` 里判断来源类型，也不要在视图里直接拼接流式协议。
