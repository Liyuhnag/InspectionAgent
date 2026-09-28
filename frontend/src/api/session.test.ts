import { beforeEach, describe, expect, it, vi } from 'vitest'

import { clearToken, currentUser, login, readToken, register, saveToken, sendCode } from '@/api/session'

function jsonResponse(body: object, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('session api', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn())
  })

  it('登录后把 token 放进 localStorage，并在后续请求头带上', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValueOnce(jsonResponse({ token: 'tok-ann', message: '已登录' }))
    await login('ann', 'secret')
    expect(readToken()).toBe('tok-ann')

    fetchMock.mockResolvedValueOnce(jsonResponse({ username: 'ann' }))
    await expect(currentUser()).resolves.toBe('ann')
    const headers = new Headers(fetchMock.mock.calls[1][1]?.headers)
    expect(headers.get('satoken')).toBe('tok-ann')
    expect(fetchMock.mock.calls[1][1]?.method).toBe('GET')
  })

  it('注册和发送验证码把字段交给后端', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValue(jsonResponse({ message: '已发送' }))
    await sendCode('ann')
    await register('ann', 'secret', '123456')
    expect(fetchMock.mock.calls[0][0]).toContain('/verification-codes')
    expect(fetchMock.mock.calls[1][0]).toContain('/users')
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
      username: 'ann',
      password: 'secret',
      code: '123456',
    })
  })

  it('401 时清掉本地 token', async () => {
    saveToken('expired')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: '未登录' }, 401))
    await expect(currentUser()).resolves.toBe('')
    expect(readToken()).toBe('')
  })

  it('没有 token 时不请求当前用户', async () => {
    clearToken()
    await expect(currentUser()).resolves.toBe('')
    expect(fetch).not.toHaveBeenCalled()
  })
})
