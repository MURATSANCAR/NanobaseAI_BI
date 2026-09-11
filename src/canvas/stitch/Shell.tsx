import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import ModulesMenu from './ModulesMenu';
import type { StitchRailItem } from './data';

const RAIL_ICONS = [
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>
  ),
  (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
  ),
];

export type ShellHead = {
  tenant: string;
  section: string;
  crumb: string;
  source: string;
  presence: string;
  zoom: string;
};

/**
 * Ortak kabuk: nokta ızgara, üst şerit, sol ray ve modül menüsü. Kanvas
 * ekranları da pano da bunu kullanır; başlık ve menü her sayfada aynı olsun.
 */
export default function Shell({
  head,
  rail,
  onZoom,
  onReset,
  children,
}: {
  head: ShellHead;
  rail: StitchRailItem[];
  onZoom?: (delta: number) => void;
  /** Düzen değiştirilmişse sıfırlama düğmesi çıkar. */
  onReset?: () => void;
  children: React.ReactNode;
}) {
  const [modulesOpen, setModulesOpen] = useState(false);
  const [copied, setCopied] = useState<'ok' | 'fail' | null>(null);
  // Pano izni reddedilirse (odak yok, güvenli bağlam değil) eski yönteme düşer; o da olmazsa bunu söyler.
  const share = () => {
    const url = window.location.href;
    const fallback = () => {
      const ta = document.createElement('textarea');
      ta.value = url;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try {
        ok = document.execCommand('copy');
      } catch {
        ok = false;
      }
      ta.remove();
      return ok;
    };
    const done = (ok: boolean) => {
      setCopied(ok ? 'ok' : 'fail');
      window.setTimeout(() => setCopied(null), 1800);
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(url).then(() => done(true), () => done(fallback()));
    } else {
      done(fallback());
    }
  };
  useLocation();

  return (
    <div className="bg-mesh-canvas font-canvas text-ink w-full h-[100dvh] overflow-hidden select-none relative">
    {/* Interactive Dot Grid Overlay */}
    <div className="absolute inset-0 dot-grid pointer-events-none z-0"></div>

    {/* ================= TOP FLOATING NAVIGATION ================= */}
    <header className="absolute top-3 inset-x-3 sm:top-5 sm:inset-x-5 lg:inset-x-7 flex items-center justify-between gap-2 z-40 pointer-events-none">
      {/* Top-Left Glass Breadcrumb Pill */}
      <div className="glass-panel min-w-0 px-2.5 py-1.5 sm:px-4 sm:py-2 rounded-full shadow-glass-float flex items-center gap-2 sm:gap-3 pointer-events-auto transition-transform hover:scale-[1.01]">
        <div className="w-6 h-6 sm:w-7 sm:h-7 shrink-0 rounded-full bg-gradient-to-tr from-coral to-violet flex items-center justify-center text-white font-black text-[11px] sm:text-xs shadow-sm">
          T
        </div>
        <div className="flex min-w-0 items-center text-xs font-semibold tracking-tight text-ink">
          <span className="hidden sm:inline text-ink font-bold hover:text-violet cursor-pointer transition">{head.tenant}</span>
          <svg className="hidden sm:block w-3.5 h-3.5 mx-1.5 text-muted/60" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
          <span className="hidden md:inline text-muted hover:text-ink cursor-pointer transition">{head.section}</span>
          <svg className="hidden md:block w-3.5 h-3.5 mx-1.5 text-muted/60" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
          <span className="min-w-0 truncate bg-violet/10 text-violet px-2 py-0.5 rounded-full font-bold flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 shrink-0 rounded-full bg-violet animate-pulse"></span>
            <span className="truncate">{head.crumb}</span>
          </span>
        </div>
        <span className="hidden lg:inline text-[10px] text-muted/70 border-l border-slate-200/80 pl-2.5 font-medium">{head.source}</span>
      </div>

      {/* Top-Right Actions & Collaboration Pill */}
      <div className="flex items-center gap-1.5 sm:gap-3 pointer-events-auto">
        {/* Collaboration Avatars */}
        <div className="hidden lg:flex glass-panel px-3 py-1.5 rounded-full shadow-glass-float items-center gap-2">
          <div className="flex -space-x-1.5 items-center">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 text-white font-bold text-[11px] flex items-center justify-center ring-2 ring-white shadow-sm" title="Emre Berk (Genel Yayın Yönetmeni)">EB</div>
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-purple-500 to-indigo-600 text-white font-bold text-[11px] flex items-center justify-center ring-2 ring-white shadow-sm" title="Elif Aydın (Yazar & Danışman)">EA</div>
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-emerald-400 to-teal-600 text-white font-bold text-[11px] flex items-center justify-center ring-2 ring-white shadow-sm" title="Selin Kara (Üretim & Telif)">SK</div>
          </div>
          <span className="text-[11px] font-semibold text-muted pl-1">{head.presence}</span>
        </div>

        {onReset && (
          <button
            type="button"
            onClick={onReset}
            title="Kart düzenini tasarımdaki hâline döndür"
            className="glass-panel px-2.5 py-1.5 sm:px-3.5 sm:py-2 rounded-full shadow-glass-float text-[11px] sm:text-xs font-bold text-muted hover:text-ink transition whitespace-nowrap"
          >
            <span className="sm:hidden">Sıfırla</span>
            <span className="hidden sm:inline">Düzeni sıfırla</span>
          </button>
        )}

        {/* Share Button */}
        <button type="button" onClick={share} className="glass-panel px-2.5 py-1.5 sm:px-4 sm:py-2 rounded-full shadow-glass-float flex items-center gap-1.5 text-[11px] sm:text-xs font-bold text-ink hover:bg-white hover:text-violet transition-all group whitespace-nowrap">
          <svg className="w-3.5 h-3.5 shrink-0 text-muted group-hover:text-violet transition" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" /></svg>
          <span className="hidden sm:inline">{copied === 'ok' ? 'Bağlantı kopyalandı' : copied === 'fail' ? 'Kopyalanamadı' : 'Paylaş'}</span>
        </button>

        {/* Canvas Zoom Indicator & Controls */}
        <div className="hidden sm:flex glass-panel px-3 py-1.5 rounded-full shadow-glass-float items-center gap-2 text-xs font-semibold text-ink">
          <button type="button" aria-label="Uzaklaştır" onClick={() => onZoom?.(-0.1)} className="w-5 h-5 flex items-center justify-center rounded-full hover:bg-slate-100 text-muted font-bold">-</button>
          <span className="text-xs font-bold w-9 text-center text-ink">{head.zoom}</span>
          <button type="button" aria-label="Yakınlaştır" onClick={() => onZoom?.(0.1)} className="w-5 h-5 flex items-center justify-center rounded-full hover:bg-slate-100 text-muted font-bold">+</button>
        </div>
      </div>
    </header>

    {/* ================= LEFT FLOATING VERTICAL MODULE RAIL ================= */}
      {/* Ray yalnız var olan ekranları taşır; ölü bağlantı yok. */}
      <aside className="absolute left-1.5 top-20 bottom-20 sm:left-6 sm:top-24 sm:bottom-24 z-30 flex flex-col items-center justify-start gap-1.5 sm:gap-2.5 py-3 sm:py-4 px-1.5 sm:px-2 w-10 sm:w-[54px] glass-panel rounded-2xl sm:rounded-3xl shadow-glass-float overflow-y-auto">
        {rail.map((item, i) => (
          <div key={item.to} className="relative group flex items-center shrink-0">
            <Link
              to={item.to}
              aria-label={item.label}
              className={
                item.badge === 'Aktif'
                  ? 'w-8 h-8 sm:w-10 sm:h-10 rounded-xl sm:rounded-2xl bg-gradient-to-tr from-coral to-violet text-white shadow-md flex items-center justify-center transition-transform hover:scale-105 [&_svg]:w-4 [&_svg]:h-4 sm:[&_svg]:w-5 sm:[&_svg]:h-5'
                  : 'w-8 h-8 sm:w-10 sm:h-10 rounded-xl sm:rounded-2xl hover:bg-white/80 text-muted hover:text-ink transition flex items-center justify-center [&_svg]:w-4 [&_svg]:h-4 sm:[&_svg]:w-5 sm:[&_svg]:h-5'
              }
            >
              {RAIL_ICONS[i % RAIL_ICONS.length]}
            </Link>
            <div className="absolute left-10 sm:left-14 z-50 whitespace-nowrap rounded-lg bg-slate-900 px-2.5 py-1 text-[11px] font-semibold text-white opacity-0 shadow-xl transition duration-150 pointer-events-none group-hover:opacity-100">
              {item.label}
            </div>
          </div>
        ))}

        {/* Modül menüsü: 18 grup, 67 modül. Ekran açmaz, listeler. */}
        <div className="relative group flex items-center mt-auto shrink-0">
          <button
            type="button"
            onClick={() => setModulesOpen((v) => !v)}
            aria-label="Modüller"
            className={
              modulesOpen
                ? 'w-8 h-8 sm:w-10 sm:h-10 rounded-xl sm:rounded-2xl bg-gradient-to-tr from-coral to-violet text-white shadow-md flex items-center justify-center transition-transform hover:scale-105'
                : 'w-8 h-8 sm:w-10 sm:h-10 rounded-xl sm:rounded-2xl hover:bg-white/80 text-muted hover:text-ink transition flex items-center justify-center'
            }
          >
            <svg className="w-4 h-4 sm:w-5 sm:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <div className="absolute left-10 sm:left-14 z-50 whitespace-nowrap rounded-lg bg-slate-900 px-2.5 py-1 text-[11px] font-semibold text-white opacity-0 shadow-xl transition duration-150 pointer-events-none group-hover:opacity-100">
            Modüller
          </div>
        </div>
      </aside>

      <ModulesMenu open={modulesOpen} onClose={() => setModulesOpen(false)} />

      {/* ================= INFINITE CANVAS STAGE ================= */}
      {children}
    </div>
  );
}
