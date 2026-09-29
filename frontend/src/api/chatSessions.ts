import { ApiError, readToken } from './session'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export interface ChatSessionRecord {
  id: string
  title: string
  updated_at: string
}

export interface ChatSessionList {
  sessions: ChatSessionRecord[]
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

/** 保存当前用户会话的新标题。 */
export async function renameChatSession(id: string, title: string): Promise<ChatSessionRecord> {
  return parse<ChatSessionRecord>(await request(
    'PATCH',
    `/chat-sessions/${encodeURIComponent(id)}`,
    { title },
  ))
}

/** 发送带 satoken 的聊天会话请求。 */
async function request(method: string, path: string, body?: object): Promise<Response> {
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
