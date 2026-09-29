import type { ChatMessage, MessagePart, PersistedTrace, TextChunkSource } from './types'

/** 优先使用输入组件的文本，组件模型为空时用编辑区里的文字。 */
export function preferDraft(modelText: string, domText: string): string {
  if (modelText.trim()) {
    return modelText
  }
  return domText.replace(/\uFEFF/g, '')
}

/** 从 XSender 的返回值里取出可发送的纯文本。 */
export function senderText(value: { text?: string } | string | null | undefined): string {
  if (typeof value === 'string') {
    return value
  }
  return value?.text ?? ''
}

/** 只拼接文本片段，忽略留给后续能力的片段。 */
export function visibleText(parts: MessagePart[]): string {
  return parts
    .filter((part) => part.type === 'text')
    .map((part) => part.text)
    .join('')
}

/**
 * 管理一轮对话。
 * 流式输出使用策略：具体来源可替换，追加方式不变。
 */
export class ChatSession {
  readonly messages: ChatMessage[] = []

  private streamingId: string | null = null

  private streamingUserId: string | null = null

  /** 创建会话消息状态并绑定服务端会话编号。 */
  constructor(
    private readonly source: TextChunkSource,
    private readonly nextId: () => string,
    private readonly sessionId = '',
  ) {}

  /** 是否正在等待当前助手回复写完。 */
  get streaming(): boolean {
    return this.streamingId !== null
  }

  /** 发送一条用户消息，并开始同一条助手消息的流式输出。 */
  send(raw: string): boolean {
    const text = raw.trim()
    if (!text || this.streamingId !== null) {
      return false
    }
    const userMessage: ChatMessage = {
      id: this.nextId(),
      role: 'user',
      status: 'complete',
      parts: [{ type: 'text', text }],
      traceStatus: 'running',
    }
    this.messages.push(userMessage)
    const assistantId = this.nextId()
    this.messages.push({
      id: assistantId,
      role: 'assistant',
      status: 'streaming',
      parts: [{ type: 'text', text: '' }],
    })
    this.streamingId = assistantId
    this.streamingUserId = userMessage.id
    this.source.start(
      this.sessionId,
      text,
      (chunk) => this.appendChunk(assistantId, chunk),
      () => this.finish(assistantId),
      () => this.fail(assistantId),
    )
    return true
  }

  /** 用持久化 Trace 恢复会话中的用户输入和运行状态。 */
  restoreTraces(traces: readonly PersistedTrace[]): void {
    this.messages.splice(0)
    for (const trace of traces) {
      this.messages.push({
        id: this.nextId(),
        role: 'user',
        status: 'complete',
        traceStatus: trace.status,
        parts: [{ type: 'text', text: trace.user_text }],
      })
    }
  }

  /** 中断尚未完成的回复，并保留已经输出的文字。 */
  abort(): void {
    if (this.streamingId !== null) {
      this.fail(this.streamingId)
    }
  }

  /** 把新到的一段写入当前助手消息，不新增消息。 */
  private appendChunk(id: string, chunk: string): void {
    const message = this.findAssistant(id)
    if (!message) {
      return
    }
    const textPart = message.parts.find((part) => part.type === 'text')
    if (textPart) {
      textPart.text += chunk
    }
  }

  /** 标记当前助手消息已经完整。 */
  private finish(id: string): void {
    const message = this.findAssistant(id)
    if (!message || message.status !== 'streaming') {
      return
    }
    message.status = 'complete'
    this._setTraceStatus('complete')
    if (this.streamingId === id) {
      this.streamingId = null
      this.streamingUserId = null
    }
  }

  /** 保留已输出文字，并把当前助手消息标为失败。 */
  private fail(id: string): void {
    const message = this.findAssistant(id)
    if (!message || message.status !== 'streaming') {
      return
    }
    message.status = 'error'
    this._setTraceStatus('failed')
    if (this.streamingId === id) {
      this.streamingId = null
      this.streamingUserId = null
      this.source.stop()
    }
  }

  /** 找到仍由本次发送创建的助手消息。 */
  private findAssistant(id: string): ChatMessage | undefined {
    return this.messages.find((message) => message.id === id && message.role === 'assistant')
  }

  /** 设置当前用户消息对应 Trace 的运行结果。 */
  private _setTraceStatus(status: 'complete' | 'failed'): void {
    const userMessage = this.messages.find((message) => message.id === this.streamingUserId)
    if (userMessage) {
      userMessage.traceStatus = status
    }
  }
}
