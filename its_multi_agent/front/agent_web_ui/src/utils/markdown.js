import DOMPurify from 'dompurify'
import { marked } from 'marked'

marked.setOptions({
  breaks: true,
  gfm: true
})

export const renderSafeMarkdown = text => {
  if (!text) return ''
  try {
    return DOMPurify.sanitize(marked.parse(text))
  } catch {
    return DOMPurify.sanitize(String(text))
  }
}
