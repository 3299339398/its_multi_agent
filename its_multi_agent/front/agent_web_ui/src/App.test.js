import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick } from 'vue'
import App from './App.vue'
import { setAuthSession } from './api/auth'

vi.mock('/its-logo.svg', () => ({ default: '/its-logo.svg' }))

const json = (data) => new Response(JSON.stringify(data))
const deferred = () => {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); await nextTick() }
const packet = text => new TextEncoder().encode(`data: ${JSON.stringify({ content: { kind: 'ANSWER', text } })}\n\n`)

describe('chat request lifecycle', () => {
  let app, vm, host, reads
  beforeEach(async () => {
    vi.useFakeTimers()
    vi.stubGlobal('innerWidth', 1440)
    sessionStorage.clear()
    vi.stubGlobal('scrollTo', vi.fn())
    reads = []
    vi.stubGlobal('fetch', vi.fn(async url => {
      if (url === '/api/query') {
        const pending = deferred()
        reads.push(pending)
        return { ok: true, body: { getReader: () => ({ read: () => pending.promise, cancel: async () => {} }) } }
      }
      if (url === '/api/user_sessions') return json({ success: true, sessions: [] })
      return json({ profiles: [], plugins: [] })
    }))
    host = document.createElement('div')
    document.body.append(host)
    app = createApp(App)
    vm = app.mount(host)
    setAuthSession('test-token', { username: 'alice' })
    vm.currentUser = 'alice'
    vm.isLoggedIn = true
    await flush()
    vm.sessions = [{ session_id: 'a', memory: [] }, { session_id: 'b', memory: [{ role: 'assistant', content: 'saved B' }] }]
    vm.selectSession('a')
  })
  afterEach(() => { app.unmount(); host.remove(); vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals(); sessionStorage.clear() })

  it('preserves every answer whitespace chunk including leading whitespace', async () => {
    const chunks = ['  \n\n', '```python\n    first = 1\n\n    second = 2\n```\n\n']
    const queue = [...chunks.map(text => ({ done: false, value: packet(text) })), { done: true }]
    fetch.mockImplementationOnce(async () => ({ ok: true, body: { getReader: () => ({ read: async () => queue.shift(), cancel: async () => {} }) } }))
    vm.userInput = 'format code'
    await vm.handleSend()
    expect(vm.chatMessages.filter(m => m.type === 'assistant').map(m => m.content).join('')).toBe(chunks.join(''))
  })

  it('updates one plan card from SSE and keeps the final answer separate', async () => {
    const event = (status, stepStatus) => ({ content: { contentType: 'sagegpt/plan', run_id: 'run-a', status,
      steps: [{ id: 'step-1', title: '解释递归', executor: 'technical', status: stepStatus, detail: '' }] } })
    const queue = [event('running', 'running'), event('completed', 'completed'),
      { content: { kind: 'ANSWER', text: '递归说明' } }].map(e => ({ done: false,
        value: new TextEncoder().encode(`data: ${JSON.stringify(e)}\n\n`) }))
    queue.push({ done: true })
    fetch.mockImplementationOnce(async () => ({ ok: true, body: { getReader: () => ({ read: async () => queue.shift(), cancel: async () => {} }) } }))
    vm.userInput = '先解释递归，再举例'
    await vm.handleSend()
    expect(vm.chatMessages.filter(m => m.type === 'PLAN')).toHaveLength(1)
    expect(vm.chatMessages.find(m => m.type === 'PLAN').plan.status).toBe('completed')
    expect(vm.chatMessages.find(m => m.type === 'assistant').content).toBe('递归说明')
    await nextTick()
    expect(host.querySelector('[aria-label="复杂任务进度"]').textContent).toContain('已完成')
  })

  it('marks an unfinished plan interrupted when the stream closes', async () => {
    const e = { content: { contentType: 'sagegpt/plan', run_id: 'run-b', status: 'running',
      steps: [{ id: 'step-1', title: '<script>bad</script>', executor: 'technical', status: 'running' }] } }
    const queue = [{ done: false, value: new TextEncoder().encode(`data: ${JSON.stringify(e)}\n\n`) }, { done: true }]
    fetch.mockImplementationOnce(async () => ({ ok: true, body: { getReader: () => ({ read: async () => queue.shift(), cancel: async () => {} }) } }))
    vm.userInput = '分步执行'
    await vm.handleSend()
    expect(vm.chatMessages.find(m => m.type === 'PLAN').plan.status).toBe('interrupted')
    await nextTick()
    expect(host.querySelector('.task-progress script')).toBeNull()
  })

  it('loads archive messages on demand and prepends older evidence without duplication', async () => {
    vm.sessions = [{ session_id: 'paged', title: 'Archive title' }]
    fetch.mockImplementation(async url => {
      if (url.includes('before_id=3')) return json({ messages: [{ id: 2, role: 'assistant', content: 'Older [old]', sources: [{ source_id: 'old', excerpt: 'Original' }] }], next_before_id: null })
      return json({ messages: [{ id: 3, role: 'user', content: 'Newer' }], next_before_id: 3 })
    })
    await vm.selectSession('paged')
    expect(vm.chatMessages.map(m => m.content)).toEqual(['Newer'])
    expect(vm.workspaceTitle).toBe('Archive title')
    await vm.loadOlderMessages()
    expect(vm.chatMessages.map(m => m.content)).toEqual(['Older [old]', 'Newer'])
    expect(vm.chatMessages[0].sources[0].excerpt).toBe('Original')
    expect(vm.nextBeforeId).toBeNull()
  })

  it('ignores a delayed message page after selecting another session', async () => {
    const pending = deferred()
    vm.sessions.push({ session_id: 'paged', title: 'Paged' })
    fetch.mockImplementationOnce(() => pending.promise)
    const loading = vm.selectSession('paged')
    await flush()
    vm.selectSession('b')
    pending.resolve(json({ messages: [{ id: 1, role: 'assistant', content: 'Stale archive' }], next_before_id: 1 }))
    await loading
    expect(vm.chatMessages.map(m => m.content)).toEqual(['saved B'])
    expect(vm.nextBeforeId).toBeNull()
    expect(vm.isLoadingMessages).toBe(false)
  })

  it('paginates metadata without duplicating sessions that move between pages', async () => {
    fetch.mockImplementation(async url => url.includes('page=2')
      ? json({ success: true, sessions: [{ session_id: 'a', title: 'A' }, { session_id: 'c', title: 'C' }], next_page: null })
      : json({ success: true, sessions: [{ session_id: 'a', title: 'A' }], next_page: 2 }))
    await vm.fetchUserSessions()
    await vm.fetchUserSessions(true)
    expect(vm.sessions.map(s => s.session_id)).toEqual(['a', 'c'])
    expect(vm.nextSessionPage).toBeNull()
  })

  it('deletes a non-current session through the authenticated API', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true))
    vm.sessions = [{ session_id: 'a', title: 'A' }, { session_id: 'b', title: 'B' }]
    vm.selectedSessionId = 'a'
    await vm.deleteSession('b')
    expect(fetch).toHaveBeenCalledWith('/api/sessions/b', expect.objectContaining({ method: 'DELETE' }))
    expect(vm.sessions.map(session => session.session_id)).toEqual(['a'])
    expect(vm.selectedSessionId).toBe('a')
  })

  it('clears deleted current session and selects the next available archive', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true))
    vm.sessions = [{ session_id: 'a', title: 'A', memory: [{ role: 'user', content: 'old' }] }, { session_id: 'b', title: 'B', memory: [{ role: 'assistant', content: 'saved B' }] }]
    await vm.selectSession('a')
    vm.chatMessages = [{ type: 'assistant', content: 'in progress' }]
    await vm.deleteSession('a')
    expect(vm.sessions.map(session => session.session_id)).toEqual(['b'])
    expect(vm.selectedSessionId).toBe('b')
    expect(vm.chatMessages.map(message => message.content)).toEqual(['saved B'])
  })

  it('collapses to a toggleable drawer on narrow screens and closes on session selection', async () => {
    window.innerWidth = 390
    window.dispatchEvent(new Event('resize'))
    await nextTick()
    expect(vm.isSidebarExpanded).toBe(false)
    const toggle = host.querySelector('.mobile-sidebar-toggle')
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    toggle.click()
    await nextTick()
    expect(vm.isSidebarExpanded).toBe(true)
    expect(host.querySelector('.sidebar-backdrop')).not.toBeNull()
    vm.selectSession('b')
    await nextTick()
    expect(vm.isSidebarExpanded).toBe(false)
    toggle.click()
    await nextTick()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(vm.isSidebarExpanded).toBe(false)
  })

  it('starts collapsed when mounted at mobile width', async () => {
    app.unmount()
    sessionStorage.clear()
    window.innerWidth = 390
    app = createApp(App)
    vm = app.mount(host)
    expect(vm.isSidebarExpanded).toBe(false)
  })

  it('allows custom model setup even when no saved models are returned', async () => {
    expect(vm.modelProfiles).toEqual([])
    const configure = host.querySelector('.model-config-button')
    expect(configure).not.toBeNull()
    configure.click()
    await nextTick()
    expect(host.querySelector('.model-config-panel input[type="password"]')).not.toBeNull()
  })

  it('ignores a delayed old stream and its cleanup after switching sessions', async () => {
    vm.userInput = 'first'
    const old = vm.handleSend()
    await flush()
    vm.selectSession('b')
    vm.userInput = 'second'
    const current = vm.handleSend()
    await flush()
    reads[0].resolve({ done: false, value: packet('STALE') })
    await flush()
    expect(vm.chatMessages.map(m => m.content)).toEqual(['saved B', 'second'])
    expect(vm.isProcessing).toBe(true)
    expect(vm.userInput).toBe('second')
    reads[1].resolve({ done: true })
    await Promise.all([old, current])
  })

  it.each(['replace', 'cancel'])('isolates a same-session request after %s', async mode => {
    vm.userInput = 'first'
    const old = vm.handleSend()
    await flush()
    if (mode === 'cancel') vm.handleCancel()
    vm.userInput = 'second'
    const current = vm.handleSend()
    await flush()
    reads[0].resolve({ done: true })
    await old
    expect(vm.isProcessing).toBe(true)
    expect(vm.userInput).toBe('second')
    reads[1].resolve({ done: true })
    await current
    expect(vm.isProcessing).toBe(false)
  })

  it('clears private state on logout and ignores a late stream completion', async () => {
    vm.customModel = { name: 'secret model', model_name: 'model', base_url: 'https://example.com', api_key: 'secret' }
    await vm.applyCustomModel()
    vm.currentLocation = { latitude: 1, longitude: 2 }
    vm.userInput = 'request'
    const pending = vm.handleSend()
    await flush()
    vm.selectedAttachments = [{ file: new File(['x'], 'private.txt'), key: 'private' }]
    vm.handleLogout()
    reads[0].resolve({ done: true })
    await pending
    expect(vm.customModel.api_key).toBe('')
    expect(vm.selectedAttachments).toEqual([])
    expect(vm.currentLocation).toBeNull()
    expect(vm.chatMessages).toEqual([])
    expect(vm.selectedModelProfile).toBe('')
    expect(vm.isProcessing).toBe(false)
  })

  it('renders archived attachments separately from the plain message text', async () => {
    vm.sessions = [{ session_id: 'attachment', memory: [{ role: 'user', content: '', attachments: [{ id: 'doc', name: '<report>.pdf', kind: 'document', media_type: 'application/pdf' }] }] }]
    vm.selectSession('attachment')
    await nextTick()
    expect(vm.chatMessages).toHaveLength(1)
    expect(vm.chatMessages[0].content).toBe('')
    expect(host.querySelector('.message-content .attachment-chip')?.textContent).toContain('<report>.pdf')
    expect(host.querySelector('report')).toBeNull()
  })

  it('restores citation snapshots with archived answers', async () => {
    vm.sessions = [{ session_id: 'cited', memory: [{ role: 'assistant', content: '36 months [manual-1]', sources: [
      { source_id: 'manual-1', source_name: 'Manual.pdf', excerpt: 'Warranty is 36 months.', page: 3 },
    ] }] }]
    vm.selectSession('cited')
    await nextTick()
    expect(vm.chatMessages[0].sources?.[0]?.excerpt).toBe('Warranty is 36 months.')
    expect(host.querySelector('.source-citation')?.dataset.sourceId).toBe('manual-1')
  })

  it('attaches a source event to the current streamed answer', async () => {
    const sourceEvent = new TextEncoder().encode(`data: ${JSON.stringify({ content: {
      contentType: 'sagegpt/sources', sources: [{ source_id: 'policy-1', excerpt: 'limit 500', source_name: 'Policy' }],
    } })}\n\n`)
    const queue = [{ done: false, value: sourceEvent }, { done: false, value: packet('Limit: 500 [policy-1]') }, { done: true }]
    fetch.mockImplementationOnce(async () => ({ ok: true, body: { getReader: () => ({ read: async () => queue.shift(), cancel: async () => {} }) } }))
    vm.userInput = 'policy'
    await vm.handleSend()
    expect(vm.chatMessages.find(message => message.type === 'assistant').sources?.[0]?.source_id).toBe('policy-1')
    expect(host.querySelector('.source-citation')?.dataset.sourceId).toBe('policy-1')
  })

  it('does not attach delayed source metadata from another session', async () => {
    vm.userInput = 'first'
    const old = vm.handleSend()
    await flush()
    vm.selectSession('b')
    reads[0].resolve({ done: false, value: new TextEncoder().encode(`data: ${JSON.stringify({ content: {
      contentType: 'sagegpt/sources', sources: [{ source_id: 'private', excerpt: 'private evidence' }],
    } })}\n\n`) })
    await old
    expect(JSON.stringify(vm.chatMessages)).not.toContain('private evidence')
  })

  it('does not restore old history after logout', async () => {
    const history = deferred()
    fetch.mockImplementationOnce(() => history.promise)
    const loading = vm.fetchUserSessions()
    vm.handleLogout()
    history.resolve(json({ success: true, sessions: [{ session_id: 'private', memory: [{ role: 'user', content: 'private text' }] }] }))
    await loading
    expect(vm.sessions).toEqual([])
    expect(vm.chatMessages).toEqual([])
  })

  it('does not restore login after an in-flight login was cleared', async () => {
    vm.handleLogout()
    const login = deferred()
    fetch.mockImplementationOnce(() => login.promise)
    vm.username = 'alice'
    vm.password = 'private'
    const loggingIn = vm.handleLogin()
    vm.handleLogout()
    login.resolve(json({ access_token: 'stale-token', user: { username: 'alice' } }))
    await loggingIn
    expect(vm.isLoggedIn).toBe(false)
    expect(sessionStorage.getItem('itsAuthToken')).toBeNull()
  })

  it('does not restore login when auth validation finishes after logout', async () => {
    app.unmount()
    const validation = deferred()
    fetch.mockImplementationOnce(() => validation.promise)
    app = createApp(App)
    vm = app.mount(host)
    vm.handleLogout()
    validation.resolve(json({ user: { username: 'alice' } }))
    await flush()
    expect(vm.isLoggedIn).toBe(false)
    expect(vm.currentUser).toBe('')
  })

  it('ignores pending model and plugin loads after logout', async () => {
    vm.handleLogout()
    await flush()
    const models = deferred(), plugins = deferred()
    fetch.mockImplementation(url => url === '/api/model-profiles' ? models.promise
      : url === '/api/plugins' ? plugins.promise : Promise.resolve(json({ success: true, sessions: [] })))
    setAuthSession('next-token', { username: 'alice' })
    vm.currentUser = 'alice'
    vm.isLoggedIn = true
    await flush()
    vm.handleLogout()
    models.resolve(json({ profiles: [{ id: 'private', name: 'private' }] }))
    plugins.resolve(json({ plugins: [{ id: 'private', enabled_by_default: true }] }))
    await flush()
    expect(vm.modelProfiles).toEqual([])
    expect(vm.plugins).toEqual([])
    expect(vm.enabledPlugins).toEqual([])
  })

  it('ignores a pending model save after logout', async () => {
    const saved = deferred()
    fetch.mockImplementationOnce(() => saved.promise)
    vm.customModel = { name: 'private', model_name: 'private', base_url: 'https://example.com', api_key: 'secret' }
    vm.customModelMode = 'saved'
    const saving = vm.applyCustomModel()
    vm.handleLogout()
    saved.resolve(json({ id: 'private' }))
    await saving
    expect(vm.selectedModelProfile).toBe('')
    expect(vm.modelConfigMessage).toBe('')
  })

  it('does not replace new-session history with a delayed refresh', async () => {
    const history = deferred()
    fetch.mockImplementationOnce(() => history.promise)
    const loading = vm.fetchUserSessions()
    vm.createNewSession()
    const newId = vm.selectedSessionId
    history.resolve(json({ success: true, sessions: [{ session_id: 'a', memory: [] }] }))
    await loading
    expect(vm.sessions.some(session => session.session_id === newId)).toBe(true)
  })

  it('ignores a delayed location result and never sends after logout', async () => {
    let located
    Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { getCurrentPosition: resolve => { located = resolve } } })
    vm.userInput = '附近'
    const sending = vm.handleSend()
    expect(vm.isProcessing).toBe(true)
    vm.handleLogout()
    located({ coords: { latitude: 1, longitude: 2, accuracy: 10 } })
    await sending
    expect(vm.currentLocation).toBeNull()
    expect(vm.chatMessages).toEqual([])
    expect(reads).toHaveLength(0)
    delete navigator.geolocation
  })

  it('clears applied temporary credentials before another login can send', async () => {
    vm.customModel = { name: 'private', model_name: 'private', base_url: 'https://example.com', api_key: 'secret' }
    await vm.applyCustomModel()
    vm.handleLogout()
    setAuthSession('other-token', { username: 'bob' })
    vm.currentUser = 'bob'
    vm.isLoggedIn = true
    await flush()
    vm.userInput = 'hello'
    const sending = vm.handleSend()
    await flush()
    const query = fetch.mock.calls.find(([url]) => url === '/api/query')
    expect(JSON.parse(query[1].body).temporary_model).toBeNull()
    reads[0].resolve({ done: true })
    await sending
  })
})
