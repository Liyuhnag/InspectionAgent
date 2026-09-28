import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import LoginView from '@/views/LoginView.vue'
import RegisterView from '@/views/RegisterView.vue'

vi.mock('@/api/session', () => ({
  ApiError: class ApiError extends Error {},
  login: vi.fn(),
  register: vi.fn(),
  sendCode: vi.fn(),
}))

import { login, register, sendCode } from '@/api/session'

async function page(component: object, path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'login', component: LoginView },
      { path: '/register', name: 'register', component: RegisterView },
      { path: '/', name: 'chat', component: { template: '<div>聊天</div>' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, {
    global: {
      plugins: [ElementPlus, router],
    },
  })
  return { wrapper, router }
}

describe('登录页和注册页', () => {
  beforeEach(() => {
    vi.mocked(login).mockReset()
    vi.mocked(register).mockReset()
    vi.mocked(sendCode).mockReset()
  })

  it('登录成功后进入聊天页', async () => {
    vi.mocked(login).mockResolvedValue()
    const { wrapper, router } = await page(LoginView, '/login')
    await wrapper.find('input[autocomplete="username"]').setValue('ann')
    await wrapper.find('input[autocomplete="current-password"]').setValue('secret')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(login).toHaveBeenCalledWith('ann', 'secret')
    expect(router.currentRoute.value.name).toBe('chat')
  })

  it('注册成功后留在注册页', async () => {
    vi.mocked(sendCode).mockResolvedValue()
    vi.mocked(register).mockResolvedValue()
    const { wrapper, router } = await page(RegisterView, '/register')
    await wrapper.find('input[autocomplete="username"]').setValue('ann')
    await wrapper.find('input[autocomplete="new-password"]').setValue('secret')
    await wrapper.find('input[autocomplete="one-time-code"]').setValue('123456')
    await wrapper.findAll('button').find((button) => button.text() === '获取验证码')?.trigger('click')
    await flushPromises()
    expect(sendCode).toHaveBeenCalledWith('ann')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(register).toHaveBeenCalledWith('ann', 'secret', '123456')
    expect(router.currentRoute.value.name).toBe('register')
    expect(wrapper.text()).toContain('用户已创建')
  })
})
