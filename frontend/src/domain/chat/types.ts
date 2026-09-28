export type MessagePartType =
  | 'text'
  | 'thinking'
  | 'tool_call'
  | 'mcp_call'
  | 'human_input'
  | 'context'

export type MessageStatus = 'complete' | 'streaming' | 'waiting_human' | 'error'

export type MessageRole = 'user' | 'assistant'

/** 消息上的一个片段。非文本片段留给后续能力，这次不展示。 */
export interface MessagePart {
  type: MessagePartType
  text: string
}

/** 一条对话消息。 */
export interface ChatMessage {
  id: string
  role: MessageRole
  status: MessageStatus
  parts: MessagePart[]
}

/** 可替换的文本流。本地间隔输出和以后的接口数据块都走这个入口。 */
export interface TextChunkSource {
  /**
   * 开始输出。每到一段调用 onChunk，结束调用 onDone，失败调用 onError。
   */
  start(
    input: string,
    onChunk: (chunk: string) => void,
    onDone: () => void,
    onError: (reason: Error) => void,
  ): void

  /** 停止尚未完成的输出。 */
  stop(): void
}
