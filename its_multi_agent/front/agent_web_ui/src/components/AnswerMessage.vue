<template>
  <div class="answer-message">
    <div class="markdown-body" v-html="html" @click="openCitation"></div>
    <div v-if="evidence.length" class="answer-sources" aria-label="参考来源">
      <span class="sources-label">来源</span>
      <button v-for="(source, index) in evidence" :key="source.source_id" type="button"
        class="source-reference" :title="`查看来源 ${index + 1}：${source.source_name}`"
        @click="openSource(source.source_id)">
        <FileText :size="14" aria-hidden="true" />
        <span class="reference-number">{{ index + 1 }}</span>
        <span class="reference-name">{{ source.source_name }}</span>
      </button>
    </div>
    <dialog ref="dialog" class="source-viewer" aria-label="引用原文" @close="onClose" @click="closeOnBackdrop">
      <template v-if="selected">
        <header class="source-header">
          <div class="source-heading">
            <span class="source-origin">{{ originLabel }} · 回答时的证据</span>
            <h3>{{ selected.source_name }}</h3>
          </div>
          <button type="button" class="source-close" aria-label="关闭来源" title="关闭来源" @click="closeSource">
            <X :size="20" aria-hidden="true" />
          </button>
        </header>
        <div class="source-details">
          <label v-if="evidence.length > 1" class="source-select-label">来源
            <select v-model="selectedId" aria-label="选择来源">
              <option v-for="(source, index) in evidence" :key="source.source_id" :value="source.source_id">
                {{ index + 1 }}. {{ source.source_name }}
              </option>
            </select>
          </label>
          <dl class="source-metadata">
            <template v-if="selected.page !== ''"><dt>页码</dt><dd>{{ selected.page }}</dd></template>
            <template v-if="selected.sheet"><dt>工作表</dt><dd>{{ selected.sheet }}</dd></template>
            <template v-if="selected.version"><dt>版本</dt><dd>{{ selected.version }}</dd></template>
          </dl>
        </div>
        <pre class="source-excerpt">{{ selected.excerpt }}</pre>
        <footer class="source-footer">
          <span v-if="selected.excerpt_truncated" class="source-truncated">原文片段已截断，未包含完整资料。</span>
          <a v-if="selected.url" :href="selected.url" target="_blank" rel="noopener noreferrer" class="source-external">
            <ExternalLink :size="15" aria-hidden="true" />打开原网页
          </a>
        </footer>
      </template>
    </dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ExternalLink, FileText, X } from '@lucide/vue'
import { normalizeSources, renderCitedMarkdown } from '../utils/citations'

const props = defineProps({ text: { type: String, default: '' }, sources: { type: Array, default: () => [] } })
const evidence = computed(() => normalizeSources(props.sources))
const html = computed(() => renderCitedMarkdown(props.text, evidence.value))
const dialog = ref(null)
const selectedId = ref('')
const selected = computed(() => evidence.value.find(source => source.source_id === selectedId.value))
const originLabel = computed(() => ({ knowledge: '知识库', attachment: '附件', web: '网络' })[selected.value?.origin] || '资料')
let trigger = null

const openSource = async id => {
  if (!evidence.value.some(source => source.source_id === id)) return
  trigger = document.activeElement
  selectedId.value = id
  await nextTick()
  if (selected.value && dialog.value && !dialog.value.open) dialog.value.showModal()
}
const openCitation = event => {
  const control = event.target.closest('button[data-source-id]')
  if (control) void openSource(control.dataset.sourceId)
}
const onClose = () => {
  selectedId.value = ''
  if (trigger?.isConnected) trigger.focus()
  trigger = null
}
const closeSource = () => {
  if (dialog.value?.open) dialog.value.close()
  else selectedId.value = ''
}
const closeOnBackdrop = event => {
  if (event.target !== dialog.value) return
  const rect = dialog.value.getBoundingClientRect()
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeSource()
}
watch(() => props.sources, closeSource)
onBeforeUnmount(closeSource)
</script>

<style scoped>
.answer-message { min-width: 0; }
.answer-sources { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; margin-top: 12px; padding-top: 10px; border-top: 1px solid #e4e7eb; }
.sources-label { color: #65717b; font-size: 12px; }
.source-reference { display: inline-flex; align-items: center; gap: 5px; min-width: 0; max-width: 100%; padding: 4px 0; background: transparent; border: 0; color: #17665d; font-size: 12px; cursor: pointer; }
.source-reference svg, .reference-number { flex-shrink: 0; }
.reference-name { min-width: 0; max-width: 230px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:deep(.source-citation) { display: inline; padding: 0 3px; margin: 0; background: transparent; border: 0; border-radius: 2px; color: #17665d; font: inherit; font-weight: 600; cursor: pointer; }
:deep(.source-citation:hover), .source-reference:hover { text-decoration: underline; }
:deep(.source-citation:focus-visible), .source-reference:focus-visible, .source-close:focus-visible { outline: 2px solid #17665d; outline-offset: 3px; }
.source-viewer { width: min(760px, calc(100vw - 32px)); max-width: none; max-height: min(82vh, 800px); margin: auto; padding: 0; border: 1px solid #d4dadf; border-radius: 8px; background: #fff; color: #26323b; box-shadow: 0 16px 56px #0003; }
.source-viewer[open] { display: flex; flex-direction: column; }
.source-viewer::backdrop { background: #17212688; }
.source-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 20px 22px 14px; border-bottom: 1px solid #e4e7eb; }
.source-heading { min-width: 0; }
.source-origin { display: block; color: #65717b; font-size: 12px; line-height: 1.6; }
.source-heading h3 { margin: 4px 0 0; font-size: 18px; line-height: 1.5; overflow-wrap: anywhere; }
.source-close { display: grid; place-items: center; flex: 0 0 32px; width: 32px; height: 32px; padding: 0; border: 0; border-radius: 4px; color: #53616c; background: #f0f3f4; cursor: pointer; }
.source-details { padding: 12px 22px 0; }
.source-select-label { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.source-select-label select { min-width: 0; flex: 1; width: 100%; height: 34px; border: 1px solid #cad2d8; border-radius: 4px; background: white; padding: 0 8px; color: #26323b; }
.source-metadata { display: flex; flex-wrap: wrap; gap: 6px 10px; margin: 6px 0 0; font-size: 12px; line-height: 1.6; }
.source-metadata dt { color: #65717b; }
.source-metadata dd { margin: 0 12px 0 0; overflow-wrap: anywhere; }
.source-excerpt { flex: 1; min-height: 0; margin: 0; padding: 20px 22px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: 14px/1.8 system-ui, sans-serif; background: white; color: #26323b; }
.source-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; padding: 12px 22px; border-top: 1px solid #e4e7eb; font-size: 12px; }
.source-truncated { color: #925510; }
.source-external { display: inline-flex; align-items: center; gap: 6px; color: #17665d; }
@media (max-width: 600px) {
  .source-viewer { max-height: 86dvh; }
  .source-header { padding: 16px; }
  .source-heading h3 { font-size: 16px; }
  .source-details { padding: 10px 16px 0; }
  .source-excerpt { padding: 16px; }
  .source-footer { padding: 12px 16px; }
  .reference-name { max-width: 190px; }
}
</style>
