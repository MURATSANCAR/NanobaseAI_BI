import { useCallback, useEffect, useRef, useState } from 'react';
import { CalendarClock, Database, Info, RefreshCw, X } from 'lucide-react';
import type { ScreenInfo, ScreenInfoMap } from './types';
import './screenInfo.css';

/** Kendiliğinden açılan kutunun ekranda kaldığı süre; fare üstündeyken ya da odak içerideyken sayım durur. */
export const AUTO_CLOSE_MS = 15_000;
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
  return { info, open, auto, toggle, close };
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

/** Başlığın altındaki bilgi kutusu. */
export function ScreenInfoPanel({ s, title }: { s: ScreenInfoState; title?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const { info, open, auto, close } = s;

  // Esc, odak kutunun içindeyken kapatır.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && ref.current?.contains(document.activeElement)) close();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, close]);

  if (!info) return null;
  return (
    <aside
      id="screen-info"
      ref={ref}
      aria-label="Bu ekran nasıl çalışır"
      aria-hidden={!open}
      data-open={open}
      className="si-panel print:hidden absolute z-30 left-3 right-3 top-16 sm:left-5 sm:right-auto sm:top-[84px] lg:left-7 sm:w-[min(600px,calc(100%-40px))]"
    >
      <div className="glass-panel shadow-glass-float rounded-2xl overflow-hidden">
        <div className="max-h-[min(62dvh,560px)] overflow-y-auto px-4 pt-3.5 pb-4 sm:px-5">
          <div className="flex items-start gap-2.5">
            <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-violet/10 text-violet">
              <Info aria-hidden className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[11px] font-bold uppercase tracking-wide text-muted">Bu ekran nasıl çalışır?</div>
              {title && <div className="text-[15px] font-extrabold leading-tight text-ink">{title}</div>}
            </div>
            <button
              type="button"
              onClick={close}
              tabIndex={open ? 0 : -1}
              aria-label="Bilgi kutusunu kapat"
              className="si-close -mr-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-muted hover:bg-slate-100 hover:text-ink"
            >
              <X aria-hidden className="h-4 w-4" />
            </button>
          </div>

          <p className="mt-2.5 text-[13px] leading-relaxed text-ink">{info.summary}</p>

          {info.how.length > 0 && (
            <ul className="mt-2.5 space-y-1.5">
              {info.how.map((h) => (
                <li key={h} className="flex gap-2 text-[12.5px] leading-snug text-ink/90">
                  <span aria-hidden className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-violet/60" />
                  <span>{h}</span>
                </li>
              ))}
            </ul>
          )}

          {(info.data || info.refresh) && (
            <dl className="mt-3 grid gap-1.5 rounded-xl bg-slate-50/80 px-3 py-2.5 text-[12px] sm:grid-cols-2 sm:gap-3">
              {info.data && (
                <div className="flex gap-2">
                  <Database aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted" />
                  <div>
                    <dt className="font-bold text-ink">Veri</dt>
                    <dd className="text-muted">{info.data}</dd>
                  </div>
                </div>
              )}
              {info.refresh && (
                <div className="flex gap-2">
                  <RefreshCw aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted" />
                  <div>
                    <dt className="font-bold text-ink">Güncelleme</dt>
                    <dd className="text-muted">{info.refresh}</dd>
                  </div>
                </div>
              )}
            </dl>
          )}

          {info.jobs && info.jobs.length > 0 && (
            <section className="mt-3">
              <h3 className="flex items-center gap-1.5 text-[12px] font-bold text-ink">
                <CalendarClock aria-hidden className="h-3.5 w-3.5 text-muted" /> Arka planda kendiliğinden
              </h3>
              <ul className="mt-1.5 space-y-1.5">
                {info.jobs.map((j) => (
                  <li key={j.name + j.when} className="rounded-lg border border-slate-200/70 bg-white/60 px-2.5 py-1.5 text-[12px] leading-snug">
                    <span className="font-bold text-ink">{j.name}</span>
                    <span className="text-violet"> · {j.when}</span>
                    <div className="text-muted">{j.what}</div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {info.actions && info.actions.length > 0 && (
            <section className="mt-3">
              <h3 className="text-[12px] font-bold text-ink">Burada neler yapabilirsiniz</h3>
              <ul className="mt-1 space-y-1">
                {info.actions.map((a) => (
                  <li key={a} className="flex gap-2 text-[12.5px] leading-snug text-ink/90">
                    <span aria-hidden className="text-violet">→</span>
                    <span>{a}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <p className="mt-3 text-[11px] text-muted">Bu kutuyu sağ üstteki «Bu ekran» düğmesiyle istediğiniz zaman yeniden açabilirsiniz.</p>
        </div>
        {/* Geri sayım: yalnız kendiliğinden açıldığında; bitince kutu kapanır. */}
        {open && auto && (
          <div className="h-[3px] bg-violet/10" aria-hidden>
            <div className="si-countdown h-full bg-violet/60" style={{ animationDuration: `${AUTO_CLOSE_MS}ms` }} onAnimationEnd={close} />
          </div>
        )}
      </div>
    </aside>
  );
}
