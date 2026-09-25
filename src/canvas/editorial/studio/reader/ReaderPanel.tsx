import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, BookOpenText, Check, Loader2, RotateCcw, Sparkles, X } from 'lucide-react';
import type { PlanPage } from '../../../engine';
import { Note, btnGhost, btnPrimary, errText } from '../../../admin/ui';
import type { EditorCtx } from '../InspectorPanel';
import { Progress } from '../shared';
import { FRONT, readerApi, type ReaderDecision, type ReaderFlag, type ReaderInfo, type ReaderRun, type RunSummary, type TurnItem } from './api';
import { findSpan, replaceTarget, targetText } from './textEdit';

/** Okur paneli: «Çocuk gözüyle» (Zeki AI metni kitabın okur yaşında okur, takıldığı yerleri işaretler) ve resimli
 *  kitapta «Sayfa çevirme» (çift sayfanın son cümlesi merak uyandırıyor mu). Öneriyi uygulamak metni değiştirir ve
 *  sayfa düzeninin otomatik kayıt sırasından gider (Ctrl/Cmd+Z ile ve sürüm geçmişinden geri alınır). */

const fmt = (t: number) => new Intl.DateTimeFormat('tr-TR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(t * 1000));
const band = (b: [number, number] | null) => (b ? (b[0] === b[1] ? `${b[0]}` : `${b[0]}–${b[1]}`) : '');
const STATUS_TR: Record<string, string> = { running: 'Okuyor…', done: 'Bitti', partial: 'Bazı sayfalar okunamadı', failed: 'Okuma yarıda kaldı', interrupted: 'Okuma yarıda kaldı' };

type Kind = 'child' | 'turn';
type ItemRef = { page: string; target: ReaderFlag['target']; id: string; start: number; end: number; quote: string };

function useRun(job: string, summary: RunSummary | null) {
  const qc = useQueryClient();
  const rid = summary?.id ?? null;
  const q = useQuery({
    queryKey: ['studio', 'reader', 'run', job, rid],
    queryFn: () => readerApi.run(job, rid!),
    enabled: !!rid,
    refetchInterval: (s) => ((s.state.data as ReaderRun | undefined)?.status === 'running' || summary?.status === 'running' ? 3000 : false),
  });
  const was = useRef<string | undefined>(undefined);
  useEffect(() => {
    const st = q.data?.status;
    if (was.current === 'running' && st && st !== 'running') void qc.invalidateQueries({ queryKey: ['studio', 'reader', 'info', job] });
    was.current = st;
  }, [q.data?.status, qc, job]);
  return q;
}

export default function ReaderPanel({ ctx, goTo }: { ctx: EditorCtx; goTo: (pid: string) => void }) {
  const job = ctx.job;
  const qc = useQueryClient();
  const info = useQuery({ queryKey: ['studio', 'reader', 'info', job], queryFn: () => readerApi.info(job), staleTime: 10_000, retry: false });
  const [tab, setTab] = useState<Kind>('child');
  const [err, setErr] = useState<string | null>(null);
  const [starting, setStarting] = useState<Kind | null>(null);
  const d = info.data;
  const child = useRun(job, d?.child ?? null);
  const turn = useRun(job, d?.turn ?? null);

  if (info.isLoading) return <p className="text-[12.5px] text-canvas-muted">Yükleniyor…</p>;
  if (info.error || !d) return <Note tone="err">{errText(info.error, 'Okur bilgisi alınamadı.')}</Note>;

  const start = async (kind: Kind) => {
    setErr(null); setStarting(kind);
    try {
      // Bekleyen düzenlemeler önce kaydedilir: Zeki AI sunucudaki son metni okur.
      await ctx.online(async () => (kind === 'child' ? readerApi.startChild(job) : readerApi.startTurn(job)));
      await qc.invalidateQueries({ queryKey: ['studio', 'reader', 'info', job] });
    } catch (e) { setErr(errText(e, 'Okuma başlatılamadı.')); } finally { setStarting(null); }
  };
  const resume = async (rid: string) => {
    setErr(null);
    try {
      await readerApi.resume(job, rid);
      await qc.invalidateQueries({ queryKey: ['studio', 'reader'] });
    } catch (e) { setErr(errText(e, 'Okuma sürdürülemedi.')); }
  };

  return (
    <div className="flex flex-col gap-3">
      {d.picture_book && (
        <div role="tablist" aria-label="Okur araçları" className="flex gap-1">
          {([['child', 'Çocuk gözüyle'], ['turn', 'Sayfa çevirme']] as const).map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
              className={`min-h-9 shrink-0 rounded-full px-3.5 text-[12.5px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] ${tab === k ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink'}`}>
              {l}
            </button>
          ))}
        </div>
      )}
      {err && <Note tone="err">{err}</Note>}
      {(tab === 'child' || !d.picture_book) ? (
        <ChildView ctx={ctx} info={d} run={child.data ?? null} summary={d.child} starting={starting === 'child'}
          onStart={() => start('child')} onResume={resume} goTo={goTo} />
      ) : (
        <TurnView ctx={ctx} info={d} run={turn.data ?? null} summary={d.turn} starting={starting === 'turn'}
          onStart={() => start('turn')} onResume={resume} goTo={goTo} />
      )}
    </div>
  );
}

// ------------------------------------------------------------------ ortak
function RunHeader({ info, summary, run, starting, onStart, onResume, startLabel, what }: {
  info: ReaderInfo; summary: RunSummary | null; run: ReaderRun | null; starting: boolean; onStart: () => void;
  onResume: (rid: string) => void; startLabel: string; what: string;
}) {
  const s = run ?? summary;
  const running = s?.status === 'running';
  const stuck = s && (s.status === 'interrupted' || s.status === 'failed' || s.status === 'partial');
  return (
    <div className="flex flex-col gap-2 rounded-2xl bg-violet-50/60 p-3">
      {s && (
        <div className="text-[12px] leading-snug text-canvas-muted">
          <span className="font-bold text-canvas-ink">{STATUS_TR[s.status] ?? s.status}</span>
          {' · '}{fmt(s.created)} · {s.by} · sürüm {s.plan_rev}
          {s.plan_rev !== info.rev && !running && <span className="block text-amber-800">Metin bu okumadan sonra değişti; bazı işaretler artık tutmayabilir.</span>}
          {s.error && <span className="block text-rose-700">{s.error}</span>}
        </div>
      )}
      {running && s && (
        <div className="flex flex-col gap-1">
          <Progress value={s.progress[0]} total={s.progress[1]} />
          <span className="text-[11.5px] text-canvas-muted">{s.progress[0]} / {s.progress[1]} {what} okundu. Okuma sürerken düzenlemeye devam edebilirsiniz.</span>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {!running && (
          <button type="button" className={btnPrimary} disabled={starting} onClick={onStart}>
            {starting ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Sparkles className="h-4 w-4" aria-hidden />}
            {s ? 'Yeniden oku' : startLabel}
          </button>
        )}
        {stuck && s && <button type="button" className={btnGhost} onClick={() => onResume(s.id)}><RotateCcw className="h-4 w-4" aria-hidden />Kalan yerden sürdür</button>}
      </div>
    </div>
  );
}

function Suggest({ from, to }: { from: string; to: string }) {
  return (
    <span className="leading-relaxed">
      <span className="rd-del">{from}</span>{' '}<ArrowRight className="inline h-3.5 w-3.5 text-canvas-muted" aria-label="yerine" />{' '}<span className="rd-ins">{to}</span>
    </span>
  );
}

function useDecisions(job: string, rid: string | undefined) {
  const [local, setLocal] = useState<Record<string, ReaderDecision | null>>({});
  useEffect(() => setLocal({}), [rid]);
  const decide = async (fid: string, decision: ReaderDecision) => {
    if (!rid) return;
    setLocal((l) => ({ ...l, [fid]: decision === 'open' ? null : decision }));
    await readerApi.decide(job, rid, fid, decision);
  };
  return { local, decide };
}

/** Sayfadaki öneriyi uygular ya da geri alır. Metin artık aynı değilse null (uygulanamaz). */
function edit(ctx: EditorCtx, ref: ItemRef, from: string, to: string): PlanPage | null {
  const page = ctx.plan.pages.find((p) => p.id === ref.page);
  if (!page) return null;
  const span = findSpan(targetText(page, ref.target, ref.id), from, ref.start, ref.start + from.length);
  if (!span) return null;
  return replaceTarget(page, ref.target, ref.id, span[0], span[1], to);
}

// ------------------------------------------------------------------ çocuk gözüyle
function ChildView({ ctx, info, run, summary, starting, onStart, onResume, goTo }: {
  ctx: EditorCtx; info: ReaderInfo; run: ReaderRun | null; summary: RunSummary | null; starting: boolean;
  onStart: () => void; onResume: (rid: string) => void; goTo: (pid: string) => void;
}) {
  const [scope, setScope] = useState<'page' | 'book'>('page');
  const [focus, setFocus] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const { local, decide } = useDecisions(ctx.job, run?.id);
  const flags = run?.flags ?? [];
  const pageId = ctx.page?.id ?? null;
  const onPage = flags.filter((f) => f.page === pageId);
  const age = info.age;
  const decisionOf = (f: ReaderFlag) => (f.fid in local ? local[f.fid] : f.decision);

  const act = async (f: ReaderFlag, what: 'apply' | 'unapply' | 'dismiss' | 'reopen') => {
    setMsg(null);
    try {
      if (what === 'apply' || what === 'unapply') {
        const p = what === 'apply' ? edit(ctx, f, f.quote, f.replacement) : edit(ctx, f, f.replacement, f.quote);
        if (!p) { setMsg('Bu yerdeki metin değişmiş; öneri uygulanamadı.'); return; }
        ctx.setPage(p, `okur:${f.fid}`);
        await decide(f.fid, what === 'apply' ? 'applied' : 'open');
      } else {
        await decide(f.fid, what === 'dismiss' ? 'dismissed' : 'open');
      }
    } catch (e) { setMsg(errText(e, 'Karar kaydedilemedi; metindeki değişiklik kaydedildi.')); }
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[12.5px] leading-snug text-canvas-muted">
        Zeki AI metni <b className="text-canvas-ink">{age ?? '?'} yaşındaki bir okur</b> gibi okur ve takıldığı yerleri işaretler
        {info.band ? ` (kitabın okur yaşı ${band(info.band)}; en küçüğüne göre)` : ''}. Her sayfa {info.passes} kez birbirinden bağımsız okunur;
        yalnız okumaların çoğunluğunda geçen işaret gösterilir.
      </p>
      <RunHeader info={info} summary={summary} run={run} starting={starting} onStart={onStart} onResume={onResume}
        startLabel="Çocuk gözüyle oku" what="sayfa" />
      {msg && <Note tone="warn">{msg}</Note>}
      {run && run.status !== 'running' && run.stats && (
        <p className="text-[11.5px] text-canvas-muted">
          {run.stats.shown} işaret gösteriliyor · okumalarda {run.stats.raw} işaret çıktı, metinde birebir bulunamayan {run.stats.dropped} tanesi atıldı.
        </p>
      )}
      {run && (
        <div role="tablist" aria-label="Kapsam" className="flex gap-1">
          {([['page', `Bu sayfa (${onPage.length})`], ['book', `Tüm kitap (${flags.length})`]] as const).map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={scope === k} onClick={() => setScope(k)}
              className={`min-h-9 rounded-full px-3 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] ${scope === k ? 'bg-canvas-ink text-white' : 'bg-slate-100 text-canvas-ink'}`}>
              {l}
            </button>
          ))}
        </div>
      )}
      {run && scope === 'page' && ctx.page && (
        <>
          <PageText page={ctx.page} flags={onPage.filter((f) => decisionOf(f) !== 'dismissed' && decisionOf(f) !== 'applied')} focus={focus} onFocus={setFocus} />
          {onPage.length === 0 && run.status !== 'running' && <p className="text-[12.5px] text-canvas-muted">Bu sayfada okurun takıldığı bir yer yok.</p>}
          <div className="flex flex-col gap-2">
            {onPage.map((f) => (
              <FlagCard key={f.fid} ctx={ctx} f={f} decision={decisionOf(f)} focused={focus === f.fid} onFocus={() => setFocus(f.fid)} act={act} />
            ))}
          </div>
        </>
      )}
      {run && scope === 'book' && (
        <div className="flex flex-col gap-3">
          {groupByPage(flags).map(([no, list]) => (
            <section key={no} className="flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-[13px] font-extrabold">{no - FRONT}. iç sayfa <span className="font-semibold text-canvas-muted">(kitapta {no}.)</span></h3>
                {list[0].page !== pageId && (
                  <button type="button" className={btnGhost} onClick={() => { goTo(list[0].page); setScope('page'); }}>Sayfaya git</button>
                )}
              </div>
              {list.map((f) => (
                <FlagCard key={f.fid} ctx={ctx} f={f} decision={decisionOf(f)} focused={false} onFocus={() => undefined} act={act} compact />
              ))}
            </section>
          ))}
          {flags.length === 0 && run.status !== 'running' && <p className="text-[12.5px] text-canvas-muted">Okur hiçbir sayfada takılmadı.</p>}
        </div>
      )}
    </div>
  );
}

function groupByPage<T extends { no: number }>(list: T[]): [number, T[]][] {
  const m = new Map<number, T[]>();
  for (const x of list) m.set(x.no, [...(m.get(x.no) ?? []), x]);
  return [...m.entries()].sort((a, b) => a[0] - b[0]);
}

/** Sayfanın metni, okurun işaretleri metnin üstünde. İşarete dokununca kartı öne çıkar. */
function PageText({ page, flags, focus, onFocus }: { page: PlanPage; flags: ReaderFlag[]; focus: string | null; onFocus: (fid: string) => void }) {
  const items = useMemo(() => {
    const out: { key: string; label: string; target: ReaderFlag['target']; id: string; text: string }[] = [];
    for (const b of page.text?.blocks ?? []) out.push({ key: `b:${b.id}`, label: '', target: 'block', id: b.id, text: b.runs.map((r) => r.text).join('') });
    for (const b of page.bubbles) out.push({ key: `u:${b.id}`, label: `Balon${b.speaker ? ` · ${b.speaker}` : ''}`, target: 'bubble', id: b.id, text: b.text });
    for (const t of page.texts) out.push({ key: `t:${t.id}`, label: 'Yazı', target: 'free', id: t.id, text: t.runs.map((r) => r.text).join('') });
    return out.filter((x) => x.text.trim());
  }, [page]);
  if (!items.length) return null;
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white p-3 font-serif text-[14px] leading-relaxed">
      {items.map((it) => {
        const spans = flags.filter((f) => f.target === it.target && f.id === it.id)
          .map((f) => ({ f, s: findSpan(it.text, f.quote, f.start, f.end) }))
          .filter((x): x is { f: ReaderFlag; s: [number, number] } => !!x.s)
          .sort((a, b) => a.s[0] - b.s[0]);
        const parts: ReactNode[] = [];
        let at = 0;
        for (const { f, s } of spans) {
          if (s[0] < at) continue;                      // örtüşen ikinci işaret metinde çizilmez, kartı listede
          if (s[0] > at) parts.push(<Fragment key={`t${at}`}>{it.text.slice(at, s[0])}</Fragment>);
          parts.push(
            <button key={f.fid} type="button" className="rd-mark" data-kind={f.kind} data-on={focus === f.fid}
              aria-label={`${f.label}: ${f.quote}`} onClick={() => onFocus(f.fid)}>
              {it.text.slice(s[0], s[1])}
            </button>,
          );
          at = s[1];
        }
        if (at < it.text.length) parts.push(<Fragment key={`t${at}`}>{it.text.slice(at)}</Fragment>);
        return (
          <p key={it.key} className="whitespace-pre-wrap break-words">
            {it.label && <span className="mr-1.5 font-canvas text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{it.label}</span>}
            {parts}
          </p>
        );
      })}
    </div>
  );
}

function FlagCard({ ctx, f, decision, focused, onFocus, act, compact }: {
  ctx: EditorCtx; f: ReaderFlag; decision: ReaderDecision | null; focused: boolean; onFocus: () => void;
  act: (f: ReaderFlag, what: 'apply' | 'unapply' | 'dismiss' | 'reopen') => void; compact?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (focused) ref.current?.scrollIntoView({ block: 'nearest' }); }, [focused]);
  const page = ctx.plan.pages.find((p) => p.id === f.page);
  const text = page ? targetText(page, f.target, f.id) : null;
  const here = findSpan(text, f.quote, f.start, f.end);
  const applied = decision === 'applied';
  const stale = !applied && !here;
  return (
    <div ref={ref} onClick={onFocus}
      className={`rounded-2xl border bg-white p-3 text-[12.5px] ${focused ? 'border-canvas-violet ring-2 ring-violet-200' : 'border-slate-200'} ${decision === 'dismissed' ? 'opacity-60' : ''}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rd-mark !cursor-default px-1.5 text-[11px] font-bold" data-kind={f.kind}>{f.label}</span>
        <span className="text-[11px] text-canvas-muted">{f.passes > 1 ? `${f.passes} okumanın ${f.votes}'${suffix(f.votes)}` : 'tek okuma'}</span>
        {f.target === 'bubble' && <span className="text-[11px] text-canvas-muted">· balonda</span>}
      </div>
      <p className="mt-1.5 font-serif text-[13.5px] italic leading-snug">«{f.quote}»</p>
      {f.reason && <p className="mt-1 leading-snug"><span className="font-bold">Okur: </span>{f.reason}</p>}
      {f.replacement && !compact && <p className="mt-1.5"><span className="font-bold">Öneri: </span><Suggest from={f.quote} to={f.replacement} /></p>}
      {f.replacement && compact && <p className="mt-1 leading-snug"><span className="font-bold">Öneri: </span>{f.replacement}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {applied && (
          <>
            <span className="inline-flex items-center gap-1 text-[12px] font-bold text-emerald-700"><Check className="h-4 w-4" aria-hidden />Uygulandı</span>
            <button type="button" className={btnGhost} onClick={(e) => { e.stopPropagation(); act(f, 'unapply'); }}>Geri al</button>
          </>
        )}
        {decision === 'dismissed' && (
          <>
            <span className="text-[12px] font-bold text-canvas-muted">Yoksayıldı</span>
            <button type="button" className={btnGhost} onClick={(e) => { e.stopPropagation(); act(f, 'reopen'); }}>Geri al</button>
          </>
        )}
        {!decision && stale && <span className="text-[12px] font-semibold text-amber-800">Bu yerdeki metin okumadan sonra değişti.</span>}
        {!decision && !stale && f.replacement && (
          <button type="button" className={btnPrimary} onClick={(e) => { e.stopPropagation(); act(f, 'apply'); }}>
            <Check className="h-4 w-4" aria-hidden />Öneriyi uygula
          </button>
        )}
        {!decision && (
          <button type="button" className={btnGhost} onClick={(e) => { e.stopPropagation(); act(f, 'dismiss'); }}>
            <X className="h-4 w-4" aria-hidden />Yoksay
          </button>
        )}
      </div>
    </div>
  );
}

/** «3 okumanın 2'sinde» — sayıya gelen bulunma eki. */
function suffix(n: number): string {
  const last = n % 10;
  const tens = n % 100;
  if (n === 0) return 'ında';
  if (tens === 10 || tens === 30) return 'unda';
  if (tens === 20 || tens === 50) return 'sinde';
  if (tens === 70 || tens === 80) return 'inde';
  if (tens === 40 || tens === 60 || tens === 90) return 'ında';
  return ({ 1: 'inde', 2: 'sinde', 3: 'ünde', 4: 'ünde', 5: 'inde', 6: 'sında', 7: 'sinde', 8: 'inde', 9: 'unda' } as Record<number, string>)[last] ?? 'inde';
}

// ------------------------------------------------------------------ sayfa çevirme
function TurnView({ ctx, info, run, summary, starting, onStart, onResume, goTo }: {
  ctx: EditorCtx; info: ReaderInfo; run: ReaderRun | null; summary: RunSummary | null; starting: boolean;
  onStart: () => void; onResume: (rid: string) => void; goTo: (pid: string) => void;
}) {
  const [msg, setMsg] = useState<string | null>(null);
  const { local, decide } = useDecisions(ctx.job, run?.id);
  const spreads = run?.spreads ?? [];
  const weak = spreads.filter((x) => x.status === 'suggested' || x.status === 'no_fix');
  const strong = spreads.filter((x) => x.status === 'strong');
  const decisionOf = (x: TurnItem) => (x.fid in local ? local[x.fid] : x.decision);

  const act = async (x: TurnItem, what: 'accept' | 'unaccept' | 'reject' | 'reopen') => {
    setMsg(null);
    try {
      if ((what === 'accept' || what === 'unaccept') && x.replacement) {
        const p = what === 'accept' ? edit(ctx, x, x.quote, x.replacement) : edit(ctx, x, x.replacement, x.quote);
        if (!p) { setMsg('Bu sayfanın son cümlesi değişmiş; öneri uygulanamadı.'); return; }
        ctx.setPage(p, `okur:${x.fid}`);
        await decide(x.fid, what === 'accept' ? 'accepted' : 'open');
      } else {
        await decide(x.fid, what === 'reject' ? 'rejected' : 'open');
      }
    } catch (e) { setMsg(errText(e, 'Karar kaydedilemedi; metindeki değişiklik kaydedildi.')); }
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[12.5px] leading-snug text-canvas-muted">
        Resimli kitapta okur her çift sayfanın sonunda sayfayı çevirir. Zeki AI her çift sayfanın son cümlesinin
        «sonra ne oldu?» merakı uyandırıp uyandırmadığına bakar; güçlü değilse soru, yarım kalan eylem, ses sözcüğü ya da
        «ama…» gibi bir kalıpla yeni cümle önerir. Güçlü sayfa sonuna öneri yapılmaz.
      </p>
      <RunHeader info={info} summary={summary} run={run} starting={starting} onStart={onStart} onResume={onResume}
        startLabel="Sayfa sonlarını değerlendir" what="çift sayfa" />
      {msg && <Note tone="warn">{msg}</Note>}
      {run && run.status !== 'running' && (
        <p className="text-[11.5px] text-canvas-muted">{spreads.length} çift sayfa değerlendirildi · {strong.length} güçlü · {weak.length} önerili.</p>
      )}
      <div className="flex flex-col gap-2">
        {weak.map((x) => {
          const dec = decisionOf(x);
          const page = ctx.plan.pages.find((p) => p.id === x.page);
          const text = page ? targetText(page, x.target, x.id) : null;
          const stale = dec !== 'accepted' && !findSpan(text, x.quote, x.start, x.end);
          return (
            <div key={x.fid} className={`rounded-2xl border border-slate-200 bg-white p-3 text-[12.5px] ${dec === 'rejected' ? 'opacity-60' : ''}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-[13px] font-extrabold">Sayfa {x.spread.map((n) => n - FRONT).join('–')}
                  <span className="ml-1.5 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-bold text-amber-800">merak {x.strength}</span>
                </span>
                {x.page !== ctx.page?.id && <button type="button" className={btnGhost} onClick={() => goTo(x.page)}>Sayfaya git</button>}
              </div>
              <p className="mt-1.5 font-serif text-[13.5px] italic leading-snug">«{x.quote}»</p>
              {x.status === 'suggested' && x.replacement ? (
                <>
                  <p className="mt-1.5"><span className="font-bold">{x.technique_label ?? 'Öneri'}: </span><Suggest from={x.quote} to={x.replacement} /></p>
                  {x.reason && <p className="mt-1 leading-snug text-canvas-muted">{x.reason}</p>}
                </>
              ) : <p className="mt-1.5 text-canvas-muted">Zeki AI bu sayfa sonu için anlamı koruyan bir cümle öneremedi.</p>}
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {dec === 'accepted' && (
                  <>
                    <span className="inline-flex items-center gap-1 text-[12px] font-bold text-emerald-700"><Check className="h-4 w-4" aria-hidden />Kabul edildi</span>
                    <button type="button" className={btnGhost} onClick={() => act(x, 'unaccept')}>Geri al</button>
                  </>
                )}
                {dec === 'rejected' && (
                  <>
                    <span className="text-[12px] font-bold text-canvas-muted">Reddedildi</span>
                    <button type="button" className={btnGhost} onClick={() => act(x, 'reopen')}>Geri al</button>
                  </>
                )}
                {!dec && stale && <span className="text-[12px] font-semibold text-amber-800">Bu sayfanın son cümlesi değişti.</span>}
                {!dec && !stale && x.status === 'suggested' && (
                  <button type="button" className={btnPrimary} onClick={() => act(x, 'accept')}><Check className="h-4 w-4" aria-hidden />Kabul et</button>
                )}
                {!dec && <button type="button" className={btnGhost} onClick={() => act(x, 'reject')}><X className="h-4 w-4" aria-hidden />Reddet</button>}
              </div>
            </div>
          );
        })}
      </div>
      {strong.length > 0 && (
        <p className="flex items-start gap-1.5 text-[12px] leading-snug text-canvas-muted">
          <BookOpenText className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          Sayfa sonu zaten güçlü: {strong.map((x) => x.spread.map((n) => n - FRONT).join('–')).join(', ')}.
        </p>
      )}
      {spreads.some((x) => x.status === 'failed') && (
        <Note tone="warn">Bazı çift sayfalar değerlendirilemedi: {spreads.filter((x) => x.status === 'failed').map((x) => x.spread.map((n) => n - FRONT).join('–')).join(', ')}.</Note>
      )}
    </div>
  );
}
