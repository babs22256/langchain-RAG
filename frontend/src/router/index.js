import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import Layout from '../layout/Layout.vue'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue')
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('../views/Register.vue')
  },
  {
    path: '/',
    component: Layout,
    redirect: '/chat',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'chat',
        name: 'chat',
        component: () => import('../views/Chat.vue')
      },
      {
        path: 'kb',
        name: 'kb',
        component: () => import('../views/AdminKB.vue'),
        meta: { requiresAdmin: true }
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('../views/Profile.vue')
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  // 未登录访问受保护页面 -> 跳登录
  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  // 非管理员访问管理页 -> 跳问答页
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: 'chat' }
  }
  return true
})

export default router
