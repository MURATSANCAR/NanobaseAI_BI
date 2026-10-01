const fs = require('node:fs');
const base = '/tmp/codex-zeki-mention-0930';
const { chromium } = require('/tmp/codex-zeki-residue-0930/build-source/node_modules/playwright');
const auth = JSON.parse(fs.readFileSync(base + '/session.json'));
const tokens = new Set();
(async () => {
  const browser = await chromium.launch({
    executablePath: '/home/administrator/.cache/ms-playwright/chromium-1187/chrome-linux/chrome',
    headless: true, args: ['--no-sandbox', '--host-resolver-rules=MAP portal.nanobase.ai 127.0.0.1'],
  });
  const rows = [];
  try {
    for (const width of [1440, 320, 390, 768]) {
      const context = await browser.newContext({ viewport: { width, height: 900 }, ignoreHTTPSErrors: true });
      await context.addCookies([{ name: '__Secure-timas_session', value: auth.token, domain: 'portal.nanobase.ai',
        path: '/timas/', httpOnly: true, secure: true, sameSite: 'Strict' }]);
      const page = await context.newPage();
      const errors = [], outside = [];
      page.on('pageerror', e => errors.push(e.message.slice(0, 160)));
      page.on('request', r => { const u = new URL(r.url()); if (/^https?:$/.test(u.protocol) && u.hostname !== 'portal.nanobase.ai') outside.push(u.hostname); });
      page.on('response', async r => {
        if (new URL(r.url()).pathname === '/timas/auth/chat-sso' && r.ok()) {
          try { const data = await r.json(); if (data.loginToken) {
            tokens.add(data.loginToken); fs.writeFileSync(base + '/chat-tokens.json', JSON.stringify([...tokens]), { mode: 0o600 });
          }} catch {}
        }
      });
      await page.goto('https://portal.nanobase.ai/timas/sohbet/direct/zeki.bot', { waitUntil: 'domcontentloaded', timeout: 60000 });
      await page.locator('[name="msg"]').first().waitFor({ state: 'visible', timeout: 60000 });
      await page.getByText('Zeki AI — size özel yanıt', { exact: false }).first().waitFor({ timeout: 30000 });
      await page.waitForTimeout(1000);
      const sizes = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
      const text = await page.locator('body').innerText();
      const row = { ...sizes, privateBotAnswerVisible: text.includes('Sorgu kaydı:'), errors, outside };
      rows.push(row);
      await page.screenshot({ path: base + '/mention-' + width + '.png' });
      if (!row.privateBotAnswerVisible || sizes.scrollWidth > width || errors.length || outside.length) throw new Error(JSON.stringify(row));
      await context.close();
    }
    fs.writeFileSync(base + '/browser-evidence.json', JSON.stringify({ passed: true, viewports: rows }, null, 2));
    console.log(JSON.stringify(rows));
  } finally {
    await browser.close();
    fs.writeFileSync(base + '/chat-tokens.json', JSON.stringify([...tokens]), { mode: 0o600 });
  }
})().catch(e => { console.error(e.message); process.exitCode = 1; });
