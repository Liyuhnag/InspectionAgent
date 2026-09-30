import { ChatSession } from './ChatSession'
import type { HistoryPage, TextChunkSource } from './types'

/** 一次会话，包含标题和自己的消息。 */
export class Dialogue {
  title = '新会话'

  tracesLoaded = false

  /** 创建本地对话状态并绑定消息来源。 */
  constructor(
    readonly id: string,
    readonly chat: ChatSession,
    title = '新会话',
  ) {
    this.title = title
  }

  /** 还没有消息时，右侧显示 AI 形象而不是对话。 */
  get empty(): boolean {
    return this.chat.messages.length === 0
  }

  /** 用第一条发送内容作为会话标题。 */
  nameFrom(text: string): void {
    if (this.title !== '新会话') {
      return
    }
    const trimmed = text.trim()
    this.title = trimmed.length > 16 ? `${trimmed.slice(0, 16)}…` : trimmed
  }
}

/** 管理左侧会话列表和当前选中的会话。 */
export class DialogueDesk {
  readonly dialogues: Dialogue[] = []

  activeId = ''

  /** 某个会话的一轮回复正常结束或失败后调用，外层据此重新读取历史。 */
  onSettled: ((id: string) => void) | null = null

  constructor(
    private readonly source: TextChunkSource,
    private readonly nextId: () => string,
    createInitial = true,
  ) {
    if (createInitial) {
      this.create()
    }
  }

  /** 当前正在查看的会话。 */
  get active(): Dialogue {
    const found = this.dialogues.find((item) => item.id === this.activeId)
    if (!found) {
      throw new Error('没有选中的会话')
    }
    return found
  }

  /** 新建空会话并立刻选中。 */
  create(): Dialogue {
    this.abortActive()
    const dialogue = this.build(this.nextId(), '新会话')
    this.dialogues.unshift(dialogue)
    this.activeId = dialogue.id
    return dialogue
  }

  /** 用服务端读取的会话替换当前列表。 */
  load(sessions: readonly { id: string; title: string }[]): void {
    this.abortActive()
    this.dialogues.splice(0)
    for (const item of sessions) {
      this.dialogues.push(this.build(item.id, item.title))
    }
    this.activeId = sessions[0]?.id ?? ''
  }

  /** 将新建的服务端会话加入列表并选中。 */
  add(id: string, title: string): Dialogue {
    this.abortActive()
    const dialogue = this.build(id, title)
    dialogue.tracesLoaded = true
    this.dialogues.unshift(dialogue)
    this.activeId = dialogue.id
    return dialogue
  }

  /** 用历史接口的一页替换会话里的消息。 */
  loadHistory(id: string, page: HistoryPage): void {
    const dialogue = this.dialogues.find((item) => item.id === id)
    if (!dialogue) {
      return
    }
    dialogue.chat.restoreHistory(page)
    dialogue.tracesLoaded = true
  }

  /** 切换会话。正在输出时先中断当前回复。 */
  select(id: string): void {
    if (id === this.activeId || !this.dialogues.some((item) => item.id === id)) {
      return
    }
    this.abortActive()
    this.activeId = id
  }

  /** 创建会话对象，并把回复结束事件转给外层。 */
  private build(id: string, title: string): Dialogue {
    const chat = new ChatSession(this.source, this.nextId, id, (aborted) => this.settled(id, aborted))
    return new Dialogue(id, chat, title)
  }

  /** 本地中断的回复还没写完，下次打开时重新读取；其余情况交给外层刷新。 */
  private settled(id: string, aborted: boolean): void {
    if (aborted) {
      const dialogue = this.dialogues.find((item) => item.id === id)
      if (dialogue) {
        dialogue.tracesLoaded = false
      }
      return
    }
    this.onSettled?.(id)
  }

  /** 中断当前会话里尚未完成的流式回复。 */
  private abortActive(): void {
    const current = this.dialogues.find((item) => item.id === this.activeId)
    current?.chat.abort()
  }
}
