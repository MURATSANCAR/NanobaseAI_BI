// Execute only on the named remote application host after deployment.
// Real UI/API/PostgreSQL; no mocks, source changes, review decisions or activation.
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const crypto = require('node:crypto'), { execFileSync } = require('node:child_process');
const assert = (value, reason) => { if (!value) throw new Error(reason); };
const uuid = value => { assert(/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value || ''), 'Explicit UUID required'); return value; };
assert(process.platform === 'linux' && os.hostname() === process.env.EDITOR_VERIFY_REMOTE_HOST, 'Named remote Linux host required');
const root = path.resolve(process.env.EDITOR_VERIFY_ROOT || path.resolve(__dirname, '..'));
const generation = uuid(process.env.EDITOR_VERIFY_GENERATION_ID);
const startedAt = Date.now();
const questions = ['Kaynaklarda anlatılan olaylardan hangileri doğrulanabiliyor?', 'Kitaptaki bütün karakterlerin kesin doğum tarihleri nelerdir?'];
const base = (process.env.EDITOR_VERIFY_BASE_URL || '').replace(/\/$/, '');
assert(base && new URL(base).hostname === '127.0.0.1' && new URL(base).port === '8810', 'Explicit real remote API 127.0.0.1:8810 required');
const token = fs.readFileSync(path.join(root, 'secrets/api_token'), 'utf8').trim();
const safe = error => String(error.message || error).split(token).join('[REDACTED]');
function command(args, input) {
  try { return execFileSync(args[0], args.slice(1), { cwd: root, input, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'], maxBuffer: 64 * 1024 * 1024 }).trim(); }
  catch { throw new Error('Remote reference command failed; raw stderr suppressed'); }
}
const sql = query => JSON.parse(command(['docker', 'compose', 'exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'editor', '-Atc', query]) || 'null');
const canonical = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const out = path.join(root, 'evidence', 'source-question-ui-' + crypto.randomUUID());
fs.mkdirSync(out, { recursive: true });
const report = { status: 'RUNNING', host: os.hostname(), api: base, generation_id: generation, scenarios: [], submissions: [], cleanup: [],
  semantic_acceptance: false, application_source_or_review_writes: 0, script_sha256: crypto.createHash('sha256').update(fs.readFileSync(__filename)).digest('hex') };
const save = () => fs.writeFileSync(path.join(out, 'verification.json'), JSON.stringify(report, null, 2), { mode: 0o600 });
const owned = new Set(), keys = new Set(), posts = [];
function idle() {
  const state = sql("SELECT json_build_object('jobs',(SELECT count(*) FROM editor.jobs WHERE status IN ('QUEUED','RUNNING')),'parses',(SELECT count(*) FROM editor.uploads WHERE status='PARSING'))");
  assert(state.jobs === 0 && state.parses === 0, 'Active job/parse exists; do not overlap question acceptance');
}
function protectedState() {
  return sql(`SELECT json_build_object('reviews',(SELECT md5(COALESCE(json_agg(row_to_json(r) ORDER BY r.id)::text,'')) FROM editor.reviews r),
    'sources',(SELECT md5(COALESCE(json_agg(row_to_json(r) ORDER BY r.id)::text,'')) FROM editor.records r WHERE generation_id='${generation}' AND kind NOT IN ('answers','source_passages','source_index')),
    'generation',(SELECT row_to_json(g) FROM editor.generations g WHERE id='${generation}'),
    'source_probes',(SELECT md5(COALESCE(json_agg(row_to_json(s) ORDER BY s.sha256)::text,'')) FROM editor.source_probes s))`);
}
const countJobs = () => sql(`SELECT count(*)::int FROM editor.jobs WHERE generation_id='${generation}' AND task='question'`);
const job = id => sql(`SELECT row_to_json(j) FROM editor.jobs j WHERE id='${uuid(id)}'`);
const referencePython = String.raw`
import sys,json,hashlib,re
from editor.config import connection
actual=json.load(sys.stdin); generation=actual['generation_id']; job_id=actual['job_id']
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
with connection() as db:
 db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
 j=db.execute('SELECT generation_id,status FROM editor.jobs WHERE id=%s',(job_id,)).fetchone()
 answer=db.execute("SELECT data FROM editor.records WHERE generation_id=%s AND kind='answers' AND record_key=%s",(generation,job_id)).fetchone()['data']
 rows=db.execute("SELECT id,kind,data FROM editor.records WHERE generation_id=%s AND kind=ANY(%s)",(generation,['source_spans','source_passages','evidence'])).fetchall()
assert str(j['generation_id'])==generation and j['status']==actual['job_status']=='COMPLETED'
assert answer==actual['answer'],'API_PG_ANSWER_MISMATCH'
assert answer['mode']=='editor_preview' and answer['verification_status']=='PARTIAL_SOURCE_SUPPORTED_DRAFT'
assert answer['is_final'] is False and answer['semantic_acceptance'] is False and answer['complete_book'] is False
assert answer['status'] in ('PARTIAL','INSUFFICIENT_EVIDENCE') and answer['review_status']=='PENDING'
assert answer['answer']=='\n'.join(c['text'] for c in answer['claims']),'FREE_ANSWER_TEXT'
assert bool(answer['claims'])==(answer['status']=='PARTIAL')
spans={str(r['id']):r['data'] for r in rows if r['kind']=='source_spans'}
passages={str(r['id']):r['data'] for r in rows if r['kind']=='source_passages'}
evidence={str(r['id']):r['data'] for r in rows if r['kind']=='evidence'}
retrieved={r['id']:r['data'] for r in answer['retrieved_passages']}
def verify_view(view,refs):
 ids=view['span_refs'];assert ids and len(ids)==len(set(ids)) and set(ids)<=set(refs)
 assert view['raw_text']=='\n'.join(spans[i]['text'] for i in ids)
 joins={(j['left_span_ref'],j['right_span_ref']):j['operation'] for j in view['line_end_joins']}
 assert len(joins)==len(view['line_end_joins']) and set(joins)<=set(zip(ids,ids[1:]))
 text=spans[ids[0]]['text']
 for left,right in zip(ids,ids[1:]):
  a,b=spans[left],spans[right];op=joins.get((left,right));x,y,w,h=a['bbox'];xx,yy,ww,hh=b['bbox']
  if op=='JOIN_VERIFIED_DROP_CAP_IN_READING_VIEW_ONLY':
   glyph=a['text'].strip();body=b['text'].lstrip()
   assert len(glyph)==1 and glyph.isalpha() and glyph.isupper() and body[0].islower()
   assert h>=1.4*hh and x<xx and -.5*w<=xx-(x+w)<=.15*hh and max(0,min(y+h,yy+hh)-max(y,yy))>=.5*hh and y+h>yy+hh
   text=text.rstrip()+body
  elif op=='REMOVE_GEOMETRIC_LINE_END_HYPHEN_IN_READING_VIEW_ONLY':
   assert re.search(r'\w-\s*$',a['text']) and re.match(r'^\s*\w',b['text'])
   assert yy>=y+.5*h and yy-(y+h)<=2*max(h,hh) and max(0,min(x+w,xx+ww)-max(x,xx))>=.5*min(w,ww)
   text=re.sub(r'-\s*$','',text)+b['text'].lstrip()
  else:
   assert op is None
   text+='\n'+b['text']
 assert text==view['reading_text']
for identifier,p in retrieved.items():
 assert passages[identifier]==p
 assert p['preview_only'] is True and p['editorial_acceptance'] is False and p['complete_book'] is False
 regions=[{'span_id':ref,**{k:spans[ref][k] for k in ('text','bbox','render_sha256')}} for ref in p['source_span_refs']]
 assert regions==p['regions'] and digest(regions)==p['source_regions_sha256']
 assert p['text']=='\n'.join(r['text'] for r in regions)
 assert all(spans[ref]['status']=='TEXT_AGREED' and spans[ref]['role']=='TEXT' and spans[ref]['pdf_page']==p['pdf_page'] for ref in p['source_span_refs'])
 assert all(ref in evidence and evidence[ref]['pdf_page']==p['pdf_page'] for ref in p['evidence_refs'])
for c in answer['claims']:
 p=retrieved[c['passage_id']];review=c['citation_review']
 assert c['span_refs']==p['source_span_refs'] and c['source_regions']==p['regions'] and c['evidence_refs']==p['evidence_refs']
 assert c['pdf_page']==p['pdf_page'] and c['passage_input_sha256']==p['input_sha256']
 assert review['passed'] is True and review['source_regions']==p['regions'] and review['source_sha256']==digest(p['regions'])
 assert review['support_span_refs']==p['source_span_refs']
 carried=[ref for view in review['source_reading_segments'] for ref in view['span_refs']]
 assert len(carried)==len(set(carried)) and set(carried)==set(p['source_span_refs'])
 for view in review['source_reading_segments']:verify_view(view,p['source_span_refs'])
 claim={key:c.get(key) for key in ('text','actor','speaker','narrative_mode','polarity')}
 claim.update(kind='STATEMENT',span_refs=p['source_span_refs'],quote=p['text'])
 assert review['input_sha256']==digest({'claim':claim,'cited_source_regions':p['regions'],'source_reading_segments':review['source_reading_segments']})
 assert review['model_result']['checks']=={key:'PASS' for key in ('entailment','actor','speaker','polarity','narrative_mode')}
 assert review['model_result']['support_span_refs'] and set(review['model_result']['support_span_refs'])<=set(p['source_span_refs'])
 assert review['metrics']['finish_reason']=='stop' and c['relevance_review']['metrics']['finish_reason']=='stop'
 assert c['relevance_review']['model_result']['relevant'] is True and c['semantic_acceptance'] is False
 assert any(all(candidate.get(key)==c.get(key) for key in ('text','passage_id','actor','speaker','narrative_mode','polarity')) for candidate in answer['raw_model_result']['claims'])
print(json.dumps({'api_pg_answer_equal':True,'source_regions_verified':True,'passed_claims':len(answer['claims']),'status':answer['status'],'answer_sha256':digest(answer),'semantic_acceptance':False}))
`;
(async () => {
  let browser, context, page, before;
  async function api(method, route, body, key) {
    const response = await context.request.fetch(base + '/v1' + route, { method, timeout: 60000,
      headers: { Authorization: 'Bearer ' + token, ...(key ? { 'Idempotency-Key': key } : {}) }, ...(body ? { data: body } : {}) });
    assert(response.ok(), `API ${route} failed (${response.status()})`); return response.json();
  }
  async function all(route) {
    const rows = [];
    for (;;) { const batch = await api('GET', route + (route.includes('?') ? '&' : '?') + `offset=${rows.length}&limit=100`); rows.push(...batch.items); if (!batch.has_more) return rows; assert(batch.items.length, 'Empty pagination'); }
  }
  async function terminal(id, timeout = 900000) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      const actual = await api('GET', '/answers/' + id), reference = job(id);
      assert(actual.generation_id === generation && String(reference.generation_id) === generation, 'Wrong answer generation');
      if (actual.job_status !== reference.status) { await sleep(200); continue; }
      if (!['QUEUED', 'RUNNING'].includes(actual.job_status)) return actual;
      await sleep(3000);
    }
    throw new Error('Owned question exceeded 15 minutes; no next question will start');
  }
  try {
    idle(); before = protectedState(); report.before = before; save();
    const { chromium } = require(path.join(root, 'runtime/browser-check/node_modules/playwright'));
    browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
    context = await browser.newContext({ viewport: { width: 390, height: 1000 } });
    const target = sql(`SELECT row_to_json(r) FROM (SELECT e.work_id,j.id AS job_id FROM editor.generations g JOIN editor.content_versions cv ON cv.id=g.content_version_id JOIN editor.editions e ON e.id=cv.edition_id JOIN editor.jobs j ON j.generation_id=g.id WHERE g.id='${generation}' AND j.task='analysis' ORDER BY j.created_at DESC LIMIT 1) r`);
    assert(target, 'Analysis generation absent'); uuid(target.work_id); uuid(target.job_id);
    assert((await all('/works')).some(row => row.id === target.work_id), 'Work absent from real API');
    assert((await all('/works/' + target.work_id + '/analyses')).some(row => row.id === target.job_id && row.generation_id === generation), 'Analysis API/PG differs');
    const capability = await api('GET', '/generations/' + generation + '/source-preview'); report.capability = capability;
    assert(capability.ready === true && capability.scope === 'PARTIAL_SOURCE_SUPPORTED_DRAFT', 'Source preview not ready');
    page = await context.newPage();
    page.on('request', request => {
      if (request.method() !== 'POST' || !request.url().endsWith('/v1/questions')) return;
      const body = request.postDataJSON(), key = request.headers()['idempotency-key'];
      posts.push({ body, key }); if (body?.generation_id === generation && /^[0-9a-f-]{36}$/.test(key || '')) keys.add(key);
    });
    await page.goto(base + '/editor/');
    await page.getByLabel('Erişim anahtarı').fill(token);
    await page.getByRole('button', { name: /^Çalışma alanını aç/ }).click();
    // Wrapped labels include option text in Playwright's label-text lookup.
    // Scope to the two actual workspace selectors, not exact label text.
    await page.locator('.selectors select').nth(0).selectOption(target.work_id);
    await page.locator('.selectors select').nth(1).selectOption(target.job_id);
    await page.getByRole('button', { name: 'Soru & cevap', exact: true }).click();
    const form = page.getByRole('region', { name: 'Kaynak destekli soru taslağı' });
    await form.waitFor();
    const input = form.locator('textarea'), send = form.getByRole('button', { name: 'Kaynaklardan yanıt iste', exact: true });
    const initialJobs = countJobs();
    for (const invalid of ['ab', 'S'.repeat(1001)]) {
      await input.fill(invalid); assert(await send.isDisabled(), 'Invalid question can be submitted');
      await sleep(300); assert(posts.length === 0 && countJobs() === initialJobs, 'Client validation created a question');
    }
    report.scenarios.push({ scenario: '3_TO_1000_CHARACTERS', status: 'PASS', no_post: true }); save();
    for (const [index, question] of questions.entries()) {
      idle(); await input.fill(question);
      const responsePromise = page.waitForResponse(r => r.url().endsWith('/v1/questions') && r.request().method() === 'POST', { timeout: 60000 });
      await send.click(); const response = await responsePromise;
      assert(response.ok(), 'Real form POST failed'); const queued = await response.json();
      uuid(queued.job_id); owned.add(queued.job_id); report.owned_jobs = [...owned]; save();
      assert(queued.generation_id === generation && queued.mode === 'editor_preview', 'POST scope mismatch');
      assert(posts.at(-1).body.question === question && posts.at(-1).body.mode === 'editor_preview', 'UI request changed question/mode');
      report.submissions.push({ response: queued, request_body: posts.at(-1).body, idempotency_key: posts.at(-1).key }); save();
      const actual = await terminal(queued.job_id);
      fs.writeFileSync(path.join(out, `question-${index + 1}.json`), JSON.stringify(actual, null, 2), { mode: 0o600 });
      assert(actual.job_status === 'COMPLETED' && actual.answer, 'Question did not produce a completed real answer');
      const proof = JSON.parse(command(['docker', 'compose', 'exec', '-T', 'api', 'python', '-c', referencePython], JSON.stringify(actual)));
      report.scenarios.push({ scenario: 'QUESTION_' + (index + 1), job_id: queued.job_id, question, ...proof }); save();
      if (index === 1) assert(actual.answer.status === 'INSUFFICIENT_EVIDENCE', 'Unsupported birth-date question was not insufficient; preserve result for correction');
      const postCount = posts.length, jobs = countJobs();
      await form.getByRole('button', { name: 'Soru kaydını görüntüle', exact: true }).click();
      await sleep(500); assert(posts.length === postCount && countJobs() === jobs, 'Same-question reopen created another job');
      assert(jobs === initialJobs + index + 1, 'Unexpected additional question job');
      // Earlier failed runs retain their real question records. API order is
      // ascending creation time, so this run's unique newest job is last.
      const answerCard = page.locator('article').filter({ has: page.getByRole('heading', { name: question, exact: true }) }).last();
      await answerCard.waitFor();
      await page.waitForFunction(({ question, answer }) => {
        const card = [...document.querySelectorAll('article')].filter(card =>
          [...card.querySelectorAll('h2')].some(title => title.textContent === question)).at(-1);
        return card && (answer ? card.textContent.includes(answer) : card.textContent.includes('Bu soru için kullanılabilir kaynaklardan doğrulanmış cevap çıkarılamadı.'));
      },
        { question, answer: actual.answer.answer }, { timeout: 30000 });
    }
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1100 });
      assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), 'Horizontal page overflow');
      await page.screenshot({ path: path.join(out, `questions-${width}.png`), fullPage: true });
      report.scenarios.push({ scenario: 'REAL_RESULTS_MOBILE', width, overflow: false, status: 'PASS' }); save();
    }
    idle(); assert(canonical(protectedState()) === canonical(before), 'Source/review/generation state changed');
    report.status = 'PASS'; report.quality_review_required = true; save();
  } catch (error) {
    report.status = 'FAILED'; report.error = safe(error); save(); process.exitCode = 1;
    if (page) await page.screenshot({ path: path.join(out, 'failure.png'), fullPage: true }).catch(() => {});
  } finally {
    if (context) {
      try {
        // Recover only keys observed in this run's real form requests.
        for (const key of keys) {
          const response = sql(`SELECT response FROM editor.idempotency WHERE key='${uuid(key)}'`);
          if (response?.job_id && response.generation_id === generation) owned.add(uuid(response.job_id));
        }
        for (const id of owned) if (['QUEUED', 'RUNNING'].includes(job(id)?.status)) {
          const reference = job(id);
          assert(reference.task === 'question' && reference.generation_id === generation && questions.includes(reference.payload?.question)
            && new Date(reference.created_at).getTime() >= startedAt, 'Refuse cancellation: job ownership not established');
          await api('POST', '/jobs/' + id + '/cancel', { purpose: 'validation' }, 'source-ui-cancel:' + id);
          const result = await terminal(id, 180000);
          report.cleanup.push({ job_id: id, terminal_status: result.job_status });
        }
        if (before) { report.protected_state_unchanged = canonical(protectedState()) === canonical(before); assert(report.protected_state_unchanged, 'Protected state changed'); }
      } catch (error) { report.cleanup_error = safe(error); report.status = 'FAILED'; process.exitCode = 1; }
    }
    if (browser) await browser.close(); save();
  }
  console.log(JSON.stringify({ status: report.status, evidence: out, semantic_acceptance: false }));
})().catch(error => { report.status = 'FAILED'; report.error = safe(error); save(); console.error(safe(error)); process.exitCode = 1; });
