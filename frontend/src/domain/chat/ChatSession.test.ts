import { describe, expect, it, vi } from 'vitest'

import { ChatSession, preferDraft, senderText, visibleText } from './ChatSession'
import { LocalTimedChunkSource, localReply } from './LocalTimedChunkSource'
import { SequenceId } from './SequenceId'
import type { TextChunkSource } from './types'

class ManualSource implements TextChunkSource {
  onChunk: ((chunk: string) => void) | null = null

  onDone: (() => void) | null = null

  onError: ((reason: Error) => void) | null = null

  sessionId = ''

  starts = 0

  stopped = 0

  /** 记下回调，交给测试手动推进。 */
  start(
    sessionId: string,
    _input: string,
    onChunk: (chunk: string) => void,
    onDone: () => void,
    onError: (reason: Error) => void,
  ): void {
    this.sessionId = sessionId
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

  it('从持久化 Trace 恢复用户输入和状态，不恢复助手正文', () => {
    const source = new ManualSource()
    const ids = new SequenceId()
    const session = new ChatSession(source, () => ids.next(), 'server-session')

    session.restoreTraces([
      {
        id: 'trace-1',
        user_text: '第一轮',
        status: 'complete',
        created_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'trace-2',
        user_text: '第二轮',
        status: 'failed',
        created_at: '2026-01-01T00:01:00Z',
      },
    ])

    expect(session.messages).toHaveLength(2)
    expect(session.messages.map((message) => visibleText(message.parts))).toEqual(['第一轮', '第二轮'])
    expect(session.messages.map((message) => message.traceStatus)).toEqual(['complete', 'failed'])
  })
})

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
