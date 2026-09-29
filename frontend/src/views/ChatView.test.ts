import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('vue-element-plus-x', () => ({
  BubbleList: {
    name: 'BubbleList',
    props: ['list'],
    template: '<ul><li v-for="item in list" :key="item.key">{{ item.content }}</li></ul>',
  },
  Conversations: {
    name: 'Conversations',
    props: ['items'],
    emits: ['change'],
    template: '<ul><li v-for="item in items" :key="item.id" @click="$emit(\'change\', { id: item.id })">{{ item.label }}</li></ul>',
  },
  Prompts: {
    name: 'Prompts',
    props: ['items'],
    emits: ['itemClick'],
    template: '<ul><li v-for="item in items" :key="item.key" class="starter" @click="$emit(\'itemClick\', item)">{{ item.label }}</li></ul>',
  },
  Welcome: {
    name: 'Welcome',
    props: ['title', 'description'],
    template: '<section class="welcome">{{ title }}</section>',
  },
  XSender: {
    name: 'XSender',
    template: '<div />',
  },
}))

vi.mock('@/api/chatSessions', () => ({
  createChatSession: vi.fn(),
  getChatSession: vi.fn(),
  listChatSessions: vi.fn(),
}))

import { SequenceId } from '@/domain/chat/SequenceId'
import type { TextChunkSource } from '@/domain/chat/types'
import { createChatSession, getChatSession, listChatSessions } from '@/api/chatSessions'
import ChatView from '@/views/ChatView.vue'

const firstSession = { id: 'session-1', title: '新会话', updated_at: '2026-01-01T00:00:00Z' }

async function mountChat(props: Record<string, unknown> = {}) {
  const wrapper = mount(ChatView, {
    props,
    global: {
      stubs: {
        ElButton: { template: '<button><slot /></button>' },
      },
    },
  })
  await flushPromises()
  return wrapper
}

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
  beforeEach(() => {
    vi.mocked(listChatSessions).mockReset().mockResolvedValue({ sessions: [firstSession] })
    vi.mocked(createChatSession).mockReset().mockResolvedValue({
      id: 'session-2',
      title: '新会话',
      updated_at: '2026-01-02T00:00:00Z',
    })
    vi.mocked(getChatSession).mockReset().mockResolvedValue(firstSession)
  })

  it('发送后在页面上显示逐段增长的回复', async () => {
    const source = new ManualSource()
    const wrapper = await mountChat({ streamSource: source })

    const exposed = wrapper.vm as unknown as {
      submitText: (text: string) => boolean
    }
    expect(wrapper.text()).toContain('新会话')
    expect(wrapper.find('.welcome').text()).toContain('巡锋')
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
    expect(wrapper.find('.welcome').exists()).toBe(false)
  })

  it('点击首页推荐任务会直接发送', async () => {
    const source = new ManualSource()
    const wrapper = await mountChat({ streamSource: source })

    await wrapper.find('.starter').trigger('click')
    expect(wrapper.text()).toContain('检查设备运行状态')
    expect(wrapper.text()).toContain('正在回复')
    expect(wrapper.find('.welcome').exists()).toBe(false)
  })

  it('会话栏可以收起再展开', async () => {
    const wrapper = await mountChat()

    expect(wrapper.text()).toContain('新建会话')
    await wrapper.get('[aria-label="收起会话栏"]').trigger('click')
    expect(wrapper.find('.session-pane').classes()).toContain('session-pane--collapsed')
    expect(wrapper.find('[aria-label="展开会话栏"]').exists()).toBe(true)
    await wrapper.get('[aria-label="展开会话栏"]').trigger('click')
    expect(wrapper.find('.session-pane').classes()).not.toContain('session-pane--collapsed')
  })

  it('服务端没有会话时自动创建默认会话', async () => {
    vi.mocked(listChatSessions).mockResolvedValue({ sessions: [] })
    const wrapper = await mountChat()

    expect(createChatSession).toHaveBeenCalledOnce()
    expect((wrapper.vm as unknown as { desk: { active: { id: string } } }).desk.active.id).toBe('session-2')
  })

  it('新建会话后选中服务端返回的编号', async () => {
    const wrapper = await mountChat()

    await wrapper.get('.session-create').trigger('click')
    await flushPromises()

    expect(createChatSession).toHaveBeenCalledOnce()
    expect((wrapper.vm as unknown as { desk: { active: { id: string } } }).desk.active.id).toBe('session-2')
  })

  it('切换会话前从服务端读取并校验编号', async () => {
    const secondSession = { id: 'session-2', title: '巡检记录', updated_at: '2026-01-02T00:00:00Z' }
    vi.mocked(listChatSessions).mockResolvedValue({ sessions: [firstSession, secondSession] })
    vi.mocked(getChatSession).mockResolvedValue(secondSession)
    const wrapper = await mountChat()

    await wrapper.findAll('.session-list li')[1].trigger('click')
    await flushPromises()

    expect(getChatSession).toHaveBeenCalledWith('session-2')
    expect((wrapper.vm as unknown as { desk: { active: { id: string; title: string } } }).desk.active)
      .toMatchObject({ id: 'session-2', title: '巡检记录' })
  })

  it('加载会话失败时显示错误并允许重试', async () => {
    vi.mocked(listChatSessions).mockRejectedValueOnce(new Error('服务不可用'))
    const wrapper = await mountChat()
    const exposed = wrapper.vm as unknown as { submitText: (text: string) => boolean }

    expect(wrapper.text()).toContain('服务不可用')
    expect(exposed.submitText('检查阀门')).toBe(false)
    await wrapper.get('.chat-stage button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('正在加载会话')
    expect(wrapper.text()).toContain('新会话')
  })
})

describe('SequenceId', () => {
  it('编号递增', () => {
    const ids = new SequenceId()
    expect(ids.next()).toBe('m-1')
    expect(ids.next()).toBe('m-2')
  })
})
