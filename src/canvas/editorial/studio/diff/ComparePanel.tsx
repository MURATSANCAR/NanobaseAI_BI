import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeftRight, ChevronDown, ChevronRight, FileDown, Loader2 } from 'lucide-react';
import { Note, btnGhost, errText, field, label as labelCls } from '../../../admin/ui';
import { FRONT, versionsApi, type Diff, type DiffPage, type Segment, type VersionJob } from '../reader/api';
import '../reader/reader.css';

/** Sürüm farkı: iki sürüm sayfa sayfa yan yana. Sürümler bu işin kayıt geçmişi (her kayıt bir sürüm) ve aynı
 *  kitabın başka işleri. Metin farkı kelime düzeyinde, yerleşim farkı madde madde, görsel farkı önizlemede kırmızı
 *  çerçeve. Değişmeyen sayfalar tek satıra daralır. «Rapor indir» aynı karşılaştırmayı PDF olarak verir. */

const fmtIso = (at: string | null | undefined) => {
  if (!at) return '';
  const d = new Date(at);
  return Number.isNaN(d.getTime()) ? at : new Intl.DateTimeFormat('tr-TR', { dateStyle: 'short', timeStyle: 'short' }).format(d);
};
const fmtSec = (t: number | null) => (t ? new Intl.DateTimeFormat('tr-TR', { dateStyle: 'short' }).format(new Date(t * 1000)) : '');
const STATUS: Record<DiffPage['status'], [string, string]> = {
  changed: ['Değişti', 'bg-violet-50 text-canvas-violet'], added: ['Eklendi', 'bg-emerald-50 text-emerald-700'],
  removed: ['Silindi', 'bg-rose-50 text-rose-700'], same: ['Aynı', 'bg-slate-100 text-canvas-muted'],
};

function defaults(jobs: VersionJob[], job: string): [string, string] | null {
  const me = jobs.find((j) => j.id === job);
  if (!me) return null;
  const older = me.revs.map((r) => r.rev).filter((r) => r < me.current).sort((x, y) => y - x)[0];
  if (older) return [`${job}:${older}`, `${job}:current`];
  const other = jobs.find((j) => j.id !== job);
  return other ? [`${other.id}:current`, `${job}:current`] : null;
}

function VersionSelect({ id, label, value, onChange, jobs }: { id: string; label: string; value: string; onChange: (v: string) => void; jobs: VersionJob[] }) {
  return (
    <label htmlFor={id} className="flex min-w-0 flex-1 flex-col gap-1">
      <span className={labelCls}>{label}</span>
      <select id={id} className={`${field} min-h-10 w-full min-w-0`} value={value} onChange={(e) => onChange(e.target.value)}>
        {jobs.map((j) => (
          <optgroup key={j.id} label={j.self ? 'Bu iş' : `Aynı kitabın başka işi · ${fmtSec(j.created_at)}${j.created_by ? ` · ${j.created_by}` : ''}`}>
            <option value={`${j.id}:current`}>Şimdiki hâli (sürüm {j.current}, {j.pages} sayfa)</option>
            {j.revs.filter((r) => r.rev !== j.current).map((r) => (
              <option key={r.rev} value={`${j.id}:${r.rev}`}>Sürüm {r.rev} · {fmtIso(r.at)} · {r.by}{r.what ? ` · ${r.what}` : ''}</option>
            ))}
          </optgroup>
        ))}
      </select>
    </label>
  );
}

export default function ComparePanel({ job, goTo }: { job: string; goTo: (pid: string) => void }) {
  const list = useQuery({ queryKey: ['studio', 'versions', job], queryFn: () => versionsApi.list(job), staleTime: 10_000, retry: false });
  const [pair, setPair] = useState<[string, string] | null>(null);
  useEffect(() => {
    if (!pair && list.data) setPair(defaults(list.data.jobs, job));
  }, [list.data, pair, job]);
  const diff = useQuery({
    queryKey: ['studio', 'versions', 'compare', job, pair?.[0], pair?.[1]],
    queryFn: () => versionsApi.compare(job, pair![0], pair![1]),
    enabled: !!pair && pair[0] !== pair[1],
    staleTime: 60_000,
    retry: false,
  });
  const [showSame, setShowSame] = useState(false);

  if (list.isLoading) return <p className="text-[12.5px] text-canvas-muted">Sürümler yükleniyor…</p>;
  if (list.error || !list.data) return <Note tone="err">{errText(list.error, 'Sürümler alınamadı.')}</Note>;
  if (!pair) return <Note tone="info">Karşılaştırılacak ikinci bir sürüm yok. Sayfa düzeninde her kayıt yeni bir sürüm olur.</Note>;

  const d = diff.data;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <VersionSelect id="rd-a" label="Önceki" value={pair[0]} onChange={(v) => setPair([v, pair[1]])} jobs={list.data.jobs} />
        <button type="button" className={`${btnGhost} self-start sm:self-auto`} aria-label="Sürümlerin yerini değiştir"
          onClick={() => setPair([pair[1], pair[0]])}><ArrowLeftRight className="h-4 w-4" aria-hidden /></button>
        <VersionSelect id="rd-b" label="Yeni" value={pair[1]} onChange={(v) => setPair([pair[0], v])} jobs={list.data.jobs} />
      </div>
      {pair[0] === pair[1] && <Note tone="info">İki farklı sürüm seçin.</Note>}
      {diff.isFetching && !d && <p className="flex items-center gap-2 text-[12.5px] text-canvas-muted"><Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />Karşılaştırılıyor…</p>}
      {diff.error && <Note tone="err">{errText(diff.error, 'Karşılaştırılamadı.')}</Note>}
      {d && (
        <>
          <Summary d={d} />
          <div className="flex flex-wrap items-center gap-2">
            <a className={btnGhost} href={versionsApi.reportUrl(job, pair[0], pair[1])} download>
              <FileDown className="h-4 w-4" aria-hidden />Değişiklik raporu (PDF)
            </a>
            <label className="inline-flex min-h-10 cursor-pointer items-center gap-2 text-[12.5px] font-bold">
              <input type="checkbox" className="h-4 w-4 accent-canvas-violet" checked={showSame} onChange={(e) => setShowSame(e.target.checked)} />
              Değişmeyen sayfaları da aç
            </label>
          </div>
          <Rows job={job} d={d} a={pair[0]} b={pair[1]} showSame={showSame} goTo={goTo} />
        </>
      )}
    </div>
  );
}

function Summary({ d }: { d: Diff }) {
  const c = d.counts;
  return (
    <div className="rounded-2xl bg-violet-50/60 p-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {([['changed', 'Değişen'], ['added', 'Eklenen'], ['removed', 'Silinen'], ['same', 'Aynı']] as const).map(([k, l]) => (
          <div key={k} className="min-w-0">
            <div className={`text-[20px] font-extrabold tabular-nums ${STATUS[k][1].split(' ')[1]}`}>{c[k]}</div>
            <div className="text-[11.5px] text-canvas-muted">{l} sayfa</div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[12px] text-canvas-muted">
        Metinde <span className="rd-ins">{d.words.ins} kelime eklendi</span>, <span className="rd-del">{d.words.del} kelime silindi</span>.
        {d.global.length > 0 && <span className="mt-1 block font-semibold text-canvas-ink">{d.global.join(' · ')}</span>}
      </p>
      <p className="mt-1 text-[11.5px] text-canvas-muted">{d.a.label} → {d.b.label}</p>
    </div>
  );
}

type Group = { kind: 'row'; p: DiffPage } | { kind: 'same'; pages: DiffPage[] };

function Rows({ job, d, a, b, showSame, goTo }: { job: string; d: Diff; a: string; b: string; showSame: boolean; goTo: (pid: string) => void }) {
  const groups = useMemo(() => {
    const out: Group[] = [];
    for (const p of d.pages) {
      if (p.status === 'same' && !showSame) {
        const last = out[out.length - 1];
        if (last?.kind === 'same') last.pages.push(p); else out.push({ kind: 'same', pages: [p] });
      } else out.push({ kind: 'row', p });
    }
    return out;
  }, [d, showSame]);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const ratio = d.page ? d.page.w / d.page.h : 0.72;
  const canGo = d.b.current && d.b.job === job;
  return (
    <div className="flex flex-col gap-2">
      {groups.map((g) => {
        if (g.kind === 'row') return <Row key={`${g.p.a?.id}-${g.p.b?.id}`} job={job} p={g.p} a={a} b={b} ratio={ratio} onGo={canGo && g.p.b ? () => goTo(g.p.b!.id) : null} />;
        const first = g.pages[0].b!.no - FRONT;
        const last = g.pages[g.pages.length - 1].b!.no - FRONT;
        const key = `s${first}`;
        const isOpen = open.has(key);
        return (
          <div key={key} className="rounded-2xl border border-dashed border-slate-200">
            <button type="button" aria-expanded={isOpen} onClick={() => setOpen((s) => { const n = new Set(s); if (n.has(key)) n.delete(key); else n.add(key); return n; })}
              className="flex min-h-10 w-full items-center gap-2 px-3 text-left text-[12.5px] font-bold text-canvas-muted">
              {isOpen ? <ChevronDown className="h-4 w-4" aria-hidden /> : <ChevronRight className="h-4 w-4" aria-hidden />}
              {first === last ? `Sayfa ${first} değişmedi` : `Sayfa ${first}–${last} değişmedi (${g.pages.length} sayfa)`}
            </button>
            {isOpen && (
              <div className="flex flex-col gap-2 px-2 pb-2">
                {g.pages.map((p) => <Row key={`${p.a?.id}-${p.b?.id}`} job={job} p={p} a={a} b={b} ratio={ratio} onGo={canGo && p.b ? () => goTo(p.b!.id) : null} />)}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function useInView<T extends Element>() {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    if (typeof IntersectionObserver === 'undefined') { setSeen(true); return; }
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { setSeen(true); io.disconnect(); } }, { rootMargin: '300px' });
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);
  return { ref, seen };
}

function Row({ job, p, a, b, ratio, onGo }: { job: string; p: DiffPage; a: string; b: string; ratio: number; onGo: (() => void) | null }) {
  const { ref, seen } = useInView<HTMLDivElement>();
  const visual = useQuery({
    queryKey: ['studio', 'versions', 'visual', job, a, b, p.a?.id, p.b?.id],
    queryFn: () => versionsApi.visual(job, a, b, p.a?.id ?? null, p.b?.id ?? null),
    enabled: seen && !!p.a && !!p.b && p.status !== 'same',
    staleTime: Infinity,
    retry: false,
  });
  const [st, tone] = STATUS[p.status];
  const title = p.b ? `Sayfa ${p.b.no - FRONT}` : `Sayfa ${p.a!.no - FRONT} (önceki)`;
  const moved = p.a && p.b && p.a.no !== p.b.no ? `önceki sürümde ${p.a.no - FRONT}. sayfa` : '';
  const regions = p.status === 'added' || p.status === 'removed' ? [] : visual.data?.regions ?? [];
  return (
    <div ref={ref} className="rounded-2xl border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-[14px] font-extrabold">{title}</span>
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${tone}`}>{st}</span>
          {moved && <span className="text-[11.5px] text-canvas-muted">{moved}</span>}
          {p.match === 'content' && <span className="text-[11.5px] text-canvas-muted">içerikten eşleşti</span>}
        </div>
        {onGo && <button type="button" className={btnGhost} onClick={onGo}>Sayfaya git</button>}
      </div>
      <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,300px)_minmax(0,1fr)]">
        <div className="grid grid-cols-2 gap-2">
          <Shot label="Önceki" src={p.a && seen ? versionsApi.previewUrl(job, a, p.a.id, 480) : null} ratio={ratio} regions={[]} />
          <Shot label="Yeni" src={p.b && seen ? versionsApi.previewUrl(job, b, p.b.id, 480) : null} ratio={ratio} regions={regions}
            busy={visual.isFetching} />
        </div>
        <div className="min-w-0 text-[12.5px]">
          {p.text.map((t, i) => <TextDiff key={i} label={t.label} segments={t.segments} />)}
          {p.layout.length > 0 && (
            <div className="mt-1">
              <div className={labelCls}>Yerleşim</div>
              <ul className="mt-1 list-disc pl-4 leading-snug">
                {p.layout.map((l, i) => <li key={i}>{l.text}</li>)}
              </ul>
            </div>
          )}
          {p.status === 'same' && <p className="text-canvas-muted">Metin ve yerleşim aynı.</p>}
          {p.status === 'changed' && !p.text.length && !p.layout.length && <p className="text-canvas-muted">Yalnız görünüşte fark var; önizlemede işaretli.</p>}
          {p.overflow && <p className="mt-1 font-semibold text-amber-800">Yeni sürümde metin kutusuna sığmıyor.</p>}
          {visual.data && regions.length > 0 && (
            <p className="mt-1 text-[11.5px] text-canvas-muted">Görselde {regions.length} bölge değişti (sayfanın %{Math.max(1, Math.round(visual.data.share * 100))}'i).</p>
          )}
          {visual.error && <p className="mt-1 text-[11.5px] text-canvas-muted">Görsel fark çizilemedi.</p>}
        </div>
      </div>
    </div>
  );
}

function Shot({ label, src, ratio, regions, busy }: { label: string; src: string | null; ratio: number; regions: { x: number; y: number; w: number; h: number }[]; busy?: boolean }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  return (
    <figure className="min-w-0">
      <figcaption className="mb-1 flex items-center gap-1 text-[11px] font-bold text-canvas-muted">
        {label}{busy && <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" aria-label="görsel fark hesaplanıyor" />}
      </figcaption>
      <div className="relative w-full overflow-hidden rounded-lg bg-slate-100 ring-1 ring-slate-200" style={{ aspectRatio: String(ratio) }}>
        {src && !failed ? (
          <img src={src} alt={`${label} sürümün sayfa önizlemesi`} loading="lazy" decoding="async" onError={() => setFailed(true)} className="absolute inset-0 h-full w-full object-fill" />
        ) : (
          <span className="absolute inset-0 flex items-center justify-center p-2 text-center text-[11px] text-canvas-muted">{src ? 'Önizleme yok' : failed ? '' : 'Bu sürümde yok'}</span>
        )}
        {regions.map((r, i) => (
          <span key={i} className="rd-region" style={{ left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.w * 100}%`, height: `${r.h * 100}%` }} />
        ))}
      </div>
    </figure>
  );
}

const WORDS = /\S+\s*/g;

function shorten(segs: Segment[], keep = 12): Segment[] {
  return segs.map((s, i) => {
    if (s.op !== 'eq') return s;
    const w = s.text.match(WORDS) ?? [s.text];
    const first = i === 0;
    const last = i === segs.length - 1;
    const room = keep * (first || last ? 1 : 2);
    if (w.length <= room + 2) return s;
    if (first) return { op: 'eq', text: `… ${w.slice(-keep).join('')}` };
    if (last) return { op: 'eq', text: `${w.slice(0, keep).join('').trimEnd()} …` };
    return { op: 'eq', text: `${w.slice(0, keep).join('')}… ${w.slice(-keep).join('')}` };
  });
}

function TextDiff({ label, segments }: { label: string; segments: Segment[] }) {
  const [full, setFull] = useState(false);
  const short = useMemo(() => shorten(segments), [segments]);
  const cut = short.some((s, i) => s.text !== segments[i].text);
  const segs = full ? segments : short;
  return (
    <div className="mb-2">
      <div className={labelCls}>{label}</div>
      <p className="mt-0.5 whitespace-pre-wrap break-words font-serif text-[13.5px] leading-relaxed">
        {segs.map((s, i) => (s.op === 'ins' ? <ins key={i} className="rd-ins">{s.text}</ins> : s.op === 'del' ? <del key={i} className="rd-del">{s.text}</del> : <span key={i}>{s.text}</span>))}
      </p>
      {cut && <button type="button" className="mt-0.5 text-[11.5px] font-bold text-canvas-violet underline" onClick={() => setFull((f) => !f)}>{full ? 'Kısalt' : 'Tüm metni göster'}</button>}
    </div>
  );
}
