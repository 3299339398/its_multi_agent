import { describe, expect, it } from 'vitest'
import { renderSafeMarkdown } from './markdown'

describe('renderSafeMarkdown', () => {
  it('preserves safe markdown formatting', () => {
    expect(renderSafeMarkdown('**知识库**')).toContain('<strong>知识库</strong>')
  })

  it('removes executable HTML', () => {
    const rendered = renderSafeMarkdown('<img src=x onerror="alert(1)"><script>alert(1)</script>')

    expect(rendered).not.toContain('onerror')
    expect(rendered).not.toContain('<script')
  })

  it('removes unsafe link protocols', () => {
    const rendered = renderSafeMarkdown('[危险链接](javascript:alert(1))')

    expect(rendered).not.toContain('javascript:')
  })
})
