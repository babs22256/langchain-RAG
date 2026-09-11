<template>
  <el-container class="chat-container">
    <!-- 会话侧边栏 -->
    <el-aside width="260px" class="sidebar">
      <el-button type="primary" class="new-btn" :icon="Plus" @click="handleNewSession">
        新建会话
      </el-button>
      <el-scrollbar class="session-scroll">
        <div
          v-for="s in sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === currentSessionId }"
          @click="switchSession(s.id)"
        >
          <span class="session-title">{{ s.title }}</span>
          <el-icon class="del" @click.stop="handleDeleteSession(s.id)"><Delete /></el-icon>
        </div>
        <el-empty v-if="!sessions.length" description="暂无会话" :image-size="60" />
      </el-scrollbar>
    </el-aside>

    <!-- 对话区 -->
    <el-main class="chat-main">
      <div class="messages" ref="messagesRef">
        <el-empty
          v-if="!messages.length && !loading"
          description="开始你的第一次商品提问吧"
        />
        <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
          <div class="avatar">{{ m.role === 'user' ? '我' : 'AI' }}</div>
          <div class="bubble">
            <template v-if="m.role === 'user'">
              <div class="content">{{ m.content }}</div>
            </template>
            <template v-else>
              <div
                class="content markdown"
                v-html="m.content ? renderMarkdown(m.content) : '正在思考…'"
              ></div>
              <div v-if="m.citations && m.citations.length" class="citations">
                <div class="cite-title">📚 引用知识库片段（{{ m.citations.length }}）</div>
                <div v-for="(c, ci) in m.citations" :key="ci" class="cite-item">
                  <div class="cite-meta">
                    [{{ ci + 1 }}] {{ c.source }} · 第 {{ c.chunk_index + 1 }} 段 ·
                    相似度 {{ (c.score * 100).toFixed(1) }}%
                  </div>
                  <div class="cite-text">{{ c.text }}</div>
                </div>
              </div>
              <div v-if="m.retrieveTime != null" class="meta">
                检索 {{ m.retrieveTime }}s · 生成 {{ m.generateTime }}s
              </div>
            </template>
          </div>
        </div>
      </div>

      <div class="input-area">
        <el-input
          v-model="input"
          type="textarea"
          :rows="2"
          resize="none"
          placeholder="请输入关于商品的问题，Enter 发送，Shift+Enter 换行"
          @keydown.enter.exact.prevent="handleSend"
        />
        <el-button type="primary" :loading="loading" @click="handleSend">发送</el-button>
      </div>
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MarkdownIt from 'markdown-it'
import { Plus, Delete } from '@element-plus/icons-vue'
import { listSessions, deleteSession, listMessages } from '../api/session'

const md = new MarkdownIt({ breaks: true, linkify: true })

const sessions = ref([])
const messages = ref([])
const currentSessionId = ref(null)
const input = ref('')
const loading = ref(false)
const messagesRef = ref(null)

function renderMarkdown(content) {
  return md.render(content || '')
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

async function loadSessions() {
  sessions.value = await listSessions()
}

async function loadMessages(sessionId) {
  const msgs = await listMessages(sessionId)
  messages.value = msgs.map((m) => ({
    role: m.role,
    content: m.content,
    citations: m.citations ? safeParse(m.citations) : []
  }))
}

function safeParse(str) {
  try {
    return JSON.parse(str)
  } catch {
    return []
  }
}

async function switchSession(id) {
  currentSessionId.value = id
  await loadMessages(id)
  scrollToBottom()
}

function handleNewSession() {
  currentSessionId.value = null
  messages.value = []
}

async function handleDeleteSession(id) {
  await ElMessageBox.confirm('确定删除该会话及其全部消息吗？', '提示', { type: 'warning' })
  await deleteSession(id)
  ElMessage.success('会话已删除')
  if (currentSessionId.value === id) {
    currentSessionId.value = null
    messages.value = []
  }
  await loadSessions()
}

function handleSSEBlock(block, aiIndex) {
  let event = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  if (!data) return
  const payload = JSON.parse(data)
  if (event === 'meta') {
    messages.value[aiIndex].citations = payload.citations || []
    messages.value[aiIndex].retrieveTime = payload.retrieve_time
    if (payload.session_id && currentSessionId.value == null) {
      currentSessionId.value = payload.session_id
    }
  } else if (event === 'token') {
    messages.value[aiIndex].content += payload.text || ''
    scrollToBottom()
  } else if (event === 'done') {
    messages.value[aiIndex].generateTime = payload.generate_time
  }
}

async function handleSend() {
  const q = input.value.trim()
  if (!q || loading.value) return
  input.value = ''
  messages.value.push({ role: 'user', content: q, citations: [] })

  // 先插入空的 AI 消息占位，流式填充
  const aiIndex = messages.value.length
  messages.value.push({
    role: 'assistant',
    content: '',
    citations: [],
    retrieveTime: null,
    generateTime: null
  })
  scrollToBottom()
  loading.value = true

  try {
    const token = localStorage.getItem('token')
    const resp = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ session_id: currentSessionId.value, message: q })
    })

    if (!resp.ok) {
      let detail = '请求失败'
      try {
        detail = (await resp.json()).detail || detail
      } catch {}
      throw new Error(detail)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop()
      for (const block of blocks) {
        handleSSEBlock(block, aiIndex)
      }
    }
  } catch (e) {
    ElMessage.error(e.message || '请求失败')
    // 出错时移除未填充的空消息
    if (messages.value[aiIndex] && !messages.value[aiIndex].content) {
      messages.value.splice(aiIndex, 1)
    }
  } finally {
    loading.value = false
    scrollToBottom()
    if (currentSessionId.value != null) {
      await loadSessions()
    }
  }
}

onMounted(async () => {
  await loadSessions()
  if (sessions.value.length) {
    await switchSession(sessions.value[0].id)
  }
})
</script>

<style scoped>
.chat-container {
  height: 100%;
}
.sidebar {
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  padding: 12px;
}
.new-btn {
  margin-bottom: 12px;
}
.session-scroll {
  flex: 1;
}
.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  color: #303133;
  margin-bottom: 4px;
}
.session-item:hover {
  background: #f5f7fa;
}
.session-item.active {
  background: #ecf5ff;
  color: #409eff;
}
.session-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}
.del {
  color: #909399;
  opacity: 0;
}
.session-item:hover .del {
  opacity: 1;
}
.chat-main {
  display: flex;
  flex-direction: column;
  padding: 0;
}
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: #f5f7fa;
}
.msg-row {
  display: flex;
  margin-bottom: 16px;
}
.msg-row.user {
  flex-direction: row-reverse;
}
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
}
.msg-row.user .avatar {
  background: #67c23a;
}
.bubble {
  max-width: 72%;
  margin: 0 12px;
  padding: 10px 14px;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.msg-row.user .bubble {
  background: #d9ecff;
}
.content {
  white-space: pre-wrap;
  line-height: 1.6;
  color: #303133;
}
.markdown :deep(p) {
  margin: 0 0 8px;
}
.markdown :deep(code) {
  background: #f0f2f5;
  padding: 2px 5px;
  border-radius: 3px;
}
.markdown :deep(ul),
.markdown :deep(ol) {
  padding-left: 20px;
  margin: 8px 0;
}
.citations {
  margin-top: 10px;
  border-top: 1px dashed #e4e7ed;
  padding-top: 10px;
}
.cite-title {
  font-weight: 600;
  color: #409eff;
  margin-bottom: 8px;
  font-size: 13px;
}
.cite-item {
  margin-bottom: 8px;
  padding: 8px 10px;
  background: #f8fafc;
  border-radius: 4px;
}
.cite-meta {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.cite-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}
.meta {
  margin-top: 8px;
  font-size: 12px;
  color: #c0c4cc;
}
.input-area {
  display: flex;
  gap: 12px;
  padding: 16px;
  border-top: 1px solid #e4e7ed;
  background: #fff;
  align-items: flex-end;
}
.input-area .el-button {
  height: 56px;
}
</style>
