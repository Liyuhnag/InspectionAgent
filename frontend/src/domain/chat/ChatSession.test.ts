import { describe, expect, it, vi } from 'vitest'

import { ChatSession, preferDraft, senderText, visibleText } from './ChatSession'
import { LocalTimedChunkSource, localReply } from './LocalTimedChunkSource'
import { SequenceId } from './SequenceId'
import type { HistoryTurn, TextChunkSource, TurnVersions } from './types'

class ManualSource implements TextChunkSource {
  onChunk: ((chunk: string) => void) | null = null

  onDone: (() => void) | null = null

  onError: ((reason: Error) => void) | null = null

  sessionId = ''

  input = ''

  siblingOf: string | undefined

  starts = 0

  stopped = 0

  /** 记下回调，交给测试手动推进。 */
  start(
    sessionId: string,
    input: string,
    onChunk: (chunk: string) => void,
    onDone: () => void,
    onError: (reason: Error) => void,
    siblingOf?: string,
  ): void {
    this.sessionId = sessionId
    this.input = input
    this.siblingOf = siblingOf
    this.starts += 1
    this.onChunk = onChunk
    this.onDone = onDone
    this.onError = onError
  }

  /** 记录停止次数。 */
  stop(): void {
    this.stopped += 1
  }
}

describe('ChatSession', () => {
  it('把助手回复逐段写入同一条消息', () => {
    const source = new ManualSource()
    const ids = new SequenceId()
    const tracked = new ChatSession(source, () => ids.next(), 'server-session')

    expect(tracked.send('  巡检记录  ')).toBe(true)
    expect(tracked.messages).toHaveLength(2)
    expect(tracked.messages[0]).toMatchObject({
      role: 'user',
      status: 'complete',
    })
    expect(visibleText(tracked.messages[0].parts)).toBe('巡检记录')
    expect(tracked.messages[1].status).toBe('streaming')
    expect(source.sessionId).toBe('server-session')
    expect(tracked.messages[0].traceStatus).toBe('running')

    source.onChunk?.('已收')
    source.onChunk?.('到。')
    expect(tracked.messages).toHaveLength(2)
    expect(visibleText(tracked.messages[1].parts)).toBe('已收到。')

    source.onDone?.()
    expect(tracked.messages[1].status).toBe('complete')
    expect(tracked.messages[0].traceStatus).toBe('complete')
    expect(tracked.streaming).toBe(false)
    expect(tracked.send('下一条')).toBe(true)
  })

  it('拒绝空白输入和流式期间的再次发送', () => {
    const source = new ManualSource()
    const ids = new SequenceId()
    const session = new ChatSession(source, () => ids.next())

    expect(session.send('   ')).toBe(false)
    expect(session.messages).toHaveLength(0)
    expect(source.starts).toBe(0)

    session.send('第一条')
    expect(session.send('第二条')).toBe(false)
    expect(session.messages).toHaveLength(2)
    expect(source.starts).toBe(1)
  })

  it('来源失败后保留已输出文字并允许再次发送', () => {
    const source = new ManualSource()
    const ids = new SequenceId()
    const session = new ChatSession(source, () => ids.next())

    session.send('失败场景')
    source.onChunk?.('部分')
    source.onError?.(new Error('中断'))

    expect(session.messages[1].status).toBe('error')
    expect(visibleText(session.messages[1].parts)).toBe('部分')
    expect(session.messages[0].traceStatus).toBe('failed')
    expect(session.streaming).toBe(false)
    expect(session.send('重试')).toBe(true)
  })

  it('从输入组件的返回值里取出纯文本', () => {
    expect(senderText({ text: '检查阀门' })).toBe('检查阀门')
    expect(senderText('直接文本')).toBe('直接文本')
    expect(senderText(undefined)).toBe('')
    expect(preferDraft('', '\uFEFF检查阀门')).toBe('检查阀门')
    expect(preferDraft('模型文本', '编辑区文本')).toBe('模型文本')
  })

  it('展示正文时忽略非文本片段', () => {
    const text = visibleText([
      { type: 'thinking', text: '内部思考' },
      { type: 'text', text: '可见' },
      { type: 'tool_call', text: '工具' },
    ])
    expect(text).toBe('可见')
  })

  it('从历史页恢复交替消息、状态、Trace 编号和版本', () => {
    const source = new ManualSource()
    const ids = new SequenceId()
    const session = new ChatSession(source, () => ids.next(), 'server-session')

    session.restoreHistory({
      turns: [
        historyTurn({ trace_id: 'trace-1', user_text: '第一轮', reply: '助手已回复', versions: versions(2, 2) }),
        historyTurn({ trace_id: 'trace-2', user_text: '第二轮', status: 'failed', reply: '部分回复' }),
      ],
      has_more: true,
    })

    expect(session.messages.map((message) => visibleText(message.parts))).toEqual([
      '第一轮',
      '助手已回复',
      '第二轮',
      '部分回复',
    ])
    expect(session.messages.map((message) => message.status)).toEqual(['complete', 'complete', 'complete', 'error'])
    expect(session.messages.map((message) => message.traceStatus)).toEqual(['complete', undefined, 'failed', undefined])
    expect(session.messages.map((message) => message.traceId)).toEqual(['trace-1', 'trace-1', 'trace-2', 'trace-2'])
    expect(session.messages[0].versions).toEqual(versions(2, 2))
    expect(session.hasMore).toBe(true)
    expect(session.oldestTraceId).toBe('trace-1')
    expect(session.turnCount).toBe(2)

    session.prependHistory({ turns: [historyTurn({ trace_id: 'trace-0', user_text: '更早' })], has_more: false })
    expect(session.messages.map((message) => visibleText(message.parts))[0]).toBe('更早')
    expect(session.oldestTraceId).toBe('trace-0')
    expect(session.hasMore).toBe(false)
  })

  it('编辑用户消息时丢弃这一轮及之后的消息，以兄弟版本发送', () => {
    const source = new ManualSource()
    const ids = new SequenceId()
    const session = new ChatSession(source, () => ids.next(), 'server-session')
    session.restoreHistory({
      turns: [historyTurn({ trace_id: 'trace-1', user_text: '第一轮' }), historyTurn({ trace_id: 'trace-2' })],
      has_more: false,
    })
    const first = session.messages[0]

    expect(session.edit(first.id, '   ')).toBe(false)
    expect(session.messages).toHaveLength(4)
    expect(session.edit(first.id, ' 改过的第一轮 ')).toBe(true)

    expect(session.messages.map((message) => visibleText(message.parts))).toEqual(['改过的第一轮', ''])
    expect(source.input).toBe('改过的第一轮')
    expect(source.siblingOf).toBe('trace-1')
    expect(session.edit(session.messages[0].id, '流式期间')).toBe(false)
  })

  it('重新生成时用原输入发送，并丢弃这一轮及之后的消息', () => {
    const source = new ManualSource()
    const ids = new SequenceId()
    const session = new ChatSession(source, () => ids.next(), 'server-session')
    session.restoreHistory({
      turns: [
        historyTurn({ trace_id: 'trace-1', user_text: '第一轮' }),
        historyTurn({ trace_id: 'trace-2', user_text: '第二轮' }),
      ],
      has_more: false,
    })

    expect(session.regenerate(session.messages[0].id)).toBe(false)
    expect(session.regenerate(session.messages[1].id)).toBe(true)

    expect(session.messages.map((message) => visibleText(message.parts))).toEqual(['第一轮', ''])
    expect(source.input).toBe('第一轮')
    expect(source.siblingOf).toBe('trace-1')
  })

  it('刚发送、还没有 Trace 编号的消息不能编辑或重新生成', () => {
    const source = new ManualSource()
    const ids = new SequenceId()
    const session = new ChatSession(source, () => ids.next())
    session.send('新消息')
    source.onDone?.()

    expect(session.edit(session.messages[0].id, '改')).toBe(false)
    expect(session.regenerate(session.messages[1].id)).toBe(false)
    expect(source.starts).toBe(1)
  })

  it('一轮结束时通知外层，并区分本地中断', () => {
    const source = new ManualSource()
    const ids = new SequenceId()
    const settled: boolean[] = []
    const session = new ChatSession(source, () => ids.next(), 's', (aborted) => settled.push(aborted))

    session.send('完成')
    source.onDone?.()
    session.send('失败')
    source.onError?.(new Error('中断'))
    session.send('本地中断')
    session.abort()

    expect(settled).toEqual([false, false, true])
  })
})

/** 同一位置的版本信息，编号为 trace-v1…trace-vN。 */
function versions(index: number, total: number): TurnVersions {
  return { index, total, trace_ids: Array.from({ length: total }, (_, i) => `trace-v${i + 1}`) }
}

/** 生成一轮已完成的历史，测试只覆盖关心的字段。 */
function historyTurn(overrides: Partial<HistoryTurn>): HistoryTurn {
  return {
    trace_id: 'trace',
    user_text: '问题',
    status: 'complete',
    created_at: '2026-01-01T00:00:00Z',
    reply: '回答',
    versions: versions(1, 1),
    ...overrides,
  }
}

describe('LocalTimedChunkSource', () => {
  it('按间隔输出完整回复', () => {
    vi.useFakeTimers()
    const chunks: string[] = []
    let done = false
    const source = new LocalTimedChunkSource(localReply, 80, 4)

    source.start(
      '',
      '阀门',
      (chunk) => chunks.push(chunk),
      () => {
        done = true
      },
      () => {
        throw new Error('不应失败')
      },
    )
    vi.advanceTimersByTime(80 * 30)

    expect(done).toBe(true)
    expect(chunks.join('')).toBe(localReply('阀门'))
    source.stop()
    vi.useRealTimers()
  })
})
