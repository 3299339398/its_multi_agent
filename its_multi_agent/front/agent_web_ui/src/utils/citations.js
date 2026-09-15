import DOMPurify from 'dompurify'
import { Marked } from 'marked'
import { renderSafeMarkdown } from './markdown'

export const safeSourceUrl = value => {
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : ''
  } catch { return '' }
}

export const normalizeSources = value => {
  if (!Array.isArray(value)) return []
  const seen = new Set()
  return value.filter(source => {
    if (!source || typeof source.source_id !== 'string' || !/^[A-Za-z0-9_:-]{1,128}$/.test(source.source_id)
      || typeof source.excerpt !== 'string' || !source.excerpt.trim() || seen.has(source.source_id)) return false
    seen.add(source.source_id)
    return true
  }).slice(0, 8).map(source => ({
    source_id: source.source_id,
    source_name: String(source.source_name || source.title || '未命名资料').slice(0, 300),
    origin: ['knowledge', 'attachment', 'web'].includes(source.origin) ? source.origin : 'knowledge',
    excerpt: source.excerpt.slice(0, 6000),
    excerpt_truncated: Boolean(source.excerpt_truncated) || source.excerpt.length > 6000,
    page: typeof source.page === 'number' || typeof source.page === 'string' ? String(source.page).slice(0, 80) : '',
    sheet: String(source.sheet || '').slice(0, 120),
    version: String(source.version || '').slice(0, 120),
    url: safeSourceUrl(source.url),
  }))
}

export const renderCitedMarkdown = (text, sources) => {
  const known = new Map(normalizeSources(sources).map((source, index) => [source.source_id, index + 1]))
  if (!known.size) return renderSafeMarkdown(text)
  const markdown = new Marked({ breaks: true, gfm: true })
  markdown.use({ extensions: [{
    name: 'sourceCitation', level: 'inline',
    start: value => value.indexOf('['),
    tokenizer(value) {
      const match = /^\[([A-Za-z0-9_:-]{1,128})\](?!\()/.exec(value)
      if (match && known.has(match[1])) return { type: 'sourceCitation', raw: match[0], id: match[1] }
    },
    renderer(token) {
      const index = known.get(token.id)
      return `<button type="button" class="source-citation" data-source-id="${token.id}" aria-label="查看来源 ${index}" title="查看来源 ${index}">[${index}]</button>`
    },
  }] })
  try {
    return DOMPurify.sanitize(markdown.parse(text || ''), { ADD_ATTR: ['data-source-id'] })
  } catch { return renderSafeMarkdown(text) }
}
