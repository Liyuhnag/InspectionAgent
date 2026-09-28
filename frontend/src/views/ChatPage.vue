<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { currentUser, logout } from '@/api/session'
import ChatView from '@/views/ChatView.vue'

const router = useRouter()
const username = ref('')

onMounted(async () => {
  username.value = await currentUser()
})

/** 退出后回到登录页。 */
async function onLogout(): Promise<void> {
  await logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <ChatView :username="username" @logout="onLogout" />
</template>
