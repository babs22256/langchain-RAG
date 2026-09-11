<template>
  <div class="kb-page">
    <!-- 统计面板 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="8">
        <el-card>
          <div class="stat">
            <div class="num">{{ stats.document_count }}</div>
            <div class="label">文档数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <div class="stat">
            <div class="num">{{ stats.chunk_count }}</div>
            <div class="label">分块数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <div class="stat">
            <div class="num">{{ stats.vector_count }}</div>
            <div class="label">向量数</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 上传 -->
    <el-card class="section">
      <template #header><span>上传文档</span></template>
      <el-upload
        drag
        :auto-upload="false"
        :show-file-list="false"
        accept=".pdf,.docx,.txt,.md"
        :on-change="onFileChange"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">将文件拖到此处，或<em>点击选择</em></div>
        <template #tip>
          <div class="el-upload__tip">
            支持 PDF / DOCX / TXT / Markdown，上传后将自动分块、向量化入库
          </div>
        </template>
      </el-upload>
      <div v-if="selectedFile" class="upload-actions">
        <span class="file-info">{{ selectedFile.name }}（{{ formatSize(selectedFile.size) }}）</span>
        <el-button type="primary" :loading="uploading" @click="handleUpload">
          上传并入库
        </el-button>
      </div>
    </el-card>

    <!-- 文档列表 -->
    <el-card class="section">
      <template #header><span>文档列表</span></template>
      <el-table :data="documents" v-loading="loadingTable" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="文件名" min-width="220" show-overflow-tooltip />
        <el-table-column prop="file_type" label="类型" width="80" />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.size) }}</template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="分块数" width="90" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openPreview(row)">预览</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 分块预览 -->
    <el-dialog v-model="previewVisible" :title="`分块预览 - ${previewName}`" width="70%">
      <el-scrollbar max-height="60vh">
        <div v-for="c in chunks" :key="c.id" class="chunk-item">
          <div class="chunk-index">第 {{ c.chunk_index + 1 }} 段</div>
          <div class="chunk-text">{{ c.text }}</div>
        </div>
      </el-scrollbar>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import {
  uploadDocument,
  listDocuments,
  previewChunks,
  deleteDocument,
  getKBStats
} from '../api/kb'

const stats = ref({ document_count: 0, chunk_count: 0, vector_count: 0 })
const documents = ref([])
const selectedFile = ref(null)
const uploading = ref(false)
const loadingTable = ref(false)

const previewVisible = ref(false)
const previewName = ref('')
const chunks = ref([])

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}

function statusText(s) {
  return { pending: '处理中', done: '已完成', failed: '失败' }[s] || s
}
function statusType(s) {
  return { pending: 'warning', done: 'success', failed: 'danger' }[s] || 'info'
}

function onFileChange(uploadFile) {
  selectedFile.value = uploadFile.raw
}

async function loadAll() {
  loadingTable.value = true
  try {
    const [s, d] = await Promise.all([getKBStats(), listDocuments()])
    stats.value = s
    documents.value = d
  } finally {
    loadingTable.value = false
  }
}

async function handleUpload() {
  if (!selectedFile.value) return
  uploading.value = true
  try {
    await uploadDocument(selectedFile.value)
    ElMessage.success('上传成功，已向量化入库')
    selectedFile.value = null
    await loadAll()
  } catch {
    // 错误已由拦截器提示
  } finally {
    uploading.value = false
  }
}

async function openPreview(row) {
  previewName.value = row.name
  chunks.value = await previewChunks(row.id)
  previewVisible.value = true
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除文档「${row.name}」吗？将同时删除其向量与分块。`, '提示', {
    type: 'warning'
  })
  await deleteDocument(row.id)
  ElMessage.success('删除成功')
  await loadAll()
}

onMounted(loadAll)
</script>

<style scoped>
.kb-page {
  max-width: 1000px;
  margin: 0 auto;
}
.stats-row {
  margin-bottom: 16px;
}
.stat {
  text-align: center;
  padding: 8px 0;
}
.stat .num {
  font-size: 32px;
  font-weight: 700;
  color: #409eff;
}
.stat .label {
  color: #909399;
  margin-top: 4px;
}
.section {
  margin-bottom: 16px;
}
.upload-actions {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 16px;
}
.file-info {
  color: #606266;
  font-size: 14px;
}
.chunk-item {
  padding: 12px;
  border-bottom: 1px solid #f0f0f0;
}
.chunk-index {
  font-weight: 600;
  color: #409eff;
  margin-bottom: 6px;
}
.chunk-text {
  color: #303133;
  line-height: 1.6;
  white-space: pre-wrap;
}
</style>
