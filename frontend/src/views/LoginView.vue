<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'

import { ApiError, login } from '@/api/session'
import AuthCard from '@/components/AuthCard.vue'

const router = useRouter()
const formRef = ref<FormInstance>()
const form = reactive({
  username: '',
  password: '',
})
const rules: FormRules = {
  username: [{ required: true, message: '请填写用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请填写密码', trigger: 'blur' }],
}
const error = ref('')
const submitting = ref(false)

/** 登录成功后进入聊天页。 */
async function submit(): Promise<void> {
  error.value = ''
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }
  submitting.value = true
  try {
    await login(form.username.trim(), form.password)
    await router.push({ name: 'chat' })
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '登录失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthCard title="登录" lead="使用已注册的用户名和密码。">
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
      <el-form-item label="用户名" prop="username">
        <el-input v-model="form.username" autocomplete="username" />
      </el-form-item>
      <el-form-item label="密码" prop="password">
        <el-input v-model="form.password" type="password" show-password autocomplete="current-password" />
      </el-form-item>
      <p v-if="error" class="auth-error">{{ error }}</p>
      <el-button class="auth-submit" type="primary" :loading="submitting" native-type="submit">登录</el-button>
    </el-form>
    <router-link class="auth-switch" to="/register">没有账号，去注册</router-link>
  </AuthCard>
</template>

<style scoped>
.auth-error {
  margin: 0 0 12px;
  color: #d4380d;
  font-size: 14px;
}

.auth-submit {
  width: 100%;
}

.auth-switch {
  display: inline-block;
  margin-top: 16px;
  color: #1677ff;
  font-size: 14px;
  text-decoration: none;
}
</style>
