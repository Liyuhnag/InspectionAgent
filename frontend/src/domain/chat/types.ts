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

/** 同一位置的各个版本（同父兄弟 Trace），index 从 1 开始。 */
export interface TurnVersions {
  index: number
  total: number
  trace_ids: string[]
}

/** 历史接口返回的一轮：用户输入、可见回复和版本信息。 */
export interface HistoryTurn {
  trace_id: string
  user_text: string
  status: TraceStatus
  created_at: string
  reply: string
  versions: TurnVersions
}

/** 当前分支路径上的一页轮次，从早到晚排列。 */
export interface HistoryPage {
  turns: HistoryTurn[]
  has_more: boolean
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
  /** 所属 Trace；刚发送、还没从历史接口拿到编号时为空。 */
  traceId?: string
  /** 只在用户消息上出现。 */
  versions?: TurnVersions
}

/** 可替换的文本流。本地间隔输出和以后的接口数据块都走这个入口。 */
export interface TextChunkSource {
  /**
   * 从指定会话开始输出。每段调用 onChunk，结束调用 onDone，失败调用 onError。
   * 给出 siblingOf 时，新一轮作为那条 Trace 的兄弟版本（编辑、重新生成）。
   */
  start(
    sessionId: string,
    input: string,
    onChunk: (chunk: string) => void,
    onDone: () => void,
    onError: (reason: Error) => void,
    siblingOf?: string,
  ): void

  /** 停止尚未完成的输出。 */
  stop(): void
}
