import { describe, expect, it } from 'vitest'
import { normalizeSources, renderCitedMarkdown, safeSourceUrl } from './citations'

const sources = [{ source_id: 'src_123', source_name: 'Manual', excerpt: 'Original evidence' }]

describe('trusted source citations', () => {
  it('turns known references into controls but leaves unknown IDs untouched', () => {
    const root = document.createElement('div')
    root.innerHTML = renderCitedMarkdown('Answer [src_123] and [invented].', sources)
    expect(root.querySelector('button')?.dataset.sourceId).toBe('src_123')
    expect(root.textContent).toContain('[invented]')
    expect(root.querySelectorAll('button')).toHaveLength(1)
  })

  it('does not interpret citations inside inline code, code blocks or links', () => {
    const root = document.createElement('div')
    root.innerHTML = renderCitedMarkdown('`[src_123]`\n\n```text\n[src_123]\n```\n\n[src_123](https://example.org)', sources)
    expect(root.querySelector('button')).toBeNull()
    expect(root.querySelector('code').textContent).toBe('[src_123]')
    expect(root.querySelector('a')?.href).toBe('https://example.org/')
  })

  it('keeps HTML sanitized when citations are enabled', () => {
    const html = renderCitedMarkdown('<img src=x onerror=alert(1)><script>alert(1)</script> [src_123]', sources)
    expect(html).not.toContain('onerror')
    expect(html).not.toContain('<script')
  })

  it('rejects invalid IDs and unsafe external links', () => {
    expect(normalizeSources([{ source_id: 'x" onclick="alert(1)', excerpt: 'x' }])).toEqual([])
    for (const url of ['javascript:alert(1)', 'data:text/html,bad', 'file:///secret', 'https://user:password@example.org']) {
      expect(safeSourceUrl(url)).toBe('')
    }
    expect(safeSourceUrl('https://example.org/manual')).toBe('https://example.org/manual')
  })
})
