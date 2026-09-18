// Read-only remote real UI/API/PostgreSQL check. No application writes or mocks.
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const crypto = require('node:crypto'), { execFileSync } = require('node:child_process');
const assert = (value, reason) => { if (!value) throw new Error(reason); };
const uuid = value => { assert(/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value || ''), 'Explicit real UUID required'); return value; };
assert(process.platform === 'linux' && os.hostname() === process.env.EDITOR_VERIFY_REMOTE_HOST, 'Named remote Linux host required');
const root = path.resolve(process.env.EDITOR_VERIFY_ROOT || path.resolve(__dirname, '..'));
const generation = uuid(process.env.EDITOR_VERIFY_GENERATION_ID), target = uuid(process.env.EDITOR_VERIFY_IMPACT_RECORD_ID);
assert(process.env.EDITOR_VERIFY_IMPACT_REFERENCE_PROOF, 'Independent API/PG impact verifier proof path required');
const referenceProofPath = path.resolve(process.env.EDITOR_VERIFY_IMPACT_REFERENCE_PROOF);
const referenceProofBytes = fs.readFileSync(referenceProofPath);
const referenceProof = JSON.parse(referenceProofBytes);
assert(referenceProof.status === 'PASS' && referenceProof.generation_id === generation && referenceProof.target_id === target
  && referenceProof.semantic_acceptance === false && referenceProof.complete === false, 'Independent graph proof scope/status mismatch');
const base = (process.env.EDITOR_VERIFY_BASE_URL || '').replace(/\/$/, '');
assert(base && new URL(base).hostname === '127.0.0.1', 'Explicit remote loopback API required');
const token = fs.readFileSync(path.join(root, 'secrets/api_token'), 'utf8').trim();
const safe = error => String(error.message || error).split(token).join('[REDACTED]');
function sql(query) {
  try { return JSON.parse(execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'editor', '-Atc', query],
    { cwd: root, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'], maxBuffer: 32 * 1024 * 1024 }).trim() || 'null'); }
  catch { throw new Error('Independent remote PostgreSQL read failed; raw stderr suppressed'); }
}
const canonical = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item);
const protectedState = () => sql(`SELECT json_build_object('records',(SELECT md5(COALESCE(json_agg(row_to_json(r) ORDER BY r.id)::text,'')) FROM editor.records r WHERE generation_id='${generation}'), 'reviews',(SELECT md5(COALESCE(json_agg(row_to_json(r) ORDER BY r.id)::text,'')) FROM editor.reviews r WHERE generation_id='${generation}'))`);
const out = path.join(root, 'evidence', 'source-impact-ui-' + crypto.randomUUID()); fs.mkdirSync(out, { recursive: true });
const report = { status: 'RUNNING', generation_id: generation, target_id: target, host: os.hostname(), api: base, scenarios: [],
  application_writes: 0, semantic_acceptance: false, dependency_graph_reference_acceptance: 'PENDING_SNAPSHOT_MATCH',
  independent_reference_proof: referenceProofPath, independent_reference_sha256: crypto.createHash('sha256').update(referenceProofBytes).digest('hex'),
  script_sha256: crypto.createHash('sha256').update(fs.readFileSync(__filename)).digest('hex') };
const save = () => fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2), { mode: 0o600 });
(async () => {
  let browser, before, page;
  try {
    const active = sql(`SELECT json_build_object('jobs',(SELECT count(*) FROM editor.jobs WHERE generation_id='${generation}' AND status IN ('QUEUED','RUNNING')))`);
    assert(active.jobs === 0, 'Selected real generation must have no active jobs');
    report.concurrency_scope = 'READ_ONLY_COMPLETED_GENERATION_OTHER_GENERATIONS_MAY_RUN';
    before = protectedState(); report.protected_before = before;
    const reference = sql(`SELECT row_to_json(r) FROM (SELECT r.id,r.kind,r.record_key,r.data,e.work_id,j.id AS job_id FROM editor.records r JOIN editor.generations g ON g.id=r.generation_id JOIN editor.content_versions cv ON cv.id=g.content_version_id JOIN editor.editions e ON e.id=cv.edition_id JOIN editor.jobs j ON j.generation_id=g.id WHERE r.generation_id='${generation}' AND r.id='${target}' AND j.task='analysis' ORDER BY j.created_at DESC LIMIT 1) r`);
    assert(reference && ['source_spans', 'source_fragments', 'page_claims'].includes(reference.kind), 'Require a selectable real source/claim record');
    assert(Number.isInteger(reference.data.pdf_page), 'Real record has no page');
    const { chromium } = require(path.join(root, 'runtime/browser-check/node_modules/playwright'));
    browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
    const context = await browser.newContext({ viewport: { width: 390, height: 1100 } });
    const api = async route => { const response = await context.request.get(base + '/v1' + route, { headers: { Authorization: 'Bearer ' + token }, timeout: 60000 }); assert(response.ok(), 'Real API request failed'); return response.json(); };
    page = await context.newPage(); const requests = [], mutationRequests = [];
    report.browser_errors = []; page.on('pageerror', error => report.browser_errors.push(safe(error)));
    report.failed_http = []; page.on('response', response => { if (response.status() >= 400) report.failed_http.push({path: new URL(response.url()).pathname, status: response.status()}); });
    page.on('request', request => {
      if (new URL(request.url()).pathname.endsWith('/impact')) requests.push(request.url());
      if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method()) && new URL(request.url()).pathname.startsWith('/v1/')) mutationRequests.push({ method: request.method(), path: new URL(request.url()).pathname });
    });
    await page.goto(base + '/editor/'); await page.getByLabel('Erişim anahtarı').fill(token);
    await page.getByRole('button', { name: /^Çalışma alanını aç/ }).click();
    await page.getByRole('combobox', { name: /^Kitap/ }).selectOption(reference.work_id);
    await page.getByRole('combobox', { name: /^Analiz sürümü/ }).selectOption(reference.job_id);
    await page.getByRole('combobox', { name: /^PDF sayfası/ }).selectOption(String(reference.data.pdf_page));
    if (reference.kind === 'source_spans') {
      const region = page.locator(`details[data-span-id="${target}"]`); await region.locator('summary').click();
      await region.getByRole('button', { name: 'Kaynakta göster', exact: true }).click();
    } else if (reference.kind === 'source_fragments') {
      // Fragment IDs must be carried by an actual DOM element; no inferred label
      // matching across repeated OCR text is permitted.
      const fragment = page.locator(`[data-fragment-id="${target}"]`);
      assert(await fragment.count() === 1, 'Fragment UI identity hook absent; choose a real source_span/page_claims target');
      await fragment.getByRole('button', { name: 'Küçük bölgeyi kaynakta göster', exact: true }).click();
    }
    const panel = page.locator('details.source-impact'); await panel.waitFor();
    assert(requests.length === 0, 'Impact fetched before user opened the panel');
    const waitImpact = () => page.waitForResponse(response => new URL(response.url()).pathname.endsWith(`/records/${target}/impact`) && response.request().method() === 'GET');
    const firstPending = waitImpact(); await panel.locator('summary').click();
    const firstResponse = await firstPending; assert(firstResponse.ok(), 'Initial real impact request failed');
    const first = await firstResponse.json();
    assert(first.generation_id === generation && first.target.id === target && /^[0-9a-f]{64}$/.test(first.snapshot_sha256), 'Impact identity/snapshot mismatch');
    assert(first.snapshot_sha256 === referenceProof.snapshot_sha256, 'Independent graph proof is stale for this UI snapshot');
    assert(canonical(first.target) === canonical(referenceProof.target), 'Independent graph target metadata differs');
    assert(first.complete === false && first.semantic_acceptance === false, 'Impact promoted semantic acceptance');
    assert(first.target.kind === reference.kind && first.target.record_key === reference.record_key, 'Impact target API/PG identity differs');
    let data = first; const items = [...data.items]; let paginated = false;
    while (data.has_more) {
      const pending = waitImpact(); await panel.getByRole('button', { name: 'Diğer bağlı kayıtları göster', exact: true }).click();
      const response = await pending; assert(response.ok(), 'Snapshot changed or impact pagination failed; preserve evidence');
      const url = new URL(response.url()); assert(url.searchParams.get('expected_snapshot_sha256') === first.snapshot_sha256, 'Pagination not bound to snapshot');
      data = await response.json(); assert(data.snapshot_sha256 === first.snapshot_sha256 && data.offset === items.length, 'Pagination snapshot/offset mismatch');
      assert(data.items.length && !data.items.some(row => items.some(old => old.id === row.id)), 'Duplicate or empty continuation');
      items.push(...data.items); paginated = true;
    }
    assert(items.length === first.total, 'Incomplete real impact listing');
    assert(referenceProof.impacted_records === items.length && referenceProof.records_verified === items.length + 1,
      'Independent graph proof record counts differ');
    await panel.getByText(`${items.length}/${first.total} bağlı kayıt gösteriliyor.`, { exact: true }).waitFor();
    let offset = 0, found = false;
    for (;;) {
      const apiRows = await api(`/generations/${generation}/${reference.kind}?pdf_page=${reference.data.pdf_page}&offset=${offset}&limit=100`);
      found ||= apiRows.items.some(row => row.id === target && canonical(row.data) === canonical(reference.data));
      if (!apiRows.has_more) break;
      assert(apiRows.items.length, 'Source API pagination did not advance'); offset += apiRows.items.length;
    }
    assert(found, 'Selected source API/PG differs');
    for (const item of items) {
      const row = sql(`SELECT json_build_object('id',id,'kind',kind,'record_key',record_key) FROM editor.records WHERE generation_id='${generation}' AND id='${uuid(item.id)}'`);
      assert(row && row.kind === item.kind && row.record_key === item.record_key, 'Impact result absent/different in PG');
    }
    fs.writeFileSync(path.join(out, 'actual-impact.json'), JSON.stringify({ ...first, items }, null, 2), { mode: 0o600 });
    report.snapshot_sha256 = first.snapshot_sha256; report.api_pg_record_identity_equal = true;
    report.dependency_graph_reference_acceptance = 'PASS_SAME_SNAPSHOT_SEPARATE_INDEPENDENT_VERIFIER';
    report.scenarios.push({ scenario: 'LAZY_FETCH_AND_REAL_RECORDS', status: 'PASS', total: items.length });
    report.scenarios.push({ scenario: 'REAL_PAGINATION', status: paginated ? 'PASS' : 'NOT_EXERCISED', reason: paginated ? undefined : 'Actual graph fits first page; no synthetic records created' });
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1100 });
      assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), 'Horizontal page overflow');
      await page.screenshot({ path: path.join(out, `impact-${width}.png`), fullPage: true });
      report.scenarios.push({ scenario: 'MOBILE', width, status: 'PASS', overflow: false }); save();
    }
    assert(mutationRequests.length === 0, 'UI made an application mutation request');
    assert(canonical(protectedState()) === canonical(before), 'Protected records/reviews changed');
    report.status = 'PASS'; report.scope = 'UI_WITH_SNAPSHOT_BOUND_INDEPENDENT_API_PG_REFERENCE';
    report.snapshot_conflict_409 = 'NOT_EXERCISED_NO_REAL_SOURCE_MUTATION';
  } catch (error) { report.status = 'FAILED'; report.error = safe(error); process.exitCode = 1;
    if (page) report.visible_failure_text = safe(await page.locator('body').innerText().catch(() => 'Unavailable'));
  }
  finally {
    if (before) {
      try { report.protected_after = protectedState(); report.protected_unchanged = canonical(before) === canonical(report.protected_after);
        if (!report.protected_unchanged) { report.status = 'FAILED'; report.error = 'Protected records/reviews changed'; process.exitCode = 1; }
      } catch (error) { report.status = 'FAILED'; report.protected_read_error = safe(error); process.exitCode = 1; }
    }
    if (browser) await browser.close(); save();
  }
  console.log(JSON.stringify({ status: report.status, evidence: out, scope: report.scope }));
})().catch(error => { report.status = 'FAILED'; report.error = safe(error); save(); console.error(safe(error)); process.exitCode = 1; });
