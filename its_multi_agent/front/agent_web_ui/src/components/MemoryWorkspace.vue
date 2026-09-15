<template>
  <section class="memory-workspace">
    <header class="memory-header">
      <div>
        <h2>长期记忆</h2>
        <p>查看和管理系统为当前用户保存的长期信息。</p>
      </div>
      <button class="refresh-button" :disabled="loading" @click="loadMemories">刷新</button>
    </header>

    <div v-if="loading" class="memory-state">正在加载长期记忆...</div>
    <div v-else-if="errorMessage" class="memory-state error">{{ errorMessage }}</div>
    <div v-else-if="memories.length === 0" class="memory-state">
      当前还没有长期记忆。完成几轮对话后，系统会自动提取稳定的用户信息。
    </div>
    <div v-else class="memory-list">
      <article v-for="memory in memories" :key="memory.id" class="memory-item">
        <div class="memory-item-main">
          <div class="memory-item-meta">
            <span class="memory-type">{{ memory.memory_type || 'fact' }}</span>
            <span>重要性 {{ formatImportance(memory.importance) }}</span>
          </div>
          <p>{{ memory.content }}</p>
          <small>来源会话：{{ memory.source_session_id || '未知' }} · {{ formatDate(memory.created_at) }}</small>
        </div>
        <button class="delete-button" :disabled="deletingId === memory.id" @click="deleteMemory(memory)">
          {{ deletingId === memory.id ? '删除中' : '删除' }}
        </button>
      </article>
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { authFetch, readJsonResponse } from '../api/auth'

const props = defineProps({ workspaceId: { type: String, default: 'default' } })
const memories = ref([])
const loading = ref(false)
const deletingId = ref(null)
const errorMessage = ref('')

const loadMemories = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await authFetch(`/api/memories?workspace_id=${encodeURIComponent(props.workspaceId)}`)
    if (!response.ok) throw new Error(`加载失败（${response.status}）`)
    const data = await readJsonResponse(response)
    memories.value = data.memories || []
  } catch (error) {
    errorMessage.value = error.message || '长期记忆暂时不可用'
  } finally {
    loading.value = false
  }
}

const deleteMemory = async (memory) => {
  if (!window.confirm('确定删除这条长期记忆吗？')) return
  deletingId.value = memory.id
  try {
    const response = await authFetch(
      `/api/memories/${memory.id}?workspace_id=${encodeURIComponent(props.workspaceId)}`,
      { method: 'DELETE' },
    )
    if (!response.ok) throw new Error(`删除失败（${response.status}）`)
    const data = await readJsonResponse(response)
    if (!data.success) throw new Error('记忆不存在或服务暂时不可用')
    memories.value = memories.value.filter((item) => item.id !== memory.id)
  } catch (error) {
    errorMessage.value = error.message || '删除失败'
  } finally {
    deletingId.value = null
  }
}

const formatImportance = (value) => `${Math.round(Number(value || 0) * 100)}%`
const formatDate = (value) => value ? new Date(Number(value) * 1000).toLocaleString() : '未知时间'

onMounted(loadMemories)
watch(() => props.workspaceId, loadMemories)
</script>

<style scoped>
.memory-workspace { display: flex; flex: 1; min-height: 0; flex-direction: column; padding: 48px clamp(28px, 8vw, 120px) 32px; color: var(--tech-text-main); background: #fff; }
.memory-header { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 22px; }
.memory-header h2 { margin: 0 0 6px; font-size: 22px; font-weight: 650; }
.memory-header p { margin: 0; color: var(--tech-text-muted); }
.refresh-button, .delete-button { border: 1px solid var(--tech-border); border-radius: 4px; background: #fff; color: var(--tech-primary); cursor: pointer; padding: 8px 12px; }
.refresh-button:disabled, .delete-button:disabled { cursor: wait; opacity: .55; }
.memory-state { padding: 64px 20px; border: 1px dashed var(--tech-border); border-radius: 6px; color: var(--tech-text-muted); text-align: center; }
.memory-state.error { border-color: #e4a6a1; color: #b42318; }
.memory-list { overflow-y: auto; }
.memory-item { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding: 16px; margin-bottom: 12px; border: 1px solid var(--tech-border); border-radius: 6px; background: #f8fafb; }
.memory-item-main { min-width: 0; }
.memory-item-meta { display: flex; gap: 12px; color: var(--tech-text-muted); font-size: .85rem; }
.memory-type { color: var(--tech-primary); }
.memory-item p { margin: 10px 0; line-height: 1.6; word-break: break-word; }
.memory-item small { color: var(--tech-text-muted); }
.delete-button { flex: 0 0 auto; color: #b42318; border-color: #e7bbb7; }
@media (max-width: 760px) { .memory-workspace { padding: 20px; } .memory-header { align-items: flex-start; flex-direction: column; } .memory-item { flex-direction: column; } .delete-button { align-self: flex-end; } }
</style>
