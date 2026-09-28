import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BarChart3, Download, Loader2, NotebookPen, Plus, Send, Sparkles, Trash2, Wand2 } from 'lucide-react';
import { ENGINE_ENABLED, translationApi, type TranslationJob, type TranslationJobDetail } from '../../engine';
import { Loading, Note, Pill, btn, btnGhost, errText, field, label, nf } from '../../admin/ui';
import { dateTime } from '../../format';
import { useCan } from '../../useAdmin';
import { Kpi, KpiRow, ModuleFrame, Panel } from '../kit';
import { FileButton, LANGS, PersonField, ProgressBar, StagePill, Tabs, fmtDay, pair, paceText, pct, type PersonPick } from './parts';
import PayoutPanel from './PayoutPanel';
<<<<<<< HEAD
=======
import MemoryBank from './MemoryBank';
import { QeJobPanel } from './qe';
>>>>>>> df8a23cf40a4ba9871d18082778a298fc177604c
import TermBank from './TermBank';
import Translators from './Translators';
import { SuggestedTranslators } from './TranslatorMatch';

/** M4 Çeviri Yönetimi: çeviri işleri (kaynak, segmentler, atama, ilerleme, ZEKİ ham taslak, dosyalar),
 *  terim bankası ve çevirmen karneleri. Çevirmenin kendi ekranı /ceviri/masam, kalite raporu /ceviri/:iş/kalite. */

const TABS = { isler: 'Çeviri işleri', terimler: 'Terim bankası', bellek: 'Çeviri belleği', cevirmenler: 'Çevirmenler' } as const;
type TabKey = keyof typeof TABS;

function JobForm({ onDone, onCancel }: { onDone: (id: string) => void; onCancel: () => void }) {
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [src, setSrc] = useState('en');
  const [tgt, setTgt] = useState('tr');
  const [translator, setTranslator] = useState<PersonPick>({ username: '', name: '' });
  const [reviewer, setReviewer] = useState<PersonPick>({ username: '', name: '' });
  const [due, setDue] = useState('');
  const create = useMutation({
    mutationFn: () =>
      translationApi.createJob({
        title: title.trim(),
        author: author.trim() || undefined,
        sourceLang: src,
        targetLang: tgt,
        translator: translator.username || undefined,
        translatorName: translator.name || undefined,
        reviewer: reviewer.username || undefined,
        reviewerName: reviewer.name || undefined,
        dueDate: due || undefined,
      }),
    onSuccess: (r) => onDone(r.id),
  });
  return (
    <form
      className="space-y-2.5 rounded-2xl border border-slate-100 bg-white/85 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (title.trim() && !create.isPending) create.mutate();
      }}
    >
      <div>
        <span className={label}>Eser adı</span>
        <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} className={`${field} mt-1`} />
      </div>
      <div>
        <span className={label}>Yazar</span>
        <input value={author} onChange={(e) => setAuthor(e.target.value)} className={`${field} mt-1`} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className={label}>Kaynak dil</span>
          <select value={src} onChange={(e) => setSrc(e.target.value)} className={`${field} mt-1`}>
            {Object.entries(LANGS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className={label}>Hedef dil</span>
          <select value={tgt} onChange={(e) => setTgt(e.target.value)} className={`${field} mt-1`}>
            {Object.entries(LANGS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div>
        <span className={label}>Çevirmen</span>
        <PersonField value={translator} onChange={setTranslator} />
        <SuggestedTranslators src={src} tgt={tgt} due={due} value={translator} onPick={setTranslator} />
      </div>
      <div>
        <span className={label}>İnceleyen</span>
        <PersonField value={reviewer} onChange={setReviewer} />
      </div>
      <label className="block">
        <span className={label}>Teslim tarihi</span>
        <input type="date" value={due} onChange={(e) => setDue(e.target.value)} className={`${field} mt-1`} />
      </label>
      {src === tgt && <Note tone="warn">Kaynak ve hedef dil aynı olamaz.</Note>}
      {create.error && <Note tone="err">{errText(create.error, 'İş açılamadı.')}</Note>}
      <div className="flex gap-1.5">
        <button type="submit" disabled={!title.trim() || src === tgt || create.isPending} className={`${btn} flex-1 bg-canvas-violet text-white`}>
          {create.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : 'İşi aç'}
        </button>
        <button type="button" className={btnGhost} onClick={onCancel}>
          Vazgeç
        </button>
      </div>
    </form>
  );
}

function JobList({ jobs, selected, onSelect, canManage }: { jobs: TranslationJob[]; selected: string | null; onSelect: (id: string) => void; canManage: boolean }) {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  return (
    <Panel>
      <div className="flex items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">Çeviri işleri</h2>
        <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{nf.format(jobs.length)}</span>
      </div>
      {canManage && (
        <div className="mt-2">
          {open ? (
            <JobForm
              onCancel={() => setOpen(false)}
              onDone={async (id) => {
                setOpen(false);
                await qc.invalidateQueries({ queryKey: ['translation', 'jobs'] });
                onSelect(id);
              }}
            />
          ) : (
            <button type="button" className={`${btnGhost} w-full`} onClick={() => setOpen(true)}>
              <Plus aria-hidden className="h-4 w-4" />
              Yeni çeviri işi
            </button>
          )}
        </div>
      )}
      {!jobs.length && (
        <p className="mt-3 px-1 text-[12px] leading-snug text-canvas-muted">
          {canManage ? 'Henüz çeviri işi yok. Yeni bir iş açıp kaynak metni yükleyin.' : 'Size açık bir çeviri işi yok.'}
        </p>
      )}
      <ul className="mt-2 space-y-1.5">
        {jobs.map((j) => (
          <li key={j.id}>
            <button
              type="button"
              onClick={() => onSelect(j.id)}
              aria-pressed={selected === j.id}
              className={`w-full rounded-2xl border px-3 py-2.5 text-left text-[12.5px] transition-colors duration-150 ${
                selected === j.id ? 'border-canvas-violet bg-white' : 'border-slate-100 bg-white/85 hover:bg-white'
              }`}
            >
              <span className="flex items-start justify-between gap-2">
                <span className="min-w-0 break-words font-extrabold leading-snug">{j.title}</span>
                <StagePill stage={j.stage} />
              </span>
              <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">
                {pair(j)}
                {j.translatorName || j.translator ? ` · ${j.translatorName || j.translator}` : ' · çevirmen atanmadı'}
              </span>
              {j.words.total > 0 && (
                <span className="mt-1.5 block">
                  <ProgressBar done={j.words.done} approved={j.words.approved} total={j.words.total} label={`${j.title} ilerleme`} />
                </span>
              )}
              <span className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] font-semibold">
                {j.words.total > 0 && (
                  <span className="font-mono tabular-nums">
                    %{pct(j.words.done, j.words.total)} çevrildi · %{pct(j.words.approved, j.words.total)} onaylı
                  </span>
                )}
                {j.dueDate && <span className="text-canvas-muted">teslim {fmtDay(j.dueDate)}</span>}
                {j.pace.overdue ? <Pill tone="err">Teslim geçti</Pill> : j.pace.late ? <Pill tone="warn">Gecikme riski</Pill> : null}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function Assignment({ job, onSaved }: { job: TranslationJobDetail; onSaved: () => void }) {
  const [translator, setTranslator] = useState<PersonPick>({ username: job.translator ?? '', name: job.translatorName ?? '' });
  const [reviewer, setReviewer] = useState<PersonPick>({ username: job.reviewer ?? '', name: job.reviewerName ?? '' });
  const [due, setDue] = useState(job.dueDate ?? '');
  const [note, setNote] = useState(job.note ?? '');
  useEffect(() => {
    setTranslator({ username: job.translator ?? '', name: job.translatorName ?? '' });
    setReviewer({ username: job.reviewer ?? '', name: job.reviewerName ?? '' });
    setDue(job.dueDate ?? '');
    setNote(job.note ?? '');
  }, [job.id, job.translator, job.translatorName, job.reviewer, job.reviewerName, job.dueDate, job.note]);
  const save = useMutation({
    mutationFn: () =>
      translationApi.updateJob(job.id, {
        translator: translator.username,
        translatorName: translator.name,
        reviewer: reviewer.username,
        reviewerName: reviewer.name,
        dueDate: due,
        note,
      }),
    onSuccess: onSaved,
  });
  // Serbest çalışan önerisi yalnız adı doldurur (kullanıcı adı boş kalır): ad değişikliği de kaydedilecek değişikliktir.
  const dirty =
    translator.username !== (job.translator ?? '') ||
    translator.name !== (job.translatorName ?? '') ||
    reviewer.username !== (job.reviewer ?? '') ||
    due !== (job.dueDate ?? '') ||
    note !== (job.note ?? '');
  return (
    <form
      className="grid gap-2.5 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <div>
        <span className={label}>Çevirmen</span>
        <PersonField value={translator} onChange={setTranslator} />
      </div>
      <div>
        <span className={label}>İnceleyen</span>
        <PersonField value={reviewer} onChange={setReviewer} />
      </div>
      <div className="sm:col-span-2">
        <SuggestedTranslators
          src={job.sourceLang}
          tgt={job.targetLang}
          words={Math.max(0, job.words.total - job.words.done)}
          due={due}
          jobId={job.id}
          value={translator}
          onPick={setTranslator}
        />
      </div>
      <label className="block">
        <span className={label}>Teslim tarihi</span>
        <input type="date" value={due} onChange={(e) => setDue(e.target.value)} className={`${field} mt-1`} />
      </label>
      <label className="block sm:row-span-2">
        <span className={label}>Çevirmene not</span>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} className={`${field} mt-1 resize-y`} placeholder="Üslup, hedef okur, dikkat edilecekler" />
      </label>
      <div className="flex items-end gap-2">
        <button type="submit" disabled={!dirty || save.isPending} className={`${btn} bg-canvas-violet text-white`}>
          {save.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : null}
          Kaydet
        </button>
        {save.isSuccess && !dirty && <span className="pb-2 text-[11.5px] font-semibold text-emerald-700">Kaydedildi</span>}
      </div>
      {save.error && (
        <div className="sm:col-span-2">
          <Note tone="err">{errText(save.error, 'Kaydedilemedi.')}</Note>
        </div>
      )}
    </form>
  );
}

function Candidates({ job, canTerm }: { job: TranslationJobDetail; canTerm: boolean }) {
  const q = useQuery({ queryKey: ['translation', 'candidates', job.id, job.source?.version], queryFn: () => translationApi.candidates(job.id), enabled: !!job.source });
  const qc = useQueryClient();
  const [openTerm, setOpenTerm] = useState<string | null>(null);
  const [target, setTarget] = useState('');
  const [jobOnly, setJobOnly] = useState(false);
  const add = useMutation({
    mutationFn: (term: string) =>
      canTerm
        ? translationApi.createTerm(
            jobOnly
              ? { source: term, target: target.trim(), jobId: job.id }
              : { source: term, target: target.trim(), sourceLang: job.sourceLang, targetLang: job.targetLang },
          )
        : translationApi.proposeTerm({ source: term, target: target.trim(), jobId: job.id }),
    onSuccess: async () => {
      setOpenTerm(null);
      setTarget('');
      await qc.invalidateQueries({ queryKey: ['translation', 'candidates', job.id] });
      await qc.invalidateQueries({ queryKey: ['translation', 'terms'] });
    },
  });
  const items = q.data?.items ?? [];
  if (!job.source) return null;
  return (
    <details className="rounded-2xl border border-slate-100 bg-white/85 p-3">
      <summary className="cursor-pointer select-none text-[12.5px] font-extrabold">
        Terim adayları {q.data ? <span className="font-mono text-[11px] font-bold text-canvas-muted">({nf.format(items.length)})</span> : null}
      </summary>
      <p className="mt-1.5 text-[11.5px] leading-snug text-canvas-muted">
        Kaynakta cümle ortasında büyük harfle en az üç kez geçen ve bankada olmayan adlar. Çeviri boyunca aynı yazılması gerekir; karşılığını girip bankaya ekleyin.
      </p>
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Adaylar okunamadı.')}</Note>}
      {q.data && !items.length && <p className="mt-2 text-[12px] text-canvas-muted">Aday yok.</p>}
      <ul className="mt-2 space-y-1.5">
        {items.map((c) => (
          <li key={c.term} className="rounded-xl border border-slate-100 bg-white px-2.5 py-2 text-[12px]">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-bold">
                {c.term} <span className="font-mono text-[11px] font-semibold text-canvas-muted">{nf.format(c.count)} kez</span>
              </span>
              {openTerm !== c.term && (
                <button type="button" className={`${btnGhost} min-h-9 px-2.5 py-1 text-[11.5px]`} onClick={() => { setOpenTerm(c.term); setTarget(''); }}>
                  <Plus aria-hidden className="h-3.5 w-3.5" />
                  {canTerm ? 'Bankaya ekle' : 'Öner'}
                </button>
              )}
            </div>
            <p className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-canvas-muted">{c.example}</p>
            {openTerm === c.term && (
              <form
                className="mt-2 flex flex-wrap items-end gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (target.trim()) add.mutate(c.term);
                }}
              >
                <label className="min-w-[10rem] flex-1">
                  <span className={label}>{LANGS[job.targetLang] ?? job.targetLang} karşılığı</span>
                  <input autoFocus value={target} onChange={(e) => setTarget(e.target.value)} className={`${field} mt-1`} />
                </label>
                {canTerm && (
                  <label className="flex min-h-11 items-center gap-1.5 text-[11.5px] font-semibold sm:min-h-9">
                    <input type="checkbox" checked={jobOnly} onChange={(e) => setJobOnly(e.target.checked)} />
                    Yalnız bu işte
                  </label>
                )}
                <button type="submit" disabled={!target.trim() || add.isPending} className={`${btn} bg-canvas-violet text-white`}>
                  {canTerm ? 'Ekle' : 'Öner'}
                </button>
                <button type="button" className={btnGhost} onClick={() => setOpenTerm(null)}>
                  Vazgeç
                </button>
                {add.error && (
                  <div className="w-full">
                    <Note tone="err">{errText(add.error, 'Eklenemedi.')}</Note>
                  </div>
                )}
              </form>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

function JobPanel({ jobId, onDeleted }: { jobId: string; onDeleted: () => void }) {
  const qc = useQueryClient();
  const canManage = useCan('ceviri.yonet');
  const canTerm = useCan('ceviri.terim');
  const canExport = useCan('veri.disa-aktar');
  const canFreelance = useCan('serbest.yonet');
  const q = useQuery({
    queryKey: ['translation', 'job', jobId],
    queryFn: () => translationApi.job(jobId),
    enabled: ENGINE_ENABLED,
    // ZEKİ taslağı arka planda sürerken kendiliğinden tazelenir.
    refetchInterval: (query) => (query.state.data?.draft.state === 'calisiyor' ? 5000 : false),
  });
  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ['translation', 'job', jobId] });
    await qc.invalidateQueries({ queryKey: ['translation', 'jobs'] });
  };
  const [notice, setNotice] = useState<string | null>(null);
  const draft = useMutation({ mutationFn: () => translationApi.draft(jobId, null), onSuccess: refresh });
  const toRed = useMutation({ mutationFn: () => translationApi.toRedaction(jobId), onSuccess: refresh });
  const del = useMutation({ mutationFn: () => translationApi.deleteJob(jobId), onSuccess: async () => { await qc.invalidateQueries({ queryKey: ['translation', 'jobs'] }); onDeleted(); } });
  const j = q.data;
  const err = errText(q.error || draft.error || toRed.error || del.error, 'Çeviri işi okunamadı.');
  useEffect(() => setNotice(null), [jobId]);
  if (!j) return <Panel>{err ? <Note tone="err">{err}</Note> : <Loading />}</Panel>;
  const manage = j.roles.manage && canManage;
  const open = j.segments.bos + j.segments.taslak;
  const drafting = j.draft.state === 'calisiyor';

  return (
    <div className="space-y-3 lg:space-y-4">
      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="break-words text-[18px] font-extrabold leading-tight tracking-tight">{j.title}</h2>
            <p className="mt-0.5 text-[12px] text-canvas-muted">
              {j.author ? `${j.author} · ` : ''}
              {pair(j)} · açan {j.createdBy}, {dateTime(j.createdAt)}
            </p>
          </div>
          <StagePill stage={j.stage} />
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {(j.roles.translate || j.roles.review) && j.source && (
            <Link to={`/ceviri/masam/${j.id}`} className={`${btn} bg-canvas-violet text-white`}>
              <NotebookPen aria-hidden className="h-4 w-4" />
              Çeviri masasında aç
            </Link>
          )}
          {j.source && (
            <Link to={`/ceviri/${j.id}/kalite`} className={btnGhost}>
              <BarChart3 aria-hidden className="h-4 w-4" />
              Kalite raporu
            </Link>
          )}
        </div>
        {err && (
          <div className="mt-2">
            <Note tone="err">{err}</Note>
          </div>
        )}
        {notice && (
          <div className="mt-2">
            <Note tone="ok">{notice}</Note>
          </div>
        )}

        {j.words.total > 0 && (
          <div className="mt-3 rounded-2xl border border-slate-100 bg-white/85 p-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2 text-[12px]">
              <span className="font-extrabold">İlerleme</span>
              <span className="font-mono tabular-nums text-canvas-muted">
                {nf.format(j.words.done)} / {nf.format(j.words.total)} kelime çevrildi · {nf.format(j.words.approved)} onaylı
              </span>
            </div>
            <div className="mt-2">
              <ProgressBar done={j.words.done} approved={j.words.approved} total={j.words.total} label="İş ilerlemesi" />
            </div>
            <dl className="mt-2.5 grid grid-cols-2 gap-2 text-[11.5px] sm:grid-cols-4">
              {(['bos', 'taslak', 'cevrildi', 'onaylandi'] as const).map((k) => (
                <div key={k}>
                  <dt className="text-canvas-muted">{{ bos: 'Boş', taslak: 'Taslak', cevrildi: 'Çevrildi', onaylandi: 'Onaylı' }[k]} segment</dt>
                  <dd className="font-mono text-[14px] font-bold tabular-nums">{nf.format(j.segments[k])}</dd>
                </div>
              ))}
            </dl>
            <p className={`mt-2 text-[12px] leading-snug ${j.pace.late ? 'font-semibold text-amber-700' : 'text-canvas-muted'}`}>{paceText(j, j.pace)}</p>
          </div>
        )}
      </Panel>

      {manage && (
        <Panel>
          <h3 className="px-1 text-[13px] font-extrabold">Atama</h3>
          <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">
            Çevirmen ve inceleyen portal kullanıcısıdır; işi «Çeviri masam» ekranında görür. Dışarıdan çalışan çevirmene XLIFF dosyası verilir, dönen dosya aşağıdan yüklenir.
          </p>
          <div className="mt-2.5">
            <Assignment job={j} onSaved={refresh} />
          </div>
        </Panel>
      )}

      {/* Çevirmenin serbest çalışan kaydı, kelime ücreti ve hakedişe aktarım (M8 ile bağ). */}
      {manage && canFreelance && <PayoutPanel job={j} />}

      <Panel>
        <h3 className="px-1 text-[13px] font-extrabold">Kaynak metin</h3>
        {j.source ? (
          <p className="mt-1 px-1 text-[12px] leading-snug">
            <a href={translationApi.sourceUrl(j.id)} className="font-semibold text-canvas-violet underline">
              v{j.source.version} · {j.source.filename}
            </a>{' '}
            <span className="text-canvas-muted">
              · {nf.format(j.chapters.length)} bölüm · {nf.format(j.segments.total)} segment · {nf.format(j.words.total)} kelime
            </span>
          </p>
        ) : (
          <p className="mt-1 px-1 text-[12px] leading-snug text-canvas-muted">Henüz kaynak yüklenmedi.</p>
        )}
        {manage && (
          <div className="mt-2.5 flex flex-wrap items-start gap-2">
            <FileButton
              accept=".docx,.txt,.md,.pdf"
              run={(f) => translationApi.uploadSource(j.id, f)}
              disabled={drafting}
              onDone={async (r) => {
                setNotice(
                  `Kaynak v${r.version}: ${nf.format(r.chapters)} bölüm, ${nf.format(r.segments)} segment, ${nf.format(r.words)} kelime.` +
                    (r.carried ? ` Önceki sürümden ${nf.format(r.carried)} segmentin çevirisi aynı cümleye taşındı.` : ''),
                );
                await refresh();
              }}
            >
              {j.source ? 'Yeni kaynak sürümü' : 'Kaynak yükle'}
            </FileButton>
            <p className="min-w-0 flex-1 basis-60 text-[11.5px] leading-snug text-canvas-muted">
              DOCX, TXT, MD ya da PDF. Metin paragraflara, paragraflar cümle segmentlerine bölünür; bölüm başlıkları ayrı segmenttir. Yeni sürümde aynı kalan cümlelerin çevirisi korunur.
            </p>
          </div>
        )}
      </Panel>

      {j.chapters.length > 0 && (
        <Panel>
          <h3 className="px-1 text-[13px] font-extrabold">Bölümler</h3>
          <ul className="mt-2 space-y-1.5">
            {j.chapters.map((c) => (
              <li key={c.no} className="rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12px]">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="min-w-0 break-words font-semibold leading-snug">
                    {c.no}. {c.title}
                  </span>
                  <span className="font-mono text-[11px] tabular-nums text-canvas-muted">
                    {nf.format(c.segments)} segment · {nf.format(c.words)} kelime · %{pct(c.wordsDone, c.words)}
                  </span>
                </div>
                <div className="mt-1.5">
                  <ProgressBar done={c.wordsDone} approved={0} total={c.words} label={`${c.title} ilerleme`} />
                </div>
                <p className="mt-1 text-[11px] text-canvas-muted">
                  {nf.format(c.bos)} boş · {nf.format(c.taslak)} taslak · {nf.format(c.cevrildi)} çevrildi · {nf.format(c.onaylandi)} onaylı
                </p>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {j.source && (
        <Panel>
          <h3 className="px-1 text-[13px] font-extrabold">ZEKİ ham taslak</h3>
          <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">
            Boş segmentler için terim bankasına uyan ham çeviri. ZEKİ çevirir; otomatik denetim sayı, terim, yasak karşılık ya da noktalama sorunu bulursa o cümleleri sorunun adıyla yeniden düzelttirir. Taslak hedef metne kendiliğinden yazılmaz; çevirmen segment segment kullanır ya da düzeltir.
          </p>
          {drafting && (
            <div className="mt-2">
              <Note tone="info">
                Taslak hazırlanıyor: %{pct(j.draft.done, j.draft.total)} (çeviri, sonra otomatik denetimin bulduğu sorunların düzeltilmesi).
              </Note>
            </div>
          )}
          {j.draft.state === 'bitti' && j.draft.note && (
            <div className="mt-2">
              <Note tone="ok">{j.draft.note}</Note>
            </div>
          )}
          {j.draft.state === 'hata' && j.draft.note && (
            <div className="mt-2">
              <Note tone="err">{j.draft.note}</Note>
            </div>
          )}
          {manage && (
            <div className="mt-2.5">
              <button type="button" disabled={drafting || draft.isPending || !open} onClick={() => draft.mutate()} className={`${btn} bg-canvas-violet text-white`}>
                {drafting || draft.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                {drafting ? 'Hazırlanıyor…' : 'Boş segmentlere taslak hazırla'}
              </button>
            </div>
          )}
        </Panel>
      )}

      {j.source && <QeJobPanel jobId={j.id} />}

      {j.source && (
        <Panel>
          <h3 className="px-1 text-[13px] font-extrabold">Dosyalar</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            <a href={translationApi.xliffUrl(j.id)} className={btnGhost}>
              <Download aria-hidden className="h-4 w-4" />
              XLIFF indir
            </a>
            {j.roles.translate && (
              <FileButton
                tone="ghost"
                accept=".xlf,.xliff,.sdlxliff,.mqxliff"
                run={(f) => translationApi.importXliff(j.id, f)}
                onDone={async (r) => {
                  setNotice(
                    `XLIFF: ${nf.format(r.updated)} segment güncellendi (${nf.format(r.confirmed)} çevrildi olarak)` +
                      (r.locked ? `, ${nf.format(r.locked)} onaylı segmente dokunulmadı` : '') +
                      (r.unknown ? `, ${nf.format(r.unknown)} segment bu işe ait değil` : '') +
                      '.',
                  );
                  await refresh();
                }}
              >
                XLIFF yükle
              </FileButton>
            )}
            {canExport && (
              <a href={translationApi.docxUrl(j.id)} className={btnGhost}>
                <Download aria-hidden className="h-4 w-4" />
                Çeviri (DOCX)
              </a>
            )}
          </div>
          <p className="mt-2 px-1 text-[11.5px] leading-snug text-canvas-muted">
            XLIFF 1.2: Trados, memoQ, OmegaT ve Phrase açar. Dönen dosyada yalnız bu işin segmentleri okunur; onaylı segmentlere dokunulmaz. DOCX'te çevrilmemiş segment «[ÇEVRİLMEDİ]» ile işaretlenir.
          </p>
          {manage && (
            <div className="mt-3 rounded-2xl border border-slate-100 bg-white/85 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="min-w-0 text-[12px] leading-snug">
                  <span className="font-extrabold">Redaksiyona aktar</span>
                  <span className="block text-[11.5px] text-canvas-muted">
                    {open
                      ? `${nf.format(open)} segment henüz çevrilmedi; çeviri bitince aktarılır.`
                      : j.workId
                        ? 'Daha önce aktarıldı; yeniden aktarmak redaksiyonda yeni metin sürümü açar.'
                        : 'Çeviri, M3 Redaksiyon\'a eser dosyası ve metin sürümü olarak gider.'}
                  </span>
                </span>
                <button type="button" disabled={!!open || toRed.isPending} onClick={() => toRed.mutate()} className={`${btn} bg-canvas-mint/15 text-emerald-700`}>
                  {toRed.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Send aria-hidden className="h-4 w-4" />}
                  Aktar
                </button>
              </div>
              {toRed.data && (
                <p className="mt-2 text-[12px]">
                  Metin sürümü {toRed.data.version} açıldı ({nf.format(toRed.data.chapters)} bölüm).{' '}
                  <Link to="/redaksiyon" className="font-bold text-canvas-violet underline">
                    Redaksiyona git
                  </Link>
                </p>
              )}
            </div>
          )}
        </Panel>
      )}

      <Candidates job={j} canTerm={canTerm} />

      {manage && (
        <div className="flex justify-end px-1">
          <button
            type="button"
            disabled={del.isPending || drafting}
            className={`${btnGhost} text-rose-700`}
            onClick={() => {
              if (window.confirm(`«${j.title}» çeviri işi, bütün segmentleri, işe özel terimleri ve dosyalarıyla silinsin mi? Bu geri alınamaz.`)) del.mutate();
            }}
          >
            <Trash2 aria-hidden className="h-4 w-4" />
            İşi sil
          </button>
        </div>
      )}
    </div>
  );
}

function Jobs() {
  const [params, setParams] = useSearchParams();
  const canManage = useCan('ceviri.yonet');
  const jobs = useQuery({ queryKey: ['translation', 'jobs'], queryFn: () => translationApi.jobs(false), enabled: ENGINE_ENABLED });
  const items = jobs.data?.items ?? [];
  const selected = params.get('is');
  const setSelected = (id: string | null) =>
    setParams(
      (p) => {
        const n = new URLSearchParams(p);
        if (id) n.set('is', id);
        else n.delete('is');
        return n;
      },
      { replace: true },
    );
  useEffect(() => {
    if (!selected && items.length) setSelected(items[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, items.length]);
  const active = items.filter((j) => j.stage === 'ceviri' || j.stage === 'inceleme');
  const words = active.reduce((a, j) => a + j.words.total, 0);
  const done = active.reduce((a, j) => a + j.words.done, 0);
  const late = active.filter((j) => j.pace.late).length;
  const waiting = active.reduce((a, j) => a + j.segments.cevrildi, 0);

  return (
    <>
      {jobs.error && <Note tone="err">{errText(jobs.error, 'Çeviri işleri okunamadı.')}</Note>}
      {jobs.data && items.length > 0 && (
        <KpiRow>
          <Kpi label="Süren iş" value={nf.format(active.length)} help={`${nf.format(items.length - active.length)} iş bitti ya da kaynak bekliyor`} />
          <Kpi label="Çevrilen kelime" value={`%${pct(done, words)}`} help={`${nf.format(done)} / ${nf.format(words)} (süren işler)`} />
          <Kpi label="Gecikme riski" value={nf.format(late)} help="Son 14 günün hızıyla teslime yetişmeyen" />
          <Kpi label="İnceleme bekleyen" value={nf.format(waiting)} help="Çevrildi, onay bekleyen segment" />
        </KpiRow>
      )}
      <div className="grid gap-3 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)] lg:items-start lg:gap-4">
        {jobs.isLoading ? <Panel><Loading /></Panel> : <JobList jobs={items} selected={selected} onSelect={setSelected} canManage={canManage} />}
        {selected ? (
          <JobPanel key={selected} jobId={selected} onDeleted={() => setSelected(null)} />
        ) : (
          <Panel>
            <p className="py-10 text-center text-[12.5px] leading-snug text-canvas-muted">
              {canManage ? 'Soldan bir çeviri işi seçin ya da yeni bir tane açın.' : 'Soldan bir çeviri işi seçin.'}
            </p>
          </Panel>
        )}
      </div>
    </>
  );
}

export default function TranslationScreen() {
  const [params, setParams] = useSearchParams();
  const tab: TabKey = (params.get('sekme') as TabKey) in TABS ? (params.get('sekme') as TabKey) : 'isler';
  return (
    <ModuleFrame
      route="/ceviri"
      crumb="Çeviri"
      title="Çeviri yönetimi"
      lead="Kaynak metin cümle segmentlerine bölünür; çevirmen kendi ekranında terim bankası, çeviri belleği ve otomatik denetimle çalışır, inceleyen onaylar ve hataları işaretler. Kalite raporu işin gerçek kayıtlarından hesaplanır."
      source="Çeviri masası"
      presence="Kaynak: çeviri kayıtları"
      aside={<Tabs tabs={TABS} value={tab} label="Çeviri bölümü" onChange={(k) => setParams({ sekme: k }, { replace: true })} />}
    >
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {tab === 'isler' && <Jobs />}
      {tab === 'terimler' && <TermBank />}
      {tab === 'bellek' && <MemoryBank />}
      {tab === 'cevirmenler' && <Translators />}
      {tab === 'isler' && (
        <p className="px-1 text-[11.5px] leading-snug text-canvas-muted">
          <Wand2 aria-hidden className="mr-1 inline h-3.5 w-3.5" />
          CRM'deki çevirmen kayıtları ve çevirdikleri kitaplar:{' '}
          <Link to="/kisiler?rol=cevirmen" className="font-bold text-canvas-violet underline">
            Çevirmenler
          </Link>
          .
        </p>
      )}
    </ModuleFrame>
  );
}
