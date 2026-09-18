// Remote real-browser/API/PostgreSQL acceptance. Creates exactly two sequential
// validation jobs for an explicitly selected non-primary completed upload.
// No mocked responses, source edits, review writes, or acceptance promotion.
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const crypto = require('node:crypto'), { execFileSync } = require('node:child_process');
const scriptRoot = path.resolve(__dirname, '..');
const root = path.resolve(process.env.EDITOR_VERIFY_ROOT || scriptRoot);
const assert = (ok, message) => { if (!ok) throw new Error(message); };
const uuid = value => { assert(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value || ''), 'Explicit UUID required'); return value; };
assert(process.platform === 'linux' && os.hostname() === process.env.EDITOR_VERIFY_REMOTE_HOST,
  'Run only on the explicitly named remote Linux application host');
const upload = uuid(process.env.EDITOR_VERIFY_COMPLETED_UPLOAD_ID);
const protectedVersion = uuid(process.env.EDITOR_VERIFY_PROTECTED_CONTENT_VERSION);
const base = process.env.EDITOR_VERIFY_BASE_URL?.replace(/\/$/, '');
assert(base && ['127.0.0.1', 'localhost', '[::1]'].includes(new URL(base).hostname), 'Explicit remote-host loopback API required');
const uiBase = (process.env.EDITOR_VERIFY_UI_BASE_URL || base).replace(/\/$/, '');
assert(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(uiBase).hostname), 'Remote-host loopback UI required');
const command = args => {
  try { return execFileSync(args[0], args.slice(1), { cwd: root, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }).trim(); }
  catch { throw new Error('Remote Compose/PostgreSQL reference command failed; raw stderr suppressed'); }
};
const sql = query => {
  const result = command(['docker', 'compose', 'exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'editor', '-Atc', query]);
  return result ? JSON.parse(result) : null;
};
const token = fs.readFileSync(path.join(root, 'secrets/api_token'), 'utf8').trim();
const safeError = error => String(error.message || error).split(token).join('[REDACTED]');
const { chromium } = require(path.join(scriptRoot, 'runtime/browser-check/node_modules/playwright'));
const out = path.join(root, 'evidence', 'upload-analysis-navigation-' + crypto.randomUUID());
fs.mkdirSync(out, { recursive: true });
const key = 'upload:' + upload + ':analysis', newerKey = 'navigation-acceptance:' + crypto.randomUUID();
const owned = new Set();
const report = { status: 'RUNNING', host: os.hostname(), api: base, ui: uiBase, installation_root: root, upload_id: upload,
  protected_content_version: protectedVersion, scenarios: [], cleanup: [], semantic_acceptance: false,
  source_or_review_writes: 0, script_sha256: crypto.createHash('sha256').update(fs.readFileSync(__filename)).digest('hex') };
const save = () => fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2));
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function idle() {
  const active = sql("SELECT json_build_object('jobs',(SELECT count(*) FROM editor.jobs WHERE status IN ('QUEUED','RUNNING')),'uploads',(SELECT count(*) FROM editor.uploads WHERE status='PARSING'))");
  assert(active.jobs === 0 && active.uploads === 0, 'Active analysis/parse exists; no new job permitted');
}
function dbJob(id) {
  return sql(`SELECT row_to_json(r) FROM (SELECT j.id,j.status,j.generation_id,g.content_version_id,j.cancellation_requested FROM editor.jobs j JOIN editor.generations g ON g.id=j.generation_id WHERE j.id='${uuid(id)}') r`);
}
function conserved() {
  return sql(`SELECT json_build_object('reviews',(SELECT count(*) FROM editor.reviews),'primary_jobs',(SELECT count(*) FROM editor.jobs j JOIN editor.generations g ON g.id=j.generation_id WHERE g.content_version_id='${protectedVersion}'),'primary_records',(SELECT count(*) FROM editor.records r JOIN editor.generations g ON g.id=r.generation_id WHERE g.content_version_id='${protectedVersion}'),'sources',(SELECT md5(COALESCE(json_agg(row_to_json(s) ORDER BY s.sha256)::text,'')) FROM editor.source_probes s))`);
}
(async () => {
  let browser, context, before, mutationStarted = false;
  const request = async (method, route, body, idempotency) => {
    const response = await context.request.fetch(base + '/v1' + route, { method, timeout: 60000,
      headers: { Authorization: 'Bearer ' + token, ...(idempotency ? { 'Idempotency-Key': idempotency } : {}) },
      ...(body ? { data: body } : {}) });
    assert(response.ok(), `Real API ${method} ${route} failed (${response.status()})`);
    return response.json();
  };
  async function cancel(id) {
    assert(owned.has(id), 'Cannot cancel a job not created by this acceptance');
    await request('POST', '/jobs/' + id + '/cancel', { purpose: 'validation' }, 'navigation-cancel:' + id);
    const until = Date.now() + 180000;
    while (Date.now() < until) {
      const actual = await request('GET', '/jobs/' + id), reference = dbJob(id);
      assert(reference && actual.generation_id === reference.generation_id, 'Job API/PG generation differs');
      if (actual.status === 'CANCELLED' && reference.status === 'CANCELLED') {
        assert(reference.cancellation_requested, 'Cancellation flag missing');
        report.cleanup.push({ job_id: id, status: 'CANCELLED', api_pg_equal: true }); save(); return;
      }
      assert(!['FAILED', 'COMPLETED'].includes(actual.status), 'Job reached unexpected terminal state before controlled cancellation');
      await sleep(1000);
    }
    throw new Error('Cancellation did not settle within 180 seconds; do not start another job');
  }
  try {
    idle(); before = conserved();
    // A fresh completed upload is necessary: never cancel a historical user's run.
    assert(sql(`SELECT count(*)::int FROM editor.idempotency WHERE key='${key}'`) === 0, 'Upload already has analysis idempotency history; select another completed upload');
    browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
    context = await browser.newContext({ viewport: { width: 390, height: 1000 } });
    const uploadState = await request('GET', '/uploads/' + upload);
    const reference = sql(`SELECT row_to_json(r) FROM (SELECT u.status,u.content_version_id,e.work_id,cv.sha256 FROM editor.uploads u JOIN editor.editions e ON e.id=u.edition_id LEFT JOIN editor.content_versions cv ON cv.id=u.content_version_id WHERE u.id='${upload}') r`);
    assert(reference && uploadState.status === 'COMPLETED' && reference.status === 'COMPLETED', 'Require a completed real upload');
    assert(uploadState.content_version_id === reference.content_version_id && uploadState.work_id === reference.work_id, 'Upload API/PG differs');
    assert(reference.content_version_id !== protectedVersion, 'Cannot exercise primary book');
    const protectedSource = sql(`SELECT to_json(sha256) FROM editor.content_versions WHERE id='${protectedVersion}'`);
    assert(protectedSource && reference.sha256 !== protectedSource, 'Require a genuinely different source PDF, not another upload of the primary book');
    report.source_sha256 = reference.sha256;
    const version = uuid(reference.content_version_id);
    const initialJobs = sql(`SELECT count(*)::int FROM editor.jobs j JOIN editor.generations g ON g.id=j.generation_id WHERE g.content_version_id='${version}'`);
    const page = await context.newPage();
    async function loginAndSelect() {
      await page.goto(uiBase + '/editor/');
      await page.getByLabel('Erişim anahtarı').fill(token);
      await page.getByRole('button', { name: /^Çalışma alanını aç/ }).click();
      await page.locator('summary').filter({ hasText: /^Yeni kitap yükle$/ }).click();
      const selector = page.getByLabel('Önceki yüklemeyi takip et');
      await selector.waitFor();
      while (!await selector.locator(`option[value="${upload}"]`).count()) {
        const more = page.getByRole('button', { name: /Daha eski yüklemeler/ });
        assert(await more.count() && await more.isVisible(), 'Upload absent from actual UI listing');
        await more.click();
        await page.waitForTimeout(300);
      }
      await selector.selectOption(upload);
      await page.getByRole('button', { name: 'Kitap analizini başlat', exact: true }).waitFor();
    }
    await loginAndSelect(); idle(); mutationStarted = true;
    const firstResponse = page.waitForResponse(r => r.url().endsWith('/content-versions/' + version + '/analyses') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Kitap analizini başlat', exact: true }).click();
    const response = await firstResponse; assert(response.ok(), 'UI analysis POST failed');
    const first = await response.json(); uuid(first.job_id); owned.add(first.job_id); report.first = first; save();
    await cancel(first.job_id);
    await page.waitForFunction(id => [...document.querySelectorAll('label')].find(x => x.textContent.includes('Analiz sürümü'))?.querySelector('select')?.value === id, first.job_id);
    assert(dbJob(first.job_id).content_version_id === version, 'First job bound to wrong content');
    idle();
    const newer = await request('POST', '/content-versions/' + version + '/analyses', { purpose: 'validation' }, newerKey);
    uuid(newer.job_id); owned.add(newer.job_id); report.newer = newer; save(); await cancel(newer.job_id);
    assert(newer.job_id !== first.job_id, 'Newer job was not distinct');
    const actualRuns = await request('GET', '/works/' + uuid(reference.work_id) + '/analyses?offset=0&limit=50');
    assert(actualRuns.items[0]?.id === newer.job_id, 'Newer job is not the default newest row; regression setup invalid');
    const referenceRuns = sql(`SELECT COALESCE(json_agg(row_to_json(r)),'[]'::json) FROM (SELECT j.id,j.generation_id,j.status FROM editor.jobs j JOIN editor.generations g ON g.id=j.generation_id JOIN editor.content_versions cv ON cv.id=g.content_version_id JOIN editor.editions e ON e.id=cv.edition_id WHERE e.work_id='${uuid(reference.work_id)}' AND j.task='analysis' ORDER BY j.created_at DESC,j.id DESC LIMIT 50) r`);
    assert(JSON.stringify(actualRuns.items.map(({ id, generation_id, status }) => ({ id, generation_id, status }))) === JSON.stringify(referenceRuns), 'Analysis listing API/PG differs');
    for (const width of [320, 390, 768, 1440]) {
      idle(); await page.setViewportSize({ width, height: 1000 });
      await page.getByRole('button', { name: 'Analizi görüntüle', exact: true }).click();
      await page.waitForFunction(id => [...document.querySelectorAll('label')].find(x => x.textContent.includes('Analiz sürümü'))?.querySelector('select')?.value === id, first.job_id);
      // A new document discards UploadBook's in-memory job. Its stable server key
      // must return the original job and navigation must select that exact ID.
      await loginAndSelect();
      const replayResponse = page.waitForResponse(r => r.url().endsWith('/content-versions/' + version + '/analyses') && r.request().method() === 'POST');
      await page.getByRole('button', { name: 'Kitap analizini başlat', exact: true }).click();
      const replay = await (await replayResponse).json();
      assert(replay.job_id === first.job_id && replay.generation_id === first.generation_id, 'Reload broke stable idempotency');
      await page.waitForFunction(id => [...document.querySelectorAll('label')].find(x => x.textContent.includes('Analiz sürümü'))?.querySelector('select')?.value === id, first.job_id);
      const count = sql(`SELECT count(*)::int FROM editor.jobs j JOIN editor.generations g ON g.id=j.generation_id WHERE g.content_version_id='${version}'`);
      assert(count === initialJobs + 2, 'Reopen or reload created an additional analysis');
      assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), 'Horizontal page overflow');
      await page.screenshot({ path: path.join(out, 'navigation-' + width + '.png'), fullPage: true });
      report.scenarios.push({ width, first_job_selected: true, reload_idempotent: true, api_pg_job_count: count, overflow: false, status: 'PASS' }); save();
    }
    assert(JSON.stringify(conserved()) === JSON.stringify(before), 'Primary book, source probes, or reviews changed');
    idle(); report.status = 'PASS'; report.api_pg_equal = true; save();
  } catch (error) {
    report.status = 'FAILED'; report.error = safeError(error); save(); process.exitCode = 1;
  } finally {
    // Recover an exact job even if the browser failed after its POST committed.
    // Both keys were fresh for this script; never cancel unrelated work.
    if (mutationStarted && context) {
      try {
        const recover = sql(`SELECT COALESCE(json_agg(response),'[]'::json) FROM editor.idempotency WHERE key IN ('${key}','${newerKey}')`);
        for (const row of recover) if (row.job_id) owned.add(uuid(row.job_id));
        for (const id of owned) if (['QUEUED', 'RUNNING'].includes(dbJob(id)?.status)) await cancel(id);
      } catch (error) { report.cleanup_error = safeError(error); report.status = 'FAILED'; process.exitCode = 1; }
    }
    if (browser) await browser.close(); save();
  }
  console.log(JSON.stringify({ status: report.status, scenarios: report.scenarios.length, evidence: out, cleanup_error: report.cleanup_error }));
})().catch(error => { console.error(safeError(error)); process.exitCode = 1; });
