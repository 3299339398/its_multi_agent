import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, reactive } from 'vue'
import AnswerMessage from './AnswerMessage.vue'

describe('citation evidence viewer', () => {
  let host, app, state
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = function () { this.open = true }
    HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new Event('close')) }
    state = reactive({ text: 'Warranty is 36 months. [manual-1]', sources: [{
      source_id: 'manual-1', origin: 'knowledge', source_name: '<Manual>.pdf', page: 7,
      version: 'v2.0', excerpt: '<img src=x onerror=alert(1)>\nWarranty: 36 months', excerpt_truncated: true,
    }] })
    host = document.createElement('div')
    document.body.append(host)
    app = createApp({ render: () => h(AnswerMessage, state) })
    app.mount(host)
  })
  afterEach(() => { app.unmount(); host.remove(); vi.restoreAllMocks() })

  it('opens original evidence and provenance from an inline citation', async () => {
    host.querySelector('.source-citation').click()
    await nextTick()
    const dialog = host.querySelector('dialog')
    expect(dialog.open).toBe(true)
    expect(dialog.textContent).toContain('<Manual>.pdf')
    expect(dialog.textContent).toContain('7')
    expect(dialog.textContent).toContain('v2.0')
    expect(dialog.querySelector('.source-excerpt').textContent).toContain('<img src=x onerror=alert(1)>')
    expect(dialog.querySelector('img')).toBeNull()
    expect(dialog.textContent).toContain('截断')
    host.querySelector('[aria-label="关闭来源"]').click()
    await nextTick()
    expect(dialog.open).toBe(false)
  })

  it('closes the viewer when its answer sources change', async () => {
    host.querySelector('.source-citation').click()
    await nextTick()
    state.sources = []
    state.text = 'Another conversation'
    await nextTick()
    expect(host.querySelector('dialog').open).toBe(false)
    expect(host.textContent).not.toContain('Warranty: 36 months')
  })

  it('does not render an external link for an unsafe source URL', async () => {
    state.sources = [{ ...state.sources[0], url: 'javascript:alert(1)' }]
    await nextTick()
    host.querySelector('.source-citation').click()
    await nextTick()
    expect(host.querySelector('dialog a')).toBeNull()
  })
})
