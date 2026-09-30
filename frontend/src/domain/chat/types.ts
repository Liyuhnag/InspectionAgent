export type MessagePartType =
  | 'text'
  | 'thinking'
  | 'tool_call'
  | 'mcp_call'
  | 'human_input'
  | 'context'

export type MessageStatus = 'complete' | 'streaming' | 'waiting_human' | 'error'

export type MessageRole = 'user' | 'assistant'

export type TraceStatus = 'running' | 'complete' | 'failed'

export type SpanType =
  | 'agent'
  | 'llm'
  | 'tool_call'
  | 'mcp_call'
  | 'thinking'
  | 'text'
  | 'human_input'

export type SpanStatus = 'running' | 'complete' | 'failed'

/** 后端持久化的一步执行记录。 */
export interface PersistedSpan {
  id: string
  sequence: number
  type: SpanType
  status: SpanStatus
  parent_span_id: string | null
  agent_name: string | null
  node: string | null
  /** 为假时只供分析和模型上下文，不进入用户气泡。 */
  visible: boolean
  model: string | null
  text: string
  truncated: boolean
  started_at: string
  ended_at: string | null
}

/** 后端持久化的一轮用户输入。 */
export interface PersistedTrace {
  id: string
  user_text: string
  status: TraceStatus
  created_at: string
  spans?: PersistedSpan[]
}

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
  traceStatus?: TraceStatus
}

/** 可替换的文本流。本地间隔输出和以后的接口数据块都走这个入口。 */
export interface TextChunkSource {
  /** 从指定会话开始输出。每段调用 onChunk，结束调用 onDone，失败调用 onError。 */
  start(
    sessionId: string,
    input: string,
    onChunk: (chunk: string) => void,
    onDone: () => void,
    onError: (reason: Error) => void,
  ): void

  /** 停止尚未完成的输出。 */
  stop(): void
}
