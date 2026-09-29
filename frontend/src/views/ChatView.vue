<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { BubbleList, Conversations, Prompts, Welcome, XSender } from 'vue-element-plus-x'
import type { BubbleListItemProps } from 'vue-element-plus-x/types/BubbleList'
import type { PromptsItemsProps } from 'vue-element-plus-x/types/Prompts'

import portrait from '@/assets/ai-assistant.png'
import assistantAvatar from '@/assets/avatar-ai.svg'
import userAvatar from '@/assets/avatar-user.svg'
import { createChatSession, getChatSession, listChatSessions } from '@/api/chatSessions'
import { preferDraft, senderText, visibleText } from '@/domain/chat/ChatSession'
import { DialogueDesk } from '@/domain/chat/DialogueDesk'
import { renderMarkdown } from '@/domain/chat/renderMarkdown'
import { SequenceId } from '@/domain/chat/SequenceId'
import { SseChunkSource } from '@/domain/chat/SseChunkSource'
import type { TextChunkSource } from '@/domain/chat/types'

const props = withDefaults(
  defineProps<{
    streamSource?: TextChunkSource
    username?: string
  }>(),
  {
    streamSource: undefined,
    username: '',
  },
)

const collapsed = ref(false)
const ids = new SequenceId()
const source = props.streamSource ?? new SseChunkSource()
const desk = reactive(new DialogueDesk(source, () => ids.next(), false))
const sessionLoading = ref(true)
const sessionBusy = ref(false)
const sessionError = ref('')
let selectionRequest = 0
const senderRef = ref<{
  getModelValue: () => { text?: string }
  clear: () => void
  $el?: HTMLElement
} | null>(null)
const sessionHoverStyle = { background: '#e8f2ff', transform: 'none', boxShadow: 'none' }
const sessionActiveStyle = { background: '#d6e8ff', color: '#1677ff' }
const starterHoverStyle = { background: '#f0f6ff', borderColor: '#1677ff' }
const starters: PromptsItemsProps[] = [
  { key: 'status', label: '检查设备运行状态', description: '例如：3 号泵房的阀门和压力表' },
  { key: 'abnormal', label: '汇总今日巡检异常', description: '按区域列出异常点和处理进度' },
  { key: 'report', label: '生成巡检报告', description: '把本次巡检结果整理成报告' },
  { key: 'history', label: '查询历史巡检记录', description: '查看某台设备最近的巡检情况' },
].map((item) => ({ ...item, itemHoverStyle: starterHoverStyle }))

/** 把消息转成气泡列表需要的展示数据。 */
function toBubble(
  message: (typeof desk.active.chat.messages)[number],
): BubbleListItemProps & { key: string; plain: boolean } {
  const content = visibleText(message.parts)
  const fromUser = message.role === 'user'
  return {
    key: message.id,
    content,
    placement: fromUser ? 'end' : 'start',
    loading: message.status === 'streaming' && content.length === 0,
    shape: 'corner',
    variant: fromUser ? 'outlined' : 'filled',
    maxWidth: '640px',
    noStyle: false,
    avatar: fromUser ? userAvatar : assistantAvatar,
    avatarAlt: fromUser ? '我' : '巡锋',
    avatarSize: '36px',
    avatarGap: '12px',
    avatarShape: 'circle',
    avatarFit: 'cover',
    plain: fromUser,
  }
}

const activeDialogue = computed(() => desk.dialogues.find((item) => item.id === desk.activeId))

const dialogueItems = computed(() => desk.dialogues.map((item) => ({
  id: item.id,
  label: item.title,
})))

const bubbles = computed(() => activeDialogue.value?.chat.messages.map((message) => toBubble(message)) ?? [])

const failed = computed(() => {
  const messages = activeDialogue.value?.chat.messages ?? []
  const last = messages[messages.length - 1]
  return last?.status === 'error'
})

/** 从后端加载会话；空列表时创建一条默认会话。 */
async function loadSessions(): Promise<void> {
  const requestId = ++selectionRequest
  sessionLoading.value = true
  sessionError.value = ''
  try {
    const response = await listChatSessions()
    const sessions = response.sessions.length ? response.sessions : [await createChatSession()]
    if (requestId === selectionRequest) {
      desk.load(sessions)
    }
  } catch (error) {
    if (requestId === selectionRequest) {
      sessionError.value = _errorMessage(error, '会话加载失败，请重试')
    }
  } finally {
    if (requestId === selectionRequest) {
      sessionLoading.value = false
    }
  }
}

/** 按 Enter 发送。Shift+Enter 留给输入框换行。 */
function onEnter(event: KeyboardEvent): void {
  const target = event.target
  if (!(target instanceof Element) || !target.closest('.chat-sender')) {
    return
  }
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) {
    return
  }
  event.preventDefault()
  event.stopImmediatePropagation()
  submitDraft()
}

/** 读取输入框里的文字。 */
function draftText(): string {
  const modelText = senderText(senderRef.value?.getModelValue())
  const editable = senderRef.value?.$el?.querySelector('[contenteditable]')
  return preferDraft(modelText, editable?.textContent ?? '')
}

/** 提交输入。流式期间和空白内容都不会发送。 */
function submitDraft(): void {
  if (!activeDialogue.value || sessionLoading.value || sessionBusy.value) {
    return
  }
  const text = draftText()
  const dialogue = activeDialogue.value
  const accepted = dialogue.chat.send(text)
  if (!accepted) {
    return
  }
  sessionError.value = ''
  senderRef.value?.clear()
}

/** 新建一个空会话，并回到 AI 形象页。 */
async function createDialogue(): Promise<void> {
  if (sessionLoading.value || sessionBusy.value) {
    return
  }
  sessionError.value = ''
  sessionBusy.value = true
  try {
    const created = await createChatSession()
    desk.add(created.id, created.title)
    senderRef.value?.clear()
  } catch (error) {
    sessionError.value = _errorMessage(error, '新建会话失败，请重试')
  } finally {
    sessionBusy.value = false
  }
}

/** 切换左侧会话。 */
async function selectDialogue(item: { id?: string }): Promise<void> {
  if (!item.id || item.id === desk.activeId || sessionLoading.value || sessionBusy.value) {
    return
  }
  const requestId = ++selectionRequest
  sessionError.value = ''
  sessionBusy.value = true
  try {
    const selected = await getChatSession(item.id)
    if (requestId === selectionRequest) {
      desk.select(selected.id)
      desk.active.title = selected.title
      senderRef.value?.clear()
    }
  } catch (error) {
    if (requestId === selectionRequest) {
      sessionError.value = _errorMessage(error, '切换会话失败，请重试')
    }
  } finally {
    if (requestId === selectionRequest) {
      sessionBusy.value = false
    }
  }
}

/** 点击首页的推荐任务，直接作为第一条消息发送。 */
function sendStarter(item: PromptsItemsProps): void {
  if (item.label) {
    submitText(item.label)
  }
}

/** 供测试直接提交一段文字。 */
function submitText(text: string): boolean {
  const dialogue = activeDialogue.value
  if (!dialogue || sessionLoading.value || sessionBusy.value) {
    return false
  }
  const accepted = dialogue.chat.send(text)
  if (accepted) {
    sessionError.value = ''
  }
  return accepted
}

/** 把异常整理为会话操作的提示文字。 */
function _errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

onMounted(() => {
  void loadSessions()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onEnter, true)
  source.stop()
})

window.addEventListener('keydown', onEnter, true)

const emit = defineEmits<{
  logout: []
}>()

defineExpose({ submitText, createDialogue, loadSessions, desk })
</script>

<template>
  <main class="chat-shell">
    <aside class="session-pane" :class="{ 'session-pane--collapsed': collapsed }">
      <div class="session-clip">
        <div class="session-body" :inert="collapsed || sessionLoading || sessionBusy">
          <div class="session-toolbar">
            <h1>会话</h1>
            <el-button
              class="session-create"
              :disabled="sessionLoading || sessionBusy"
              @click="createDialogue"
            >新建会话</el-button>
          </div>
          <Conversations
            class="session-list"
            :active="desk.activeId"
            :items="dialogueItems"
            row-key="id"
            label-key="label"
            :show-built-in-menu="false"
            :items-hover-style="sessionHoverStyle"
            :items-active-style="sessionActiveStyle"
            @change="selectDialogue"
          />
          <div class="session-user">
            <img class="session-user-avatar" :src="userAvatar" alt="" />
            <span class="session-user-name">{{ props.username }}</span>
            <el-button class="session-logout" link @click="emit('logout')">退出</el-button>
          </div>
        </div>
      </div>
      <button
        class="session-fold"
        type="button"
        :aria-label="collapsed ? '展开会话栏' : '收起会话栏'"
        @click="collapsed = !collapsed"
      >
        <span class="session-fold-icon" />
      </button>
    </aside>

    <section class="chat-pane" :class="{ 'chat-pane--empty': !activeDialogue || activeDialogue.empty }">
      <p v-if="sessionError" class="chat-status" role="alert">{{ sessionError }}</p>
      <img
        v-if="activeDialogue?.empty"
        class="chat-backdrop"
        :src="portrait"
        alt=""
        aria-hidden="true"
      />
      <div class="chat-stage" :class="{ 'chat-stage--empty': !activeDialogue || activeDialogue.empty }">
        <div v-if="sessionLoading" class="chat-empty" role="status">正在加载会话</div>
        <div v-else-if="!activeDialogue" class="chat-empty">
          <el-button v-if="sessionError" @click="loadSessions">重试</el-button>
        </div>
        <div v-else-if="activeDialogue.empty" class="chat-empty">
          <Welcome
            class="chat-welcome"
            variant="borderless"
            :icon="assistantAvatar"
            title="你好，我是巡锋"
            description="告诉我要巡检的设备或区域，我可以帮你核对运行状态、汇总异常，并整理成巡检报告。"
          />
          <Prompts
            class="chat-starters"
            title="可以试试这样问"
            :items="starters"
            wrap
            @item-click="sendStarter"
          />
        </div>
        <BubbleList v-else class="chat-list" :list="bubbles">
          <template #content="{ item }">
            <span v-if="item.plain">{{ item.content }}</span>
            <div v-else class="bubble-md" v-html="renderMarkdown(item.content ?? '')" />
          </template>
        </BubbleList>
        <p v-if="activeDialogue?.chat.streaming" class="chat-status">正在回复</p>
        <p v-else-if="failed" class="chat-status">回复中断，可以再次发送</p>
      </div>

      <div class="chat-sender">
        <XSender
          ref="senderRef"
          placeholder="输入消息"
          device="pc"
          submit-type="enter"
          :loading="activeDialogue?.chat.streaming ?? false"
          :disabled="!activeDialogue || sessionLoading || sessionBusy || (activeDialogue?.chat.streaming ?? false)"
          :tip-config="false"
          @submit="submitDraft"
        />
      </div>
    </section>
  </main>
</template>

<style scoped>
.chat-shell {
  height: 100vh;
  display: flex;
  background: #f5f8ff;
  color: #1f2a44;
}

.session-pane {
  position: relative;
  width: 280px;
  flex: none;
  background: #ffffff;
  border-right: 1px solid #d6e4ff;
  transition: width 0.24s ease;
}

.session-pane--collapsed {
  width: 0;
}

.session-clip {
  height: 100%;
  overflow: hidden;
}

.session-body {
  width: 280px;
  height: 100%;
  display: flex;
  flex-direction: column;
  transition: opacity 0.16s ease;
}

.session-pane--collapsed .session-body {
  opacity: 0;
}

.session-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 20px 16px 12px;
}

.session-fold {
  position: absolute;
  z-index: 2;
  top: calc(50% - 28px);
  left: 100%;
  display: grid;
  place-items: center;
  width: 18px;
  height: 56px;
  padding: 0;
  border: 1px solid #d6e4ff;
  border-left: 0;
  border-radius: 0 10px 10px 0;
  background: #ffffff;
  cursor: pointer;
}

.session-fold:focus-visible {
  outline: 2px solid #1677ff;
  outline-offset: 2px;
}

.session-fold-icon {
  width: 7px;
  height: 7px;
  margin-left: -3px;
  border-right: 2px solid #1677ff;
  border-bottom: 2px solid #1677ff;
  border-radius: 1px;
  transform: rotate(135deg);
}

.session-pane--collapsed .session-fold-icon {
  margin-left: -5px;
  transform: rotate(-45deg);
}

.session-toolbar h1 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1677ff;
}

.session-create {
  border-color: #1677ff;
  color: #1677ff;
}

.session-user {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: auto;
  padding: 12px 16px;
  border-top: 1px solid #d6e4ff;
}

.session-user-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  flex: none;
}

.session-user-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: #1f2a44;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-logout {
  flex: none;
  color: #5b6b88;
}

.session-list {
  flex: 1;
  min-height: 0;
}

.chat-pane {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.chat-stage {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 880px;
  margin: 0 auto;
  padding: 24px 32px 0;
  box-sizing: border-box;
}

.chat-pane--empty {
  position: relative;
  overflow: hidden;
}

.chat-backdrop {
  position: absolute;
  right: 2%;
  top: 50%;
  width: min(44%, 540px);
  height: auto;
  transform: translateY(-58%);
  pointer-events: none;
  -webkit-mask-image: radial-gradient(ellipse 76% 70% at 50% 42%, #000 42%, transparent 70%);
  mask-image: radial-gradient(ellipse 76% 70% at 50% 42%, #000 42%, transparent 70%);
}

.chat-stage--empty {
  justify-content: center;
  padding-bottom: 8vh;
}

.chat-pane--empty .chat-stage,
.chat-pane--empty .chat-sender {
  position: relative;
  z-index: 1;
}

.chat-pane--empty .chat-stage {
  max-width: 640px;
  margin-left: 6%;
}

@media (max-width: 1280px) {
  .chat-backdrop {
    display: none;
  }

  .chat-pane--empty .chat-stage {
    margin-left: auto;
  }
}

.chat-empty {
  display: flex;
  flex-direction: column;
  gap: 32px;
  padding: 0 8px;
}

.chat-welcome {
  --elx-welcome-filled-bg: transparent;
  --elx-welcome-icon-size: 56px;
  --elx-welcome-padding: 0;
  align-items: center;
}

.chat-welcome :deep(.elx-welcome__icon) {
  border-radius: 50%;
}

.chat-welcome :deep(.elx-welcome__icon .icon-image) {
  padding: 0;
}

.chat-welcome :deep(.elx-welcome__icon .el-image__inner) {
  object-fit: cover;
}

.chat-welcome :deep(.elx-welcome__title) {
  font-size: 22px;
  color: #1f2a44;
}

.chat-welcome :deep(.elx-welcome__description) {
  line-height: 1.7;
  color: #5b6b88;
}

.chat-starters :deep(.elx-prompts__title) {
  font-size: 13px;
  color: #5b6b88;
}

.chat-starters :deep(.elx-prompts__items) {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.chat-starters :deep(.elx-prompts__item) {
  border-color: #d6e4ff;
  border-radius: 10px;
}

.chat-starters :deep(.elx-prompts__item-label) {
  color: #1f2a44;
}

.chat-starters :deep(.elx-prompts__item-description) {
  font-size: 13px;
  color: #5b6b88;
}

.chat-list {
  flex: 1;
  min-height: 0;
}

.chat-status {
  margin: 0;
  padding: 8px 0 12px 48px;
  font-size: 13px;
  color: #5b6b88;
}

.chat-sender {
  width: calc(100% - 64px);
  max-width: 816px;
  margin: 0 auto 24px;
  box-sizing: border-box;
  background: #ffffff;
  border: 1px solid #d6e4ff;
  border-radius: 12px;
}

.chat-sender:focus-within {
  border-color: #1677ff;
}

/* XSender 用 ::after 再画一圈边框，圆角是 24px，和外壳的 12px 错开，左上角会多出一条线。 */
.chat-sender :deep(.elx-x-sender) {
  border-radius: inherit;
  box-shadow: none;
  background: transparent;
}

.chat-sender :deep(.elx-x-sender)::after,
.chat-sender :deep(.elx-x-sender):focus-within::after {
  border-width: 0 !important;
}

.chat-shell :deep(.elx-bubble--end .elx-bubble__content) {
  background: #1677ff;
  color: #ffffff;
}

.chat-shell :deep(.elx-bubble--start .elx-bubble__content) {
  background: #ffffff;
  color: #1f2a44;
  border: 1px solid #d6e4ff;
}

.bubble-md :deep(p),
.bubble-md :deep(ul),
.bubble-md :deep(ol),
.bubble-md :deep(pre) {
  margin: 0 0 8px;
}

.bubble-md :deep(p:last-child),
.bubble-md :deep(ul:last-child),
.bubble-md :deep(ol:last-child),
.bubble-md :deep(pre:last-child) {
  margin-bottom: 0;
}

.bubble-md :deep(ul),
.bubble-md :deep(ol) {
  padding-left: 1.2em;
}

.bubble-md :deep(h1),
.bubble-md :deep(h2),
.bubble-md :deep(h3) {
  margin: 0 0 8px;
  font-size: 16px;
  line-height: 1.4;
}

.bubble-md :deep(code) {
  padding: 0 4px;
  border-radius: 4px;
  background: #f5f8ff;
}

.bubble-md :deep(pre) {
  overflow: auto;
  padding: 8px 12px;
  border-radius: 8px;
  background: #f5f8ff;
}

.bubble-md :deep(pre code) {
  padding: 0;
  background: transparent;
}

.chat-shell :deep(*:hover) {
  transform: none !important;
  translate: none !important;
}
</style>
