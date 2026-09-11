<template>
  <el-container class="layout">
    <el-header class="header">
      <div class="logo">🛒 RAG 电商知识库问答系统</div>
      <el-menu
        mode="horizontal"
        :default-active="activeMenu"
        router
        class="nav"
        :ellipsis="false"
      >
        <el-menu-item index="/chat">知识库问答</el-menu-item>
        <el-menu-item v-if="auth.isAdmin" index="/kb">知识库管理</el-menu-item>
        <el-menu-item index="/profile">账号设置</el-menu-item>
      </el-menu>
      <div class="user-box">
        <span class="username">
          {{ auth.user?.username }}
          <el-tag v-if="auth.isAdmin" size="small" type="warning">管理员</el-tag>
        </span>
        <el-button size="small" @click="handleLogout">退出登录</el-button>
      </div>
    </el-header>
    <el-main class="main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeMenu = computed(() => route.path)

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout {
  height: 100%;
}
.header {
  display: flex;
  align-items: center;
  background-color: #fff;
  border-bottom: 1px solid #e4e7ed;
  padding: 0 24px;
}
.logo {
  font-size: 18px;
  font-weight: 700;
  color: #303133;
  margin-right: 40px;
  white-space: nowrap;
}
.nav {
  flex: 1;
  border-bottom: none;
}
.user-box {
  display: flex;
  align-items: center;
  gap: 12px;
}
.username {
  font-size: 14px;
  color: #303133;
}
.main {
  height: calc(100% - 60px);
  overflow: auto;
}
</style>
