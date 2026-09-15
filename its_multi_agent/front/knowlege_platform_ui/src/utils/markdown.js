import DOMPurify from 'dompurify'
import { marked } from 'marked'

export const renderSafeMarkdown = text => {
  return DOMPurify.sanitize(marked.parse(text || ''))
}
