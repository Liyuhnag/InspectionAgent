import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('vue-element-plus-x', () => ({
  BubbleList: {
    name: 'BubbleList',
    props: ['list'],
    template: '<ul><li v-for="item in list" :key="item.key">{{ item.content }}</li></ul>',
  },
  Conversations: {
    name: 'Conversations',
    props: ['items'],
    template: '<ul><li v-for="item in items" :key="item.id">{{ item.label }}</li></ul>',
  },
  XSender: {
    name: 'XSender',
    template: '<div />',
  },
}))

import { SequenceId } from '@/domain/chat/SequenceId'
import type { TextChunkSource } from '@/domain/chat/types'
import ChatView from '@/views/ChatView.vue'

class ManualSource implements TextChunkSource {
  onChunk: ((chunk: string) => void) | null = null

  onDone: (() => void) | null = null

  /** 保存回调。 */
  start(
    _input: string,
    onChunk: (chunk: string) => void,
    onDone: () => void,
    _onError: (reason: Error) => void,
  ): void {
    this.onChunk = onChunk
    this.onDone = onDone
  }

  /** 测试来源不需要取消计时。 */
  stop(): void {}
}

describe('ChatView', () => {
  it('发送后在页面上显示逐段增长的回复', async () => {
    const source = new ManualSource()
    const wrapper = mount(ChatView, {
      props: { streamSource: source },
      global: {
        stubs: {
          ElButton: { template: '<button><slot /></button>' },
        },
      },
    })

    const exposed = wrapper.vm as unknown as {
      submitText: (text: string) => boolean
    }
    expect(wrapper.text()).toContain('新会话')
    expect(wrapper.find('img').attributes('alt')).toBe('AI 助手')
    expect(exposed.submitText('检查阀门')).toBe(true)
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('检查阀门')
    expect(wrapper.text()).toContain('正在回复')

    source.onChunk?.('收到')
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('收到')

    source.onDone?.()
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).not.toContain('正在回复')
    expect(wrapper.find('img').exists()).toBe(false)
  })
})

describe('SequenceId', () => {
  it('编号递增', () => {
    const ids = new SequenceId()
    expect(ids.next()).toBe('m-1')
    expect(ids.next()).toBe('m-2')
  })
})
