import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react';
import { ghostBtn, press } from '../shared';
import { epubApi, type EpubPage, type EpubResult } from './api';
import { useReadAloud } from './useReadAloud';

/** Tarayıcıda basit önizleme: e-kitabın kendi sayfaları çerçevede, sayfa sayfa. Sabit sayfada sayfa kitabın ölçüsüyle
 *  dizilir ve kutuya sığdırılır; geniş ekranda açılım (sol + sağ sayfa), telefonda tek sayfa. Akışkanda bölüm bölüm,
 *  çerçeve kendi içinde kayar. Sayfa değişimi hareketsiz: ok tuşuyla art arda çevrilir. Çerçevede betik çalışmaz.
 *  Sesli e-kitapta «Dinle»: görünen sayfa(lar) e-kitabın kendi sesi ve ses eşlemesiyle okunur, okunan kelime vurgulanır,
 *  sayfa bitince önizleme sonraki sayfaya geçip okumayı sürdürür. */

type Props = { jobId: string; result: EpubResult };

function spreadsOf(pages: EpubPage[]): EpubPage[][] {
  const out: EpubPage[][] = [];
  let open: EpubPage[] | null = null;
  for (const p of pages) {
    if (p.side === 'left') {
      if (open) out.push(open);
      open = [p];
    } else if (p.side === 'right') {
      out.push(open ? [...open, p] : [p]);
      open = null;
    } else {
      if (open) out.push(open);
      open = null;
      out.push([p]);
    }
  }
  if (open) out.push(open);
  return out;
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

export default function EpubPreview({ jobId, result }: Props) {
  const fixed = result.layout === 'fixed' && !!result.viewport;
  const [box, width] = useWidth<HTMLDivElement>();
  const wide = width >= 640;
  const groups = useMemo(
    () => (fixed ? (wide ? spreadsOf(result.pages) : result.pages.map((p) => [p])) : result.pages.map((p) => [p])),
    [fixed, wide, result.pages],
  );
  const [i, setI] = useState(0);
  const at = Math.min(i, groups.length - 1);
  // Ekran genişliği tek sayfa ↔ açılım arasında değişince aynı sayfada kalınır.
  const anchor = useRef<string | null>(null);
  useEffect(() => {
    if (!anchor.current) return;
    const k = groups.findIndex((g) => g.some((p) => p.href === anchor.current));
    if (k >= 0) setI(k);
  }, [groups]);
  const go = (n: number) => {
    const k = Math.max(0, Math.min(groups.length - 1, n));
    anchor.current = groups[k]?.[0]?.href ?? null;
    setI(k);
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'ArrowRight') { e.preventDefault(); go(at + 1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); go(at - 1); }
  };
  const current = groups[at] ?? [];
  const label = current.map((p) => (p.no ? `s. ${p.no}` : p.title)).join(' – ');
  const frameMap = useRef(new Map<string, HTMLIFrameElement>());
  const frameRef = (href: string) => (el: HTMLIFrameElement | null) => {
    if (el) frameMap.current.set(href, el);
    else frameMap.current.delete(href);
  };
  const listen = useReadAloud(jobId, result.build, current, frameMap, () => {
    // Sesi olan sonraki sayfaya geç (kapak, künye gibi sessiz sayfalar atlanır).
    const next = groups.findIndex((g, k) => k > at && g.some((p) => p.smil));
    if (next < 0) return false;
    go(next);
    return true;
  });

  let frames: ReactNode;
  if (fixed) {
    const [vw, vh] = result.viewport!;
    const slots = wide ? 2 : 1;
    const scale = width ? Math.min((width - 8) / (vw * slots), 1) : 0.3;
    const lone = current.length === 1;
    frames = (
      <div className="flex justify-center rounded-2xl bg-slate-100/70 p-2">
        {wide && lone && current[0].side === 'right' && <div style={{ width: vw * scale }} aria-hidden />}
        {current.map((p) => (
          <div key={p.href} className="overflow-hidden bg-white shadow-md" style={{ width: vw * scale, height: vh * scale }}>
            <iframe
              ref={frameRef(p.href)}
              title={`E-kitap önizlemesi: ${p.title}`}
              src={epubApi.contentUrl(jobId, result.build, p.href)}
              sandbox="allow-same-origin"
              loading="lazy"
              className="block origin-top-left border-0"
              style={{ width: vw, height: vh, transform: `scale(${scale})` }}
            />
          </div>
        ))}
        {wide && lone && current[0].side === 'left' && <div style={{ width: vw * scale }} aria-hidden />}
      </div>
    );
  } else {
    const p = current[0];
    frames = p ? (
      <iframe
        ref={frameRef(p.href)}
        title={`E-kitap önizlemesi: ${p.title}`}
        src={epubApi.contentUrl(jobId, result.build, p.href)}
        sandbox="allow-same-origin"
        className="block h-[70vh] w-full rounded-2xl border border-slate-200 bg-white"
      />
    ) : null;
  }

  return (
    <div ref={box} tabIndex={0} onKeyDown={onKey} aria-label="E-kitap önizlemesi; sayfa çevirmek için sol ve sağ ok tuşları"
      className="flex flex-col gap-2 rounded-2xl outline-none focus-visible:ring-2 focus-visible:ring-canvas-violet/40">
      <div className="flex items-center justify-between gap-2">
        <button type="button" className={ghostBtn} onClick={() => go(at - 1)} disabled={at <= 0} aria-label="Önceki sayfa">
          <ChevronLeft className="h-4 w-4" aria-hidden />
        </button>
        {fixed ? (
          <span className="text-center text-[12px] font-bold text-canvas-muted" aria-live="polite">{label} · {at + 1}/{groups.length}</span>
        ) : (
          <select value={at} onChange={(e) => go(Number(e.target.value))} aria-label="Bölüm"
            className="min-h-10 min-w-0 flex-1 rounded-xl border border-slate-200 bg-white/90 px-2 text-base font-semibold sm:text-[12.5px]">
            {groups.map((g, k) => <option key={g[0].href} value={k}>{g[0].title}</option>)}
          </select>
        )}
        <button type="button" className={ghostBtn} onClick={() => go(at + 1)} disabled={at >= groups.length - 1} aria-label="Sonraki sayfa">
          <ChevronRight className="h-4 w-4" aria-hidden />
        </button>
      </div>
      {result.audio?.on && (
        <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200/80 bg-white/80 p-2">
          <button type="button" onClick={listen.toggle} disabled={!listen.hasAudio && !listen.playing}
            aria-label={listen.playing ? 'Dinlemeyi durdur' : 'Bu sayfayı dinle'}
            className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-canvas-coral to-canvas-violet text-white shadow-md disabled:opacity-40 ${press}`}>
            {listen.playing ? <Pause className="h-5 w-5" aria-hidden /> : <Play className="ml-0.5 h-5 w-5" aria-hidden />}
          </button>
          <span className="min-w-0 flex-1 text-[12px] leading-snug text-canvas-muted" aria-live="polite">
            {listen.error ? <span className="text-rose-700">{listen.error}</span>
              : listen.playing ? 'Okunuyor; okunan kelime e-kitaptaki gibi vurgulanır. Sayfa bitince sonrakine geçer.'
                : listen.hasAudio ? 'Önizlemede dinle: bu sayfa e-kitabın kendi sesiyle okunur.'
                  : 'Bu sayfada okunacak ses yok (kapak, künye, resim sayfası).'}
          </span>
        </div>
      )}
      {frames}
    </div>
  );
}
