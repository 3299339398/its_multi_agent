<template>
  <section class="preview-workspace" aria-label="网页预览">
    <header class="preview-header">
      <div class="preview-heading"><span>网页预览</span><h2>{{ file?.filename || '正在打开网页' }}</h2></div>
      <div class="preview-actions">
        <button type="button" @click="$emit('back')"><ArrowLeft :size="16" />返回</button>
        <button type="button" :disabled="!documentSource" @click="frameVersion++"><RotateCcw :size="16" />重新播放</button>
        <button type="button" :disabled="!file || downloading" @click="download"><Download :size="16" />{{ downloading ? '下载中' : '下载 HTML' }}</button>
      </div>
    </header>
    <div v-if="loading" class="preview-status" role="status">正在加载网页...</div>
    <div v-else-if="error" class="preview-status error" role="alert"><p>{{ error }}</p><button type="button" @click="loadFile">重新加载</button></div>
    <iframe v-else-if="documentSource" :key="frameVersion" class="preview-frame" :title="`${file.filename} 网页预览`" :src="documentSource" sandbox="allow-scripts" referrerpolicy="no-referrer" allow="camera 'none'; microphone 'none'; geolocation 'none'; clipboard-read 'none'; clipboard-write 'none'" />
    <p v-if="downloadError" class="download-error" role="alert">{{ downloadError }}</p>
    <footer>支持自包含 HTML、SVG、CSS 和 JavaScript 动画。需要外部资源的页面可下载后在本地打开。</footer>
  </section>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { ArrowLeft, Download, RotateCcw } from '@lucide/vue'
import { authFetch, readErrorMessage, readJsonResponse } from '../api/auth'
import { downloadArtifact, isHtmlArtifact } from '../utils/fileArtifacts'

const props = defineProps({ artifactId: { type: String, required: true } })
defineEmits(['back'])
const file = ref(null)
const documentSource = ref('')
const loading = ref(false)
const error = ref('')
const downloadError = ref('')
const downloading = ref(false)
const frameVersion = ref(0)
let controller

const loadFile = async () => {
  controller?.abort()
  const request = new AbortController()
  controller = request
  file.value = null
  documentSource.value = ''
  error.value = ''
  downloadError.value = ''
  loading.value = true
  try {
    if (!/^[0-9a-f]{32}$/.test(props.artifactId)) throw new Error('文件标识无效')
    const url = `/api/files/${encodeURIComponent(props.artifactId)}`
    const metadata = await authFetch(url, { signal: request.signal })
    if (!metadata.ok) throw new Error(await readErrorMessage(metadata, '读取文件失败'))
    const item = await readJsonResponse(metadata)
    if (!isHtmlArtifact(item)) throw new Error('此文件不是可预览的 HTML 网页，请使用下载功能。')
    const preview = await authFetch(`${url}/preview-ticket`, { method: 'POST', signal: request.signal })
    if (!preview.ok) throw new Error(await readErrorMessage(preview, '读取网页失败'))
    const ticket = await readJsonResponse(preview)
    if (request.signal.aborted) return
    if (!/^\/api\/file-previews\/[A-Za-z0-9_.-]+$/.test(ticket.preview_url || '')) throw new Error('预览地址无效')
    documentSource.value = ticket.preview_url
    file.value = item
    frameVersion.value++
  } catch (failure) {
    if (!request.signal.aborted) error.value = failure.message || '网页加载失败'
  } finally {
    if (!request.signal.aborted) loading.value = false
  }
}
const download = async () => {
  downloading.value = true
  downloadError.value = ''
  try { await downloadArtifact(file.value) }
  catch (failure) { downloadError.value = failure.message || '下载失败' }
  finally { downloading.value = false }
}
watch(() => props.artifactId, loadFile, { immediate: true })
onBeforeUnmount(() => controller?.abort())
</script>

<style scoped>
.preview-workspace { display: flex; flex: 1; flex-direction: column; min-height: 0; background: #f5f7f8; }
.preview-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; padding: 18px 24px; background: #fff; border-bottom: 1px solid #dde2e7; }
.preview-heading { min-width: 0; }
.preview-heading span { color: #147565; font-size: 12px; }
.preview-heading h2 { margin: 5px 0 0; font-size: 17px; color: #26323b; overflow-wrap: anywhere; }
.preview-actions { display: flex; flex-wrap: wrap; gap: 8px; }
button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 11px; border: 1px solid #d5dfdb; border-radius: 7px; background: #fff; color: #35665b; font-size: 12px; cursor: pointer; }
button:disabled { opacity: .5; cursor: not-allowed; }
.preview-frame { flex: 1; min-height: 300px; width: 100%; border: 0; background: #fff; }
.preview-status { display: grid; flex: 1; align-content: center; justify-items: center; padding: 30px; color: #687780; }
.error, .download-error { color: #a33d37; }
.download-error { padding: 0 20px; font-size: 13px; }
footer { padding: 12px 24px; border-top: 1px solid #dde2e7; color: #78858b; font-size: 12px; line-height: 1.6; }
@media (max-width: 760px) { .preview-header { padding: 16px; } footer { padding: 10px 16px; } }
</style>
