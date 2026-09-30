import { ApiError, readToken } from './session'
import type { HistoryPage, PersistedSpan, PersistedTrace } from '@/domain/chat/types'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export interface ChatSessionRecord {
  id: string
  title: string
  updated_at: string
}

export interface ChatSessionList {
  sessions: ChatSessionRecord[]
}

export interface ChatTraceList {
  traces: PersistedTrace[]
}

/** 读取当前用户的持久化会话列表。 */
export async function listChatSessions(): Promise<ChatSessionList> {
  return parse<ChatSessionList>(await request('GET', '/chat-sessions'))
}

/** 为当前用户创建一条空会话。 */
export async function createChatSession(): Promise<ChatSessionRecord> {
  return parse<ChatSessionRecord>(await request('POST', '/chat-sessions'))
}

/** 读取指定的当前用户会话。 */
export async function getChatSession(id: string): Promise<ChatSessionRecord> {
  return parse<ChatSessionRecord>(await request('GET', `/chat-sessions/${encodeURIComponent(id)}`))
}

/** 读取会话内已持久化的用户输入和 Trace 状态。 */
export async function listChatSessionTraces(sessionId: string): Promise<ChatTraceList> {
  return parse<ChatTraceList>(await request(
    'GET',
    `/chat-sessions/${encodeURIComponent(sessionId)}/traces`,
  ))
}

/** 读取指定 Trace 的执行片段。 */
export async function listChatSessionSpans(
  sessionId: string,
  traceId: string,
): Promise<{ spans: PersistedSpan[] }> {
  return parse<{ spans: PersistedSpan[] }>(await request(
    'GET',
    `/chat-sessions/${encodeURIComponent(sessionId)}/traces/${encodeURIComponent(traceId)}/spans`,
  ))
}

/** 读取当前分支路径上的一页轮次；给出 before 时读取它之前更早的轮次。 */
export async function getChatSessionHistory(
  sessionId: string,
  options: { limit?: number; before?: string } = {},
): Promise<HistoryPage> {
  const query = new URLSearchParams()
  if (options.limit !== undefined) {
    query.set('limit', String(options.limit))
  }
  if (options.before) {
    query.set('before', options.before)
  }
  const encoded = query.toString()
  const suffix = encoded ? `?${encoded}` : ''
  return parse<HistoryPage>(await request(
    'GET',
    `/chat-sessions/${encodeURIComponent(sessionId)}/history${suffix}`,
  ))
}

/** 切换到指定版本所在的分支，返回切换后的第一页历史。 */
export async function switchChatSessionBranch(sessionId: string, traceId: string): Promise<HistoryPage> {
  return parse<HistoryPage>(await request(
    'PUT',
    `/chat-sessions/${encodeURIComponent(sessionId)}/active-trace`,
    { trace_id: traceId },
  ))
}

/** 打开指定会话的一轮回复事件流；给出 siblingOf 时作为那条 Trace 的兄弟版本。 */
export function openChatSessionReply(
  sessionId: string,
  text: string,
  signal: AbortSignal,
  siblingOf?: string,
): Promise<Response> {
  return request(
    'POST',
    `/chat-sessions/${encodeURIComponent(sessionId)}/replies`,
    siblingOf ? { text, sibling_of: siblingOf } : { text },
    signal,
  )
}

/** 保存当前用户会话的新标题。 */
export async function renameChatSession(id: string, title: string): Promise<ChatSessionRecord> {
  return parse<ChatSessionRecord>(await request(
    'PATCH',
    `/chat-sessions/${encodeURIComponent(id)}`,
    { title },
  ))
}

/** 发送带 satoken 的聊天会话请求。 */
async function request(
  method: string,
  path: string,
  body?: object,
  signal?: AbortSignal,
): Promise<Response> {
  const headers = new Headers()
  const token = readToken()
  if (token) {
    headers.set('satoken', token)
  }
  if (body) {
    headers.set('Content-Type', 'application/json')
  }
  return fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  })
}

/** 解析 JSON 响应，并把后端错误转换为统一异常。 */
async function parse<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : '请求失败'
    throw new ApiError(detail)
  }
  return body as T
}
