import type { TextChunkSource } from './types'

/** 把完整回复按固定间隔切成小段。 */
export class LocalTimedChunkSource implements TextChunkSource {
  private timer: ReturnType<typeof setInterval> | null = null

  constructor(
    private readonly replyOf: (input: string) => string,
    private readonly intervalMs = 80,
    private readonly chunkSize = 4,
  ) {}

  /** 按间隔把回复交给调用方。 */
  start(
    input: string,
    onChunk: (chunk: string) => void,
    onDone: () => void,
    onError: (reason: Error) => void,
  ): void {
    this.stop()
    const reply = this.replyOf(input)
    let index = 0
    this.timer = setInterval(() => {
      try {
        const chunk = reply.slice(index, index + this.chunkSize)
        index += this.chunkSize
        if (chunk) {
          onChunk(chunk)
        }
        if (index >= reply.length) {
          this.stop()
          onDone()
        }
      } catch (reason) {
        this.stop()
        onError(reason instanceof Error ? reason : new Error(String(reason)))
      }
    }, this.intervalMs)
  }

  /** 取消当前计时。 */
  stop(): void {
    if (this.timer !== null) {
      clearInterval(this.timer)
      this.timer = null
    }
  }
}

/** 根据用户输入生成一段本地回复。 */
export function localReply(input: string): string {
  return `已收到：「${input}」。这段回复按片段出现在同一个气泡中。`
}
