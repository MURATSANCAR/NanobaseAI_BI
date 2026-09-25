import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { ghostBtn } from '../shared';
import { epubApi, type EpubPage, type EpubResult } from './api';

/** Tarayıcıda basit önizleme: e-kitabın kendi sayfaları çerçevede, sayfa sayfa. Sabit sayfada sayfa kitabın ölçüsüyle
 *  dizilir ve kutuya sığdırılır; geniş ekranda açılım (sol + sağ sayfa), telefonda tek sayfa. Akışkanda bölüm bölüm,
 *  çerçeve kendi içinde kayar. Sayfa değişimi hareketsiz: ok tuşuyla art arda çevrilir. Çerçevede betik çalışmaz. */

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
      {frames}
    </div>
  );
}
