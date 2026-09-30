import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('vue-element-plus-x', () => ({
  BubbleList: {
    name: 'BubbleList',
    props: ['list'],
    template: '<ul><li v-for="item in list" :key="item.key"><slot name="content" :item="item">{{ item.content }}</slot></li></ul>',
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
  getChatSessionHistory: vi.fn(),
  listChatSessions: vi.fn(),
  switchChatSessionBranch: vi.fn(),
}))

import { SequenceId } from '@/domain/chat/SequenceId'
import type { HistoryPage, HistoryTurn, TextChunkSource } from '@/domain/chat/types'
import {
  createChatSession,
  getChatSession,
  getChatSessionHistory,
  listChatSessions,
  switchChatSessionBranch,
} from '@/api/chatSessions'
import ChatView from '@/views/ChatView.vue'

const firstSession = { id: 'session-1', title: '新会话', updated_at: '2026-01-01T00:00:00Z' }
const emptyPage: HistoryPage = { turns: [], has_more: false }

async function mountChat(props: Record<string, unknown> = {}) {
  const wrapper = mount(ChatView, {
    props,
    global: {
      stubs: {
        ElButton: { template: '<button><slot /></button>' },
        ElInput: {
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template: '<textarea class="edit-box" :value="modelValue" '
            + '@input="$emit(\'update:modelValue\', $event.target.value)" />',
        },
      },
    },
  })
  await flushPromises()
  return wrapper
}

/** 生成一轮已完成的历史。 */
function turn(traceId: string, userText: string, reply: string, overrides: Partial<HistoryTurn> = {}): HistoryTurn {
  return {
    trace_id: traceId,
    user_text: userText,
    status: 'complete',
    created_at: '2026-01-01T00:00:00Z',
    reply,
    versions: { index: 1, total: 1, trace_ids: [traceId] },
    ...overrides,
  }
}

class ManualSource implements TextChunkSource {
  onChunk: ((chunk: string) => void) | null = null

  onDone: (() => void) | null = null

  input = ''

  siblingOf: string | undefined

  /** 保存回调。 */
  start(
    _sessionId: string,
    input: string,
    onChunk: (chunk: string) => void,
    onDone: () => void,
    _onError: (reason: Error) => void,
    siblingOf?: string,
  ): void {
    this.input = input
    this.siblingOf = siblingOf
    this.onChunk = onChunk
    this.onDone = onDone
  }

  /** 测试来源不需要取消计时。 */
  stop(): void {}
}

describe('ChatView', () => {
  beforeEach(() => {
    vi.mocked(listChatSessions).mockReset().mockResolvedValue({ sessions: [firstSession] })
    vi.mocked(getChatSessionHistory).mockReset().mockResolvedValue(emptyPage)
    vi.mocked(switchChatSessionBranch).mockReset().mockResolvedValue(emptyPage)
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

  it('重新打开会话时只发一次历史请求就恢复对话', async () => {
    vi.mocked(getChatSessionHistory).mockResolvedValue({
      turns: [turn('trace-1', '检查 1 号线压力', '已经输出的部分', { status: 'failed' })],
      has_more: false,
    })
    const wrapper = await mountChat()

    expect(getChatSessionHistory).toHaveBeenCalledOnce()
    expect(getChatSessionHistory).toHaveBeenCalledWith('session-1')
    expect(wrapper.text()).toContain('检查 1 号线压力')
    expect(wrapper.text()).toContain('已经输出的部分')
    expect(wrapper.text()).toContain('回复失败')
    expect(wrapper.find('.chat-more').exists()).toBe(false)
  })

  it('一轮回复结束后重新读取历史，新消息才可以编辑和重新生成', async () => {
    const source = new ManualSource()
    const wrapper = await mountChat({ streamSource: source })
    const exposed = wrapper.vm as unknown as { submitText: (text: string) => boolean }

    exposed.submitText('检查阀门')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.bubble-edit-start').exists()).toBe(false)
    expect(wrapper.find('.bubble-regenerate').exists()).toBe(false)

    vi.mocked(getChatSessionHistory).mockResolvedValue({
      turns: [turn('trace-1', '检查阀门', '收到')],
      has_more: false,
    })
    source.onChunk?.('收到')
    source.onDone?.()
    await flushPromises()

    expect(getChatSessionHistory).toHaveBeenLastCalledWith('session-1', { limit: 20 })
    expect(wrapper.find('.bubble-edit-start').exists()).toBe(true)
    expect(wrapper.find('.bubble-regenerate').exists()).toBe(true)
  })

  it('原位编辑：取消恢复原样，确认后丢弃后续轮次并以兄弟版本发送', async () => {
    vi.mocked(getChatSessionHistory).mockResolvedValue({
      turns: [turn('trace-1', '第一问', '第一答'), turn('trace-2', '第二问', '第二答')],
      has_more: false,
    })
    const source = new ManualSource()
    const wrapper = await mountChat({ streamSource: source })

    await wrapper.findAll('.bubble-edit-start')[0].trigger('click')
    expect((wrapper.get('.edit-box').element as HTMLTextAreaElement).value).toBe('第一问')
    await wrapper.get('.bubble-edit-cancel').trigger('click')
    expect(wrapper.find('.edit-box').exists()).toBe(false)
    expect(wrapper.text()).toContain('第二答')

    await wrapper.findAll('.bubble-edit-start')[0].trigger('click')
    await wrapper.get('.edit-box').setValue('   ')
    expect(wrapper.get('.bubble-edit-confirm').attributes('disabled')).toBeDefined()
    await wrapper.get('.edit-box').setValue('改过的第一问')
    await wrapper.get('.bubble-edit-confirm').trigger('click')

    expect(source.input).toBe('改过的第一问')
    expect(source.siblingOf).toBe('trace-1')
    expect(wrapper.find('.edit-box').exists()).toBe(false)
    expect(wrapper.text()).toContain('改过的第一问')
    expect(wrapper.text()).not.toContain('第二问')
    for (const button of wrapper.findAll('.bubble-edit-start, .bubble-regenerate')) {
      expect(button.attributes('disabled')).toBeDefined()
    }
  })

  it('重新生成用原输入发送兄弟版本', async () => {
    vi.mocked(getChatSessionHistory).mockResolvedValue({
      turns: [turn('trace-1', '第一问', '第一答'), turn('trace-2', '第二问', '第二答')],
      has_more: false,
    })
    const source = new ManualSource()
    const wrapper = await mountChat({ streamSource: source })

    await wrapper.findAll('.bubble-regenerate')[1].trigger('click')

    expect(source.input).toBe('第二问')
    expect(source.siblingOf).toBe('trace-2')
    expect(wrapper.text()).not.toContain('第二答')
    expect(wrapper.text()).toContain('第一答')
  })

  it('切换版本时调用接口并用返回的分支替换消息', async () => {
    const versions = { index: 2, total: 2, trace_ids: ['trace-old', 'trace-new'] }
    vi.mocked(getChatSessionHistory).mockResolvedValue({
      turns: [turn('trace-new', '新问法', '新回答', { versions })],
      has_more: false,
    })
    vi.mocked(switchChatSessionBranch).mockResolvedValue({
      turns: [
        turn('trace-old', '旧问法', '旧回答', { versions: { ...versions, index: 1 } }),
        turn('trace-old-2', '旧分支的追问', '旧分支的回答'),
      ],
      has_more: false,
    })
    const wrapper = await mountChat()

    expect(wrapper.text()).toContain('2 / 2')
    expect(wrapper.get('.bubble-version-next').attributes('disabled')).toBeDefined()
    await wrapper.get('.bubble-version-prev').trigger('click')
    await flushPromises()

    expect(switchChatSessionBranch).toHaveBeenCalledWith('session-1', 'trace-old')
    expect(wrapper.text()).toContain('1 / 2')
    expect(wrapper.text()).toContain('旧分支的追问')
    expect(wrapper.text()).not.toContain('新回答')
  })

  it('有更早轮次时可以加载到顶部', async () => {
    vi.mocked(getChatSessionHistory)
      .mockResolvedValueOnce({ turns: [turn('trace-2', '较新的问题', '较新的回答')], has_more: true })
      .mockResolvedValueOnce({ turns: [turn('trace-1', '较早的问题', '较早的回答')], has_more: false })
    const wrapper = await mountChat()

    await wrapper.get('.chat-more-button').trigger('click')
    await flushPromises()

    expect(getChatSessionHistory).toHaveBeenLastCalledWith('session-1', { before: 'trace-2' })
    expect(wrapper.text().indexOf('较早的问题')).toBeLessThan(wrapper.text().indexOf('较新的问题'))
    expect(wrapper.find('.chat-more').exists()).toBe(false)
  })
})

describe('SequenceId', () => {
  it('编号递增', () => {
    const ids = new SequenceId()
    expect(ids.next()).toBe('m-1')
    expect(ids.next()).toBe('m-2')
  })
})
