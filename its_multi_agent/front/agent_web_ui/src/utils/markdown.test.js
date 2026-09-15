import { describe, expect, it } from 'vitest'
import { renderSafeMarkdown } from './markdown'

describe('renderSafeMarkdown', () => {
  it('renders GitHub-flavored line breaks', () => {
    expect(renderSafeMarkdown('第一行\n第二行')).toContain('<br>')
  })

  it('removes executable HTML and unsafe links', () => {
    const rendered = renderSafeMarkdown('<img src=x onerror="alert(1)">[链接](javascript:alert(1))')

    expect(rendered).not.toContain('onerror')
    expect(rendered).not.toContain('javascript:')
  })
})
