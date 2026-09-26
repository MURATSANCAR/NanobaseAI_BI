import { Suspense, createContext, lazy, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Search } from 'lucide-react';
import ModulesMenu from './ModulesMenu';
import { useTimasSession } from '../TimasSession';
import DataRefresh from '../DataRefresh';
import DesktopNav from '../nav/DesktopNav';
import PhoneNav from '../nav/PhoneNav';
import CommandPalette from '../nav/CommandPalette';
import { pushRecent } from '../nav/navState';
import { NavUiContext, initials, paletteKey, useNavData, type NavUi } from '../nav/useNav';
import '../nav/nav.css';

const ProfileDialog = lazy(() => import('../kampus/ProfileDialog'));

export type ShellHead = {
  tenant: string;
  section: string;
  crumb: string;
  source: string;
  presence: string;
  /** Verilmezse kabuk kendi yakınlaştırmasını gösterir. */
  zoom?: string;
  /** Menüde olmayan detay sayfasının adı (kitap adı, stüdyo işi…); kırıntının son halkası ve «Son açılanlar». */
  detail?: string;
};

export const ZOOM_MIN = 0.5;
export const ZOOM_MAX = 2;
const ZoomContext = createContext(1);
/** Kabuğun yakınlaştırma çarpanı (0.5–2). Kabuk içindeki her ekran okuyabilir. */
export const useShellZoom = () => useContext(ZoomContext);

/**
 * Ekran içeriğinin yakınlaştırılan katı. `main` sabit kalır (üst şerit ve menüyle hizası bozulmaz),
 * içi CSS `zoom` ile büyür/küçülür; taşan kısım main'in kendi kaydırmasında kalır.
 */
export function ZoomStage({ className = '', style, children }: { className?: string; style?: React.CSSProperties; children: React.ReactNode }) {
  const zoom = useShellZoom();
  return (
    <div className={`shell-zoom-stage ${className}`} style={{ ...style, zoom }}>
      {children}
    </div>
  );
}

const pathOf = (to: string) => to.split('?')[0];

/**
 * Ortak kabuk: nokta ızgara, üst şerit ve portalın tek menüsü (nav/navModel.ts). Masaüstünde çalışma alanı
 * rayı + bağlam paneli, telefonda alt çubuk + menü sayfası; ⌘K / Ctrl K «Ara veya git». Menü ekrandan
 * bağımsızdır: hangi öğenin etkin olduğu adresten bulunur. Ekranların `main`'i `.shell-stage`'e göre
 * yerleşir (menünün yanında başlar, telefonda alt çubuğun üstünde biter).
 */
export default function Shell({
  head,
  onZoom,
  onReset,
  children,
}: {
  head: ShellHead;
  onZoom?: (delta: number) => void;
  /** Düzen değiştirilmişse sıfırlama düğmesi çıkar. */
  onReset?: () => void;
  children: React.ReactNode;
}) {
  const who = useTimasSession();
  const whoName = who.data?.displayName || who.data?.username || '';
  const nav = useNavData();
  const loc = useLocation();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [modulesOpen, setModulesOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  // Yakınlaştırma: kanvas kendi durumunu verir (onZoom); öteki ekranlarda kabuk kendisi tutar.
  const [ownZoom, setOwnZoom] = useState(1);
  const zoomHandler = onZoom ?? ((delta: number) => setOwnZoom((z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Number((z + delta).toFixed(2))))));
  const zoomLabel = head.zoom ?? `%${Math.round(ownZoom * 100)}`;

  // ⌘K / Ctrl K her ekranda paleti açar/kapatır.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Kırıntı: çalışma alanı › ekran › (detay sayfasıysa) iş/kitap adı.
  const active = nav.active;
  const onDetail = !!active && loc.pathname.replace(/\/+$/, '') !== pathOf(active.item.to);
  const detail = head.detail ?? (active && onDetail && head.crumb && head.crumb !== active.item.label ? head.crumb : undefined);
  const crumbGroup = active ? (active.group.id === 'kampus' ? null : active.group.label) : head.section;
  const crumbItem = active ? active.item.label : head.crumb;

  // Son açılanlar: menüdeki her ekran ve detay sayfası (Kampüs hariç — rayda hep var).
  const { update } = nav;
  const here = loc.pathname + loc.search;
  const recentLabel = active && active.group.id !== 'kampus' ? detail ?? active.item.label : null;
  const recentGroup = active ? (detail ? `${active.group.label} · ${active.item.label}` : active.group.label) : '';
  useEffect(() => {
    if (!recentLabel) return;
    update((s) => ({ ...s, recent: pushRecent(s.recent, { to: here, label: recentLabel, group: recentGroup, at: Date.now() }) }));
  }, [here, recentLabel, recentGroup, update]);

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

  const openPalette = useCallback(() => {
    setModulesOpen(false);
    setPaletteOpen(true);
  }, []);
  const ui = useMemo<NavUi>(
    () => ({
      openPalette,
      openModules: () => setModulesOpen((v) => !v),
      openProfile: () => setProfileOpen(true),
    }),
    [openPalette],
  );

  return (
    <NavUiContext.Provider value={ui}>
    <ZoomContext.Provider value={onZoom ? 1 : ownZoom}>
    <div
      data-docked={nav.state.collapsed ? '0' : '1'}
      className="nav-root bg-mesh-canvas font-canvas text-ink w-full h-[100dvh] overflow-hidden select-none relative print:h-auto print:overflow-visible print:bg-white"
    >
    {/* Interactive Dot Grid Overlay */}
    <div className="absolute inset-0 dot-grid pointer-events-none z-0 print:hidden"></div>

    <DesktopNav nav={nav} whoName={whoName} modulesOpen={modulesOpen} />

    <div className="shell-stage">
    {/* ================= TOP FLOATING NAVIGATION ================= */}
    <header className="print:hidden absolute top-3 inset-x-3 sm:top-5 sm:inset-x-5 lg:inset-x-7 flex items-center justify-between gap-2 z-40 pointer-events-none">
      {/* Kırıntı: çalışma alanı › ekran › detay. Telefonda yalnız ekran adı. */}
      <nav aria-label="Konum" className="glass-panel min-w-0 px-2.5 py-1.5 sm:px-4 sm:py-2 rounded-full shadow-glass-float flex items-center gap-2 sm:gap-3 pointer-events-auto">
        <Link to="/" aria-label={`${head.tenant} · Kampüs`} className="md:hidden w-6 h-6 sm:w-7 sm:h-7 shrink-0 rounded-full bg-gradient-to-tr from-coral to-violet flex items-center justify-center text-white font-black text-[11px] sm:text-xs shadow-sm">
          T
        </Link>
        <ol className="flex min-w-0 items-center text-xs font-semibold tracking-tight text-ink">
          {crumbGroup && (
            <li className="hidden sm:flex items-center text-muted">
              {crumbGroup}
              <svg aria-hidden className="w-3.5 h-3.5 mx-1.5 text-muted/60" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
            </li>
          )}
          {detail && active ? (
            <>
              <li className="hidden md:flex items-center min-w-0">
                <Link to={active.item.to} className="truncate text-ink font-bold">{crumbItem}</Link>
                <svg aria-hidden className="w-3.5 h-3.5 mx-1.5 shrink-0 text-muted/60" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" /></svg>
              </li>
              <li className="min-w-0 truncate bg-violet/10 text-violet px-2 py-0.5 rounded-full font-bold" aria-current="page">
                <span className="truncate">{detail}</span>
              </li>
            </>
          ) : (
            <li className="min-w-0 truncate bg-violet/10 text-violet px-2 py-0.5 rounded-full font-bold" aria-current="page">
              <span className="truncate">{crumbItem}</span>
            </li>
          )}
        </ol>
        {head.source && <span className="hidden xl:inline max-w-[260px] truncate text-[11px] text-muted/70 border-l border-slate-200/80 pl-2.5 font-medium">{head.source}</span>}
      </nav>

      {/* Top-Right Actions */}
      <div className="flex items-center gap-1.5 sm:gap-3 pointer-events-auto">
        <div className="hidden lg:flex glass-panel px-3 py-1.5 rounded-full shadow-glass-float items-center gap-2">
          <div
            className="w-7 h-7 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 text-white font-bold text-[11px] flex items-center justify-center ring-2 ring-white shadow-sm"
            title={whoName || 'Oturum'}
          >
            {initials(whoName)}
          </div>
          <span className="text-[11px] font-semibold text-muted pl-1">{head.presence}</span>
        </div>

        {/* Telefonda arama üst şeritte (masaüstünde rayda). */}
        <button
          type="button"
          onClick={openPalette}
          aria-label={`Ara veya git (${paletteKey()})`}
          className="md:hidden glass-panel min-h-10 min-w-10 flex items-center justify-center rounded-full shadow-glass-float text-ink active:scale-[0.97] transition-transform"
        >
          <Search aria-hidden className="h-4 w-4" />
        </button>

        {onReset && (
          <button
            type="button"
            onClick={onReset}
            title="Kart düzenini tasarımdaki hâline döndür"
            className="glass-panel min-h-10 px-3 py-1.5 sm:min-h-0 sm:px-3.5 sm:py-2 rounded-full active:scale-[0.97] shadow-glass-float text-[11px] sm:text-xs font-bold text-muted hover:text-ink transition whitespace-nowrap"
          >
            <span className="sm:hidden">Sıfırla</span>
            <span className="hidden sm:inline">Düzeni sıfırla</span>
          </button>
        )}

        {/* Veri gösteren her ekranda: son güncelleme, 5 dk otomatik yenileme, elle yenileme. */}
        <DataRefresh />

        {/* Share Button */}
        <button type="button" onClick={share} aria-label="Paylaş" className="glass-panel min-h-10 min-w-10 justify-center px-2.5 py-1.5 sm:min-h-0 sm:min-w-0 sm:px-4 sm:py-2 rounded-full active:scale-[0.97] shadow-glass-float flex items-center gap-1.5 text-[11px] sm:text-xs font-bold text-ink hover:bg-white hover:text-violet transition-all group whitespace-nowrap">
          <svg className="w-3.5 h-3.5 shrink-0 text-muted group-hover:text-violet transition" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" /></svg>
          <span className="hidden sm:inline">{copied === 'ok' ? 'Bağlantı kopyalandı' : copied === 'fail' ? 'Kopyalanamadı' : 'Paylaş'}</span>
        </button>

        {/* Canvas Zoom Indicator & Controls */}
        <div className="hidden sm:flex glass-panel px-3 py-1.5 rounded-full shadow-glass-float items-center gap-2 text-xs font-semibold text-ink">
          <button type="button" aria-label="Uzaklaştır" onClick={() => zoomHandler(-0.1)} className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-slate-100 text-muted font-bold">-</button>
          <span className="text-xs font-bold w-9 text-center text-ink">{zoomLabel}</span>
          <button type="button" aria-label="Yakınlaştır" onClick={() => zoomHandler(0.1)} className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-slate-100 text-muted font-bold">+</button>
        </div>
      </div>
    </header>

      {/* ================= INFINITE CANVAS STAGE ================= */}
      {children}
    </div>

      <PhoneNav nav={nav} whoName={whoName} />
      <ModulesMenu open={modulesOpen} onClose={() => setModulesOpen(false)} />
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} nav={nav} />
      {profileOpen && (
        <Suspense fallback={null}>
          <ProfileDialog open={profileOpen} onClose={() => setProfileOpen(false)} />
        </Suspense>
      )}
    </div>
    </ZoomContext.Provider>
    </NavUiContext.Provider>
  );
}
