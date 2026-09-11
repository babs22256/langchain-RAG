<template>
  <el-card class="profile-card">
    <template #header>
      <span>账号设置</span>
    </template>
    <el-descriptions :column="1" border class="info">
      <el-descriptions-item label="用户名">{{ auth.user?.username }}</el-descriptions-item>
      <el-descriptions-item label="角色">
        <el-tag v-if="auth.isAdmin" type="warning">管理员</el-tag>
        <el-tag v-else>普通用户</el-tag>
      </el-descriptions-item>
    </el-descriptions>

    <el-divider content-position="left">修改密码</el-divider>
    <el-form :model="form" label-width="90px" class="pwd-form">
      <el-form-item label="旧密码">
        <el-input v-model="form.old_password" type="password" show-password />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input v-model="form.new_password" type="password" show-password />
      </el-form-item>
      <el-form-item label="确认新密码">
        <el-input v-model="form.confirm" type="password" show-password />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" @click="handleSubmit">
          确认修改
        </el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const form = ref({ old_password: '', new_password: '', confirm: '' })

async function handleSubmit() {
  if (!form.value.old_password || !form.value.new_password) {
    ElMessage.warning('请填写完整')
    return
  }
  if (form.value.new_password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  if (form.value.new_password !== form.value.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  loading.value = true
  try {
    await auth.changePassword(form.value.old_password, form.value.new_password)
    ElMessage.success('密码修改成功，请重新登录')
    auth.logout()
    window.location.href = '/login'
  } catch {
    // 错误已由拦截器提示
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.profile-card {
  max-width: 640px;
  margin: 0 auto;
}
.info {
  margin-bottom: 8px;
}
.pwd-form {
  margin-top: 16px;
  max-width: 420px;
}
</style>
