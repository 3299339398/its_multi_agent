import { createRouter, createWebHistory } from 'vue-router'
import Layout from '@/layout/index.vue'
import { getAuthToken, verifyAuthSession } from '@/api/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录' }
  },
  {
    path: '/',
    component: Layout,
    redirect: '/knowledge',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('@/views/Knowledge.vue'),
        meta: { title: '知识库管理', icon: 'Files', requiresAdmin: true }
      },
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('@/views/Chat.vue'),
        meta: { title: '智能问答', icon: 'ChatDotRound' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async to => {
  if (to.path === '/login') {
    if (!getAuthToken()) return true
    try {
      const user = await verifyAuthSession()
      return user?.role === 'admin' ? '/knowledge' : '/chat'
    } catch {
      return true
    }
  }

  if (!to.matched.some(record => record.meta.requiresAuth)) return true
  if (!getAuthToken()) return { path: '/login', query: { redirect: to.fullPath } }

  try {
    const user = await verifyAuthSession()
    if (to.meta.requiresAdmin && user?.role !== 'admin') return '/chat'
    return true
  } catch {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
})

export default router
