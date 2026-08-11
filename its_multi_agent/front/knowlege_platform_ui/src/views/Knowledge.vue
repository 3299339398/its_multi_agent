<template>
  <div class="knowledge-container">
    <header class="page-header">
      <div>
        <p class="eyebrow">ADMIN WORKSPACE</p>
        <h2>知识库管理</h2>
        <p class="subtitle">管理文档入库、索引状态和知识空间。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" plain @click="refreshAll">刷新</el-button>
    </header>

    <section class="stats-grid" aria-label="知识库统计">
      <article v-for="item in statCards" :key="item.key" class="stat-card">
        <span>{{ item.label }}</span>
        <strong>{{ statistics[item.key] ?? 0 }}</strong>
      </article>
    </section>

    <el-card class="upload-card">
      <template #header>
        <div class="card-header">
          <div>
            <strong>文档入库</strong>
            <span>支持 Markdown、TXT、PDF、DOCX、XLSX，单个文件不超过 10 MB。</span>
          </div>
        </div>
      </template>
      <el-form class="scope-form" inline label-position="top">
        <el-form-item label="知识空间">
          <el-input v-model.trim="uploadScope.knowledge_space" maxlength="64" placeholder="default" />
        </el-form-item>
        <el-form-item label="知识领域">
          <el-select v-model="uploadScope.domain" placeholder="选择知识领域">
            <el-option v-for="item in domainOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <el-upload
        class="upload-area"
        drag
        action=""
        :http-request="handleUpload"
        :show-file-list="false"
        :disabled="uploading"
        accept=".md,.txt,.pdf,.docx,.xlsx,text/markdown,text/plain,application/pdf"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="el-upload__text">将文档拖到此处，或 <em>点击选择文件</em></div>
        <div class="el-upload__tip">上传后会自动提取内容并建立向量与关键词索引。</div>
      </el-upload>
      <el-alert v-if="uploadMessage" :title="uploadMessage" :type="uploadFailed ? 'error' : 'success'" :closable="false" show-icon />
    </el-card>

    <section class="documents-section">
      <div class="section-heading">
        <div>
          <h3>文档目录</h3>
          <span>共 {{ total }} 个文档</span>
        </div>
      </div>
      <el-form class="filter-form" inline @submit.prevent="applyFilters">
        <el-form-item>
          <el-input v-model.trim="filters.search" clearable :prefix-icon="Search" placeholder="搜索文件名" @keyup.enter="applyFilters" />
        </el-form-item>
        <el-form-item>
          <el-input v-model.trim="filters.knowledge_space" clearable placeholder="知识空间" @keyup.enter="applyFilters" />
        </el-form-item>
        <el-form-item>
          <el-select v-model="filters.domain" clearable placeholder="知识领域" @change="applyFilters">
            <el-option v-for="item in domainOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-select v-model="filters.status" clearable placeholder="全部状态" @change="applyFilters">
            <el-option label="处理中" value="processing" />
            <el-option label="已完成" value="complete" />
            <el-option label="失败" value="failed" />
            <el-option label="删除失败" value="deletion_failed" />
          </el-select>
        </el-form-item>
        <el-button :icon="Search" type="primary" @click="applyFilters">查询</el-button>
      </el-form>

      <el-table v-loading="loading" :data="documents" class="document-table" empty-text="暂无符合条件的文档">
        <el-table-column label="文件" min-width="220">
          <template #default="{ row }">
            <div class="file-cell"><strong>{{ row.file_name }}</strong><small>{{ row.document_hash.slice(0, 12) }}...</small></div>
          </template>
        </el-table-column>
        <el-table-column label="范围" min-width="150">
          <template #default="{ row }"><span>{{ row.knowledge_space }} / {{ row.domain }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }"><el-tag :type="statusType(row.status)" effect="plain">{{ statusLabel(row.status) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="切片" prop="chunks_added" width="80" />
        <el-table-column label="大小" width="100"><template #default="{ row }">{{ formatBytes(row.file_size) }}</template></el-table-column>
        <el-table-column label="上传人" prop="uploaded_by" width="110" />
        <el-table-column label="更新时间" width="170"><template #default="{ row }">{{ formatTime(row.updated_at) }}</template></el-table-column>
        <el-table-column fixed="right" label="操作" width="90">
          <template #default="{ row }">
            <el-tooltip content="删除文档" placement="top">
              <el-button aria-label="删除文档" :icon="Delete" circle text type="danger" :disabled="row.status === 'processing'" @click="confirmDelete(row)" />
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        background
        layout="total, sizes, prev, pager, next"
        @current-change="loadDocuments"
        @size-change="handleSizeChange"
      />
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { Delete, Refresh, Search, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import { deleteDocument, getDocumentStatistics, getIngestionTask, listDocuments, uploadFile } from '@/api/knowledge'

const documents = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const uploading = ref(false)
const uploadMessage = ref('')
const uploadFailed = ref(false)
const activeTaskId = ref('')
let taskTimer
let taskPollAttempts = 0
const MAX_TASK_POLL_ATTEMPTS = 120
const statistics = reactive({
  total_documents: 0,
  complete_documents: 0,
  processing_documents: 0,
  failed_documents: 0,
  total_chunks: 0,
  knowledge_spaces: 0,
  domains: 0
})
const filters = reactive({ search: '', status: '', knowledge_space: '', domain: '' })
const uploadScope = reactive({ knowledge_space: 'default', domain: 'general' })
const domainOptions = [
  { value: 'general', label: '通用' },
  { value: 'policy', label: '制度政策' },
  { value: 'technical', label: '技术资料' },
  { value: 'product', label: '产品资料' },
  { value: 'project', label: '项目资料' },
  { value: 'service', label: '服务资料' }
]
const statCards = [
  { key: 'total_documents', label: '文档总数' },
  { key: 'complete_documents', label: '已完成' },
  { key: 'processing_documents', label: '处理中' },
  { key: 'failed_documents', label: '失败待处理' },
  { key: 'total_chunks', label: '索引切片' },
  { key: 'knowledge_spaces', label: '知识空间' }
]

const queryParams = computed(() => ({
  page: page.value,
  page_size: pageSize.value,
  search: filters.search,
  status: filters.status,
  knowledge_space: filters.knowledge_space,
  domain: filters.domain
}))

const loadDocuments = async () => {
  loading.value = true
  try {
    const result = await listDocuments(queryParams.value)
    documents.value = result.items || []
    total.value = result.total || 0
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '读取文档目录失败')
  } finally {
    loading.value = false
  }
}

const loadStatistics = async () => {
  try {
    Object.assign(statistics, await getDocumentStatistics())
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '读取知识库统计失败')
  }
}

const refreshAll = () => Promise.all([loadDocuments(), loadStatistics()])
const applyFilters = () => { page.value = 1; loadDocuments() }
const handleSizeChange = size => { pageSize.value = size; page.value = 1; loadDocuments() }

const handleUpload = async ({ file }) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('knowledge_space', uploadScope.knowledge_space || 'default')
  formData.append('domain', uploadScope.domain || 'general')
  uploading.value = true
  uploadMessage.value = ''
  try {
    const result = await uploadFile(formData)
    uploadFailed.value = false
    if (result.status === 'queued' && result.task_id) {
      activeTaskId.value = result.task_id
      uploadMessage.value = `${file.name} 已提交后台任务，正在处理...`
      uploadFailed.value = false
      taskPollAttempts = 0
      taskTimer = window.setInterval(() => pollTask(file.name), 1500)
      return
    }
    uploadMessage.value = result.status === 'duplicate'
      ? `${file.name} 已存在，跳过重复入库。`
      : `${file.name} 入库成功，新增 ${result.chunks_added} 个切片。`
    ElMessage.success(uploadMessage.value)
    await refreshAll()
  } catch (error) {
    uploadFailed.value = true
    uploadMessage.value = error.response?.data?.detail || '文档入库失败，请稍后重试'
    ElMessage.error(uploadMessage.value)
  } finally {
    if (!activeTaskId.value) uploading.value = false
  }
}

const pollTask = async fileName => {
  if (!activeTaskId.value) return
  taskPollAttempts += 1
  try {
    const task = await getIngestionTask(activeTaskId.value)
    if (task.status === 'success') {
      window.clearInterval(taskTimer); taskTimer = undefined; activeTaskId.value = ''
      uploading.value = false
      uploadMessage.value = `${fileName} 入库完成，新增 ${task.chunks_added} 个切片。`
      ElMessage.success(uploadMessage.value)
      await refreshAll()
    } else if (task.status === 'failed') {
      window.clearInterval(taskTimer); taskTimer = undefined; activeTaskId.value = ''
      uploading.value = false; uploadFailed.value = true
      uploadMessage.value = task.error_message || '文档入库失败，可重试。'
      ElMessage.error(uploadMessage.value)
      await refreshAll()
    }
  } catch { /* transient polling errors are retried */ }
  if (taskPollAttempts >= MAX_TASK_POLL_ATTEMPTS && taskTimer) {
    window.clearInterval(taskTimer); taskTimer = undefined; activeTaskId.value = ''
    uploading.value = false; uploadFailed.value = true
    uploadMessage.value = '任务状态长时间未返回，请刷新页面后重试。'
  }
}

const confirmDelete = async row => {
  try {
    await ElMessageBox.confirm(
      `确认删除“${row.file_name}”吗？删除后将同时移除向量和关键词索引。`,
      '删除文档',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
    await deleteDocument(row.document_hash)
    ElMessage.success('文档已删除')
    await refreshAll()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error.response?.data?.detail || '文档删除失败')
    }
  }
}

const statusLabel = status => ({ processing: '处理中', complete: '已完成', failed: '失败', deletion_failed: '删除失败', deleted: '已删除' }[status] || status)
const statusType = status => ({ processing: 'warning', complete: 'success', failed: 'danger', deletion_failed: 'danger', deleted: 'info' }[status] || 'info')
const formatBytes = bytes => {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`
}
const formatTime = timestamp => timestamp ? new Date(timestamp * 1000).toLocaleString() : '-'

onMounted(refreshAll)
onUnmounted(() => { if (taskTimer) window.clearInterval(taskTimer) })
</script>

<style lang="scss" scoped>
.knowledge-container { max-width: 1280px; margin: 0 auto; }
.page-header, .section-heading, .card-header { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.page-header { margin-bottom: 24px; }
.eyebrow { margin: 0 0 6px; color: #58a6ff; font-size: 11px; font-weight: 700; letter-spacing: 1.2px; }
h2, h3 { margin: 0; color: #fff; }
h2 { font-size: 24px; }
h3 { font-size: 18px; }
.subtitle, .card-header span, .section-heading span { color: #8b949e; font-size: 13px; }
.subtitle { margin: 8px 0 0; }
.stats-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }
.stat-card { padding: 16px; border: 1px solid #30363d; border-radius: 6px; background: #161b22; }
.stat-card span { display: block; color: #8b949e; font-size: 12px; }
.stat-card strong { display: block; margin-top: 8px; color: #f0f3f6; font-size: 25px; }
.upload-card, .documents-section { margin-bottom: 18px; }
.upload-card { border-color: #30363d; background: #161b22; }
.card-header { align-items: flex-start; }
.card-header div { display: flex; flex-direction: column; gap: 5px; }
.scope-form { margin-bottom: 4px; }
.scope-form :deep(.el-form-item) { margin-right: 14px; }
.scope-form :deep(.el-input) { width: 180px; }
.upload-area :deep(.el-upload-dragger) { width: 100%; min-height: 150px; box-sizing: border-box; background: #0d1117; border-color: #30363d; }
.upload-area :deep(.el-upload-dragger:hover) { border-color: #58a6ff; }
.upload-icon { margin: 28px 0 8px; color: #58a6ff; font-size: 42px; }
.upload-area :deep(.el-upload__text) { color: #8b949e; }
.upload-area :deep(em) { color: #58a6ff; font-style: normal; }
.upload-area :deep(.el-upload__tip) { color: #6e7681; }
.upload-card :deep(.el-alert) { margin-top: 14px; }
.documents-section { padding: 20px; border: 1px solid #30363d; border-radius: 6px; background: #161b22; }
.filter-form { margin: 20px 0 14px; }
.filter-form :deep(.el-form-item) { margin-right: 10px; margin-bottom: 8px; }
.filter-form :deep(.el-input), .filter-form :deep(.el-select) { width: 160px; }
.document-table { width: 100%; --el-table-bg-color: #161b22; --el-table-tr-bg-color: #161b22; --el-table-header-bg-color: #0d1117; --el-table-border-color: #30363d; --el-table-row-hover-bg-color: #1f242d; }
.file-cell { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.file-cell strong { overflow: hidden; color: #f0f3f6; text-overflow: ellipsis; white-space: nowrap; }
.file-cell small { color: #6e7681; font-family: monospace; }
.documents-section :deep(.el-pagination) { justify-content: flex-end; margin-top: 18px; }
@media (max-width: 900px) { .stats-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 600px) {
  .page-header { align-items: flex-start; }
  .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .documents-section { padding: 14px 10px; }
  .filter-form { display: grid; grid-template-columns: 1fr 1fr; }
  .filter-form :deep(.el-form-item), .filter-form :deep(.el-input), .filter-form :deep(.el-select) { width: 100%; }
  .filter-form .el-button { width: 100%; }
  .documents-section :deep(.el-pagination) { justify-content: center; }
}
</style>
