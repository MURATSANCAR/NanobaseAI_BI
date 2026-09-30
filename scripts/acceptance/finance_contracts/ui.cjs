// Run on the test server against the real portal; never intercept/mock API responses.
const { chromium } = require('/tmp/navshot/node_modules/playwright-core');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const out = process.env.FINANCE_UI_OUT;
  const browser = await chromium.launch({ executablePath: '/opt/playwright-browsers/chromium-1228/chrome-linux64/chrome', args: ['--no-sandbox'] });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
    await context.addCookies([{ name: '__Secure-timas_session', value: process.env.FINANCE_UI_TOKEN, domain: 'portal.nanobase.ai', path: '/', secure: true, httpOnly: true }]);
    const page = await context.newPage();
    const question = process.env.FINANCE_UI_QUESTION || '29 Eylül 2026 tarihinde kitap bazında satılan adet nedir?';
    const answerPromise = page.waitForResponse(r => r.url().endsWith('/api/v1/ask') && r.request().method() === 'POST', { timeout: 240000 });
    await page.goto('https://portal.nanobase.ai/timas/genel-bakis?soru=' + encodeURIComponent(question), { waitUntil: 'domcontentloaded' });
    const response = await answerPromise;
    if (!response.ok()) throw new Error('Real ask API HTTP ' + response.status());
    const answer = await response.json();
    fs.writeFileSync(path.join(out, 'answer.json'), JSON.stringify(answer));
    if (!answer.resultId || answer.semantic?.engine !== 'finance_contract_v1') throw new Error('New engine full result missing');
    const fullPromise = page.waitForResponse(r => r.url().endsWith('/api/v1/result/' + answer.resultId));
    await page.getByRole('button', { name: /Tam sonucu aç/ }).click();
    const full = await (await fullPromise).json();
    fs.writeFileSync(path.join(out, 'full.json'), JSON.stringify(full));
    await page.getByRole('button', { name: 'CSV indir', exact: true }).waitFor();
    const checks = [];
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      const geometry = await page.evaluate(() => {
        const root = document.documentElement, dialog = document.querySelector('dialog');
        const rect = dialog.getBoundingClientRect();
        return { viewport: innerWidth, pageWidth: root.scrollWidth, dialogLeft: rect.left, dialogRight: rect.right, dialogHeight: rect.height, viewportHeight: innerHeight };
      });
      if (geometry.pageWidth > width + 1 || geometry.dialogLeft < -1 || geometry.dialogRight > width + 1 || geometry.dialogHeight > 1000) throw new Error('Overflow ' + JSON.stringify(geometry));
      await page.screenshot({ path: path.join(out, `result-${width}.png`), fullPage: true });
      checks.push({ width, ...geometry, status: 'PASS' });
    }
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'CSV indir', exact: true }).click();
    await (await downloadPromise).saveAs(path.join(out, 'result.csv'));
    if (full.totalRows > 50) {
      await page.getByRole('button', { name: 'Sonraki', exact: true }).click();
      if (!(await page.getByRole('dialog').innerText()).includes('2 /')) throw new Error('Second result page not shown');
    }
    const sectionChecks = [];
    for (const [index, section] of (full.sections || []).entries()) {
      await page.getByRole('navigation', { name: 'Rapor bölümleri' }).getByRole('button', { name: section.title, exact: true }).click();
      for (const width of [320, 390, 768, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        const size = await page.evaluate(() => {
          const rect = document.querySelector('dialog').getBoundingClientRect();
          return { pageWidth: document.documentElement.scrollWidth, left: rect.left, right: rect.right, height: rect.height };
        });
        if (size.pageWidth > width + 1 || size.left < -1 || size.right > width + 1 || size.height > 1000) throw new Error('Section overflow ' + JSON.stringify(size));
        await page.screenshot({ path: path.join(out, `section-${index}-${width}.png`), fullPage: true });
        sectionChecks.push({ index, width, status: section.status, rows: section.totalRows, ...size });
      }
      if (['COMPLETE', 'PARTIAL'].includes(section.status)) {
        const pending = page.waitForEvent('download');
        await page.getByRole('button', { name: 'CSV indir', exact: true }).click();
        await (await pending).saveAs(path.join(out, `section-${index}.csv`));
      }
    }
    await page.getByRole('button', { name: 'Kapat', exact: true }).click();
    const clarificationPage = await context.newPage();
    await clarificationPage.setViewportSize({ width: 320, height: 1000 });
    const clarificationPromise = clarificationPage.waitForResponse(r => r.url().endsWith('/api/v1/ask') && r.request().method() === 'POST', { timeout: 240000 });
    await clarificationPage.goto('https://portal.nanobase.ai/timas/genel-bakis?soru=' + encodeURIComponent('29 Eylül 2026 tarihinde perakende satış tutarı ne kadar?'), { waitUntil: 'domcontentloaded' });
    const clarification = await (await clarificationPromise).json();
    if (clarification.type !== 'CLARIFICATION') throw new Error('Ambiguous amount was answered without clarification');
    await clarificationPage.getByText(clarification.explanation, { exact: false }).first().waitFor();
    await clarificationPage.screenshot({ path: path.join(out, 'clarification-320.png'), fullPage: true });
    fs.writeFileSync(path.join(out, 'browser.json'), JSON.stringify({ checks, sectionChecks, clarificationVisible: true, resultId: answer.resultId, totalRows: full.totalRows, previewRows: answer.records.length, sourceWrites: 0 }, null, 2));
    console.log(JSON.stringify({ browser: 'PASS', rows: full.totalRows, widths: checks.map(x => x.width) }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
