// Remote-only real PDF/browser/API/PostgreSQL acceptance. Never fulfills mock responses.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const { chromium } = require(path.join(root, 'runtime/browser-check/node_modules/playwright'));
const base = process.env.EDITOR_VERIFY_BASE_URL?.replace(/\/$/, '');
const source = process.env.EDITOR_VERIFY_PDF;
if (!base || !source) throw new Error('Explicit real API and original PDF are required');
const command = args => execFileSync('rtk', ['proxy', ...args], { cwd: root, encoding: 'utf8' }).trim();
const config = JSON.parse(command(['docker', 'compose', 'config', '--format', 'json']));
if (!config.name.includes('qualification')) throw new Error('Use an isolated qualification installation');
const token = fs.readFileSync(path.join(root, 'secrets/api_token'), 'utf8').trim();
const bytes = fs.readFileSync(source), hash = crypto.createHash('sha256').update(bytes).digest('hex');
const out = path.join(root, 'evidence', 'upload-resume-' + crypto.randomUUID());
fs.mkdirSync(out, { recursive: true });
const sql = query => JSON.parse(command(['docker', 'compose', 'exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'editor', '-Atc', query]));
const uuid = value => {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value)) throw new Error('Invalid API upload ID');
  return value;
};
const snapshot = () => sql(`SELECT json_build_object('reviews',(SELECT count(*) FROM editor.reviews),'generations',(SELECT count(*) FROM editor.generations),'manifest',(SELECT md5(manifest::text) FROM editor.source_probes WHERE sha256='${hash}'))`);
const dbUpload = id => sql(`SELECT row_to_json(r) FROM (SELECT u.status,u.expected_bytes,u.expected_sha256,u.content_version_id,cv.sha256 FROM editor.uploads u LEFT JOIN editor.content_versions cv ON cv.id=u.content_version_id WHERE u.id='${uuid(id)}') r`);
const report = { api: base, source_sha256: hash, source_bytes: bytes.length, scenarios: [], semantic_acceptance: false, status: 'RUNNING' };
const save = () => fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
function check(condition, message) { if (!condition) throw new Error(message); }
async function login(page) {
  await page.getByLabel('Erişim anahtarı').fill(token);
  await page.getByRole('button', { name: 'Çalışma alanını aç', exact: true }).click();
  await page.locator('.upload-book summary').click();
}
async function viewport(page, name) {
  check(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), 'Page overflow: ' + name);
  await page.screenshot({ path: path.join(out, name + '.png'), fullPage: true });
}
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
  try {
    const before = snapshot();
    // Require the real source already parsed in this installation: this acceptance
    // exercises upload recovery, not eight concurrent/repeated cold parse runs.
    check(before.manifest, 'First qualify this original PDF ingestion in the target installation');
    for (const width of [320, 390, 768, 1440]) for (const interrupted of ['CREATED', 'RECEIVED']) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      try {
        const page = await context.newPage();
        const headers = { Authorization: 'Bearer ' + token };
        const get = async p => {
          const response = await context.request.get(base + p, { headers });
          check(response.ok(), 'Real GET failed: ' + p + ' ' + response.status());
          return response.json();
        };
        await page.goto(base + '/editor/'); await login(page);
        await page.getByLabel('Kitap adı', { exact: true }).fill(path.basename(source, path.extname(source)));
        await page.getByLabel('Baskı / sürüm', { exact: true }).fill('Özgün PDF — kesilen aktarım kabulü');
        await page.getByLabel('PDF dosyası', { exact: true }).setInputFiles(source);
        let interruptedRequest = false;
        const routePattern = interrupted === 'CREATED' ? '**/v1/uploads/*/content' : '**/v1/uploads/*/complete';
        const abort = async route => { interruptedRequest = true; await route.abort('connectionfailed'); };
        await page.route(routePattern, abort);
        const sessionResponse = page.waitForResponse(r => /\/v1\/editions\/[^/]+\/uploads$/.test(r.url()) && r.request().method() === 'POST');
        await page.getByRole('button', { name: 'Yükle ve kaynağı hazırla', exact: true }).click();
        const session = await (await sessionResponse).json(); uuid(session.id);
        await page.locator('.upload-book [role="alert"]').waitFor({ timeout: 120000 });
        check(interruptedRequest, 'No network interruption occurred');
        await page.unroute(routePattern, abort);
        const initial = await get('/v1/uploads/' + session.id), dbInitial = dbUpload(session.id);
        check(initial.status === interrupted && dbInitial.status === interrupted, 'Interrupted API/PG state differs');
        check(dbInitial.expected_sha256 === hash && dbInitial.expected_bytes === bytes.length && !dbInitial.content_version_id, 'Upload source identity differs');
        // A reload discards all in-memory attempt metadata. Recovery must use the
        // durable upload listing and the existing server-side upload identity.
        await page.reload(); await login(page);
        await page.getByLabel('Önceki yüklemeyi takip et').selectOption(session.id);
        const button = page.getByRole('button', { name: interrupted === 'CREATED' ? 'Yüklemeyi sürdür' : 'Kaynak hazırlamayı başlat', exact: true });
        await button.waitFor();
        if (interrupted === 'CREATED') await page.getByLabel('Özgün PDF dosyası', { exact: true }).setInputFiles(source);
        await viewport(page, interrupted + '-' + width);
        let putCount = 0;
        page.on('request', request => { if (request.method() === 'PUT' && request.url().endsWith('/' + session.id + '/content')) putCount++; });
        const completeResponse = page.waitForResponse(r => r.url().endsWith('/' + session.id + '/complete') && r.request().method() === 'POST', { timeout: 120000 });
        await button.click();
        const completedRequest = await completeResponse;
        check(completedRequest.ok(), 'Complete failed: ' + completedRequest.status());
        await page.getByRole('button', { name: 'Kitap analizini başlat', exact: true }).waitFor({ timeout: 180000 });
        const actual = await get('/v1/uploads/' + session.id), dbFinal = dbUpload(session.id);
        check(actual.status === 'COMPLETED' && dbFinal.status === 'COMPLETED', 'Recovery did not complete');
        check(actual.content_version_id === dbFinal.content_version_id && dbFinal.sha256 === hash, 'Recovered API/PG source differs');
        check(putCount === (interrupted === 'CREATED' ? 1 : 0), 'Unexpected repeated/omitted PDF transmission');
        await viewport(page, 'ready-' + interrupted + '-' + width);
        report.scenarios.push({ width, interrupted, upload_id: session.id, api_pg_equal: true, put_count: putCount, status: 'PASS' });
        save(); console.log(JSON.stringify(report.scenarios.at(-1)));
      } finally { await context.close(); }
    }
    check(JSON.stringify(snapshot()) === JSON.stringify(before), 'Source manifest, reviews or generations changed');
    report.source_manifest_and_analysis_unchanged = true; report.status = 'PASS'; save();
  } catch (error) { report.status = 'FAILED'; report.error = error.message; save(); throw error; }
  finally { await browser.close(); }
  console.log(JSON.stringify({ status: report.status, scenarios: report.scenarios.length, evidence: out }));
})().catch(error => { console.error(error.message); process.exitCode = 1; });
