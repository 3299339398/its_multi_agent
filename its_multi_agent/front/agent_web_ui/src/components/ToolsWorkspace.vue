<template>
  <section class="tools-workspace" aria-label="工具管理">
    <div class="tools-page-header">
      <div>
        <span class="page-eyebrow">知行插件</span>
        <h2>为你的任务选择工具</h2>
        <p>从查找资料到生成网页，让助手拥有完成任务所需的能力。</p>
      </div>
      <button class="secondary-button" type="button" @click="$emit('back')"><ArrowLeft :size="16" />返回对话</button>
    </div>

    <div class="workspace-summary">
      <span><FolderKanban :size="16" />{{ workspaceName || '当前工作区' }}</span>
      <span class="enabled-count">已启用 {{ enabledIds.length }} 个工具插件</span>
    </div>
    <p v-if="busy" class="page-notice" role="status">任务正在执行，完成后可调整工具选择。</p>
    <p v-if="error" class="page-error" role="alert">{{ error }}</p>

    <div class="tools-toolbar">
      <div class="filter-tabs" aria-label="插件筛选">
        <button type="button" :class="{ active: filter === 'all' }" :aria-pressed="filter === 'all'" @click="filter = 'all'">全部工具</button>
        <button type="button" :class="{ active: filter === 'enabled' }" :aria-pressed="filter === 'enabled'" @click="filter = 'enabled'">已启用</button>
      </div>
      <label class="plugin-search"><Search :size="17" /><input v-model="query" type="search" aria-label="搜索工具" placeholder="搜索工具或用途" /></label>
      <button class="refresh-button" type="button" :disabled="loading || busy" aria-label="刷新工具列表" @click="$emit('refresh')"><RefreshCw :size="17" :class="{ spinning: loading }" /></button>
    </div>

    <p v-if="loading" class="empty-state" role="status">正在加载工具...</p>
    <div v-else-if="visiblePlugins.length" class="plugin-grid">
      <article v-for="plugin in visiblePlugins" :key="plugin.id" class="plugin-card" :class="{ enabled: enabledIds.includes(plugin.id), restricted: !allowedIds.includes(plugin.id) }">
        <div class="card-top">
          <span class="plugin-icon" :class="plugin.id"><component :is="pluginIcon(plugin.id)" :size="24" aria-hidden="true" /></span>
          <span class="status-badge" :class="{ on: enabledIds.includes(plugin.id) }">{{ statusLabel(plugin) }}</span>
        </div>
        <h3>{{ plugin.name }}</h3>
        <p class="plugin-description">{{ describe(plugin) }}</p>
        <div class="example-task">{{ examples[plugin.id] || '为助手提供更多任务处理能力' }}</div>
        <details class="plugin-details">
          <summary>查看能力 <ChevronDown :size="14" /></summary>
          <ul><li v-for="tool in plugin.tools" :key="tool">{{ tool }}</li></ul>
        </details>
        <div class="card-footer">
          <small v-if="!allowedIds.includes(plugin.id)">当前工作区未开放</small>
          <small v-else-if="plugin.requires_confirmation"><ShieldCheck :size="14" />{{ confirmedIds.includes(plugin.id) ? '已确认授权' : '启用时需确认' }}</small>
          <small v-else>可随时启用</small>
          <button type="button" class="enable-button" :class="{ enabled: enabledIds.includes(plugin.id) }" :disabled="busy || !allowedIds.includes(plugin.id)" :aria-label="`${enabledIds.includes(plugin.id) ? '停用' : '启用'}${plugin.name}`" :aria-pressed="enabledIds.includes(plugin.id)" @click="$emit('toggle', plugin)">
            <Check v-if="enabledIds.includes(plugin.id)" :size="14" />{{ enabledIds.includes(plugin.id) ? '已启用' : '启用' }}
          </button>
        </div>
      </article>
    </div>
    <div v-else class="empty-state">{{ query ? '没有找到匹配的工具，试试其他关键词。' : filter === 'enabled' ? '尚未启用工具，请在全部工具中选择。' : '暂时没有可用工具，请刷新列表。' }}</div>
    <p class="page-footnote">选择即时生效，用于此工作区接下来发送的任务。切换工作区后需重新选择并确认授权。</p>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ArrowLeft, BookOpen, Check, ChevronDown, Code2, FileText, FolderKanban, MapPin, RefreshCw, Search, ShieldCheck, Wrench } from '@lucide/vue'

const props = defineProps({
  plugins: { type: Array, default: () => [] },
  enabledIds: { type: Array, default: () => [] },
  confirmedIds: { type: Array, default: () => [] },
  allowedIds: { type: Array, default: () => [] },
  workspaceName: { type: String, default: '' },
  busy: Boolean,
  loading: Boolean,
  error: { type: String, default: '' },
  describe: { type: Function, default: plugin => plugin.description || '' },
})
defineEmits(['toggle', 'back', 'refresh'])
const query = ref('')
const filter = ref('all')
const examples = {
  knowledge: '例如：查找产品参数，并给出资料来源。',
  search: '例如：查询最新资讯，比较公开资料。',
  map: '例如：查找附近服务站，规划出行路线。',
  files: '例如：制作 SVG 动画网页，生成可下载的 HTML。',
  coding: '例如：定位代码问题，修改文件并运行预设检查。',
}
const pluginIcon = id => ({ knowledge: BookOpen, search: Search, map: MapPin, files: FileText, coding: Code2 })[id] || Wrench
const statusLabel = plugin => !props.allowedIds.includes(plugin.id) ? '未开放' : props.enabledIds.includes(plugin.id) ? '已启用' : '未启用'
const visiblePlugins = computed(() => {
  const term = query.value.trim().toLowerCase()
  return props.plugins.filter(plugin =>
    (filter.value !== 'enabled' || props.enabledIds.includes(plugin.id)) &&
    (!term || `${plugin.name} ${props.describe(plugin)} ${examples[plugin.id] || ''} ${(plugin.tools || []).join(' ')}`.toLowerCase().includes(term)),
  )
})
</script>

<style scoped>
.tools-workspace { flex: 1; min-height: 0; overflow-y: auto; padding: 40px max(24px, calc((100% - 1080px) / 2)); color: var(--ui-ink, #17212b); background: #fff; }
.tools-page-header { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 26px; }
.page-eyebrow { color: #147565; font-size: 12px; font-weight: 600; }
h2 { margin: 8px 0 10px; font-size: 28px; font-weight: 650; letter-spacing: -.6px; }
.tools-page-header p { margin: 0; color: #687380; font-size: 14px; line-height: 1.6; }
button { cursor: pointer; font: inherit; }
button:disabled { cursor: not-allowed; opacity: .5; }
.secondary-button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; flex-shrink: 0; padding: 9px 13px; border: 1px solid #dde2e7; border-radius: 8px; background: #fff; font-size: 13px; color: #48565f; }
.workspace-summary { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; padding: 14px 16px; margin-bottom: 26px; border: 1px solid #e6ece9; border-radius: 10px; background: #f7faf9; font-size: 13px; }
.workspace-summary > span { display: flex; align-items: center; gap: 8px; }
.enabled-count { color: #147565; }
.tools-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 22px; }
.filter-tabs { display: flex; gap: 5px; margin-right: auto; }
.filter-tabs button { white-space: nowrap; padding: 8px 12px; border: 0; border-radius: 7px; background: transparent; color: #687380; font-size: 13px; }
.filter-tabs button.active { color: #147565; background: #e6f2ef; font-weight: 600; }
.plugin-search { display: flex; align-items: center; gap: 8px; padding: 8px 11px; border: 1px solid #dde2e7; border-radius: 8px; color: #687380; }
.plugin-search input { width: 175px; min-width: 0; border: 0; background: transparent; font-size: 13px; color: inherit; }
.refresh-button { display: grid; place-items: center; width: 35px; height: 35px; border: 1px solid #dde2e7; border-radius: 8px; background: #fff; color: #687380; }
.plugin-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 18px; }
.plugin-card { display: flex; flex-direction: column; min-width: 0; padding: 22px; border: 1px solid #e0e5e8; border-radius: 12px; background: #fff; }
.plugin-card.enabled { border-color: #bfd9d0; }
.plugin-card.restricted { background: #fafbfc; }
.card-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
.plugin-icon { display: grid; place-items: center; width: 48px; height: 48px; border-radius: 12px; color: #147565; background: #eaf4f0; }
.plugin-icon.search { color: #435fbd; background: #edf2ff; }
.plugin-icon.files { color: #9d6e2f; background: #fff4df; }
.plugin-icon.coding { color: #7755a9; background: #f3edfc; }
.status-badge { border-radius: 20px; padding: 4px 8px; background: #f1f3f5; color: #7a8590; font-size: 11px; }
.status-badge.on { color: #147565; background: #e6f2ef; }
h3 { margin: 0 0 9px; font-size: 17px; }
.plugin-description { margin: 0; color: #687380; font-size: 13px; line-height: 1.7; }
.example-task { margin: 15px 0; color: #78858b; font-size: 12px; line-height: 1.7; }
.plugin-details { margin-bottom: 18px; color: #687380; font-size: 12px; }
.plugin-details summary { display: flex; align-items: center; gap: 5px; cursor: pointer; width: fit-content; }
.plugin-details ul { padding-left: 16px; overflow-wrap: anywhere; line-height: 1.8; }
.card-footer { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: auto; padding-top: 16px; border-top: 1px solid #edf0f2; }
.card-footer small { display: flex; align-items: center; gap: 4px; color: #7a8590; font-size: 11px; }
.enable-button { display: flex; align-items: center; gap: 5px; padding: 7px 14px; border: 1px solid #147565; border-radius: 7px; background: #147565; color: #fff; font-size: 12px; }
.enable-button.enabled { background: #fff; color: #147565; border-color: #bfd9d0; }
.enable-button.enabled:hover:not(:disabled) { background: #e6f2ef; }
.page-footnote { color: #8a959e; font-size: 12px; line-height: 1.8; margin-top: 26px; }
.page-notice { color: #9d6e2f; font-size: 13px; }
.page-error { color: #b34640; font-size: 13px; }
.empty-state { padding: 70px 15px; text-align: center; color: #7a8590; font-size: 14px; }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 760px) { .tools-workspace { padding: 24px 16px; } h2 { font-size: 23px; } .tools-page-header { align-items: flex-start; flex-direction: column; } .tools-toolbar { flex-wrap: wrap; } .filter-tabs { width: 100%; } .plugin-search { flex: 1; } .plugin-search input { width: 100%; } .plugin-grid { grid-template-columns: 1fr; } }
</style>
