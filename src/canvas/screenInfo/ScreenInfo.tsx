import { useCallback, useEffect, useRef, useState } from 'react';
import { CalendarClock, ChevronRight, Database, Info, RefreshCw, X } from 'lucide-react';
import type { ScreenInfo, ScreenInfoMap } from './types';
import './screenInfo.css';

/** Kendiliğinden açılan kısa kutunun ekranda kaldığı süre; fare üstündeyken ya da odak içerideyken sayım durur. */
export const AUTO_CLOSE_MS = 8_000;
const SEEN_KEY = 'timas.screenInfo.seen';

// İçerik ayrı parça: yüzlerce ekranın metni kabuğun ilk yüklemesine binmesin.
let contentPromise: Promise<ScreenInfoMap> | null = null;
const loadContent = () => (contentPromise ??= import('./content').then((m) => m.default));

/** `path:/kitap/:id` kalıbı → düzenli ifade. */
const patternOf = (p: string) => new RegExp(`^${p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\\:[^/]+|:[^/]+/g, '[^/]+')}/?$`);

/** Ekranın içerik anahtarı: adrese birebir uyan `path:` kalıbı önce (menü öğesine bağlı detay sayfasının kendi
 *  metni olabilir, ör. `/kitap/:id` Masam'a bağlı), yoksa menü öğesi kimliği. */
export function resolveKey(content: ScreenInfoMap, itemId: string | undefined, pathname: string): string | null {
  for (const k of Object.keys(content)) {
    if (k.startsWith('path:') && patternOf(k.slice(5)).test(pathname)) return k;
  }
  return itemId && content[itemId] ? itemId : null;
}

function readSeen(): Record<string, 1> {
  try {
    return JSON.parse(window.localStorage.getItem(SEEN_KEY) || '{}') as Record<string, 1>;
  } catch {
    return {};
  }
}
function markSeen(key: string) {
  try {
    window.localStorage.setItem(SEEN_KEY, JSON.stringify({ ...readSeen(), [key]: 1 }));
  } catch {
    /* depolama kapalıysa kutu her girişte yine açılır; ekran çalışmaya devam eder */
  }
}

export type ScreenInfoState = {
  info: ScreenInfo | null;
  open: boolean;
  /** Kendiliğinden mi açıldı (geri sayım yalnız o zaman). */
  auto: boolean;
  toggle: () => void;
  close: () => void;
  /** Kendiliğinden açılan kısa kutuyu tam metne açar (geri sayım durur). */
  expand: () => void;
};

/** Kabuk bir kez çağırır; düğme ve kutu aynı durumu paylaşır. */
export function useScreenInfo(itemId: string | undefined, pathname: string): ScreenInfoState {
  const [content, setContent] = useState<ScreenInfoMap | null>(null);
  const [open, setOpen] = useState(false);
  const [auto, setAuto] = useState(false);

  useEffect(() => {
    let live = true;
    loadContent().then((c) => live && setContent(c), () => undefined);
    return () => {
      live = false;
    };
  }, []);

  const key = content ? resolveKey(content, itemId, pathname) : null;
  const info = key && content ? content[key] : null;

  // Ekran değişince kapan; bu ekrana ilk girişse bir kare sonra aç (kapalı hâl çizilsin ki geçiş görünsün).
  useEffect(() => {
    setOpen(false);
    setAuto(false);
    if (!key || readSeen()[key]) return;
    markSeen(key);
    const raf = window.requestAnimationFrame(() => {
      setAuto(true);
      setOpen(true);
    });
    return () => window.cancelAnimationFrame(raf);
  }, [key]);

  const toggle = useCallback(() => {
    setAuto(false);
    setOpen((v) => !v);
  }, []);
  const close = useCallback(() => setOpen(false), []);
  const expand = useCallback(() => setAuto(false), []);
  return { info, open, auto, toggle, close, expand };
}

/** Başlık çubuğundaki «Bu ekran» düğmesi. İçeriği olmayan ekranda görünmez. */
export function ScreenInfoButton({ s }: { s: ScreenInfoState }) {
  if (!s.info) return null;
  return (
    <button
      type="button"
      onClick={s.toggle}
      aria-expanded={s.open}
      aria-controls="screen-info"
      title="Bu ekran nasıl çalışır?"
      className="si-trigger glass-panel min-h-10 min-w-10 justify-center px-2.5 py-1.5 sm:min-h-0 sm:min-w-0 sm:px-3.5 sm:py-2 rounded-full shadow-glass-float flex items-center gap-1.5 text-[11px] sm:text-xs font-bold text-ink hover:bg-white hover:text-violet whitespace-nowrap"
    >
      <Info aria-hidden className="h-3.5 w-3.5 shrink-0" />
      <span className="hidden sm:inline">Bu ekran</span>
    </button>
  );
}

/** «Bu ekran» düğmesinin altında açılan küçük kutu. İlk girişte kendiliğinden yalnız özet görünür; ayrıntı
 *  (veri, güncelleme, arka plan işleri, yapılabilecekler) katlı durur. Dışarı tıklamak ya da Esc kapatır. */
export function ScreenInfoPanel({ s, title }: { s: ScreenInfoState; title?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const { info, open, auto, close, expand } = s;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    // Düğmeye basış toggle'a kalır; yoksa aynı tıklama önce kapatıp sonra yeniden açardı.
    const onDown = (e: PointerEvent) => {
      const t = e.target as Element | null;
      if (!t || ref.current?.contains(t) || t.closest('[aria-controls="screen-info"]')) return;
      close();
    };
    window.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onDown, true);
    return () => {
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onDown, true);
    };
  }, [open, close]);

  if (!info) return null;
  const hasDetails = !!(info.data || info.refresh || info.jobs?.length || info.actions?.length);
  return (
    <aside
      id="screen-info"
      ref={ref}
      aria-label="Bu ekran nasıl çalışır"
      aria-hidden={!open}
      data-open={open}
      className="si-panel print:hidden absolute z-30 left-3 right-3 top-[60px] sm:left-auto sm:right-5 sm:top-[68px] lg:right-7 sm:w-[380px]"
    >
      <div className="glass-panel shadow-glass-float rounded-2xl overflow-hidden">
        <div className="max-h-[min(60dvh,460px)] overflow-y-auto px-4 pt-3 pb-3.5">
          <div className="flex items-center gap-2">
            <Info aria-hidden className="h-4 w-4 shrink-0 text-violet" />
            <div className="min-w-0 flex-1 truncate text-[13px] font-extrabold text-ink">{title || 'Bu ekran'}</div>
            <button
              type="button"
              onClick={close}
              tabIndex={open ? 0 : -1}
              aria-label="Kapat"
              title="Kapat (Esc)"
              className="si-close -mr-2 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-muted hover:bg-slate-100 hover:text-ink"
            >
              <X aria-hidden className="h-4 w-4" />
            </button>
          </div>

          <p className="mt-1 text-[12.5px] leading-relaxed text-ink/90">{info.summary}</p>

          {auto ? (
            <button
              type="button"
              onClick={expand}
              tabIndex={open ? 0 : -1}
              className="mt-2 text-[12px] font-bold text-violet hover:underline"
            >
              Nasıl çalışır →
            </button>
          ) : (
            <>
              {info.how.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {info.how.map((h) => (
                    <li key={h} className="flex gap-2 text-[12px] leading-snug text-ink/85">
                      <span aria-hidden className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-violet/70" />
                      <span>{h}</span>
                    </li>
                  ))}
                </ul>
              )}

              {hasDetails && (
                <details className="si-details group mt-2.5 border-t border-slate-200/70 pt-2">
                  <summary className="flex cursor-pointer list-none items-center gap-1 text-[12px] font-bold text-muted hover:text-ink [&::-webkit-details-marker]:hidden">
                    <ChevronRight aria-hidden className="h-3.5 w-3.5 transition-transform duration-150 group-open:rotate-90" />
                    Ayrıntılar
                  </summary>
                  <div className="mt-2 space-y-2 text-[12px] leading-snug">
                    {info.data && (
                      <div className="flex gap-2">
                        <Database aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted" />
                        <div><span className="font-bold text-ink">Veri: </span><span className="text-muted">{info.data}</span></div>
                      </div>
                    )}
                    {info.refresh && (
                      <div className="flex gap-2">
                        <RefreshCw aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted" />
                        <div><span className="font-bold text-ink">Güncelleme: </span><span className="text-muted">{info.refresh}</span></div>
                      </div>
                    )}
                    {info.jobs?.map((j) => (
                      <div key={j.name + j.when} className="flex gap-2">
                        <CalendarClock aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted" />
                        <div>
                          <span className="font-bold text-ink">{j.name}</span>
                          <span className="text-violet"> · {j.when}</span>
                          <div className="text-muted">{j.what}</div>
                        </div>
                      </div>
                    ))}
                    {info.actions && info.actions.length > 0 && (
                      <ul className="space-y-0.5 pt-0.5">
                        {info.actions.map((a) => (
                          <li key={a} className="flex gap-2 text-ink/85">
                            <span aria-hidden className="text-violet">→</span>
                            <span>{a}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </details>
              )}
            </>
          )}
        </div>
        {/* Geri sayım: yalnız kendiliğinden açıldığında; bitince kutu kapanır. */}
        {open && auto && (
          <div className="h-0.5 bg-violet/10" aria-hidden>
            <div className="si-countdown h-full bg-violet/50" style={{ animationDuration: `${AUTO_CLOSE_MS}ms` }} onAnimationEnd={close} />
          </div>
        )}
      </div>
    </aside>
  );
}
