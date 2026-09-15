<template>
  <main class="login-page">
    <section class="login-panel" aria-labelledby="login-title">
      <div class="brand-mark" aria-hidden="true">ITS</div>
      <div class="login-heading">
        <p>知识服务平台</p>
        <h1 id="login-title">{{ isRegistering ? '注册客户端账号' : '登录工作台' }}</h1>
      </div>

      <el-form label-position="top" @submit.prevent="handleSubmit">
        <el-form-item label="用户名">
          <el-input
            v-model.trim="username"
            autocomplete="username"
            maxlength="64"
            placeholder="请输入用户名"
            size="large"
          />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="password"
            :autocomplete="isRegistering ? 'new-password' : 'current-password'"
            maxlength="256"
            placeholder="请输入密码"
            show-password
            size="large"
            type="password"
          />
        </el-form-item>
        <el-form-item v-if="isRegistering" label="确认密码">
          <el-input
            v-model="confirmPassword"
            autocomplete="new-password"
            maxlength="256"
            placeholder="请再次输入密码"
            show-password
            size="large"
            type="password"
          />
        </el-form-item>
        <p v-if="errorMessage" class="login-error" role="alert">{{ errorMessage }}</p>
        <el-button
          class="submit-button"
          :disabled="!canSubmit"
          :loading="submitting"
          native-type="submit"
          size="large"
          type="primary"
        >
          {{ isRegistering ? '注册并进入' : '登录' }}
        </el-button>
        <el-button class="mode-button" link type="primary" @click="toggleMode">
          {{ isRegistering ? '已有账号，返回登录' : '注册客户端账号' }}
        </el-button>
      </el-form>
    </section>
  </main>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login, register } from '@/api/auth'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const isRegistering = ref(false)
const submitting = ref(false)
const errorMessage = ref('')
const canSubmit = computed(() => username.value.length > 0 && password.value.length >= 8 && (!isRegistering.value || password.value === confirmPassword.value))

const toggleMode = () => {
  isRegistering.value = !isRegistering.value
  errorMessage.value = ''
  confirmPassword.value = ''
}

const handleSubmit = async () => {
  if (!canSubmit.value || submitting.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    const user = isRegistering.value
      ? await register(username.value, password.value)
      : await login(username.value, password.value)
    const requestedPath = typeof route.query.redirect === 'string' ? route.query.redirect : ''
    const fallbackPath = user.role === 'admin' ? '/knowledge' : '/chat'
    await router.replace(requestedPath || fallbackPath)
  } catch (error) {
    errorMessage.value = error.message || '登录失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}
</script>

<style lang="scss" scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: #f3f5f7;
  color: #202a35;
}

.login-panel {
  box-sizing: border-box;
  width: min(100%, 380px);
  padding: 36px;
  background: #fff;
  border: 1px solid #dce2e8;
  border-radius: 8px;
  box-shadow: 0 18px 50px rgba(31, 42, 55, 0.12);
}

.brand-mark {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  margin-bottom: 24px;
  border-radius: 8px;
  background: #176b5b;
  color: #fff;
  font-size: 15px;
  font-weight: 700;
}

.login-heading {
  margin-bottom: 28px;

  p {
    margin: 0 0 6px;
    color: #687583;
    font-size: 14px;
  }

  h1 {
    margin: 0;
    font-size: 26px;
    letter-spacing: 0;
  }
}

.submit-button {
  width: 100%;
  margin-top: 8px;
  background: #176b5b;
  border-color: #176b5b;
}

.login-error {
  margin: -4px 0 14px;
  color: #b42318;
  font-size: 13px;
}

.mode-button {
  display: flex;
  width: 100%;
  margin-top: 14px;
}

@media (max-width: 480px) {
  .login-page { padding: 16px; }
  .login-panel { padding: 28px 22px; }
}
</style>
