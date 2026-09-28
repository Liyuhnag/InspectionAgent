<script setup lang="ts">
import { reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'

import { ApiError, register, sendCode } from '@/api/session'
import AuthCard from '@/components/AuthCard.vue'

const formRef = ref<FormInstance>()
const form = reactive({
  username: '',
  password: '',
  code: '',
})
const rules: FormRules = {
  username: [{ required: true, message: '请填写用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请填写密码', trigger: 'blur' }],
  code: [{ required: true, message: '请填写验证码', trigger: 'blur' }],
}
const notice = ref('')
const error = ref('')
const sending = ref(false)
const submitting = ref(false)

/** 向该用户名发送验证码。 */
async function requestCode(): Promise<void> {
  error.value = ''
  notice.value = ''
  const username = form.username.trim()
  if (!username) {
    error.value = '请填写用户名'
    return
  }
  sending.value = true
  try {
    await sendCode(username)
    notice.value = '已发送'
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '发送失败'
  } finally {
    sending.value = false
  }
}

/** 提交注册。成功后留在本页。 */
async function submit(): Promise<void> {
  error.value = ''
  notice.value = ''
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }
  submitting.value = true
  try {
    await register(form.username.trim(), form.password, form.code.trim())
    notice.value = '用户已创建'
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '注册失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthCard title="注册" lead="填写用户名、密码和验证码。">
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
      <el-form-item label="用户名" prop="username">
        <el-input v-model="form.username" autocomplete="username" />
      </el-form-item>
      <el-form-item label="密码" prop="password">
        <el-input v-model="form.password" type="password" show-password autocomplete="new-password" />
      </el-form-item>
      <el-form-item label="验证码" prop="code">
        <div class="code-row">
          <el-input v-model="form.code" autocomplete="one-time-code" />
          <el-button :loading="sending" @click="requestCode">获取验证码</el-button>
        </div>
      </el-form-item>
      <p v-if="notice" class="auth-notice">{{ notice }}</p>
      <p v-if="error" class="auth-error">{{ error }}</p>
      <el-button class="auth-submit" type="primary" :loading="submitting" native-type="submit">注册</el-button>
    </el-form>
    <router-link class="auth-switch" to="/login">已有账号，去登录</router-link>
  </AuthCard>
</template>

<style scoped>
.code-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.code-row .el-input {
  flex: 1;
}

.auth-notice,
.auth-error {
  margin: 0 0 12px;
  font-size: 14px;
}

.auth-notice {
  color: #1677ff;
}

.auth-error {
  color: #d4380d;
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
