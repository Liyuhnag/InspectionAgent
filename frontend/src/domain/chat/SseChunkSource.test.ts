import { beforeEach, describe, expect, it, vi } from 'vitest'

import { saveToken } from '@/api/session'
import { ChatSession, visibleText } from '@/domain/chat/ChatSession'
import { SseChunkSource } from '@/domain/chat/SseChunkSource'
import { SequenceId } from '@/domain/chat/SequenceId'

const reply = [
  '关于「阀门」：东区今日巡检已完成现场核对，共发现 2 项异常，其余点位正常。',
  '1 号线压力表读数 0.31 MPa，低于运行区间 0.40–0.55 MPa，偏差持续约 20 分钟。',
  '现场阀门开度正常，管线无可见泄漏。建议先复核压力变送器零点，并对照上游泵出口压力，',
  '确认是表计漂移还是实际供压不足。复核完成前，该点标记为待处理，不纳入本班关闭项。',
  '3 号泵房阀门已逐个核对，入口阀、出口阀和旁路阀位置与操作票一致。',
  '出口压力 0.42 MPa，振动和温度未见异常，盘车无卡涩。润滑油位在标线中部，地面无积油。此项可以关闭。',
  '2 号冷却水泵备用状态已确认，控制柜指示灯正常。东区通道照明有 1 盏不亮，已另行报修，',
  '不影响本次「阀门」的结论。巡检人应写明到达时间和表计照片编号。',
  '若下一班压力仍低于 0.40 MPa，升级为异常工单并通知值班长。',
  '同时核对消防栓铅封、应急照明和通道堆物。铅封完好，应急照明试灯正常，通道无占压。',
  '配电间温度 27 摄氏度，湿度在允许范围内，无焦糊味。接地线连接牢固，柜门关闭并上锁。',
  '以上结果仅覆盖本班已到达的点位。未到达的西区管廊不在本次结论内，留待下一班补检。',
].join('')

function sseBody(): string {
  const chunks = [reply.slice(0, 4), reply.slice(4)]
  const events = chunks.map((text) => `event: chunk\ndata: ${JSON.stringify({ text })}\n\n`)
  events.push('event: done\ndata: {}\n\n')
  return events.join('')
}

function streamFrom(text: string): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text)
  return new ReadableStream({
    start(controller) {
      controller.enqueue(bytes)
      controller.close()
    },
  })
}

describe('SseChunkSource', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn())
  })

  it('把后端事件追加到同一条助手消息', async () => {
    saveToken('tok-reply')
    vi.mocked(fetch).mockResolvedValue(new Response(streamFrom(sseBody()), { status: 200 }))
    const source = new SseChunkSource()
    const session = new ChatSession(source, () => new SequenceId().next(), 'session-test')

    expect(session.send('阀门')).toBe(true)
    await vi.waitFor(() => {
      expect(session.messages[1].status).toBe('complete')
    })

    const [url, init] = vi.mocked(fetch).mock.calls[0]
    expect(String(url)).toContain('/chat-sessions/session-test/replies')
    expect(init?.method).toBe('POST')
    expect(new Headers(init?.headers).get('satoken')).toBe('tok-reply')
    expect(JSON.parse(String(init?.body))).toEqual({ text: '阀门' })
    expect(session.messages).toHaveLength(2)
    expect(visibleText(session.messages[1].parts)).toBe(reply)
  })

  it('收到 error 后保留已输出文字并允许再次发送', async () => {
    saveToken('tok-reply')
    const partial = 'event: chunk\ndata: {"text":"部分"}\n\nevent: error\ndata: {"detail":"回复失败"}\n\n'
    vi.mocked(fetch).mockResolvedValue(new Response(streamFrom(partial), { status: 200 }))
    const source = new SseChunkSource()
    const ids = new SequenceId()
    const session = new ChatSession(source, () => ids.next(), 'session-test')

    session.send('失败')
    await vi.waitFor(() => {
      expect(session.messages[1].status).toBe('error')
    })
    expect(visibleText(session.messages[1].parts)).toBe('部分')
    expect(session.streaming).toBe(false)
    expect(session.send('重试')).toBe(true)
  })

  it('中断时取消请求', async () => {
    saveToken('tok-reply')
    let signal: AbortSignal | undefined
    vi.mocked(fetch).mockImplementation((_url, init) => {
      signal = init?.signal ?? undefined
      return new Promise(() => undefined)
    })
    const source = new SseChunkSource()
    const session = new ChatSession(source, () => new SequenceId().next(), 'session-test')

    session.send('中断')
    await vi.waitFor(() => {
      expect(signal).toBeDefined()
    })
    session.abort()
    expect(session.messages[1].status).toBe('error')
    expect(signal?.aborted).toBe(true)
  })
})
