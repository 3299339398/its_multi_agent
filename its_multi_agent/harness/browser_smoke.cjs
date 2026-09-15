// Run against a local Vite server; API fixtures avoid paid model calls or user data.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');

(async () => {
  const browser = await chromium.launch({ channel: process.env.ITS_BROWSER_CHANNEL || 'msedge', headless: true });
  const output = process.env.ITS_BROWSER_ARTIFACTS || path.join(os.tmpdir(), 'its-browser-smoke');
  await fs.mkdir(output, { recursive: true });
  const answer = '```python\nif True:\n    first = 1\n\n    second = 2\n```\nSee [manual-1].';
  try {
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }, { width: 320, height: 740 }]) {
      const context = await browser.newContext({ viewport });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => {
        sessionStorage.setItem('itsAuthToken', 'browser-test-token');
        sessionStorage.setItem('itsAuthUser', JSON.stringify({ username: 'reviewer', user_id: 'reviewer', role: 'user' }));
      });
      await page.route('**/api/**', async route => {
        const url = new URL(route.request().url());
        if (!url.pathname.startsWith('/api/')) return route.continue();
        let body = {};
        if (url.pathname === '/api/auth/me') body = { user: { username: 'reviewer', user_id: 'reviewer', role: 'user' } };
        if (url.pathname === '/api/user_sessions') body = { success: true, sessions: [{ session_id: 'browser_test', title: 'Read the document', total_messages: 2 }], next_page: null };
        if (url.pathname === '/api/sessions/browser_test/messages') body = url.searchParams.has('before_id')
          ? { messages: [{ id: 1, role: 'assistant', content: 'Earlier archived answer' }], next_before_id: null }
          : { messages: [{ id: 2, role: 'user', content: 'Read the document', attachments: [{ id: 'example', name: 'manual.txt', kind: 'document' }] }], next_before_id: 2 };
        if (url.pathname === '/api/model-profiles') body = { profiles: [{ id: 'preview', name: 'Technical support model with a long name' }] };
        if (url.pathname === '/api/plugins') body = { plugins: [] };
        if (url.pathname === '/api/query') {
          const packets = [
            { content: { contentType: 'sagegpt/sources', sources: [{ source_id: 'manual-1', origin: 'knowledge', source_name: 'ZX-81 manual', excerpt: 'Disconnect power before servicing.\nKeep the original data.', page: 12, version: '2026.09', excerpt_truncated: true }] } },
            { content: { kind: 'ANSWER', text: answer } },
            { status: 'FINISHED', content: { contentType: 'sagegpt/finish' }, metadata: { finishReason: 'NORMAL' } },
          ];
          await route.fulfill({ contentType: 'text/event-stream', body: packets.map(packet => `data: ${JSON.stringify(packet)}\n\n`).join('') });
          return;
        }
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
      });
      await page.goto(process.env.ITS_PREVIEW_URL || 'http://127.0.0.1:5173/');
      await page.getByText('manual.txt', { exact: true }).waitFor({ timeout: 10000 }).catch(async error => {
        console.error(JSON.stringify({ errors, body: (await page.locator('body').innerText()).slice(0, 1600) }));
        await page.screenshot({ path: path.join(output, `failure-${viewport.width}.png`), fullPage: true });
        throw error;
      });
      await page.getByRole('button', { name: '加载更早消息', exact: true }).click();
      await page.getByText('Earlier archived answer', { exact: true }).waitFor();
      await page.locator('textarea').fill('Show formatted Python code');
      await page.getByRole('button', { name: '发送', exact: true }).click();
      const code = page.locator('pre code').last();
      await code.waitFor();
      assert.equal(await code.textContent(), 'if True:\n    first = 1\n\n    second = 2\n');
      assert.deepEqual(errors, []);
      const sendBounds = await page.locator('.send-button').boundingBox();
      const locationBounds = await page.locator('.location-button').boundingBox();
      assert.ok(locationBounds.x + locationBounds.width <= sendBounds.x, 'composer buttons must not overlap');
      const messageBounds = await page.locator('.message-wrapper.assistant').last().boundingBox();
      const composerBounds = await page.locator('.input-container').boundingBox();
      assert.ok(Math.abs(messageBounds.x - composerBounds.x) < 2, 'answer and composer must align');
      const originalTitle = await page.locator('.workspace-title h1').textContent();
      await page.locator('.workspace-title h1').evaluate(node => { node.textContent = 'A very long conversation title '.repeat(12); });
      const titleBounds = await page.locator('.workspace-title').boundingBox();
      const modelBounds = await page.locator('.model-selector').boundingBox();
      assert.ok(titleBounds.x + titleBounds.width <= modelBounds.x + 1, 'title must not overlap model controls');
      await page.locator('.workspace-title h1').evaluate((node, title) => { node.textContent = title; }, originalTitle);
      await page.getByRole('button', { name: '模型设置', exact: true }).click();
      const configBounds = await page.locator('.model-config-panel').boundingBox();
      assert.ok(configBounds.x >= 0 && configBounds.x + configBounds.width <= viewport.width);
      await page.getByRole('button', { name: '模型设置', exact: true }).click();
      if (viewport.width <= 760) {
        await page.getByRole('button', { name: '展开侧边栏', exact: true }).click();
        await page.screenshot({ path: path.join(output, `sidebar-${viewport.width}.png`), fullPage: true });
        await page.getByRole('button', { name: '关闭侧边栏', exact: true }).click({ position: { x: viewport.width - 10, y: 100 } });
      }
      await page.screenshot({ path: path.join(output, `chat-${viewport.width}.png`), fullPage: true });
      const citation = page.locator('.source-citation').last();
      await citation.click();
      const dialog = page.getByRole('dialog', { name: '引用原文' });
      await dialog.waitFor();
      assert.match(await dialog.innerText(), /Disconnect power before servicing/);
      assert.match(await dialog.innerText(), /2026.09/);
      const bounds = await dialog.boundingBox();
      assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= viewport.width);
      assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= viewport.height);
      await page.screenshot({ path: path.join(output, `citation-${viewport.width}.png`), fullPage: true });
      await page.keyboard.press('Escape');
      await dialog.waitFor({ state: 'hidden' });
      assert.equal(await citation.evaluate(node => node === document.activeElement), true);
      const dimensions = await page.evaluate(() => ({ viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
      assert.ok(dimensions.scrollWidth <= dimensions.viewport);
      console.log(JSON.stringify({ viewport, codeFormatting: 'pass', pageErrors: errors.length, dimensions }));
      await context.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
