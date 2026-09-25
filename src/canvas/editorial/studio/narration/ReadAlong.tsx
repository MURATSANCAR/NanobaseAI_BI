import { Fragment, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import type { NarrationBlock, NarrationVoice } from './api';

/** Okunan kelime vurgulu önizleme. Vurgu saniyede 3–4 kez yer değiştirir: geçiş animasyonu yok, arka plan anında
 *  değişir (sık tekrarlanan değişimde her geçiş gecikme gibi hissettirir). Zamanlı kelimeye tıklamak sesi oradan
 *  başlatır; okunuşu yazılışından farklı kelime (sayı, kısaltma, sözlük) noktalı altı çizgili, okunuşu ipucunda. */

type Timed = { key: string; start: number; end: number };

const KIND: Record<string, string> = {
  bubble: 'Balon', heading: 'Başlık', sound: 'Ses sözcüğü', dialogue: 'Konuşma', text: 'Serbest yazı', para: '',
};

/** Şu anki kelime: başlangıcı `t`'den küçük olan son kelime (sesler arası sessizlikte önceki kelimede kalır). */
export function wordAt(list: Timed[], t: number): string | null {
  let lo = 0;
  let hi = list.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (list[mid].start <= t) {
      ans = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  if (ans < 0) return null;
  // Uzun sessizlikte (parça arası duraklama) vurgu kalkar.
  return t - list[ans].end > 0.6 ? null : list[ans].key;
}

function useCurrentWord(audio: RefObject<HTMLAudioElement | null>, list: Timed[]) {
  const [current, setCurrent] = useState<string | null>(null);
  useEffect(() => {
    const el = audio.current;
    if (!el) return;
    let raf = 0;
    const tick = () => {
      setCurrent(wordAt(list, el.currentTime));
      if (!el.paused && !el.ended) raf = requestAnimationFrame(tick);
    };
    const start = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(tick);
    };
    const once = () => setCurrent(wordAt(list, el.currentTime));
    const stop = () => {
      cancelAnimationFrame(raf);
      once();
    };
    const end = () => {
      cancelAnimationFrame(raf);
      setCurrent(null);
    };
    el.addEventListener('play', start);
    el.addEventListener('pause', stop);
    el.addEventListener('seeked', once);
    el.addEventListener('ended', end);
    if (!el.paused) start();
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener('play', start);
      el.removeEventListener('pause', stop);
      el.removeEventListener('seeked', once);
      el.removeEventListener('ended', end);
    };
  }, [audio, list]);
  return current;
}

export default function ReadAlong({ blocks, audio, voices, timed }: {
  blocks: NarrationBlock[];
  audio: RefObject<HTMLAudioElement | null>;
  voices: NarrationVoice[];
  /** Sesi olan (güncel) sayfa mı; değilse kelimeler tıklanmaz. */
  timed: boolean;
}) {
  const list = useMemo<Timed[]>(() => {
    const out: Timed[] = [];
    if (timed) {
      for (const b of blocks) for (const w of b.words) if (w.start != null && w.end != null) out.push({ key: `${b.id}:${w.i}`, start: w.start, end: w.end });
    }
    return out.sort((a, b) => a.start - b.start);
  }, [blocks, timed]);
  const current = useCurrentWord(audio, list);
  const box = useRef<HTMLDivElement>(null);

  // Vurgulanan kelime görünür alanda kalsın (uzun sayfada); kaydırma anlık, yalnız gerekince.
  useEffect(() => {
    if (!current || !box.current) return;
    const el = box.current.querySelector<HTMLElement>(`[data-w="${CSS.escape(current)}"]`);
    if (!el) return;
    const b = box.current.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    if (r.top < b.top || r.bottom > b.bottom) el.scrollIntoView({ block: 'nearest', behavior: 'auto' });
  }, [current]);

  const label = (id: string) => voices.find((v) => v.id === id)?.label ?? '';
  const seek = (t: number | null) => {
    const el = audio.current;
    if (!el || t == null) return;
    el.currentTime = Math.max(0, t - 0.02);
    void el.play().catch(() => undefined);
  };

  if (!blocks.length) return <p className="text-[12.5px] text-canvas-muted">Bu sayfada okunacak metin yok.</p>;

  return (
    <div ref={box} className="max-h-[52vh] overflow-y-auto rounded-2xl border border-slate-200/80 bg-white/90 p-3 sm:p-4" aria-live="off">
      {blocks.map((b) => {
        const tag = KIND[b.kind] ?? '';
        const who = b.speaker ? `${b.speaker} · ${label(b.voice)}` : tag;
        let at = 0;
        return (
          <div key={b.id} className={`mb-3 last:mb-0 ${b.kind === 'bubble' ? 'rounded-xl border border-violet-200/70 bg-violet-50/50 px-3 py-2' : ''}`}>
            {who && <div className="mb-0.5 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{who}</div>}
            <p className={`text-[15px] leading-[1.9] text-canvas-ink ${b.kind === 'heading' ? 'font-extrabold' : ''} ${b.kind === 'sound' ? 'font-bold italic text-canvas-violet' : ''}`}>
              {b.words.map((w) => {
                const gap = b.text.slice(at, w.char[0]);
                at = w.char[1];
                const key = `${b.id}:${w.i}`;
                const on = key === current;
                const clickable = timed && w.start != null;
                const differs = !!w.spoken && w.spoken.replace(/[.,;:!?…]+$/, '') !== w.text.replace(/^[“"'‘«(–—-]+|[”"'’»).,;:!?…]+$/g, '');
                const cls = `rounded-[5px] px-[1px] ${on ? 'bg-canvas-violet/20 text-canvas-ink shadow-[0_0_0_2px_rgba(124,92,255,0.18)]' : ''} ${differs ? 'underline decoration-dotted decoration-canvas-violet/60 underline-offset-4' : ''}`;
                return (
                  <Fragment key={w.i}>
                    {gap}
                    {clickable ? (
                      <span role="button" tabIndex={-1} data-w={key} onClick={() => seek(w.start)}
                        title={differs ? `Okunuş: ${w.spoken}` : undefined}
                        className={`${cls} cursor-pointer`}>{w.text}</span>
                    ) : (
                      <span data-w={key} title={differs ? `Okunuş: ${w.spoken}` : undefined} className={cls}>{w.text}</span>
                    )}
                  </Fragment>
                );
              })}
              {b.text.slice(at)}
            </p>
          </div>
        );
      })}
    </div>
  );
}
