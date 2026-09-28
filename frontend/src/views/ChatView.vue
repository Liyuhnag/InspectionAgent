<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { BubbleList, Conversations, XSender } from 'vue-element-plus-x'
import type { BubbleListItemProps } from 'vue-element-plus-x/types/BubbleList'

import portrait from '@/assets/ai-assistant.png'
import { preferDraft, senderText, visibleText } from '@/domain/chat/ChatSession'
import { DialogueDesk } from '@/domain/chat/DialogueDesk'
import { LocalTimedChunkSource, localReply } from '@/domain/chat/LocalTimedChunkSource'
import { SequenceId } from '@/domain/chat/SequenceId'
import type { TextChunkSource } from '@/domain/chat/types'

const props = withDefaults(
  defineProps<{
    streamSource?: TextChunkSource
  }>(),
  {
    streamSource: undefined,
  },
)

const ids = new SequenceId()
const source = props.streamSource ?? new LocalTimedChunkSource(localReply)
const desk = reactive(new DialogueDesk(source, () => ids.next()))
const senderRef = ref<{
  getModelValue: () => { text?: string }
  clear: () => void
  $el?: HTMLElement
} | null>(null)
const sessionHoverStyle = { background: '#e8f2ff', transform: 'none', boxShadow: 'none' }
const sessionActiveStyle = { background: '#d6e8ff', color: '#1677ff' }

/** 把消息转成气泡列表需要的展示数据。 */
function toBubble(message: (typeof desk.active.chat.messages)[number]): BubbleListItemProps & { key: string } {
  const content = visibleText(message.parts)
  return {
    key: message.id,
    content,
    placement: message.role === 'user' ? 'end' : 'start',
    loading: message.status === 'streaming' && content.length === 0,
    shape: 'corner',
    variant: message.role === 'user' ? 'outlined' : 'filled',
    noStyle: false,
  }
}

const dialogueItems = computed(() => desk.dialogues.map((item) => ({
  id: item.id,
  label: item.title,
})))

const bubbles = computed(() => desk.active.chat.messages.map((message) => toBubble(message)))

const failed = computed(() => {
  const last = desk.active.chat.messages[desk.active.chat.messages.length - 1]
  return last?.status === 'error'
})

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
  const text = draftText()
  const dialogue = desk.active
  const accepted = dialogue.chat.send(text)
  if (!accepted) {
    return
  }
  dialogue.nameFrom(text)
  senderRef.value?.clear()
}

/** 新建一个空会话，并回到 AI 形象页。 */
function createDialogue(): void {
  desk.create()
  senderRef.value?.clear()
}

/** 切换左侧会话。 */
function selectDialogue(item: { id?: string }): void {
  if (!item.id) {
    return
  }
  desk.select(item.id)
  senderRef.value?.clear()
}

/** 供测试直接提交一段文字。 */
function submitText(text: string): boolean {
  const dialogue = desk.active
  const accepted = dialogue.chat.send(text)
  if (accepted) {
    dialogue.nameFrom(text)
  }
  return accepted
}

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onEnter, true)
  source.stop()
})

window.addEventListener('keydown', onEnter, true)

defineExpose({ submitText, createDialogue, desk })
</script>

<template>
  <main class="chat-shell">
    <aside class="session-pane">
      <div class="session-toolbar">
        <h1>会话</h1>
        <el-button class="session-create" @click="createDialogue">新建会话</el-button>
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
    </aside>

    <section class="chat-pane">
      <div class="chat-stage" :class="{ 'chat-stage--empty': desk.active.empty }">
        <div v-if="desk.active.empty" class="chat-empty">
          <p class="chat-empty-title">我是你的巡检智能体<br />我能为你做些什么</p>
          <img class="chat-portrait" :src="portrait" alt="AI 助手" />
        </div>
        <BubbleList v-else class="chat-list" :list="bubbles" />
        <p v-if="desk.active.chat.streaming" class="chat-status">正在回复</p>
        <p v-else-if="failed" class="chat-status">回复中断，可以再次发送</p>
      </div>

      <div class="chat-sender">
        <XSender
          ref="senderRef"
          placeholder="输入消息"
          device="pc"
          submit-type="enter"
          :loading="desk.active.chat.streaming"
          :disabled="desk.active.chat.streaming"
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
  width: 280px;
  flex: none;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-right: 1px solid #d6e4ff;
}

.session-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 20px 16px 12px;
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
  padding: 16px 32px 0;
}

.chat-stage--empty {
  align-items: center;
  justify-content: center;
  padding: 0 48px 14vh;
  background:
    radial-gradient(ellipse 34% 42% at 62% 36%, rgba(214, 232, 255, 0.95), transparent 72%);
}

.chat-empty {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  width: min(860px, 100%);
}

.chat-portrait {
  width: min(440px, 52%);
  height: auto;
  flex: none;
  display: block;
  -webkit-mask-image: radial-gradient(ellipse 80% 78% at 50% 46%, #000 46%, transparent 74%);
  mask-image: radial-gradient(ellipse 80% 78% at 50% 46%, #000 46%, transparent 74%);
}

.chat-empty-title {
  position: relative;
  margin: 0 28px 72px 0;
  padding: 14px 18px;
  background: #ffffff;
  border: 1px solid #d6e4ff;
  border-radius: 14px;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.6;
  color: #1f2a44;
}

.chat-empty-title::after {
  content: "";
  position: absolute;
  right: -5px;
  top: 22px;
  width: 8px;
  height: 8px;
  background: #ffffff;
  border-right: 1px solid #d6e4ff;
  border-top: 1px solid #d6e4ff;
  transform: rotate(45deg);
}

.chat-list {
  flex: 1;
  min-height: 0;
}

.chat-status {
  margin: 0;
  padding: 8px 0 12px;
  color: #1677ff;
}

.chat-sender {
  margin: 0 32px 24px;
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

.chat-shell :deep(*:hover) {
  transform: none !important;
  translate: none !important;
}
</style>
