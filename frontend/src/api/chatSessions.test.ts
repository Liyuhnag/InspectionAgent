import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, saveToken } from './session'
import {
  createChatSession,
  getChatSession,
  listChatSessionSpans,
  listChatSessionTraces,
  listChatSessions,
  openChatSessionReply,
  renameChatSession,
} from './chatSessions'

describe('聊天会话 API', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    localStorage.clear()
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    saveToken('session-token')
  })

  it('携带 satoken 读取列表和单条会话', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ sessions: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: 'a'.repeat(32),
        title: '新会话',
        updated_at: '2026-01-01T00:00:00Z',
      }), { status: 200 }))

    expect(await listChatSessions()).toEqual({ sessions: [] })
    const session = await getChatSession('a'.repeat(32))

    expect(session.title).toBe('新会话')
    expect(fetchMock).toHaveBeenNthCalledWith(1, 'http://127.0.0.1:8000/chat-sessions', expect.objectContaining({ method: 'GET' }))
    expect(fetchMock).toHaveBeenNthCalledWith(2, `http://127.0.0.1:8000/chat-sessions/${'a'.repeat(32)}`, expect.objectContaining({ method: 'GET' }))
    for (const [, options] of fetchMock.mock.calls) {
      expect(new Headers(options?.headers).get('satoken')).toBe('session-token')
    }
  })

  it('创建会话不传入归属用户名', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      id: 'b'.repeat(32),
      title: '新会话',
      updated_at: '2026-01-01T00:00:00Z',
    }), { status: 201 }))

    const session = await createChatSession()

    expect(session.id).toBe('b'.repeat(32))
    expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8000/chat-sessions', expect.objectContaining({ method: 'POST' }))
    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined()
  })

  it('用 PATCH 保存会话标题并携带 satoken', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      id: 'c'.repeat(32),
      title: '巡检记录',
      updated_at: '2026-01-01T00:00:00Z',
    }), { status: 200 }))

    const session = await renameChatSession('c'.repeat(32), '巡检记录')

    expect(session.title).toBe('巡检记录')
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe(`http://127.0.0.1:8000/chat-sessions/${'c'.repeat(32)}`)
    expect(options?.method).toBe('PATCH')
    expect(options?.body).toBe(JSON.stringify({ title: '巡检记录' }))
    expect(new Headers(options?.headers).get('satoken')).toBe('session-token')
  })

  it('按会话读取 Trace 历史', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ traces: [] }), { status: 200 }))

    await expect(listChatSessionTraces('session-1')).resolves.toEqual({ traces: [] })

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/chat-sessions/session-1/traces',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('按会话和 Trace 编号读取 Span', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ spans: [] }), { status: 200 }))

    await expect(listChatSessionSpans('session-1', 'trace-1')).resolves.toEqual({ spans: [] })

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/chat-sessions/session-1/traces/trace-1/spans',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('将回复流绑定到会话编号并传递中断信号', async () => {
    fetchMock.mockResolvedValueOnce(new Response('stream', { status: 200 }))
    const controller = new AbortController()

    await openChatSessionReply('session-2', '巡检', controller.signal)

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/chat-sessions/session-2/replies',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ text: '巡检' }),
        signal: controller.signal,
      }),
    )
  })

  it('把后端错误转换为 ApiError', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: '会话不存在' }), { status: 404 }))

    const request = getChatSession('missing')
    await expect(request).rejects.toBeInstanceOf(ApiError)
    await expect(request).rejects.toThrow('会话不存在')
  })
})
