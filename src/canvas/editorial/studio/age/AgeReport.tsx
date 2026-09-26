import { useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Dialog } from '@base-ui/react/dialog';
import { AlertTriangle, Baby, Check, ChevronDown, Download, ExternalLink, Info, Loader2, RefreshCw, X } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { ghostBtn, gradientBtn, press, Progress } from '../shared';
import { ageApi, type AgeCheck, type AgeFinding, type AgeLevel, type AgeView, type AgeWord, type Decision, type PageRef } from './api';
import './age.css';

/** Yaş uygunluğu raporu (sözleşme: apps/editor/src/editor/production/age_report.py). Sayfa stüdyosunun üst
 *  şeridinde tek düğme; rapor yan sayfada açılır. Kelime düzeyi, cümle uzunluğu, hassas içerik ve okul/MEB
 *  ölçütleri; her bulgu sayfasına bağlı (tıklayınca sayfa düzeninde o sayfa açılır); editör kararları kim/ne zaman
 *  kaydıyla. Model ya da formül adı ekranda yok: ölçülerin adı ve kaynaklar PDF'in ekinde. */

const LEVEL: Record<AgeLevel, { tone: string; dot: string }> = {
  uygun: { tone: 'border-emerald-200 bg-emerald-50 text-emerald-800', dot: 'bg-emerald-500' },
  sinirda: { tone: 'border-amber-200 bg-amber-50 text-amber-800', dot: 'bg-amber-400' },
  uyumsuz: { tone: 'border-rose-200 bg-rose-50 text-rose-800', dot: 'bg-rose-500' },
  belirtilmemis: { tone: 'border-violet-200 bg-violet-50 text-violet-800', dot: 'bg-canvas-violet' },
  degerlendirilemedi: { tone: 'border-violet-200 bg-violet-50 text-violet-800', dot: 'bg-canvas-violet' },
  cocuk_degil: { tone: 'border-slate-200 bg-slate-50 text-slate-700', dot: 'bg-slate-400' },
};
const KIND: Record<string, string> = { LONG_SENTENCE: 'Uzun cümle', HARD_PAGE: 'Zor sayfa', SENSITIVE: 'Hassas içerik' };
const CATEGORY: Record<string, string> = {
  VIOLENCE: 'şiddet', FEAR: 'korku', UNSAFE_IMITABLE: 'taklit edilebilir tehlike', SUBSTANCE: 'madde kullanımı',
  DEATH_GRIEF: 'ölüm/yas', INSULT_DISCRIMINATION: 'aşağılama/ayrımcılık', SEXUAL: 'cinsellik',
};
const when = (t: number) => new Intl.DateTimeFormat('tr-TR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(t * 1000));
const pct = (v: number | undefined) => (v == null ? '' : `%${(Math.round(v * 1000) / 10).toLocaleString('tr-TR')}`);
const chip = `inline-flex min-h-8 items-center rounded-full px-2.5 text-[11.5px] font-bold ${press}`;

type Tab = 'bulgu' | 'kelime' | 'olcut' | 'liste';

function useAge(jobId: string, open: boolean) {
  return useQuery({
    queryKey: ['studio', 'age', jobId],
    queryFn: () => ageApi.get(jobId),
    enabled: !!jobId,
    retry: false,
    refetchInterval: (q) => ((q.state.data as AgeView | undefined)?.status.state === 'running' ? 2500 : open ? 60_000 : false),
  });
}

/** Stüdyonun üst şeridine konan giriş: rapor durumunu küçük bir işaretle gösterir, yan sayfayı açar. */
export default function AgeReportEntry({ jobId }: { jobId: string }) {
  const [open, setOpen] = useState(false);
  const q = useAge(jobId, open);
  const level = q.data?.report?.verdict.level;
  const running = q.data?.status.state === 'running';
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger className={ghostBtn} title="Kelime düzeyi, cümle uzunluğu, hassas içerik ve okul/MEB ölçütleri">
        {running ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Baby className="h-4 w-4" aria-hidden />}
        Yaş uygunluğu
        {level && <span className={`h-2 w-2 rounded-full ${LEVEL[level].dot}`} aria-label={q.data?.report?.verdict.label} />}
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Backdrop className="age-scrim" />
        <Dialog.Popup className="age-sheet font-canvas text-canvas-ink" aria-describedby={undefined}>
          <Sheet jobId={jobId} view={q.data} error={q.error} onNavigate={() => setOpen(false)} />
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Sheet({ jobId, view, error, onNavigate }: { jobId: string; view: AgeView | undefined; error: unknown; onNavigate: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('bulgu');
  const set = (v: AgeView) => qc.setQueryData(['studio', 'age', jobId], (old: AgeView | undefined) => ({ ...old, ...v }));
  const run = useMutation({
    mutationFn: () => ageApi.run(jobId),
    onSettled: () => qc.invalidateQueries({ queryKey: ['studio', 'age', jobId] }),
  });
  const decide = useMutation({
    mutationFn: (v: { kind: 'finding' | 'word' | 'check'; id: string; state: string | null; note?: string; choice?: Record<string, string> }) =>
      ageApi.decide(jobId, v.kind, v.id, v.state, v.note ?? '', v.choice),
    onSuccess: set,
  });
  const apply = useMutation({
    mutationFn: (v: { lemma: string; form: string; to: string }) => ageApi.apply(jobId, v.lemma, v.form, v.to),
    onSuccess: (v) => { set(v); qc.invalidateQueries({ queryKey: ['studio', 'job', jobId] }); },
  });
  const goto = (p: { pid: string | null }) => {
    onNavigate();
    navigate(`/kitap-tasarim/${jobId}/sayfalar${p.pid ? `?sayfa=${encodeURIComponent(p.pid)}` : ''}`);
  };

  const rep = view?.report ?? null;
  const st = view?.status;
  const running = st?.state === 'running';
  const findings = useMemo(() => (rep?.findings ?? []).filter((f) => f.kind !== 'BOOK_MEASURES')
    .sort((a, b) => (a.page_no ?? 0) - (b.page_no ?? 0)), [rep]);
  const listDone = view?.checklist.filter((c) => c.decision).length ?? 0;
  const err = errText(run.error || decide.error || apply.error || error, '');

  const tabs: [Tab, string, number | string][] = [
    ['bulgu', 'Sayfa sayfa', findings.length],
    ['kelime', 'Kelimeler', rep?.words.length ?? 0],
    ['olcut', 'Okul/MEB ölçütleri', rep?.checks.length ?? 0],
    ['liste', 'Kontrol listesi', `${listDone}/${view?.checklist.length ?? 0}`],
  ];

  return (
    <>
      <header className="flex items-start gap-3 border-b border-slate-200/80 px-4 pb-3 pt-4 sm:px-5">
        <div className="min-w-0 flex-1">
          <Dialog.Title className="text-[17px] font-extrabold tracking-tight">Yaş uygunluğu raporu</Dialog.Title>
          <p className="mt-0.5 text-[12px] leading-snug text-canvas-muted">
            {rep ? <>Hedef yaş: <b className="text-canvas-ink">{rep.band ? `${rep.band[0]}–${rep.band[1]}` : 'belirtilmemiş'}</b>{rep.band_source !== 'yok' && ` · ${rep.band_source}`} · {when(rep.at)} · {rep.by}</>
              : 'Kelime düzeyi, cümle uzunluğu, hassas içerik ve okul/MEB ölçütleri.'}
          </p>
        </div>
        <Dialog.Close className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl hover:bg-slate-100 ${press}`} aria-label="Kapat">
          <X className="h-5 w-5" aria-hidden />
        </Dialog.Close>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-3 sm:px-5">
        <div className="flex flex-wrap gap-2">
          <button type="button" className={gradientBtn} disabled={running || run.isPending} onClick={() => run.mutate()}>
            {running || run.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <RefreshCw className="h-4 w-4" aria-hidden />}
            {running ? 'Çıkarılıyor…' : rep ? 'Raporu yenile' : 'Raporu çıkar'}
          </button>
          {rep && <a className={ghostBtn} href={ageApi.pdfUrl(jobId)}><Download className="h-4 w-4" aria-hidden />PDF indir</a>}
        </div>
        {running && (
          <div className="mt-3 rounded-2xl border border-violet-100 bg-white/80 p-3" role="status" aria-live="polite">
            <div className="text-[12.5px] font-bold">{st?.step || 'Hazırlanıyor'}{st?.total ? ` · ${st.done}/${st.total}` : ''}</div>
            {!!st?.total && <div className="mt-2"><Progress value={st.done ?? 0} total={st.total} /></div>}
            <p className="mt-1.5 text-[11.5px] text-canvas-muted">Zeki AI her pasajı ve seyrek kelimeyi tek tek okuyor; ekranı kapatabilirsiniz, rapor çıkınca burada olur.</p>
          </div>
        )}
        {st?.state === 'failed' && <div className="mt-3"><Note tone="err">{st.error}</Note></div>}
        {err && <div className="mt-3"><Note tone="err">{err}</Note></div>}
        {!view && !error && <div className="mt-6 flex justify-center"><Loader2 className="h-5 w-5 animate-spin text-canvas-violet motion-reduce:animate-none" aria-hidden /></div>}
        {view && !rep && !running && st?.state !== 'failed' && (
          <p className="mt-4 text-[13px] text-canvas-muted">Henüz rapor yok. «Raporu çıkar» kitabın güncel metnini (sayfa düzeni varsa oradaki metni) hedef yaşa göre ölçer.</p>
        )}

        {rep && (
          <>
            <Verdict rep={rep} />
            <div className="age-tabs mt-4" role="tablist" aria-label="Rapor bölümleri">
              {tabs.map(([k, t, n]) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                  className={`${chip} shrink-0 border ${tab === k ? 'border-canvas-violet bg-violet-50 text-canvas-violet' : 'border-slate-200 bg-white text-canvas-ink'}`}>
                  {t}<span className="ml-1.5 rounded-full bg-white/80 px-1.5 font-mono text-[10.5px] text-canvas-muted">{n}</span>
                </button>
              ))}
            </div>
            <div className="mt-3" role="tabpanel">
              {tab === 'bulgu' && <Findings items={findings} goto={goto} decide={decide.mutate} busy={decide.isPending} />}
              {tab === 'kelime' && <Words rep={rep} goto={goto} decide={decide.mutate} apply={apply.mutate} busy={decide.isPending || apply.isPending} applied={apply.data} />}
              {tab === 'olcut' && <Checks items={rep.checks} goto={goto} />}
              {tab === 'liste' && <Checklist view={view!} decide={decide.mutate} busy={decide.isPending} />}
            </div>
            <Sources view={view!} />
          </>
        )}
      </div>
    </>
  );
}

function Verdict({ rep }: { rep: NonNullable<AgeView['report']> }) {
  const v = rep.verdict;
  const Icon = v.level === 'uygun' ? Check : v.level === 'sinirda' || v.level === 'uyumsuz' ? AlertTriangle : Info;
  return (
    <section className={`mt-4 rounded-2xl border p-3.5 ${LEVEL[v.level].tone}`} aria-label="Bant uyumu">
      <div className="flex items-center gap-2 text-[15px] font-extrabold"><Icon className="h-5 w-5 shrink-0" aria-hidden />{v.label}</div>
      <ul className="mt-1.5 flex flex-col gap-1 text-[12.5px] leading-snug">
        {v.reasons.map((r) => <li key={r}>{r}</li>)}
      </ul>
      {rep.stale && <p className="mt-2 text-[12px] font-bold">Metin rapordan sonra değişti; bulgular eski metne göre. Raporu yenileyin.</p>}
      {rep.text_source !== 'plan' && <p className="mt-2 text-[11.5px] opacity-80">Sayfa düzeni kurulmadığı için sayfalar {rep.text_source === 'pagemap' ? 'dizginin sayfalarıdır' : 'bölümlerdir'}; bulgudan sayfa düzenine geçiş sayfa düzeni kurulunca açılır.</p>}
    </section>
  );
}

function PageChip({ p, goto }: { p: PageRef & { label?: string | null }; goto: (p: { pid: string | null }) => void }) {
  const text = p.label || (p.page_no ? `${p.page_no}. sayfa` : p.where || 'kitap geneli');
  if (!p.pid) return <span className={`${chip} bg-slate-100 text-canvas-muted`}>{text}</span>;
  return (
    <button type="button" onClick={() => goto(p)} className={`${chip} bg-violet-50 text-canvas-violet hover:bg-violet-100`} title="Sayfa düzeninde aç">
      {text}
    </button>
  );
}

function DecisionLine({ d }: { d: Decision | undefined }) {
  if (!d) return null;
  const t: Record<string, string> = { dismissed: 'Sorun değil', fix: 'Düzeltilecek', approved: 'Onaylandı', rejected: 'Reddedildi', ok: 'Uygun', not_ok: 'Uygun değil' };
  return <p className="mt-1 text-[11px] text-canvas-muted">{t[d.state] ?? d.state} · {d.by} · {when(d.at)}{d.note ? ` · “${d.note}”` : ''}</p>;
}

type Decide = (v: { kind: 'finding' | 'word' | 'check'; id: string; state: string | null; note?: string; choice?: Record<string, string> }) => void;

function Toggle({ on, children, onClick, disabled, tone = 'violet' }: { on: boolean; children: ReactNode; onClick: () => void; disabled?: boolean; tone?: 'violet' | 'ok' | 'bad' }) {
  const onCls = tone === 'ok' ? 'border-emerald-500 bg-emerald-50 text-emerald-800' : tone === 'bad' ? 'border-rose-400 bg-rose-50 text-rose-800' : 'border-canvas-violet bg-violet-50 text-canvas-violet';
  return (
    <button type="button" aria-pressed={on} disabled={disabled} onClick={onClick}
      className={`inline-flex min-h-9 items-center gap-1 rounded-xl border px-3 text-[12px] font-bold disabled:opacity-50 ${press} ${on ? onCls : 'border-slate-200 bg-white text-canvas-ink'}`}>
      {on && <Check className="h-3.5 w-3.5" aria-hidden />}{children}
    </button>
  );
}

function Findings({ items, goto, decide, busy }: { items: AgeFinding[]; goto: (p: { pid: string | null }) => void; decide: Decide; busy: boolean }) {
  if (!items.length) return <p className="text-[13px] text-canvas-muted">Sayfa düzeyinde bulgu yok.</p>;
  return (
    <ul className="flex flex-col gap-2">
      {items.map((f) => {
        const s = f.decision?.state;
        return (
          <li key={f.id} className={`rounded-2xl border bg-white/90 p-3 ${s === 'dismissed' ? 'border-slate-200 opacity-70' : f.severity === 'WARN' ? 'border-rose-200' : 'border-slate-200'}`}>
            <div className="flex flex-wrap items-center gap-1.5">
              <PageChip p={f} goto={goto} />
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${f.severity === 'WARN' ? 'bg-rose-50 text-rose-700' : 'bg-slate-100 text-canvas-muted'}`}>
                {KIND[f.kind] ?? f.kind}{f.kind === 'SENSITIVE' && f.details.category ? ` · ${CATEGORY[f.details.category] ?? ''}` : ''}
              </span>
              {f.removed && <span className="text-[11px] text-canvas-muted">(sayfa silinmiş)</span>}
            </div>
            <p className="mt-1.5 text-[12.5px] leading-snug">{f.message}</p>
            {f.quote && <blockquote className="mt-1.5 break-words rounded-xl bg-amber-50/60 px-2.5 py-1.5 text-[12px] italic leading-snug">“{f.quote}”</blockquote>}
            {f.suggestion && <p className="mt-1 text-[11.5px] text-canvas-muted">Öneri: {f.suggestion}</p>}
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Toggle on={s === 'dismissed'} disabled={busy} tone="ok" onClick={() => decide({ kind: 'finding', id: f.id, state: s === 'dismissed' ? null : 'dismissed' })}>Sorun değil</Toggle>
              <Toggle on={s === 'fix'} disabled={busy} tone="bad" onClick={() => decide({ kind: 'finding', id: f.id, state: s === 'fix' ? null : 'fix' })}>Düzeltilecek</Toggle>
            </div>
            <DecisionLine d={f.decision} />
          </li>
        );
      })}
    </ul>
  );
}

function Words({ rep, goto, decide, apply, busy, applied }: {
  rep: NonNullable<AgeView['report']>; goto: (p: { pid: string | null }) => void; decide: Decide;
  apply: (v: { lemma: string; form: string; to: string }) => void; busy: boolean; applied?: { count: number };
}) {
  const ws = rep.word_stats;
  if (!ws.reference) return <p className="text-[13px] text-canvas-muted">Bu yaş bandı için kelime derlemi yok; seyrek kelime listesi çıkarılmadı.</p>;
  return (
    <div>
      <p className="text-[12px] leading-snug text-canvas-muted">
        Bu yaş için yayımlanmış {ws.books} kitabın en çok {ws.K} tanesinde geçen kökler seyrek sayılır. Kitapta {rep.words.length} seyrek kök; içerik sözcükleri içindeki payı {pct(ws.rare_share)}
        {ws.rare_share_p95 != null ? ` (bant kitaplarında %95’lik sınır ${pct(ws.rare_share_p95)})` : ''}. Öneriyi onaylamak metni değiştirmez; «Metne uygula» sayfa düzenindeki metne yazar.
      </p>
      {applied && <div className="mt-2"><Note tone="ok">{applied.count} yerde değiştirildi; sayfalar yeniden diziliyor.</Note></div>}
      <ul className="mt-2 flex flex-col gap-2">
        {rep.words.map((w) => <WordCard key={w.lemma} w={w} goto={goto} decide={decide} apply={apply} busy={busy} canApply={rep.text_source === 'plan'} />)}
      </ul>
      {!!ws.unknown?.length && (
        <details className="mt-3 rounded-2xl border border-slate-200 bg-white/70 p-3 text-[12px]">
          <summary className="cursor-pointer font-bold">Sözlükte çözümlenemeyen {ws.unknown.length} biçim (kelime düzeyine katılmadı)</summary>
          <p className="mt-1.5 break-words leading-relaxed text-canvas-muted">{ws.unknown.map((u) => `${u.form} (${u.pages.join(', ')})`).join(' · ')}</p>
        </details>
      )}
    </div>
  );
}

function WordCard({ w, goto, decide, apply, busy, canApply }: {
  w: AgeWord; goto: (p: { pid: string | null }) => void; decide: Decide; apply: (v: { lemma: string; form: string; to: string }) => void; busy: boolean; canApply: boolean;
}) {
  const d = w.decision;
  const [pick, setPick] = useState<Record<string, string>>(() => d?.choice ?? {});
  const pages = useMemo(() => {
    const seen = new Map<string, AgeWord['pages'][number]>();
    for (const p of w.pages) seen.set(p.pid ?? String(p.page_no), seen.get(p.pid ?? String(p.page_no)) ?? p);
    return [...seen.values()];
  }, [w.pages]);
  const opts = w.suggestion?.by_form ?? {};
  const doneForms = new Set((d?.applied ?? []).map((a) => a.form));
  return (
    <li className={`rounded-2xl border border-slate-200 bg-white/90 p-3 ${d?.state === 'rejected' ? 'opacity-70' : ''}`}>
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-[15px] font-extrabold">{w.lemma}</span>
        <span className="text-[11.5px] text-canvas-muted">bant kitaplarının {w.df === 0 ? 'hiçbirinde yok' : `${w.df} tanesinde`}</span>
      </div>
      {w.suggestion?.meaning && <p className="mt-0.5 text-[12px] text-canvas-muted">{w.suggestion.meaning}</p>}
      <p className="mt-1.5 break-words text-[12px] italic leading-snug">“{w.pages[0].sentence}”</p>
      <div className="mt-2 flex flex-wrap gap-1.5">{pages.map((p) => <PageChip key={p.pid ?? p.page_no} p={p} goto={goto} />)}</div>
      {w.suggestion_error && <p className="mt-2 text-[11.5px] text-amber-700">{w.suggestion_error}</p>}
      {w.forms.map((f) => (
        <div key={f} className="mt-2">
          <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">«{f}» yerine</div>
          {opts[f]?.length ? (
            <div className="mt-1 flex flex-wrap gap-1.5">
              {opts[f].map((o) => (
                <Toggle key={o} on={pick[f] === o} disabled={busy || d?.state === 'approved'} onClick={() => setPick((p) => ({ ...p, [f]: p[f] === o ? '' : o }))}>{o}</Toggle>
              ))}
              {d?.state === 'approved' && d.choice?.[f] && canApply && !doneForms.has(f) && (
                <button type="button" className={`${ghostBtn} !min-h-9`} disabled={busy} onClick={() => apply({ lemma: w.lemma, form: f, to: d.choice![f] })}>
                  Metne uygula: {f} → {d.choice[f]}
                </button>
              )}
            </div>
          ) : <p className="mt-1 text-[11.5px] text-canvas-muted">Sade karşılık önerilmedi.</p>}
        </div>
      ))}
      <div className="mt-2.5 flex flex-wrap gap-1.5">
        <Toggle on={d?.state === 'approved'} tone="ok" disabled={busy || (d?.state !== 'approved' && !Object.values(pick).some(Boolean))}
          onClick={() => decide({ kind: 'word', id: w.lemma, state: d?.state === 'approved' ? null : 'approved', choice: pick })}>Öneriyi onayla</Toggle>
        <Toggle on={d?.state === 'rejected'} tone="bad" disabled={busy}
          onClick={() => decide({ kind: 'word', id: w.lemma, state: d?.state === 'rejected' ? null : 'rejected' })}>Kelime kalsın</Toggle>
      </div>
      {d?.applied?.map((a) => <p key={a.at} className="mt-1 text-[11px] text-emerald-700">Uygulandı: {a.form} → {a.to} ({a.count} yer) · {a.by} · {when(a.at)}</p>)}
      <DecisionLine d={d} />
    </li>
  );
}

function Checks({ items, goto }: { items: AgeCheck[]; goto: (p: { pid: string | null }) => void }) {
  const tone = { ok: 'bg-emerald-50 text-emerald-700', warn: 'bg-amber-50 text-amber-800', info: 'bg-violet-50 text-canvas-violet' } as const;
  const label = { ok: 'Uygun', warn: 'Dikkat', info: 'Bilgi' } as const;
  if (!items.length) return <p className="text-[13px] text-canvas-muted">Hedef yaş 18 ve üstü: okul ölçütleri uygulanmadı.</p>;
  return (
    <ul className="flex flex-col gap-2">
      {items.map((c) => (
        <li key={c.id} className="rounded-2xl border border-slate-200 bg-white/90 p-3">
          <div className="flex items-start justify-between gap-2">
            <b className="text-[13px] leading-snug">{c.title}</b>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold ${tone[c.status]}`}>{label[c.status]}</span>
          </div>
          <p className="mt-1 text-[12px] leading-snug text-canvas-muted">{c.detail}</p>
          <p className="mt-1 text-[11px] text-canvas-muted">Kaynak: {c.source}</p>
          {!!c.pages?.length && (
            <details className="mt-1.5">
              <summary className="cursor-pointer text-[11.5px] font-bold">{c.pages.length} yer</summary>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {c.pages.map((p, i) => <span key={i} className="inline-flex items-center gap-1"><PageChip p={p} goto={goto} />{p.word && <span className="text-[11px]">{p.word}</span>}</span>)}
              </div>
            </details>
          )}
        </li>
      ))}
    </ul>
  );
}

function Checklist({ view, decide, busy }: { view: AgeView; decide: Decide; busy: boolean }) {
  const [notes, setNotes] = useState<Record<string, string>>({});
  return (
    <div>
      <p className="text-[12px] leading-snug text-canvas-muted">Otomatik denetlenemeyen maddeler. İşaretleyen kişi ve zaman rapora ve PDF’e yazılır.</p>
      <ul className="mt-2 flex flex-col gap-2">
        {view.checklist.map((c) => {
          const s = c.decision?.state;
          const note = notes[c.id] ?? c.decision?.note ?? '';
          return (
            <li key={c.id} className="rounded-2xl border border-slate-200 bg-white/90 p-3">
              <p className="text-[13px] font-bold leading-snug">{c.title}</p>
              <p className="mt-0.5 text-[11px] text-canvas-muted">Kaynak: {c.source}</p>
              <input value={note} onChange={(e) => setNotes((n) => ({ ...n, [c.id]: e.target.value }))} maxLength={500}
                placeholder="Not (isteğe bağlı)" aria-label={`${c.title} notu`}
                className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-[12.5px] outline-none focus:border-canvas-violet" />
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Toggle on={s === 'ok'} tone="ok" disabled={busy} onClick={() => decide({ kind: 'check', id: c.id, state: s === 'ok' ? null : 'ok', note })}>Uygun</Toggle>
                <Toggle on={s === 'not_ok'} tone="bad" disabled={busy} onClick={() => decide({ kind: 'check', id: c.id, state: s === 'not_ok' ? null : 'not_ok', note })}>Uygun değil</Toggle>
              </div>
              <DecisionLine d={c.decision} />
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Sources({ view }: { view: AgeView }) {
  return (
    <details className="group mt-4 rounded-2xl border border-slate-200 bg-white/70 p-3">
      <summary className="flex cursor-pointer list-none items-center justify-between text-[12.5px] font-bold">
        Kaynaklar <ChevronDown className="h-4 w-4 group-open:rotate-180" aria-hidden />
      </summary>
      <ul className="mt-2 flex flex-col gap-1.5 text-[12px]">
        {Object.entries(view.sources).map(([k, s]) => (
          <li key={k} className="break-words">
            <b>{k}</b> — <a className="inline-flex items-center gap-1 text-canvas-violet underline" href={s.url} target="_blank" rel="noreferrer">{s.title}<ExternalLink className="h-3 w-3" aria-hidden /></a>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] text-canvas-muted">Ölçülerin adları ve bant karşılaştırması PDF’in ekindedir.</p>
    </details>
  );
}
