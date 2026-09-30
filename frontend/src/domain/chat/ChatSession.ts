import type { ChatMessage, HistoryPage, HistoryTurn, MessagePart, TextChunkSource } from './types'

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
 * 管理一个会话里当前分支上的消息。
 * 流式输出使用策略：具体来源可替换，追加方式不变。
 */
export class ChatSession {
  readonly messages: ChatMessage[] = []

  /** 当前分支上是否还有更早的轮次没有加载。 */
  hasMore = false

  private streamingId: string | null = null

  private streamingUserId: string | null = null

  /**
   * 创建会话消息状态并绑定服务端会话编号。
   * 一轮回复结束（完成、失败或被中断）时调用 onSettled，aborted 表示是本地主动中断。
   */
  constructor(
    private readonly source: TextChunkSource,
    private readonly nextId: () => string,
    private readonly sessionId = '',
    private readonly onSettled: (aborted: boolean) => void = () => undefined,
  ) {}

  /** 是否正在等待当前助手回复写完。 */
  get streaming(): boolean {
    return this.streamingId !== null
  }

  /** 已显示的最早一轮的 Trace 编号，用于加载更早的对话。 */
  get oldestTraceId(): string | undefined {
    return this.messages[0]?.traceId
  }

  /** 已显示的轮数。 */
  get turnCount(): number {
    return this.messages.filter((message) => message.role === 'user').length
  }

  /** 发送一条用户消息，并开始同一条助手消息的流式输出；siblingOf 给出时作为那一轮的新版本。 */
  send(raw: string, siblingOf?: string): boolean {
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
      () => this.fail(assistantId, false),
      siblingOf,
    )
    return true
  }

  /** 编辑一条已持久化的用户消息：丢弃它及之后的消息，把新内容作为这一轮的新版本发送。 */
  edit(messageId: string, raw: string): boolean {
    const index = this.messages.findIndex((message) => message.id === messageId && message.role === 'user')
    const target = this.messages[index]
    if (!target?.traceId || !raw.trim() || this.streaming) {
      return false
    }
    this.messages.splice(index)
    return this.send(raw, target.traceId)
  }

  /** 重新生成一条已持久化的助手回复：丢弃这一轮及之后的消息，用原输入发送新版本。 */
  regenerate(messageId: string): boolean {
    const index = this.messages.findIndex((message) => message.id === messageId && message.role === 'assistant')
    const userMessage = this.messages[index - 1]
    if (index < 1 || userMessage?.role !== 'user' || !userMessage.traceId || this.streaming) {
      return false
    }
    const text = visibleText(userMessage.parts)
    this.messages.splice(index - 1)
    return this.send(text, userMessage.traceId)
  }

  /** 用历史接口的一页替换全部消息。 */
  restoreHistory(page: HistoryPage): void {
    this.messages.splice(0, this.messages.length, ...page.turns.flatMap((turn) => this.turnMessages(turn)))
    this.hasMore = page.has_more
  }

  /** 把更早的一页插到最前面。 */
  prependHistory(page: HistoryPage): void {
    this.messages.unshift(...page.turns.flatMap((turn) => this.turnMessages(turn)))
    this.hasMore = page.has_more
  }

  /** 中断尚未完成的回复，并保留已经输出的文字。 */
  abort(): void {
    if (this.streamingId !== null) {
      this.fail(this.streamingId, true)
    }
  }

  /** 把一轮历史展开成用户、助手两条消息。 */
  private turnMessages(turn: HistoryTurn): ChatMessage[] {
    return [
      {
        id: this.nextId(),
        role: 'user',
        status: 'complete',
        traceStatus: turn.status,
        traceId: turn.trace_id,
        versions: turn.versions,
        parts: [{ type: 'text', text: turn.user_text }],
      },
      {
        id: this.nextId(),
        role: 'assistant',
        status: turn.status === 'complete' ? 'complete' : 'error',
        traceId: turn.trace_id,
        parts: [{ type: 'text', text: turn.reply }],
      },
    ]
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
    this.setTraceStatus('complete')
    if (this.streamingId === id) {
      this.streamingId = null
      this.streamingUserId = null
    }
    this.onSettled(false)
  }

  /** 保留已输出文字，并把当前助手消息标为失败。 */
  private fail(id: string, aborted: boolean): void {
    const message = this.findAssistant(id)
    if (!message || message.status !== 'streaming') {
      return
    }
    message.status = 'error'
    this.setTraceStatus('failed')
    if (this.streamingId === id) {
      this.streamingId = null
      this.streamingUserId = null
      this.source.stop()
    }
    this.onSettled(aborted)
  }

  /** 找到仍由本次发送创建的助手消息。 */
  private findAssistant(id: string): ChatMessage | undefined {
    return this.messages.find((message) => message.id === id && message.role === 'assistant')
  }

  /** 设置当前用户消息对应 Trace 的运行结果。 */
  private setTraceStatus(status: 'complete' | 'failed'): void {
    const userMessage = this.messages.find((message) => message.id === this.streamingUserId)
    if (userMessage) {
      userMessage.traceStatus = status
    }
  }
}
