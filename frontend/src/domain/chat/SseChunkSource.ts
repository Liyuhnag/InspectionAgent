import { openChatSessionReply } from '@/api/chatSessions'

import type { TextChunkSource } from './types'

interface SseEvent {
  event: string
  data: string
}

/**
 * 策略。从后端的 SSE 读取文本段。
 * 变化点是回复来源，追加方式仍由 ChatSession 负责。
 */
export class SseChunkSource implements TextChunkSource {
  private controller: AbortController | null = null

  private finished = false

  /** 开始读取事件流。 */
  start(
    sessionId: string,
    input: string,
    onChunk: (chunk: string) => void,
    onDone: () => void,
    onError: (reason: Error) => void,
    siblingOf?: string,
  ): void {
    this.stop()
    this.finished = false
    const controller = new AbortController()
    this.controller = controller
    void this.read(sessionId, input, controller, onChunk, onDone, onError, siblingOf)
  }

  /** 取消尚未结束的请求。 */
  stop(): void {
    this.controller?.abort()
    this.controller = null
  }

  /** 读取响应并按事件回调。连接中断且尚未结束时视为失败。 */
  private async read(
    sessionId: string,
    input: string,
    controller: AbortController,
    onChunk: (chunk: string) => void,
    onDone: () => void,
    onError: (reason: Error) => void,
    siblingOf?: string,
  ): Promise<void> {
    try {
      const response = await openChatSessionReply(sessionId, input, controller.signal, siblingOf)
      if (!response.ok || !response.body) {
        this.fail(onError, new Error('回复失败'))
        return
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (!this.finished) {
        const step = await reader.read()
        if (step.done) {
          break
        }
        buffer += decoder.decode(step.value, { stream: true })
        buffer = this.consume(buffer, onChunk, onDone, onError)
      }
      if (!this.finished && !controller.signal.aborted) {
        this.fail(onError, new Error('回复失败'))
      }
    } catch (reason) {
      if (controller.signal.aborted) {
        return
      }
      const error = reason instanceof Error ? reason : new Error(String(reason))
      this.fail(onError, error)
    }
  }

  /** 取出已经收齐的事件，留下半截在缓冲里。 */
  private consume(
    buffer: string,
    onChunk: (chunk: string) => void,
    onDone: () => void,
    onError: (reason: Error) => void,
  ): string {
    const parts = buffer.split('\n\n')
    const rest = parts.pop() ?? ''
    for (const part of parts) {
      const event = parseEvent(part)
      if (event) {
        this.apply(event, onChunk, onDone, onError)
      }
    }
    return rest
  }

  /** 按事件名把文本、结束或失败交给调用方。 */
  private apply(
    event: SseEvent,
    onChunk: (chunk: string) => void,
    onDone: () => void,
    onError: (reason: Error) => void,
  ): void {
    if (this.finished) {
      return
    }
    if (event.event === 'chunk') {
      const text = readField(event.data, 'text')
      if (text) {
        onChunk(text)
      }
      return
    }
    if (event.event === 'done') {
      this.finished = true
      onDone()
      this.stop()
      return
    }
    if (event.event === 'error') {
      this.finished = true
      onError(new Error(readField(event.data, 'detail') || '回复失败'))
      this.stop()
    }
  }

  /** 结束读取并通知失败。已经结束时不再通知。 */
  private fail(onError: (reason: Error) => void, reason: Error): void {
    if (this.finished) {
      return
    }
    this.finished = true
    onError(reason)
    this.stop()
  }
}

/** 从一块 SSE 文本里取出事件名和 data。 */
function parseEvent(block: string): SseEvent | null {
  let event = ''
  let data = ''
  for (const line of block.split('\n')) {
    const trimmed = line.replace(/\r$/, '')
    if (trimmed.startsWith('event:')) {
      event = trimmed.slice('event:'.length).trim()
    } else if (trimmed.startsWith('data:')) {
      data = trimmed.slice('data:'.length).trim()
    }
  }
  if (!event) {
    return null
  }
  return { event, data }
}

/** 读取 data 里的一个字符串字段。格式不对时返回空。 */
function readField(data: string, field: string): string {
  try {
    const payload: unknown = JSON.parse(data)
    if (typeof payload !== 'object' || payload === null || !(field in payload)) {
      return ''
    }
    const value = (payload as Record<string, unknown>)[field]
    return typeof value === 'string' ? value : ''
  } catch {
    return ''
  }
}
