<template>
  <section class="knowledge-workspace">
    <header class="workspace-header">
      <div>
        <h2>知识库</h2>
        <p>检索已入库的私域文档，或将多领域资料添加到指定知识空间。</p>
      </div>
      <div class="workspace-tabs" role="tablist" aria-label="知识库工作区">
        <button :class="{ active: activeTab === 'query' }" @click="activeTab = 'query'">智能问答</button>
        <button v-if="isAdmin" :class="{ active: activeTab === 'upload' }" @click="activeTab = 'upload'">文档入库</button>
      </div>
    </header>

    <div v-if="activeTab === 'query'" class="knowledge-chat">
      <div class="scope-controls">
        <label>
          <span>知识空间</span>
          <input v-model.trim="knowledgeSpace" :disabled="loading" maxlength="64" placeholder="default" />
        </label>
        <label>
          <span>知识领域</span>
          <select v-model="domain" :disabled="loading">
            <option v-for="item in domainOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
      </div>
      <div ref="messageList" class="knowledge-messages">
        <p v-if="messages.length === 0" class="empty-state">输入问题，系统将基于当前知识库作答。</p>
        <article v-for="(message, index) in messages" :key="index" :class="['knowledge-message', message.role]">
          <div v-if="message.loading" class="loading-text">正在检索知识库...</div>
          <template v-else>
            <div v-html="renderMarkdown(message.content)"></div>
            <details v-if="message.sources?.length" class="answer-evidence">
              <summary>参考来源（{{ message.sources.length }}）</summary>
              <ul>
                <li v-for="(source, sourceIndex) in message.sources" :key="`${sourceIndex}-${source.title}`">
                  <strong>{{ source.source_name || source.title }}</strong>
                  <span v-if="source.page != null">第 {{ source.page }} 页</span>
                  <span v-if="source.sheet">工作表 {{ source.sheet }}</span>
                  <span v-if="source.score != null">相关度 {{ formatScore(source.score) }}</span>
                </li>
              </ul>
            </details>
            <details v-if="message.searchQueries?.length > 1" class="answer-evidence">
              <summary>检索表达（{{ message.searchQueries.length }}）</summary>
              <ol><li v-for="query in message.searchQueries" :key="query">{{ query }}</li></ol>
            </details>
          </template>
        </article>
      </div>
      <form class="knowledge-input" @submit.prevent="sendQuestion">
        <textarea v-model="question" :disabled="loading" placeholder="请输入知识库问题" rows="3"></textarea>
        <button type="submit" :disabled="loading || !question.trim()">{{ loading ? '检索中' : '发送' }}</button>
      </form>
    </div>

    <div v-else-if="isAdmin" class="knowledge-upload">
      <div class="scope-controls upload-scope">
        <label>
          <span>知识空间</span>
          <input v-model.trim="knowledgeSpace" :disabled="uploading" maxlength="64" placeholder="default" />
        </label>
        <label>
          <span>知识领域</span>
          <select v-model="domain" :disabled="uploading">
            <option v-for="item in domainOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
      </div>
      <label class="upload-dropzone" :class="{ disabled: uploading }">
        <input type="file" accept=".md,.txt,.pdf,.docx,.xlsx,text/markdown,text/plain,application/pdf" :disabled="uploading" @change="uploadFile" />
        <strong>{{ uploading ? '文档处理中...' : '选择知识库文档' }}</strong>
        <span>支持 .md、.txt、.pdf、.docx、.xlsx，上传后将被提取并写入知识库。</span>
      </label>
      <p v-if="uploadMessage" :class="['upload-result', uploadFailed ? 'error' : 'success']">{{ uploadMessage }}</p>
      <div v-if="uploadHistory.length" class="upload-history">
        <h3>本次记录</h3>
        <div v-for="item in uploadHistory" :key="item.id" class="upload-history-item">
          <span>{{ item.name }}</span>
          <span :class="item.failed ? 'error' : 'success'">{{ item.message }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { nextTick, onUnmounted, ref } from 'vue'
import { authFetch, getAuthUser } from '../api/auth'
import { renderSafeMarkdown as renderMarkdown } from '../utils/markdown'

const activeTab = ref('query')
const isAdmin = getAuthUser()?.role === 'admin'
const question = ref('')
const loading = ref(false)
const messages = ref([])
const messageList = ref(null)
const uploading = ref(false)
const uploadMessage = ref('')
const uploadFailed = ref(false)
const uploadHistory = ref([])
const knowledgeSpace = ref('default')
const domain = ref('general')
const domainOptions = [
  { value: 'general', label: '通用' },
  { value: 'policy', label: '制度政策' },
  { value: 'technical', label: '技术资料' },
  { value: 'product', label: '产品资料' },
  { value: 'project', label: '项目资料' },
  { value: 'service', label: '服务资料' },
]
let uploadTimer
let uploadPollAttempts = 0
const MAX_UPLOAD_POLL_ATTEMPTS = 120

const normalizedScope = () => ({
  knowledge_space: knowledgeSpace.value || 'default',
  domain: domain.value || 'general',
})
const formatScore = (score) => Number(score).toFixed(3)

const scrollToBottom = async () => {
  await nextTick()
  if (messageList.value) {
    messageList.value.scrollTop = messageList.value.scrollHeight
  }
}

const sendQuestion = async () => {
  const text = question.value.trim()
  if (!text || loading.value) return

  question.value = ''
  messages.value.push({ role: 'user', content: text })
  messages.value.push({ role: 'assistant', content: '', loading: true })
  loading.value = true
  await scrollToBottom()

  try {
    const response = await authFetch('/api/knowledge/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: text, ...normalizedScope() }),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '知识库服务暂时不可用')
    messages.value[messages.value.length - 1] = {
      role: 'assistant',
      content: data.answer || '未获得有效回答。',
      sources: data.sources || [],
      searchQueries: data.search_queries || [],
    }
  } catch (error) {
    messages.value[messages.value.length - 1] = { role: 'assistant', content: `查询失败：${error.message}` }
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

const uploadFile = async (event) => {
  const [file] = event.target.files
  event.target.value = ''
  if (!file || uploading.value) return

  const formData = new FormData()
  formData.append('file', file)
  const scope = normalizedScope()
  formData.append('knowledge_space', scope.knowledge_space)
  formData.append('domain', scope.domain)
  uploading.value = true
  uploadMessage.value = ''

  try {
    const response = await authFetch('/api/knowledge/upload', { method: 'POST', body: formData })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '文档上传失败')
    if (data.status === 'queued' && data.task_id) {
      uploadMessage.value = `${data.file_name} 已提交后台任务，正在处理...`
      uploadFailed.value = false
      uploadPollAttempts = 0
      uploadTimer = window.setInterval(async () => {
        uploadPollAttempts += 1
        try {
          const taskResponse = await authFetch(`/api/knowledge/tasks/${encodeURIComponent(data.task_id)}`)
          const task = await taskResponse.json().catch(() => ({}))
          if (task.status === 'success' || task.status === 'failed') {
            window.clearInterval(uploadTimer); uploadTimer = undefined
            uploading.value = false; uploadFailed.value = task.status === 'failed'
            uploadMessage.value = task.status === 'success'
              ? `${data.file_name} 入库完成，新增 ${task.chunks_added} 个切片。`
              : (task.error_message || '文档入库失败，可在管理后台重试。')
          }
        } catch { /* retry on next tick */ }
        if (uploadPollAttempts >= MAX_UPLOAD_POLL_ATTEMPTS && uploadTimer) {
          window.clearInterval(uploadTimer); uploadTimer = undefined
          uploading.value = false; uploadFailed.value = true
          uploadMessage.value = '任务状态长时间未返回，请刷新页面后重试。'
        }
      }, 1500)
      return
    }
    const message = data.status === 'duplicate'
      ? `${data.file_name} 在 ${data.knowledge_space}/${data.domain} 中已存在，已跳过重复入库。`
      : `${data.file_name} 已入库至 ${data.knowledge_space}/${data.domain}，新增 ${data.chunks_added} 个切片。`
    uploadMessage.value = message
    uploadFailed.value = false
    uploadHistory.value.unshift({ id: `${Date.now()}-${file.name}`, name: file.name, message, failed: false })
  } catch (error) {
    const message = error.message || '文档上传失败'
    uploadMessage.value = message
    uploadFailed.value = true
    uploadHistory.value.unshift({ id: `${Date.now()}-${file.name}`, name: file.name, message, failed: true })
  } finally {
    if (!uploadTimer) uploading.value = false
  }
}

onUnmounted(() => { if (uploadTimer) window.clearInterval(uploadTimer) })
</script>

<style scoped>
.knowledge-workspace { display: flex; flex: 1; min-height: 0; flex-direction: column; padding: 48px clamp(28px, 8vw, 120px) 32px; color: var(--tech-text-main); background: #fff; }
.workspace-header { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 22px; }
.workspace-header h2 { margin: 0 0 6px; font-size: 22px; font-weight: 650; }
.workspace-header p { margin: 0; color: var(--tech-text-muted); }
.workspace-tabs { display: flex; border: 1px solid var(--tech-border); border-radius: 6px; overflow: hidden; }
.workspace-tabs button { border: 0; border-right: 1px solid var(--tech-border); background: transparent; color: var(--tech-text-muted); cursor: pointer; padding: 8px 12px; }
.workspace-tabs button:last-child { border-right: 0; }
.workspace-tabs button { background: #fff; }
.workspace-tabs button.active { background: var(--tech-primary-soft); color: var(--tech-primary); }
.knowledge-chat { display: flex; flex: 1; min-height: 0; flex-direction: column; border: 1px solid var(--tech-border); border-radius: 6px; background: #fff; overflow: hidden; }
.scope-controls { display: grid; grid-template-columns: repeat(2, minmax(0, 220px)); gap: 12px; padding: 14px; border-bottom: 1px solid var(--tech-border); }
.scope-controls label { display: grid; gap: 5px; color: var(--tech-text-muted); font-size: 12px; }
.scope-controls input, .scope-controls select { min-width: 0; padding: 8px 10px; border: 1px solid var(--tech-border); border-radius: 4px; background: #fff; color: var(--tech-text-main); }
.scope-controls input:focus, .scope-controls select:focus { outline: none; border-color: #7da99f; box-shadow: 0 0 0 3px rgba(23, 107, 91, .08); }
.upload-scope { padding: 0 0 14px; border-bottom: 0; }
.knowledge-messages { flex: 1; overflow-y: auto; padding: 20px; }
.empty-state { margin: 0; color: var(--tech-text-muted); text-align: center; padding: 72px 0; }
.knowledge-message { max-width: 82%; padding: 12px 14px; margin-bottom: 14px; border-radius: 6px; line-height: 1.6; }
.knowledge-message.user { margin-left: auto; background: #edf5f2; border: 1px solid #c8ddd7; }
.knowledge-message.assistant { border: 1px solid var(--tech-border); background: #f8fafb; }
.answer-evidence { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--tech-border); color: var(--tech-text-muted); font-size: 12px; }
.answer-evidence summary { cursor: pointer; color: var(--tech-primary); }
.answer-evidence ul, .answer-evidence ol { margin: 8px 0 0; padding-left: 20px; }
.answer-evidence li { margin: 5px 0; }
.answer-evidence li span { margin-left: 10px; }
.knowledge-message :deep(p:first-child) { margin-top: 0; }
.knowledge-message :deep(p:last-child) { margin-bottom: 0; }
.knowledge-input { display: flex; gap: 12px; padding: 14px; border-top: 1px solid var(--tech-border); }
.knowledge-input textarea { flex: 1; min-height: 52px; padding: 10px; background: #fff !important; border: 1px solid var(--tech-border) !important; border-radius: 5px; color: var(--tech-text-main); }
.knowledge-input textarea:focus { border-color: #7da99f !important; box-shadow: 0 0 0 3px rgba(23, 107, 91, .08) !important; }
.knowledge-input button { align-self: flex-end; padding: 10px 16px; border: 1px solid var(--tech-primary); border-radius: 4px; background: var(--tech-primary); color: #fff; cursor: pointer; }
.knowledge-input button:disabled { cursor: not-allowed; opacity: .55; }
.knowledge-upload { max-width: 760px; }
.upload-dropzone { min-height: 180px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; border: 1px dashed #9ebfb7; border-radius: 6px; cursor: pointer; background: #f8fbfa; text-align: center; }
.upload-dropzone input { display: none; }
.upload-dropzone span { color: var(--tech-text-muted); }
.upload-dropzone.disabled { cursor: wait; opacity: .7; }
.upload-result { padding: 10px 12px; border-radius: 4px; }
.upload-history { margin-top: 28px; }
.upload-history h3 { font-size: 15px; }
.upload-history-item { display: flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--tech-border); }
.success { color: #176b5b; }
.error { color: #b42318; }
@media (max-width: 760px) { .knowledge-workspace { padding: 20px; } .workspace-header { align-items: flex-start; flex-direction: column; } .scope-controls { grid-template-columns: 1fr; } .knowledge-message { max-width: 100%; } .knowledge-input { flex-direction: column; } .knowledge-input button { align-self: stretch; } .upload-history-item { align-items: flex-start; flex-direction: column; } }
</style>
