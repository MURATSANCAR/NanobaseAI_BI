import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { Note } from '../../../admin/ui';
import { press } from '../shared';
import { SCREEN, proofApi, useProofReport, type ProofBook, type ProofReport, type ProofTarget } from './api';

/** Baskı provası: aynı sayfa solda ekrandaki, sağda seçili kâğıda basılmış hâliyle; aradaki çizgi sürüklenir
 *  (dokunmada yatay sürükleme, dikey kaydırma sayfaya kalır; klavyede ok tuşları). Renk kaybı ve mürekkep fazlası
 *  isteğe bağlı taranmış katman olarak provanın üstüne konur. Kaydırıcı parmağı birebir izler, animasyon yoktur. */

type Props = { jobId: string; book: ProofBook; paper: string; rev: string; pageHint: number };

const pct = (v: number) => `%${v.toLocaleString('tr-TR', { maximumFractionDigits: v < 1 ? 2 : 1 })}`;

/** Önbelleği paylaşmak için genişlik basamaklı istenir. */
function widthFor(px: number, cover: boolean) {
  const steps = cover ? [1400, 2000, 3000] : [600, 900, 1200, 1600];
  const want = px * Math.min(window.devicePixelRatio || 1, 2);
  return steps.find((s) => s >= want) ?? steps[steps.length - 1];
}

export default function ProofCompare({ jobId, book, paper, rev, pageHint }: Props) {
  const [target, setTarget] = useState<ProofTarget>({ kind: 'page', n: Math.min(Math.max(1, pageHint), book.pages) });
  const [paperTone, setPaperTone] = useState(true);
  const [showGamut, setShowGamut] = useState(true);
  const [showTac, setShowTac] = useState(true);
  const [pos, setPos] = useState(50);
  const [loaded, setLoaded] = useState('');
  const box = useRef<HTMLDivElement>(null);
  const clip = useRef<HTMLDivElement>(null);
  const line = useRef<HTMLDivElement>(null);
  const drag = useRef<number | null>(null);
  const [w, setW] = useState(900);

  const cover = target.kind === 'cover';
  const paperInfo = book.papers.find((p) => p.key === paper);
  const width = cover ? book.cover?.size_mm?.[0] ?? 2 * book.trim_w + 2 * book.bleed : book.trim_w + 2 * book.bleed;
  const height = book.trim_h + 2 * book.bleed;

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(widthFor(el.getBoundingClientRect().width, cover)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [cover]);

  // Çizgi konumu doğrudan öğeye yazılır (her harekette yeniden çizim yok).
  const apply = (p: number) => {
    if (clip.current) clip.current.style.clipPath = `inset(0 0 0 ${p}%)`;
    if (line.current) line.current.style.transform = `translateX(${(p / 100) * (box.current?.clientWidth ?? 0)}px)`;
  };
  useLayoutEffect(() => { if (drag.current === null) apply(pos); });
  useEffect(() => {
    const ro = new ResizeObserver(() => apply(pos));
    if (box.current) ro.observe(box.current);
    return () => ro.disconnect();
  }, [pos]);

  const at = (clientX: number) => {
    const r = box.current!.getBoundingClientRect();
    return Math.min(100, Math.max(0, ((clientX - r.left) / r.width) * 100));
  };
  const onDown = (e: React.PointerEvent) => {
    if (drag.current !== null) return;               // ikinci parmak konumu zıplatmaz
    drag.current = e.pointerId;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const p = at(e.clientX);
    apply(p);
    setPos(p);
  };
  const onMove = (e: React.PointerEvent) => {
    if (drag.current !== e.pointerId) return;
    apply(at(e.clientX));
  };
  const onUp = (e: React.PointerEvent) => {
    if (drag.current !== e.pointerId) return;
    drag.current = null;
    setPos(at(e.clientX));
  };

  const screenUrl = proofApi.imageUrl(jobId, target, SCREEN, w, rev);
  const proofUrl = proofApi.imageUrl(jobId, target, paper, w, rev, paperTone ? 'paper' : 'plain');
  const report = useProofReport(jobId, target, paper, w, rev);
  const r: ProofReport | undefined = report.data;
  const ready = loaded === proofUrl;

  const step = (d: number) => {
    if (target.kind === 'cover') return;
    setTarget({ kind: 'page', n: Math.min(book.pages, Math.max(1, target.n + d)) });
  };

  const chip = (on: boolean) =>
    `inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3 text-[12px] font-bold ${press} ${on ? 'border-canvas-violet bg-violet-50 text-canvas-violet' : 'border-slate-200 bg-white/80 text-canvas-ink'}`;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {book.cover && (
          <button type="button" className={chip(cover)} aria-pressed={cover} onClick={() => setTarget({ kind: 'cover' })}>Kapak</button>
        )}
        <div className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white/80 p-0.5">
          <button type="button" aria-label="Önceki sayfa" disabled={!cover && target.n <= 1}
            onClick={() => (cover ? setTarget({ kind: 'page', n: 1 }) : step(-1))}
            className={`inline-flex h-9 w-9 items-center justify-center rounded-lg disabled:opacity-40 ${press}`}>
            <ChevronLeft className="h-4 w-4" aria-hidden />
          </button>
          <label className="sr-only" htmlFor="proof-page">Sayfa</label>
          <select id="proof-page" value={cover ? '' : target.n}
            onChange={(e) => setTarget({ kind: 'page', n: Number(e.target.value) })}
            className="h-9 rounded-lg bg-transparent px-1 font-mono text-[12px] tabular-nums outline-none">
            {cover && <option value="">kapak</option>}
            {Array.from({ length: book.pages }, (_, i) => <option key={i + 1} value={i + 1}>{`s. ${i + 1} / ${book.pages}`}</option>)}
          </select>
          <button type="button" aria-label="Sonraki sayfa" disabled={!cover && target.n >= book.pages}
            onClick={() => (cover ? setTarget({ kind: 'page', n: 1 }) : step(1))}
            className={`inline-flex h-9 w-9 items-center justify-center rounded-lg disabled:opacity-40 ${press}`}>
            <ChevronRight className="h-4 w-4" aria-hidden />
          </button>
        </div>
        <span className="hidden flex-1 md:block" />
        <button type="button" className={chip(paperTone)} aria-pressed={paperTone} onClick={() => setPaperTone((v) => !v)}
          title="Kâğıdın kendi rengi ve mürekkebin en koyu tonu (kapalıyken beyaz, ekran beyazı sayılır)">
          <span className="h-3 w-3 rounded-full border border-slate-300" style={{ background: paperInfo?.white ?? '#fff' }} aria-hidden />
          Kâğıt tonu
        </button>
        <button type="button" className={chip(showGamut)} aria-pressed={showGamut} onClick={() => setShowGamut((v) => !v)}>
          <span className="proof-swatch proof-swatch-gamut" aria-hidden />Renk kaybı
        </button>
        <button type="button" className={chip(showTac)} aria-pressed={showTac} onClick={() => setShowTac((v) => !v)}>
          <span className="proof-swatch proof-swatch-tac" aria-hidden />Mürekkep fazlası
        </button>
      </div>

      <div ref={box} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
        className="proof-compare relative mx-auto w-full select-none overflow-hidden rounded-xl bg-slate-100 shadow-md"
        style={{ aspectRatio: `${width} / ${height}`, maxWidth: cover ? '100%' : `min(100%, calc(72vh * ${width / height}))` }}>
        <img src={screenUrl} alt="Ekranda" draggable={false} className="absolute inset-0 h-full w-full" />
        <div ref={clip} className="absolute inset-0" style={{ clipPath: `inset(0 0 0 ${pos}%)` }}>
          <img src={proofUrl} alt={`Baskıda: ${paperInfo?.label ?? ''}`} draggable={false} onLoad={() => setLoaded(proofUrl)}
            className="absolute inset-0 h-full w-full" />
          {showGamut && ready && (
            <img src={proofApi.imageUrl(jobId, target, paper, w, rev, 'gamut')} alt="" draggable={false} className="absolute inset-0 h-full w-full" />
          )}
          {showTac && ready && (
            <img src={proofApi.imageUrl(jobId, target, paper, w, rev, 'tac')} alt="" draggable={false} className="absolute inset-0 h-full w-full" />
          )}
          {!ready && (
            <span className="absolute right-2 top-9 inline-flex items-center gap-1.5 rounded-full bg-white/90 px-2.5 py-1 text-[11px] font-bold text-canvas-violet shadow-sm">
              <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden />Prova hazırlanıyor…
            </span>
          )}
        </div>
        <span className="pointer-events-none absolute left-2 top-2 rounded-full bg-black/55 px-2 py-0.5 text-[11px] font-bold text-white">Ekranda</span>
        <span className="pointer-events-none absolute right-2 top-2 rounded-full bg-canvas-violet/90 px-2 py-0.5 text-[11px] font-bold text-white">
          Baskıda · {paperInfo?.label}
        </span>
        <div ref={line} className="pointer-events-none absolute inset-y-0 left-0 w-0" aria-hidden>
          <div className="absolute inset-y-0 -left-px w-0.5 bg-white shadow-[0_0_0_1px_rgba(20,24,40,0.25)]" />
          <div className="absolute left-0 top-1/2 flex h-9 w-9 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white text-canvas-ink shadow-md">
            <ChevronLeft className="-mr-1 h-3.5 w-3.5" /><ChevronRight className="-ml-1 h-3.5 w-3.5" />
          </div>
        </div>
        <label className="sr-only" htmlFor="proof-split">Ekran ile baskı arasındaki çizgi</label>
        <input id="proof-split" type="range" min={0} max={100} value={Math.round(pos)} onChange={(e) => setPos(Number(e.target.value))}
          className="sr-only" />
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <Stat tone={!r ? 'info' : r.gamut_share >= 5 ? 'warn' : 'ok'} title="Renk kaybı">
          {!r ? (report.isError ? 'Ölçülemedi.' : 'Ölçülüyor…') : r.gamut_share === 0
            ? `${r.label} kâğıtta ekrandaki renkler korunuyor.`
            : `${cover ? 'Kapağın' : 'Sayfanın'} ${pct(r.gamut_share)} kadarında renk baskıda belirgin biçimde soluklaşır ya da ton değiştirir (taranmış alan).`}
        </Stat>
        <Stat tone={!r ? 'info' : r.tac_share > 0 ? 'warn' : 'ok'} title="Mürekkep yükü">
          {!r ? '…' : (
            <>
              En yüksek {pct(r.tac_max)} · bu kâğıtta sınır {pct(r.tac_limit)}.{' '}
              {r.tac_share > 0 ? `${pct(r.tac_share)} alanda sınır aşılıyor: kuruma ve sayfaların yapışma riski, matbaaya danışın.` : 'Sınırın altında.'}
              <span className="mt-0.5 block font-normal text-canvas-muted">
                {r.tac_source === 'baski' ? 'Matbaaya gidecek baskı dosyasından ölçüldü.' : 'Baskı dosyası henüz üretilmedi; ölçüm bu provadan.'}
              </span>
            </>
          )}
        </Stat>
      </div>
      {paperInfo && <p className="text-[11px] text-canvas-muted">{paperInfo.note} Ekran ayarı ve ortam ışığı sonucu etkiler; son onay matbaa provasıyla verilir.</p>}
    </div>
  );
}

function Stat({ tone, title, children }: { tone: 'ok' | 'warn' | 'info'; title: string; children: React.ReactNode }) {
  return (
    <Note tone={tone}>
      <span className="block text-[10.5px] font-extrabold uppercase tracking-wide opacity-80">{title}</span>
      {children}
    </Note>
  );
}
