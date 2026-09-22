import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { bookAskApi } from '../engine';

/** Sohbet cevabındaki sayfa rozeti («s. 14») ve o sayfanın görsel önizlemesi.
 *
 *  Fare (ince işaretçi): rozete gelince kısa gecikmeyle açılır, çıkınca kapanır; önizlemenin üstüne geçmek kapatmaz.
 *  Dokunmatik: rozete dokunmak aç/kapa, dışına dokunmak kapatır. Klavye: rozet odaklanabilir, odakta açılır,
 *  Escape kapatır (odak rozette kalır). Kaydırma ve pencere boyutu değişince kapanır (konum kayar).
 *
 *  Konum: rozetin üstünde, ortalanmış; üstte yer yoksa altına, ekran kenarına taşarsa içeri kaydırılır.
 *  Görsel köprüden gelir (oturum çerezi otomatik); tarayıcı bir saat önbellekler, ikinci açılış anında.
 *  Kitap kimliği yoksa yalnız eski rozet çizilir (önizleme yok). */

const WIDTH = 240; // önizleme genişliği; dar ekranda viewport'a sığdırılır
const GUTTER = 8; // ekran kenarına bırakılan boşluk
const GAP = 8; // rozet ile önizleme arası
const OPEN_DELAY = 150; // hover: yanlışlıkla açılmasın
const CLOSE_DELAY = 80; // hover: rozetten önizlemeye geçerken kapanmasın
const EXIT_MS = 100; // çıkış geçişi (girişten hızlı)

type Phase = 'closed' | 'pre' | 'open' | 'closing';
type Placement = { left: number; top: number; width: number; originX: number; above: boolean };

const finePointer = () => typeof window !== 'undefined' && window.matchMedia('(hover: hover) and (pointer: fine)').matches;

export function pageNumberOf(label: string): number | null {
  const m = /\d+/.exec(label);
  const n = m ? Number(m[0]) : NaN;
  return Number.isFinite(n) && n >= 1 ? n : null;
}

export default function PageRef({ label, bookId, bookTitle }: { label: string; bookId?: string | null; bookTitle?: string | null }) {
  const page = bookId ? pageNumberOf(label) : null;
  if (!bookId || page === null) return <span className="zk-page-ref">{label}</span>;
  return <PeekButton label={label} bookId={bookId} bookTitle={bookTitle ?? null} page={page} />;
}

function PeekButton({ label, bookId, bookTitle, page }: { label: string; bookId: string; bookTitle: string | null; page: number }) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const timer = useRef<number | null>(null);
  const [phase, setPhase] = useState<Phase>('closed');
  const [instant, setInstant] = useState(false); // klavyeyle açılış: geçiş yok
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [place, setPlace] = useState<Placement | null>(null);

  const clearTimer = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  };

  const open = useCallback((viaKeyboard = false) => {
    clearTimer();
    setInstant(viaKeyboard);
    setPhase((p) => (p === 'open' || p === 'pre' ? p : 'pre'));
  }, []);

  const close = useCallback(() => {
    clearTimer();
    setPhase((p) => (p === 'closed' ? p : 'closing'));
  }, []);

  const openLater = () => {
    clearTimer();
    timer.current = window.setTimeout(() => open(false), OPEN_DELAY);
  };
  const closeLater = () => {
    clearTimer();
    timer.current = window.setTimeout(close, CLOSE_DELAY);
  };

  useEffect(() => clearTimer, []);

  // pre → open bir kare sonra (giriş geçişi çalışsın); closing → closed çıkış süresi sonunda.
  useEffect(() => {
    if (phase === 'pre') {
      const f = window.requestAnimationFrame(() => setPhase((p) => (p === 'pre' ? 'open' : p)));
      return () => window.cancelAnimationFrame(f);
    }
    if (phase === 'closing') {
      const t = window.setTimeout(() => setPhase((p) => (p === 'closing' ? 'closed' : p)), EXIT_MS);
      return () => window.clearTimeout(t);
    }
    return undefined;
  }, [phase]);

  const shown = phase !== 'closed';

  // Konum: rozete göre ölçülür; görsel yüklenince yükseklik değişir, yeniden ölçülür.
  useLayoutEffect(() => {
    if (!shown || !trigger.current || !pop.current) return;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const width = Math.min(WIDTH, vw - GUTTER * 2);
    const r = trigger.current.getBoundingClientRect();
    const h = pop.current.offsetHeight;
    const cx = r.left + r.width / 2;
    const left = Math.min(Math.max(cx - width / 2, GUTTER), Math.max(GUTTER, vw - width - GUTTER));
    const above = r.top - GAP - h >= GUTTER;
    let top = above ? r.top - GAP - h : r.bottom + GAP;
    if (!above && top + h > vh - GUTTER) top = Math.max(GUTTER, vh - GUTTER - h);
    setPlace({ left, top, width, originX: Math.min(Math.max(cx - left, 0), width), above });
  }, [shown, loaded, failed]);

  // Açıkken: dışına dokunuş/tıklama, Escape, kaydırma ve boyut değişimi kapatır.
  useEffect(() => {
    if (!shown) return;
    const onPointer = (e: PointerEvent) => {
      const t = e.target as Node;
      if (trigger.current?.contains(t) || pop.current?.contains(t)) return;
      close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    const onMove = () => close();
    document.addEventListener('pointerdown', onPointer, true);
    document.addEventListener('keydown', onKey);
    window.addEventListener('scroll', onMove, true);
    window.addEventListener('resize', onMove);
    return () => {
      document.removeEventListener('pointerdown', onPointer, true);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('scroll', onMove, true);
      window.removeEventListener('resize', onMove);
    };
  }, [shown, close]);

  const src = bookAskApi.pageImageUrl(bookId, page);
  const style: CSSProperties | undefined = place
    ? { left: place.left, top: place.top, width: place.width, ['--zk-origin' as string]: `${place.originX}px ${place.above ? '100%' : '0%'}` }
    : { left: -9999, top: 0, width: Math.min(WIDTH, (typeof window !== 'undefined' ? window.innerWidth : WIDTH) - GUTTER * 2) };

  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="zk-page-ref zk-page-ref--live"
        aria-label={`Sayfa ${page}, önizleme`}
        aria-expanded={phase === 'open' || phase === 'pre'}
        aria-describedby={shown ? id : undefined}
        onMouseEnter={() => { if (finePointer()) openLater(); }}
        onMouseLeave={() => { if (finePointer()) closeLater(); }}
        onFocus={(e) => { if (e.currentTarget.matches(':focus-visible')) open(true); }}
        onBlur={close}
        onClick={() => {
          if (finePointer()) return; // farede hover yönetir; tıklama okumayı bozmasın
          if (phase === 'open' || phase === 'pre') close();
          else open(false);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Escape' && shown) {
            e.stopPropagation();
            close();
          }
        }}
      >
        {label}
      </button>
      {shown && createPortal(
        <div
          ref={pop}
          id={id}
          role="tooltip"
          className="zk-peek"
          data-state={phase}
          data-instant={instant || undefined}
          style={style}
          onMouseEnter={() => { if (finePointer()) clearTimer(); }}
          onMouseLeave={() => { if (finePointer()) closeLater(); }}
        >
          <div className="zk-peek-label">
            <span>s. {page}</span>
            {bookTitle && <span className="zk-peek-title">{bookTitle}</span>}
          </div>
          {failed ? (
            <p className="zk-peek-empty">Sayfa görseli yok</p>
          ) : (
            <div className="zk-peek-frame" data-loaded={loaded || undefined} style={loaded ? undefined : { minHeight: Math.round((place?.width ?? WIDTH) * 1.41) }}>
              {!loaded && <span aria-hidden className="zk-peek-skeleton" />}
              <img
                src={src}
                alt={`${bookTitle ? `«${bookTitle}» ` : ''}sayfa ${page}`}
                loading="lazy"
                decoding="async"
                draggable={false}
                onLoad={() => setLoaded(true)}
                onError={() => setFailed(true)}
              />
            </div>
          )}
        </div>,
        document.body,
      )}
    </>
  );
}
