<template>
  <section class="files-workspace">
    <header class="files-header">
      <div>
        <h2>生成文件</h2>
        <p>支持 TXT、Markdown、JSON、CSV 和 HTML；点击预览即可观看网页与 SVG 动画。</p>
      </div>
      <button class="icon-action" type="button" title="刷新文件列表" aria-label="刷新文件列表" :disabled="loading" @click="loadFiles">
        <RefreshCw :size="17" :class="{ spinning: loading }" aria-hidden="true" />
      </button>
    </header>

    <p v-if="errorMessage" class="files-error" role="alert">{{ errorMessage }}</p>
    <div v-if="loading && files.length === 0" class="files-empty" role="status">正在加载文件...</div>
    <div v-else-if="files.length === 0" class="files-empty">暂无生成文件</div>
    <ul v-else class="files-list">
      <li v-for="file in files" :key="file.id" class="file-row">
        <FileText :size="18" class="file-icon" aria-hidden="true" />
        <div class="file-details">
          <strong :title="file.filename">{{ file.filename }}</strong>
          <small>{{ formatBytes(file.size) }} · {{ formatDate(file.created_at) }}</small>
          <small v-if="file.session_id">会话 {{ file.session_id }}</small>
        </div>
        <div class="file-actions">
          <button v-if="isHtmlArtifact(file)" class="preview-action" type="button" :aria-label="`预览 ${file.filename}`" @click="$emit('preview', file.id)">
            <Eye :size="16" aria-hidden="true" />预览
          </button>
          <button class="icon-action" type="button" :title="`下载 ${file.filename}`" :aria-label="`下载 ${file.filename}`" :disabled="busyId === file.id" @click="downloadFile(file)">
            <Download :size="16" aria-hidden="true" />
          </button>
          <button class="icon-action danger" type="button" :title="`删除 ${file.filename}`" :aria-label="`删除 ${file.filename}`" :disabled="busyId === file.id" @click="deleteFile(file)">
            <Trash2 :size="16" aria-hidden="true" />
          </button>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Download, Eye, FileText, RefreshCw, Trash2 } from '@lucide/vue'
import { authFetch, readJsonResponse } from '../api/auth'
import { downloadArtifact, isHtmlArtifact } from '../utils/fileArtifacts'

defineEmits(['preview'])

const files = ref([])
const loading = ref(false)
const busyId = ref('')
const errorMessage = ref('')

const loadFiles = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await authFetch('/api/files')
    if (!response.ok) throw new Error(`读取文件失败（HTTP ${response.status}）`)
    const data = await readJsonResponse(response)
    files.value = Array.isArray(data.files) ? data.files : []
  } catch (error) {
    errorMessage.value = error.message || '读取文件失败'
  } finally {
    loading.value = false
  }
}

const downloadFile = async (file) => {
  busyId.value = file.id
  errorMessage.value = ''
  try {
    await downloadArtifact(file)
  } catch (error) {
    errorMessage.value = error.message || '下载失败'
  } finally {
    busyId.value = ''
  }
}

const deleteFile = async (file) => {
  if (!window.confirm(`确定删除“${file.filename}”吗？`)) return
  busyId.value = file.id
  errorMessage.value = ''
  try {
    const response = await authFetch(`/api/files/${encodeURIComponent(file.id)}`, { method: 'DELETE' })
    if (!response.ok) throw new Error(`删除失败（HTTP ${response.status}）`)
    files.value = files.value.filter(item => item.id !== file.id)
  } catch (error) {
    errorMessage.value = error.message || '删除失败'
  } finally {
    busyId.value = ''
  }
}

const formatBytes = (value) => {
  const size = Number(value) || 0
  return size < 1024 ? `${size} B` : `${(size / 1024).toFixed(1)} KB`
}
const formatDate = (value) => value ? new Date(Number(value) * 1000).toLocaleString() : '时间未知'

onMounted(loadFiles)
</script>

<style scoped>
.files-workspace { display: flex; flex: 1; min-height: 0; flex-direction: column; padding: 32px max(24px, calc((100% - 780px) / 2)); color: #26323b; background: #fff; }
.files-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding-bottom: 18px; border-bottom: 1px solid #e1e7e4; }
.files-header h2 { margin: 0 0 5px; font-size: 20px; }
.files-header p { margin: 0; color: #687780; font-size: 13px; }
.icon-action { display: grid; place-items: center; width: 34px; height: 34px; flex: 0 0 34px; border: 1px solid #d5dfdb; border-radius: 5px; background: #fff; color: #35665b; cursor: pointer; }
.icon-action:hover:not(:disabled) { background: #eff6f3; }
.icon-action:disabled { opacity: .5; cursor: wait; }
.icon-action.danger { color: #a33d37; border-color: #e7c7c3; }
.files-list { overflow-y: auto; padding: 0; margin: 0; list-style: none; }
.file-row { display: flex; align-items: center; gap: 14px; padding: 14px 4px; border-bottom: 1px solid #edf0ef; }
.file-icon { flex: 0 0 auto; color: #55796f; }
.file-details { display: grid; min-width: 0; flex: 1; gap: 4px; }
.file-details strong { overflow: hidden; color: #293b36; font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.file-details small { color: #687780; font-size: 12px; overflow-wrap: anywhere; }
.file-actions { display: flex; flex: 0 0 auto; gap: 6px; }
.preview-action { display: inline-flex; align-items: center; justify-content: center; gap: 5px; height: 34px; padding: 0 10px; border: 1px solid #d5dfdb; border-radius: 5px; background: #eff6f3; color: #35665b; font-size: 12px; cursor: pointer; }
.files-empty, .files-error { padding: 56px 16px; color: #687780; text-align: center; }
.files-error { padding: 12px 0; color: #a33d37; text-align: left; }
.spinning { animation: spin .9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 760px) { .files-workspace { padding: 20px 14px; } .file-row { align-items: flex-start; gap: 9px; } }
</style>
