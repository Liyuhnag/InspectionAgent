import { createRouter, createWebHistory } from 'vue-router'

import { currentUser } from '@/api/session'
import LoginView from '@/views/LoginView.vue'
import RegisterView from '@/views/RegisterView.vue'
import ChatPage from '@/views/ChatPage.vue'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/register', name: 'register', component: RegisterView, meta: { public: true } },
    { path: '/', name: 'chat', component: ChatPage },
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.public) {
    return true
  }
  const username = await currentUser()
  if (!username) {
    return { name: 'login' }
  }
  return true
})

export default router
