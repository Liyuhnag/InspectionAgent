import { describe, expect, it } from 'vitest'

import { DialogueDesk } from './DialogueDesk'
import { SequenceId } from './SequenceId'
import type { TextChunkSource } from './types'

class ManualSource implements TextChunkSource {
  stopped = 0

  onChunk: ((chunk: string) => void) | null = null

  onDone: (() => void) | null = null

  /** 保存回调。 */
  start(
    _sessionId: string,
    _input: string,
    onChunk: (chunk: string) => void,
    onDone: () => void,
    _onError: (reason: Error) => void,
  ): void {
    this.onChunk = onChunk
    this.onDone = onDone
  }

  /** 记录停止次数。 */
  stop(): void {
    this.stopped += 1
  }
}

describe('DialogueDesk', () => {
  it('新建会话后选中空会话，发送后才有对话内容', () => {
    const ids = new SequenceId()
    const desk = new DialogueDesk(new ManualSource(), () => ids.next())

    expect(desk.dialogues).toHaveLength(1)
    expect(desk.active.empty).toBe(true)
    expect(desk.active.title).toBe('新会话')

    desk.create()
    expect(desk.dialogues).toHaveLength(2)
    expect(desk.active.id).toBe(desk.dialogues[0].id)

    desk.active.chat.send('检查北门阀门')
    desk.active.nameFrom('检查北门阀门')
    expect(desk.active.empty).toBe(false)
    expect(desk.active.title).toBe('检查北门阀门')
  })

  it('从服务端加载会话并以服务端编号新建会话', () => {
    const desk = new DialogueDesk(new ManualSource(), () => 'unused', false)

    expect(desk.dialogues).toHaveLength(0)
    desk.load([
      { id: 'server-1', title: '第一条' },
      { id: 'server-2', title: '第二条' },
    ])
    expect(desk.dialogues.map((item) => item.id)).toEqual(['server-1', 'server-2'])
    expect(desk.activeId).toBe('server-1')
    expect(desk.active.title).toBe('第一条')
    desk.loadHistory('server-1', {
      turns: [{
        trace_id: 'trace-1',
        user_text: '恢复的请求',
        status: 'complete',
        created_at: '2026-01-01T00:00:00Z',
        reply: '恢复的回答',
        versions: { index: 1, total: 1, trace_ids: ['trace-1'] },
      }],
      has_more: false,
    })
    expect(desk.active.chat.messages[0].parts[0].text).toBe('恢复的请求')
    expect(desk.active.chat.messages[1].parts[0].text).toBe('恢复的回答')
    expect(desk.active.tracesLoaded).toBe(true)

    const created = desk.add('server-3', '新会话')
    expect(desk.activeId).toBe('server-3')
    expect(created.id).toBe('server-3')
  })

  it('切换会话时中断正在输出的回复', () => {
    const source = new ManualSource()
    const ids = new SequenceId()
    const desk = new DialogueDesk(source, () => ids.next())
    const first = desk.active
    first.chat.send('第一条')
    source.onChunk?.('部分')

    desk.create()
    expect(first.chat.streaming).toBe(false)
    expect(first.chat.messages[1].status).toBe('error')
    expect(source.stopped).toBe(1)
    expect(desk.active.empty).toBe(true)
    expect(first.tracesLoaded).toBe(false)
  })

  it('回复正常结束后通知外层刷新，本地中断时不通知', () => {
    const source = new ManualSource()
    const desk = new DialogueDesk(source, () => 'unused', false)
    const settled: string[] = []
    desk.onSettled = (id) => settled.push(id)
    desk.load([{ id: 'server-1', title: '第一条' }, { id: 'server-2', title: '第二条' }])

    desk.active.chat.send('完成')
    source.onDone?.()
    desk.active.chat.send('被中断')
    desk.select('server-2')

    expect(settled).toEqual(['server-1'])
  })
})
