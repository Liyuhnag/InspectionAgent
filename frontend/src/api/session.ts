const TOKEN_KEY = 'satoken'
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export class ApiError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

/** 读出浏览器里保存的登录 token。 */
export function readToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

/** 登录成功后保存 token。 */
export function saveToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

/** 退出时丢掉 token。 */
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

/** 发送注册验证码。 */
export async function sendCode(username: string): Promise<void> {
  await parse(await request('POST', '/verification-codes', { username }))
}

/** 提交注册。成功后留在注册页。 */
export async function register(username: string, password: string, code: string): Promise<void> {
  await parse(await request('POST', '/users', { username, password, code }))
}

/** 登录并把 token 写入 localStorage。 */
export async function login(username: string, password: string): Promise<void> {
  const body = await parse<{ token: string }>(await request('POST', '/session', { username, password }))
  saveToken(body.token)
}

/** 用当前 token 读取用户名。未登录时返回空。 */
export async function currentUser(): Promise<string> {
  if (!readToken()) {
    return ''
  }
  const response = await request('GET', '/session')
  if (response.status === 401) {
    clearToken()
    return ''
  }
  const body = await parse<{ username: string }>(response)
  return body.username
}

/** 通知后端删掉会话，并清除本地 token。 */
export async function logout(): Promise<void> {
  if (readToken()) {
    await request('DELETE', '/session')
  }
  clearToken()
}

async function request(method: string, path: string, body?: object, signal?: AbortSignal): Promise<Response> {
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

async function parse<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : '请求失败'
    throw new ApiError(detail)
  }
  return body as T
}
