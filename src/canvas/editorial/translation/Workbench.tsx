import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BarChart3,
  BookMarked,
  Check,
  ClipboardCopy,
  Download,
  History,
  Loader2,
  Plus,
  RotateCcw,
  Sparkles,
  Trash2,
  Undo2,
} from 'lucide-react';
import {
  ENGINE_ENABLED,
  translationApi,
  type SegmentDetail,
  type SegmentRow,
  type TranslationJob,
  type TranslationJobDetail,
} from '../../engine';
import { Loading, Note, Pill, btn, btnGhost, errText, field, label, nf } from '../../admin/ui';
import { dateTime } from '../../format';
import { useCan } from '../../useAdmin';
import { useTimasSession } from '../../TimasSession';
import { ModuleFrame, Panel, useDebounced } from '../kit';
import { CATEGORY, FileButton, ProgressBar, SEG, SEVERITY, StagePill, dirOf, fmtDay, langName, pair, paceText, pct, useWide } from './parts';

/** Çeviri masam: çevirmenin ve inceleyenin kendi ekranı. Sol: bölümün segmentleri (kaynak | hedef); etkin
 *  segmentte yazılır. Sağ (telefonda segmentin altında): terimler, çeviri belleği, ZEKİ taslağı, otomatik
 *  denetim, inceleme hataları ve bağlam. Kısayollar: ⌘/Ctrl+Enter onayla ve sonrakine geç, Alt+↓/↑ gezin.
 *  Çeviri kipinde yazılan metin 1,5 sn sonra taslak olarak kendiliğinden kaydedilir. */

type Mode = 'ceviri' | 'inceleme';
const FILTER_LABEL: Record<string, string> = {
  hepsi: 'Bütün segmentler',
  bos: 'Boş',
  taslak: 'Taslak',
  cevrildi: 'Çevrildi (onay bekliyor)',
  onaylandi: 'Onaylı',
  sorunlu: 'Denetim uyarısı olan',
  hatali: 'İnceleme hatası olan',
  taslakli: 'ZEKİ taslağı bekleyen',
};
const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);
const MOD = isMac ? '⌘' : 'Ctrl';

function MyJobs({ me }: { me: string }) {
  const q = useQuery({ queryKey: ['translation', 'jobs', 'mine'], queryFn: () => translationApi.jobs(true), enabled: ENGINE_ENABLED });
  const items = q.data?.items ?? [];
  return (
    <Panel>
      <h2 className="px-1 text-[13px] font-extrabold">Size atanmış çeviri işleri</h2>
      {q.error && <Note tone="err">{errText(q.error, 'İşler okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {q.data && !items.length && (
        <p className="mt-2 px-1 text-[12.5px] leading-snug text-canvas-muted">
          Şu an size atanmış çeviri ya da inceleme işi yok. İş, «Çeviri» ekranında çevirmen ya da inceleyen olarak adınız yazılınca burada görünür.
        </p>
      )}
      <ul className="mt-2 grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
        {items.map((j) => {
          const reviewer = j.reviewer === me;
          const translator = j.translator === me;
          return (
            <li key={j.id}>
              <Link
                to={`/ceviri/masam/${j.id}`}
                className="block rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px] transition-colors duration-150 hover:bg-white"
              >
                <span className="flex items-start justify-between gap-2">
                  <span className="min-w-0 break-words font-extrabold leading-snug">{j.title}</span>
                  <StagePill stage={j.stage} />
                </span>
                <span className="mt-0.5 block text-[11px] text-canvas-muted">
                  {pair(j)} · {translator && reviewer ? 'çevirmen ve inceleyen' : translator ? 'çevirmen' : 'inceleyen'}
                </span>
                {j.words.total > 0 && (
                  <span className="mt-2 block">
                    <ProgressBar done={j.words.done} approved={j.words.approved} total={j.words.total} label={`${j.title} ilerleme`} />
                  </span>
                )}
                <span className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] font-semibold">
                  <span className="font-mono tabular-nums">
                    {translator ? `${nf.format(j.segments.bos + j.segments.taslak)} segment çevrilecek` : `${nf.format(j.segments.cevrildi)} segment onay bekliyor`}
                  </span>
                  {j.dueDate && <span className="text-canvas-muted">teslim {fmtDay(j.dueDate)}</span>}
                  {j.pace.overdue ? <Pill tone="err">Teslim geçti</Pill> : j.pace.late ? <Pill tone="warn">Gecikme riski</Pill> : null}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function Section({ title, icon, children, count }: { title: string; icon: ReactNode; children: ReactNode; count?: number }) {
  return (
    <section className="rounded-2xl border border-slate-100 bg-white/85 p-3">
      <h3 className="flex items-center gap-1.5 text-[12px] font-extrabold">
        {icon}
        {title}
        {count != null && <span className="font-mono text-[11px] font-bold text-canvas-muted">{nf.format(count)}</span>}
      </h3>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function ProposeTerm({ jobId, canTerm, job, onDone }: { jobId: string; canTerm: boolean; job: TranslationJob; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [s, setS] = useState('');
  const [t, setT] = useState('');
  const m = useMutation({
    mutationFn: () =>
      canTerm
        ? translationApi.createTerm({ source: s.trim(), target: t.trim(), sourceLang: job.sourceLang, targetLang: job.targetLang })
        : translationApi.proposeTerm({ source: s.trim(), target: t.trim(), jobId }),
    onSuccess: () => {
      setOpen(false);
      setS('');
      setT('');
      onDone();
    },
  });
  if (!open)
    return (
      <button type="button" className="mt-2 inline-flex min-h-9 items-center gap-1 text-[11.5px] font-bold text-canvas-violet hover:underline" onClick={() => setOpen(true)}>
        <Plus aria-hidden className="h-3.5 w-3.5" />
        {canTerm ? 'Terim ekle' : 'Terim öner'}
      </button>
    );
  return (
    <form
      className="mt-2 space-y-1.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (s.trim() && t.trim()) m.mutate();
      }}
    >
      <input value={s} onChange={(e) => setS(e.target.value)} placeholder={`${langName(job.sourceLang)} terim`} className={field} />
      <input value={t} onChange={(e) => setT(e.target.value)} placeholder={`${langName(job.targetLang)} karşılık`} className={field} />
      {m.error && <Note tone="err">{errText(m.error, 'Eklenemedi.')}</Note>}
      <div className="flex gap-1.5">
        <button type="submit" disabled={!s.trim() || !t.trim() || m.isPending} className={`${btn} bg-canvas-violet text-white`}>
          {canTerm ? 'Ekle' : 'Öner'}
        </button>
        <button type="button" className={btnGhost} onClick={() => setOpen(false)}>
          Vazgeç
        </button>
      </div>
      {!canTerm && <p className="text-[11px] leading-snug text-canvas-muted">Öneri terim bankasına «aday» olarak düşer; yetkili kişi onaylayınca denetime girer.</p>}
    </form>
  );
}

function ErrorForm({ segId, onDone }: { segId: string; onDone: () => void }) {
  const [category, setCategory] = useState('anlam');
  const [severity, setSeverity] = useState('kucuk');
  const [note, setNote] = useState('');
  const m = useMutation({
    mutationFn: () => translationApi.addError(segId, { category, severity, note: note.trim() || undefined }),
    onSuccess: () => {
      setNote('');
      onDone();
    },
  });
  return (
    <form
      className="mt-2 space-y-1.5"
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate();
      }}
    >
      <div className="grid grid-cols-2 gap-1.5">
        <label className="block">
          <span className={label}>Kategori</span>
          <select value={category} onChange={(e) => setCategory(e.target.value)} className={`${field} mt-1`}>
            {Object.entries(CATEGORY).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className={label}>Ağırlık</span>
          <select value={severity} onChange={(e) => setSeverity(e.target.value)} className={`${field} mt-1`}>
            {Object.entries(SEVERITY).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Açıklama (isteğe bağlı)" className={field} />
      {m.error && <Note tone="err">{errText(m.error, 'Hata kaydedilemedi.')}</Note>}
      <button type="submit" disabled={m.isPending} className={`${btnGhost} w-full`}>
        <Plus aria-hidden className="h-4 w-4" />
        Hata işaretle
      </button>
    </form>
  );
}

function Aside({
  d,
  job,
  mode,
  canTerm,
  onUse,
  onInsert,
  refresh,
}: {
  d: SegmentDetail | undefined;
  job: TranslationJobDetail;
  mode: Mode;
  canTerm: boolean;
  onUse: (text: string) => void;
  onInsert: (text: string) => void;
  refresh: () => void;
}) {
  const delErr = useMutation({ mutationFn: (id: string) => translationApi.deleteError(id), onSuccess: refresh });
  if (!d) return <Loading />;
  const editable = mode === 'ceviri' ? d.roles.translate && d.status !== 'onaylandi' : d.roles.review;
  const tgtDir = dirOf(job.targetLang);
  return (
    <div className="space-y-2">
      <Section title="Terimler" icon={<BookMarked aria-hidden className="h-4 w-4 text-canvas-violet" />} count={d.terms.length}>
        {!d.terms.length && <p className="text-[11.5px] text-canvas-muted">Bu segmentte bankadaki bir terim geçmiyor.</p>}
        <ul className="space-y-1.5">
          {d.terms.map((t) => (
            <li key={t.id} className="text-[12px] leading-snug">
              <div className="flex items-start justify-between gap-2">
                <span className="min-w-0 break-words">
                  <span className="font-bold">{t.source}</span> → <span dir={tgtDir}>{t.target || '—'}</span>
                  {t.status === 'aday' && <span className="ml-1 text-[10.5px] font-bold uppercase text-amber-700">aday</span>}
                </span>
                {t.status === 'onayli' && t.target && (d.target ? (t.ok ? <Pill tone="ok">Var</Pill> : <Pill tone="warn">Yok</Pill>) : null)}
              </div>
              {t.forbidden.length > 0 && <p className="text-[11px] text-rose-700">Kullanılmaz: {t.forbidden.join(', ')}</p>}
              {t.note && <p className="text-[11px] text-canvas-muted">{t.note}</p>}
              {editable && t.target && (
                <button type="button" className="mt-0.5 min-h-8 text-[11px] font-bold text-canvas-violet hover:underline" onClick={() => onInsert(t.target.split('|')[0].trim())}>
                  Metne ekle
                </button>
              )}
            </li>
          ))}
        </ul>
        <ProposeTerm jobId={job.id} job={job} canTerm={canTerm} onDone={refresh} />
      </Section>

      {d.draft && (
        <Section title="ZEKİ taslağı" icon={<Sparkles aria-hidden className="h-4 w-4 text-canvas-violet" />}>
          <p dir={tgtDir} className="whitespace-pre-wrap text-[12.5px] leading-relaxed">
            {d.draft}
          </p>
          {editable && (
            <button type="button" className={`${btnGhost} mt-2 min-h-9 px-2.5`} onClick={() => onUse(d.draft ?? '')}>
              Taslağı kullan
            </button>
          )}
          <p className="mt-1 text-[11px] text-canvas-muted">Makine taslağıdır; olduğu gibi onaylamadan önce okuyun.</p>
        </Section>
      )}

      <Section title="Çeviri belleği" icon={<History aria-hidden className="h-4 w-4 text-canvas-violet" />} count={d.memory.length}>
        {!d.memory.length && <p className="text-[11.5px] text-canvas-muted">Bu dil çiftinde benzer (%70+) çevrilmiş cümle yok.</p>}
        <ul className="space-y-2">
          {d.memory.map((m, i) => (
            <li key={i} className="text-[12px] leading-snug">
              <div className="flex items-center gap-1.5">
                <Pill tone={m.score === 100 ? 'ok' : 'violet'}>%{m.score}</Pill>
                <span className="min-w-0 truncate text-[11px] text-canvas-muted">{m.sameJob ? 'bu iş' : m.job}</span>
              </div>
              <p className="mt-0.5 text-canvas-muted">{m.source}</p>
              <p dir={tgtDir} className="font-semibold">
                {m.target}
              </p>
              {editable && (
                <button type="button" className="min-h-8 text-[11px] font-bold text-canvas-violet hover:underline" onClick={() => onUse(m.target)}>
                  Kullan
                </button>
              )}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Otomatik denetim" icon={<AlertTriangle aria-hidden className="h-4 w-4 text-amber-600" />} count={d.issues.length}>
        {!d.target ? (
          <p className="text-[11.5px] text-canvas-muted">Hedef yazılınca denetlenir.</p>
        ) : !d.issues.length ? (
          <p className="text-[11.5px] font-semibold text-emerald-700">Uyarı yok.</p>
        ) : (
          <ul className="space-y-1 text-[12px] leading-snug">
            {d.issues.map((x, i) => (
              <li key={i}>
                <span className="font-bold">{ISSUE[x.code] ?? x.code}:</span> {x.text}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-1 text-[11px] text-canvas-muted">Kayıtlı metne bakar; kaydedince yenilenir.</p>
      </Section>

      {(d.errorList.length > 0 || (mode === 'inceleme' && d.roles.review && d.status !== 'bos')) && (
        <Section title="İnceleme hataları" icon={<AlertTriangle aria-hidden className="h-4 w-4 text-rose-600" />} count={d.errorList.length}>
          <ul className="space-y-1.5">
            {d.errorList.map((x) => (
              <li key={x.id} className="flex items-start justify-between gap-2 text-[12px] leading-snug">
                <span className="min-w-0">
                  <span className="font-bold">{CATEGORY[x.category] ?? x.category}</span>{' '}
                  <Pill tone={SEVERITY[x.severity]?.tone ?? 'muted'}>{SEVERITY[x.severity]?.label ?? x.severity}</Pill>
                  {x.note && <span className="block text-canvas-muted">{x.note}</span>}
                  <span className="block text-[10.5px] text-canvas-muted">
                    {x.by} · {dateTime(x.at)}
                  </span>
                </span>
                {mode === 'inceleme' && d.roles.review && (
                  <button type="button" aria-label="Hatayı kaldır" disabled={delErr.isPending} onClick={() => delErr.mutate(x.id)} className={`${btnGhost} min-h-8 px-2`}>
                    <Trash2 aria-hidden className="h-3.5 w-3.5" />
                  </button>
                )}
              </li>
            ))}
          </ul>
          {mode === 'inceleme' && d.roles.review && d.status !== 'bos' && <ErrorForm segId={d.id} onDone={refresh} />}
        </Section>
      )}

      {d.context.length > 0 && (
        <details className="rounded-2xl border border-slate-100 bg-white/85 p-3">
          <summary className="cursor-pointer select-none text-[12px] font-extrabold">Bağlam (önceki ve sonraki cümleler)</summary>
          <ul className="mt-2 space-y-1.5 text-[11.5px] leading-snug">
            {d.context.map((c) => (
              <li key={c.no} className={c.no < d.no ? '' : 'border-t border-slate-100 pt-1.5'}>
                <span className="font-mono text-[10.5px] text-canvas-muted">{c.no}</span> {c.source}
                {c.target && (
                  <span dir={tgtDir} className="block font-semibold">
                    {c.target}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

const ISSUE: Record<string, string> = {
  sayi: 'Sayı',
  terim: 'Terim',
  yasak: 'Yasak karşılık',
  noktalama: 'Noktalama',
  denge: 'Denge',
  baglanti: 'Bağlantı',
  bosluk: 'Boşluk',
  ayni: 'Kopya',
  tutarsiz: 'Tutarsız',
  uzunluk: 'Uzunluk',
};

function Editor({
  row,
  job,
  mode,
  wide,
  canTerm,
  onPatch,
  onNext,
  onPrev,
  asideEl,
  listKey,
}: {
  row: SegmentRow;
  job: TranslationJobDetail;
  mode: Mode;
  wide: boolean;
  canTerm: boolean;
  onPatch: (p: Partial<SegmentRow>) => void;
  onNext: () => void;
  onPrev: () => void;
  /** Masaüstünde yan panelin DOM kabı; yan panel buraya portal ile çizilir. */
  asideEl: HTMLElement | null;
  listKey: unknown[];
}) {
  const qc = useQueryClient();
  const detailKey = useMemo(() => ['translation', 'segment', row.id], [row.id]);
  const detail = useQuery({ queryKey: detailKey, queryFn: () => translationApi.segment(row.id), enabled: ENGINE_ENABLED });
  const d = detail.data;
  const [text, setText] = useState(row.target);
  const base = useRef({ target: row.target, updatedAt: row.updatedAt });
  const latest = useRef(text);
  latest.current = text;
  const area = useRef<HTMLTextAreaElement>(null);
  const translating = mode === 'ceviri';
  const canWrite = translating ? (d?.roles.translate ?? true) && row.status !== 'onaylandi' : (d?.roles.review ?? true);
  const dirty = text !== base.current.target;

  // Başkası değiştirdiyse ve yerelde yazılmamışsa sunucudaki hâle geç.
  useEffect(() => {
    const newer = d?.updatedAt && (!base.current.updatedAt || new Date(d.updatedAt) > new Date(base.current.updatedAt));
    if (d && newer && latest.current === base.current.target) {
      base.current = { target: d.target, updatedAt: d.updatedAt };
      setText(d.target);
    }
  }, [d]);

  const refreshDetail = useCallback(() => void qc.invalidateQueries({ queryKey: detailKey }), [qc, detailKey]);
  const afterWrite = useCallback(() => {
    refreshDetail();
    void qc.invalidateQueries({ queryKey: ['translation', 'job', job.id] });
    void qc.invalidateQueries({ queryKey: ['translation', 'jobs'] });
  }, [qc, job.id, refreshDetail]);

  // Kayıtlar sırayla gider: otomatik taslak kaydı sürerken «onayla» gelirse eski sürüm damgasıyla çakışmasın.
  const chain = useRef<Promise<unknown>>(Promise.resolve());
  const [pending, setPending] = useState(0);
  const [writeErr, setWriteErr] = useState<unknown>(null);
  const enqueue = useCallback(<R,>(fn: () => Promise<R>, quiet = false): Promise<R> => {
    const p = chain.current.then(fn, fn);
    chain.current = p.catch(() => undefined);
    if (!quiet) {
      setPending((n) => n + 1);
      setWriteErr(null);
      p.catch((e) => setWriteErr(e)).finally(() => setPending((n) => n - 1));
    }
    return p;
  }, []);
  const persist = useCallback(
    (status: 'taslak' | 'cevrildi', target: string, quiet = false) =>
      enqueue(async () => {
        const r = await translationApi.save(row.id, { target, status, updatedAt: base.current.updatedAt });
        base.current = { target: target.trim() ? target : '', updatedAt: r.updatedAt };
        onPatch({ target: base.current.target, status: r.status, updatedAt: r.updatedAt });
        if (r.repeatsFilled) void qc.invalidateQueries({ queryKey: listKey });
        if (quiet) {
          void qc.invalidateQueries({ queryKey: ['translation', 'job', job.id] });
          void qc.invalidateQueries({ queryKey: detailKey });
        }
        else afterWrite();
        return r;
      }, quiet),
    [enqueue, row.id, onPatch, qc, listKey, job.id, afterWrite, detailKey],
  );
  const decide = useCallback(
    (action: 'onayla' | 'geri', toTranslator?: boolean) =>
      enqueue(async () => {
        const target = latest.current;
        const r = await translationApi.review(row.id, { action, target: action === 'onayla' ? target : undefined, toTranslator });
        const status = action === 'onayla' ? 'onaylandi' : toTranslator ? 'taslak' : 'cevrildi';
        base.current = { target: action === 'onayla' ? target : base.current.target, updatedAt: r.updatedAt };
        onPatch({ status, updatedAt: r.updatedAt, target: base.current.target });
        afterWrite();
        return r;
      }),
    [enqueue, row.id, onPatch, afterWrite],
  );

  // Çeviri kipinde otomatik taslak kaydı (1,5 sn yazmaya ara verince).
  const idle = useDebounced(text, 1500);
  useEffect(() => {
    if (translating && canWrite && idle === latest.current && idle !== base.current.target) {
      void persist('taslak', idle).catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idle]);

  // Segmentten ayrılınca kaydedilmemiş metin taslak olarak yazılır (sessiz; liste önbelleği güncellenir).
  const persistRef = useRef(persist);
  persistRef.current = persist;
  useEffect(
    () => () => {
      if (translating && latest.current !== base.current.target) {
        void persistRef.current('taslak', latest.current, true).catch(() => void qc.invalidateQueries({ queryKey: listKey }));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const confirm = useCallback(async () => {
    if (!latest.current.trim()) return;
    if (translating) await persist('cevrildi', latest.current);
    else await decide('onayla');
    onNext();
  }, [translating, persist, decide, onNext]);

  const insert = (t: string) => {
    const el = area.current;
    if (!el) {
      setText((x) => (x ? `${x} ${t}` : t));
      return;
    }
    const s = el.selectionStart ?? text.length;
    const e = el.selectionEnd ?? text.length;
    const next = text.slice(0, s) + t + text.slice(e);
    setText(next);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(s + t.length, s + t.length);
    });
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      void confirm().catch(() => undefined);
    } else if (e.altKey && e.key === 'ArrowDown') {
      e.preventDefault();
      onNext();
    } else if (e.altKey && e.key === 'ArrowUp') {
      e.preventDefault();
      onPrev();
    }
  };

  const aside = <Aside d={d} job={job} mode={mode} canTerm={canTerm} onUse={(t) => setText(t)} onInsert={insert} refresh={refreshDetail} />;
  const err = writeErr || detail.error;
  const conflict = err && /değiştirildi/.test((err as Error).message ?? '');
  const srcDir = dirOf(job.sourceLang);
  const tgtDir = dirOf(job.targetLang);
  const busy = pending > 0;
  const rows = Math.min(12, Math.max(3, Math.ceil(Math.max(row.source.length, text.length) / 70) + 1));

  return (
    <div className="space-y-2">
      <p dir={srcDir} className={`whitespace-pre-wrap text-[13.5px] leading-relaxed ${row.heading ? 'font-extrabold' : ''}`}>
        {row.source}
      </p>
      <textarea
        ref={area}
        autoFocus
        dir={tgtDir}
        value={text}
        readOnly={!canWrite}
        rows={rows}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKey}
        aria-label={`${row.no}. segmentin ${langName(job.targetLang)} çevirisi`}
        placeholder={canWrite ? `${langName(job.targetLang)} çeviri` : ''}
        className={`${field} resize-y text-[14px] leading-relaxed sm:text-[13.5px] ${!canWrite ? 'bg-slate-50' : ''}`}
      />
      {mode === 'inceleme' && d && d.diff.length > 0 && (
        <p dir={tgtDir} className="rounded-xl bg-slate-50 px-2.5 py-2 text-[12px] leading-relaxed">
          <span className="mr-1 text-[10.5px] font-bold uppercase text-canvas-muted">Çevirmenden fark:</span>
          {d.diff.map((o, i) =>
            o.op === 'eq' ? (
              <span key={i}>{o.text}</span>
            ) : o.op === 'del' ? (
              <del key={i} className="bg-canvas-coral/10 decoration-canvas-coral/60">
                {o.text}
              </del>
            ) : (
              <ins key={i} className="bg-canvas-mint/15 font-semibold no-underline">
                {o.text}
              </ins>
            ),
          )}
        </p>
      )}
      {err && (
        <Note tone="err">
          {errText(err, 'Kaydedilemedi.')}{' '}
          {conflict && (
            <button
              type="button"
              className="font-bold underline"
              onClick={async () => {
                const fresh = await detail.refetch();
                if (fresh.data) {
                  base.current = { target: fresh.data.target, updatedAt: fresh.data.updatedAt };
                  setText(fresh.data.target);
                  setWriteErr(null);
                }
              }}
            >
              Güncel hâli yükle
            </button>
          )}
        </Note>
      )}
      <div className="flex flex-wrap items-center gap-1.5">
        {translating ? (
          <>
            <button type="button" disabled={!canWrite || busy || !text.trim()} onClick={() => void confirm().catch(() => undefined)} className={`${btn} bg-canvas-violet text-white`}>
              {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Check aria-hidden className="h-4 w-4" />}
              Onayla ve geç
            </button>
            <button type="button" disabled={!canWrite} onClick={() => setText(row.source)} className={btnGhost} title="Kaynağı hedefe kopyala (özel adlar, sayılar)">
              <ClipboardCopy aria-hidden className="h-4 w-4" />
              Kaynağı kopyala
            </button>
          </>
        ) : (
          <>
            <button type="button" disabled={!canWrite || busy || !text.trim() || row.status === 'bos'} onClick={() => void confirm().catch(() => undefined)} className={`${btn} bg-canvas-mint/15 text-emerald-700`}>
              {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Check aria-hidden className="h-4 w-4" />}
              {dirty ? 'Düzeltip onayla' : 'Onayla ve geç'}
            </button>
            {row.status === 'onaylandi' ? (
              <button type="button" disabled={busy} onClick={() => void decide('geri').catch(() => undefined)} className={btnGhost}>
                <Undo2 aria-hidden className="h-4 w-4" />
                Onayı geri al
              </button>
            ) : row.status === 'cevrildi' ? (
              <button type="button" disabled={busy} onClick={() => void decide('geri', true).catch(() => undefined)} className={btnGhost}>
                <RotateCcw aria-hidden className="h-4 w-4" />
                Çevirmene geri gönder
              </button>
            ) : null}
          </>
        )}
        <span className="ml-auto flex gap-1">
          <button type="button" aria-label="Önceki segment" onClick={onPrev} className={`${btnGhost} px-2.5`}>
            <ArrowUp aria-hidden className="h-4 w-4" />
          </button>
          <button type="button" aria-label="Sonraki segment" onClick={onNext} className={`${btnGhost} px-2.5`}>
            <ArrowDown aria-hidden className="h-4 w-4" />
          </button>
        </span>
      </div>
      <p className="text-[11px] leading-snug text-canvas-muted">
        {translating
          ? `${MOD}+Enter onayla ve sonrakine geç · Alt+↓/↑ gezin · yazdıkça taslak kaydedilir${busy ? ' · kaydediliyor…' : dirty ? '' : row.updatedAt ? ' · kaydedildi' : ''}`
          : `${MOD}+Enter onayla ve sonrakine geç · Alt+↓/↑ gezin · düzeltme onayla birlikte kaydedilir${dirty ? ' · kaydedilmemiş düzeltme var' : ''}`}
      </p>
      {!wide && <div className="pt-1">{aside}</div>}
      {wide && asideEl ? createPortal(aside, asideEl) : null}
    </div>
  );
}

function Row({ s, active, onOpen, srcDir, tgtDir, children }: { s: SegmentRow; active: boolean; onOpen: () => void; srcDir: string; tgtDir: string; children?: ReactNode }) {
  if (active)
    return (
      <li id={`seg-${s.id}`} className="scroll-mt-24 rounded-2xl border border-canvas-violet bg-white p-3 shadow-sm">
        <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="font-mono font-bold tabular-nums text-canvas-muted">{s.no}</span>
          <Pill tone={SEG[s.status].tone}>{SEG[s.status].label}</Pill>
          {s.heading && <Pill tone="muted">Başlık</Pill>}
          <span className="text-canvas-muted">{nf.format(s.words)} kelime</span>
          {s.updatedBy && <span className="text-canvas-muted">· {s.updatedBy}</span>}
        </div>
        {children}
      </li>
    );
  return (
    <li id={`seg-${s.id}`} className="scroll-mt-24 [contain-intrinsic-size:auto_72px] [content-visibility:auto]">
      <button
        type="button"
        onClick={onOpen}
        className="grid w-full grid-cols-[auto_minmax(0,1fr)] gap-x-2.5 rounded-2xl border border-slate-100 bg-white/85 px-3 py-2 text-left text-[12.5px] transition-colors duration-150 hover:bg-white md:grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)]"
      >
        <span className="flex flex-col items-center gap-1 pt-0.5">
          <span className="font-mono text-[10.5px] font-bold tabular-nums text-canvas-muted">{s.no}</span>
          <span aria-label={SEG[s.status].label} className={`h-2 w-2 rounded-full ${SEG[s.status].dot}`} />
        </span>
        <span dir={srcDir} className={`min-w-0 break-words leading-snug ${s.heading ? 'font-extrabold' : ''}`}>
          {s.source}
        </span>
        <span dir={tgtDir} className="col-start-2 mt-1 min-w-0 break-words leading-snug md:col-start-3 md:mt-0">
          {s.target ? <span className="font-semibold">{s.target}</span> : <span className="italic text-canvas-muted">{s.hasDraft ? 'ZEKİ taslağı var' : 'Boş'}</span>}
          {(s.issues.length > 0 || s.errors > 0 || s.edited) && (
            <span className="mt-1 flex flex-wrap gap-1">
              {s.issues.length > 0 && <Pill tone="warn">{nf.format(s.issues.length)} uyarı</Pill>}
              {s.errors > 0 && <Pill tone="err">{nf.format(s.errors)} hata</Pill>}
              {s.edited && <Pill tone="violet">İnceleyen düzeltti</Pill>}
            </span>
          )}
        </span>
      </button>
    </li>
  );
}

function Desk({ jobId, me }: { jobId: string; me: string }) {
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const canTerm = useCan('ceviri.terim');
  const wide = useWide();
  const job = useQuery({
    queryKey: ['translation', 'job', jobId],
    queryFn: () => translationApi.job(jobId),
    enabled: ENGINE_ENABLED,
    refetchInterval: (query) => (query.state.data?.draft.state === 'calisiyor' ? 8000 : false),
  });
  const j = job.data;
  const both = !!j && j.roles.translate && j.roles.review;
  const [modeChoice, setModeChoice] = useState<Mode | null>(null);
  const mode: Mode = !j ? 'ceviri' : both ? modeChoice ?? (j.reviewer === me && j.translator !== me ? 'inceleme' : 'ceviri') : j.roles.review ? 'inceleme' : 'ceviri';
  const [chapter, setChapter] = useState<number | null | undefined>(undefined);
  const [filter, setFilter] = useState('hepsi');
  const [text, setText] = useState('');
  const q = useDebounced(text, 300);
  const [active, setActive] = useState<string | null>(params.get('segment'));
  const [asideEl, setAsideEl] = useState<HTMLDivElement | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // ?segment= ile gelindiyse (kalite raporundan) o segmentin bölümü açılır.
  const target = params.get('segment');
  const jump = useQuery({ queryKey: ['translation', 'segment', target], queryFn: () => translationApi.segment(target as string), enabled: !!target && ENGINE_ENABLED });
  useEffect(() => {
    if (chapter !== undefined || !j) return;
    if (target) {
      if (jump.data) setChapter(jump.data.chapter);
      else if (jump.error) setChapter(j.chapters[0]?.no ?? null);
      return;
    }
    const open = j.chapters.find((c) => (mode === 'ceviri' ? c.bos + c.taslak > 0 : c.cevrildi > 0));
    setChapter(open?.no ?? j.chapters[0]?.no ?? null);
  }, [j, chapter, target, jump.data, jump.error, mode]);

  const listKey = useMemo(() => ['translation', 'segments', jobId, chapter ?? null, filter, q], [jobId, chapter, filter, q]);
  const list = useQuery({
    queryKey: listKey,
    queryFn: () => translationApi.segments(jobId, { chapter, filter, q }),
    enabled: ENGINE_ENABLED && chapter !== undefined,
    placeholderData: (prev) => prev,
  });
  const items = list.data?.items ?? [];

  useEffect(() => {
    if (!items.length) return;
    if (!active || (!items.some((s) => s.id === active) && !list.isPlaceholderData)) {
      const first = items.find((s) => (mode === 'ceviri' ? s.status === 'bos' || s.status === 'taslak' : s.status === 'cevrildi')) ?? items[0];
      setActive(first.id);
    }
  }, [items, active, mode, list.isPlaceholderData]);

  useEffect(() => {
    if (active) document.getElementById(`seg-${active}`)?.scrollIntoView({ block: 'nearest' });
  }, [active]);

  const patch = useCallback(
    (id: string, p: Partial<SegmentRow>) =>
      qc.setQueryData<{ items: SegmentRow[] }>(listKey, (old) => (old ? { ...old, items: old.items.map((x) => (x.id === id ? { ...x, ...p } : x)) } : old)),
    [qc, listKey],
  );
  const idx = items.findIndex((s) => s.id === active);
  const go = useCallback(
    (dir: 1 | -1, preferOpen: boolean) => {
      if (idx < 0) return;
      const wanted = (s: SegmentRow) => (mode === 'ceviri' ? s.status === 'bos' || s.status === 'taslak' : s.status === 'cevrildi');
      if (preferOpen && dir === 1) {
        const n = items.slice(idx + 1).find(wanted);
        if (n) return setActive(n.id);
      }
      const n = items[idx + dir];
      if (n) setActive(n.id);
    },
    [idx, items, mode],
  );

  const refreshAll = async () => {
    await qc.invalidateQueries({ queryKey: ['translation', 'segments', jobId] });
    await qc.invalidateQueries({ queryKey: ['translation', 'job', jobId] });
    await qc.invalidateQueries({ queryKey: ['translation', 'segment'] });
  };
  const placeDrafts = useMutation({ mutationFn: () => translationApi.useDraft(jobId, chapter ?? null), onSuccess: async (r) => { setNotice(`${nf.format(r.filled)} boş segmente ZEKİ taslağı yerleştirildi (taslak olarak; her birini okuyup onaylayın).`); await refreshAll(); } });
  const approveAll = useMutation({ mutationFn: () => translationApi.approveMany(jobId, chapter ?? null), onSuccess: async (r) => { setNotice(`${nf.format(r.approved)} segment onaylandı.`); await refreshAll(); } });

  if (!j) return <Panel>{job.error ? <Note tone="err">{errText(job.error, 'Çeviri işi okunamadı.')}</Note> : <Loading />}</Panel>;
  const ch = j.chapters.find((c) => c.no === chapter);
  const srcDir = dirOf(j.sourceLang);
  const tgtDir = dirOf(j.targetLang);
  const waitingReview = ch ? ch.cevrildi : j.segments.cevrildi;

  return (
    <>
      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="break-words text-[18px] font-extrabold leading-tight tracking-tight">{j.title}</h2>
            <p className="mt-0.5 text-[12px] text-canvas-muted">
              {pair(j)}
              {j.translator ? ` · çevirmen ${j.translatorName || j.translator}` : ''}
              {j.reviewer ? ` · inceleyen ${j.reviewerName || j.reviewer}` : ''}
            </p>
          </div>
          {both && (
            <div className="grid grid-cols-2 gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Çalışma kipi">
              {(['ceviri', 'inceleme'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="tab"
                  aria-selected={mode === m}
                  onClick={() => setModeChoice(m)}
                  className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${mode === m ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'}`}
                >
                  {m === 'ceviri' ? 'Çeviri' : 'İnceleme'}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="mt-2.5">
          <ProgressBar done={j.words.done} approved={j.words.approved} total={j.words.total} label="İş ilerlemesi" />
          <p className="mt-1.5 text-[11.5px] leading-snug text-canvas-muted">
            <span className="font-mono font-bold tabular-nums text-canvas-ink">%{pct(j.words.done, j.words.total)}</span> çevrildi,{' '}
            <span className="font-mono font-bold tabular-nums text-canvas-ink">%{pct(j.words.approved, j.words.total)}</span> onaylı. <span className={j.pace.late ? 'font-semibold text-amber-700' : ''}>{paceText(j, j.pace)}</span>
          </p>
        </div>
        {j.note && (
          <div className="mt-2">
            <Note tone="info">
              <span className="font-bold">İş notu:</span> {j.note}
            </Note>
          </div>
        )}
        <div className="mt-2.5 flex flex-wrap gap-1.5">
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
                setNotice(`XLIFF: ${nf.format(r.updated)} segment güncellendi (${nf.format(r.confirmed)} çevrildi olarak)${r.locked ? `, ${nf.format(r.locked)} onaylı segmente dokunulmadı` : ''}${r.unknown ? `, ${nf.format(r.unknown)} segment bu işe ait değil` : ''}.`);
                await refreshAll();
              }}
            >
              XLIFF yükle
            </FileButton>
          )}
          {mode === 'ceviri' && j.roles.translate && items.some((s) => s.hasDraft && s.status === 'bos') && (
            <button type="button" disabled={placeDrafts.isPending} onClick={() => placeDrafts.mutate()} className={btnGhost}>
              <Sparkles aria-hidden className="h-4 w-4" />
              {ch ? 'Bu bölümde taslakları yerleştir' : 'Taslakları yerleştir'}
            </button>
          )}
          {mode === 'inceleme' && j.roles.review && waitingReview > 0 && (
            <button
              type="button"
              disabled={approveAll.isPending}
              onClick={() => {
                if (window.confirm(`${ch ? 'Bu bölümdeki' : 'İşteki'} ${nf.format(waitingReview)} çevrildi segmenti düzeltmeden onaylansın mı?`)) approveAll.mutate();
              }}
              className={`${btn} bg-canvas-mint/15 text-emerald-700`}
            >
              <Check aria-hidden className="h-4 w-4" />
              {ch ? 'Bölümdeki çevrilenleri onayla' : 'Çevrilenlerin hepsini onayla'}
            </button>
          )}
          <Link to={`/ceviri/${j.id}/kalite`} className={btnGhost}>
            <BarChart3 aria-hidden className="h-4 w-4" />
            Kalite raporu
          </Link>
        </div>
        {notice && (
          <div className="mt-2">
            <Note tone="ok">{notice}</Note>
          </div>
        )}
        {(placeDrafts.error || approveAll.error) && (
          <div className="mt-2">
            <Note tone="err">{errText(placeDrafts.error || approveAll.error, 'İşlem yapılamadı.')}</Note>
          </div>
        )}
        {j.draft.state === 'calisiyor' && (
          <div className="mt-2">
            <Note tone="info">
              ZEKİ taslağı hazırlanıyor: {nf.format(j.draft.done)} / {nf.format(j.draft.total)} segment.
            </Note>
          </div>
        )}
      </Panel>

      {!j.source ? (
        <Panel>
          <p className="py-8 text-center text-[12.5px] text-canvas-muted">Bu işin kaynak metni henüz yüklenmedi.</p>
        </Panel>
      ) : (
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,380px)] lg:items-start lg:gap-4">
          <Panel>
            <div className="grid gap-2 sm:grid-cols-3">
              <label className="block">
                <span className={label}>Bölüm</span>
                <select
                  value={chapter == null ? '' : String(chapter)}
                  onChange={(e) => {
                    setChapter(e.target.value ? Number(e.target.value) : null);
                    setActive(null);
                  }}
                  className={`${field} mt-1`}
                >
                  <option value="">Bütün bölümler</option>
                  {j.chapters.map((c) => (
                    <option key={c.no} value={c.no}>
                      {c.no}. {c.title.slice(0, 60)} — %{pct(c.wordsDone, c.words)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className={label}>Göster</span>
                <select
                  value={filter}
                  onChange={(e) => {
                    setFilter(e.target.value);
                    setActive(null);
                  }}
                  className={`${field} mt-1`}
                >
                  {Object.entries(FILTER_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className={label}>Ara</span>
                <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Kaynakta ya da çeviride" className={`${field} mt-1`} />
              </label>
            </div>
            <div className="mt-2 flex items-center justify-between gap-2 px-1 text-[11.5px] text-canvas-muted">
              <span className="flex items-center gap-1.5">
                {list.isFetching && <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" />}
                <span className="font-mono tabular-nums">
                  {nf.format(items.length)} segment{list.data ? ` / işte ${nf.format(list.data.total)}` : ''}
                </span>
              </span>
              <span className="hidden gap-3 md:flex">
                <span>{langName(j.sourceLang)}</span>
                <span>{langName(j.targetLang)}</span>
              </span>
            </div>
            {list.error && <Note tone="err">{errText(list.error, 'Segmentler okunamadı.')}</Note>}
            {list.data && !items.length && <p className="py-8 text-center text-[12.5px] text-canvas-muted">Bu süzgece uyan segment yok.</p>}
            <ul className="mt-2 space-y-1.5">
              {items.map((s) => (
                <Row key={s.id} s={s} active={s.id === active} onOpen={() => setActive(s.id)} srcDir={srcDir} tgtDir={tgtDir}>
                  {s.id === active && (
                    <Editor
                      key={`${s.id}-${mode}`}
                      row={s}
                      job={j}
                      mode={mode}
                      wide={wide}
                      canTerm={canTerm}
                      listKey={listKey}
                      onPatch={(p) => patch(s.id, p)}
                      onNext={() => go(1, true)}
                      onPrev={() => go(-1, false)}
                      asideEl={asideEl}
                    />
                  )}
                </Row>
              ))}
            </ul>
          </Panel>
          {wide && (
            <div className="lg:sticky lg:top-0">
              {!active && (
                <Panel>
                  <p className="text-[12px] text-canvas-muted">Bir segment seçin.</p>
                </Panel>
              )}
              <div ref={setAsideEl} />
            </div>
          )}
        </div>
      )}
    </>
  );
}

export default function Workbench() {
  const { jobId } = useParams();
  const session = useTimasSession();
  const nav = useNavigate();
  const me = (session.data?.username ?? '').toLowerCase();
  return (
    <ModuleFrame
      route="/ceviri/masam"
      crumb="Çeviri masam"
      title="Çeviri masam"
      lead="Segment segment çeviri ve inceleme. Terim bankası, çeviri belleği ve otomatik denetim yanınızda; yazdığınız kendiliğinden taslak olarak kaydedilir, onayladığınız segment ilerlemeye sayılır."
      source="Çeviri masası"
      presence="Kaynak: çeviri kayıtları"
      aside={
        jobId ? (
          <button type="button" className={`${btnGhost} w-full lg:w-auto`} onClick={() => nav('/ceviri/masam')}>
            Bütün işlerim
          </button>
        ) : undefined
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {jobId ? <Desk key={jobId} jobId={jobId} me={me} /> : <MyJobs me={me} />}
    </ModuleFrame>
  );
}
