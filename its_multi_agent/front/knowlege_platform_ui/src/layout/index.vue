<template>
  <div class="app-wrapper">
    <div class="sidebar">
      <div class="logo">ITS Knowledge</div>
      <el-menu
        :default-active="activeMenu"
        background-color="#f8fafb"
        text-color="#596574"
        active-text-color="#115a4c"
        router
        class="el-menu-vertical"
      >
        <el-menu-item v-if="currentUser?.role === 'admin'" index="/knowledge">
          <el-icon><Files /></el-icon>
          <span>知识库管理</span>
        </el-menu-item>
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>智能问答</span>
        </el-menu-item>
      </el-menu>
      <div class="account-panel">
        <div class="account-copy">
          <strong>{{ currentUser?.username }}</strong>
          <span>{{ currentUser?.role === 'admin' ? '管理员' : '普通用户' }}</span>
        </div>
        <el-tooltip content="退出登录" placement="right">
          <el-button aria-label="退出登录" circle text @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
          </el-button>
        </el-tooltip>
      </div>
    </div>
    <div class="main-container">
      <router-view v-slot="{ Component }">
        <transition name="fade-transform" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChatDotRound, Files, SwitchButton } from '@element-plus/icons-vue'
import { clearAuthSession, getAuthUser } from '@/api/auth'

const route = useRoute()
const router = useRouter()
const activeMenu = computed(() => route.path)
const currentUser = ref(getAuthUser())

const handleLogout = () => {
  clearAuthSession()
  router.replace('/login')
}

const handleUnauthorized = () => router.replace('/login')

onMounted(() => window.addEventListener('auth:unauthorized', handleUnauthorized))
onBeforeUnmount(() => window.removeEventListener('auth:unauthorized', handleUnauthorized))
</script>

<style lang="scss" scoped>
.app-wrapper {
  display: flex;
  height: 100dvh;
  width: 100%;
  background-color: #0d1117;
  color: #c9d1d9;
}

.sidebar {
  width: 240px;
  background-color: #001529;
  border-right: 1px solid #30363d;
  display: flex;
  flex-direction: column;
  box-shadow: 2px 0 10px rgba(0,0,0,0.5);
  z-index: 10;

  .logo {
    height: 60px;
    line-height: 60px;
    text-align: center;
    font-size: 22px;
    font-weight: bold;
    background: linear-gradient(90deg, #00f260, #0575e6);
    -webkit-background-clip: text;
    color: transparent;
    border-bottom: 1px solid #30363d;
    letter-spacing: 1px;
  }
  
  .el-menu-vertical {
    border-right: none;
    flex: 1;
  }
}

.account-panel {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-top: 1px solid #30363d;

  .account-copy {
    min-width: 0;
    flex: 1;
    display: flex;
    flex-direction: column;

    strong, span {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    strong { color: #f0f3f6; font-size: 14px; }
    span { margin-top: 3px; color: #8b949e; font-size: 12px; }
  }
}

.main-container {
  min-width: 0;
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  background-image: radial-gradient(#2d333b 1px, transparent 1px);
  background-size: 30px 30px;
  background-color: #0d1117;
}

@media (max-width: 720px) {
  .app-wrapper {
    flex-direction: column;
  }

  .sidebar {
    width: 100%;
    height: 58px;
    flex: 0 0 58px;
    flex-direction: row;
    align-items: stretch;
    border-right: 0;
    border-bottom: 1px solid #30363d;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);

    .logo {
      width: 72px;
      height: 58px;
      line-height: 58px;
      flex: 0 0 72px;
      overflow: hidden;
      font-size: 0;
      border-bottom: 0;
    }

    .logo::after {
      content: 'ITS';
      font-size: 18px;
    }

    .el-menu-vertical {
      min-width: 0;
      display: flex;
      flex-direction: row;

      :deep(.el-menu-item) {
        height: 58px;
        padding: 0 12px;
        flex: 1;
        justify-content: center;
      }
    }
  }

  .account-panel {
    flex: 0 0 auto;
    padding: 8px;
    border-top: 0;

    .account-copy { display: none; }
  }

  .main-container {
    padding: 12px;
  }
}

@media (max-width: 420px) {
  .sidebar {
    .logo { width: 54px; flex-basis: 54px; }
    .el-menu-vertical :deep(.el-menu-item) { padding: 0 8px; }
    .el-menu-vertical :deep(.el-menu-item .el-icon) { margin-right: 5px; }
  }
}

.fade-transform-leave-active,
.fade-transform-enter-active {
  transition: all 0.4s ease;
}

.fade-transform-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}

.fade-transform-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
</style>
