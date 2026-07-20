import puppeteer from 'puppeteer-core';

const CHROME = '/Users/murat/.cache/puppeteer/chrome/mac_arm-150.0.7871.24/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
const ORIGIN = process.env.BI_ORIGIN || 'https://portal.nanobase.ai';
const routes = [
  '/bi/',
  '/bi/budget',
  '/bi/chat',
  '/bi/templates',
  '/bi/queries',
  '/bi/glossary',
  '/bi/semantic-catalog',
  '/bi/scenario-reviews',
  '/bi/sources',
  '/bi/schema',
  '/bi/shares',
  '/bi/schedules',
  '/bi/alerts',
  '/bi/audit',
  '/bi/settings',
];

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const page = await browser.newPage();
page.setDefaultTimeout(25000);
page.setDefaultNavigationTimeout(25000);

const results = [];
for (const route of routes) {
  const errors = [];
  const pageErrors = [];
  const failed = [];
  const onConsole = (msg) => {
    if (msg.type() === 'error') errors.push(msg.text().slice(0, 240));
  };
  const onPageError = (err) => pageErrors.push(String(err).slice(0, 400));
  const onRequestFailed = (req) => {
    const u = req.url();
    if (u.includes('favicon') || u.includes('fonts.g')) return;
    failed.push(`${req.failure()?.errorText || 'fail'} ${u.slice(0, 160)}`);
  };
  page.on('console', onConsole);
  page.on('pageerror', onPageError);
  page.on('requestfailed', onRequestFailed);

  const url = `${ORIGIN}${route}`;
  let finalUrl = '';
  let bodyText = '';
  let rootLen = 0;
  let title = '';
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    await new Promise((r) => setTimeout(r, 2500));
    finalUrl = page.url();
    title = await page.title();
    bodyText = await page.evaluate(() => document.body?.innerText?.slice(0, 600) || '');
    rootLen = await page.evaluate(() => document.getElementById('root')?.innerHTML?.length || 0);
  } catch (e) {
    pageErrors.push(`goto: ${String(e).slice(0, 300)}`);
  }

  page.off('console', onConsole);
  page.off('pageerror', onPageError);
  page.off('requestfailed', onRequestFailed);

  results.push({
    route,
    finalUrl: finalUrl.replace(ORIGIN, ''),
    blank: rootLen < 50,
    rootLen,
    pageErrors: pageErrors.slice(0, 5),
    consoleErrors: errors.slice(0, 6),
    failedReqs: failed.slice(0, 6),
    snippet: bodyText.replace(/\s+/g, ' ').slice(0, 180),
  });
}

await browser.close();
console.log(JSON.stringify(results, null, 2));
