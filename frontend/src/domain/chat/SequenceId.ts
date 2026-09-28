/** 按递增序号生成消息编号。 */
export class SequenceId {
  private current = 0

  /** 返回下一个编号。 */
  next(): string {
    this.current += 1
    return `m-${this.current}`
  }
}
