import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Link } from 'react-router-dom';
import { ChevronsLeft, Grid2x2, PanelLeftOpen, Search, X } from 'lucide-react';
import type { NavGroupId } from './navModel';
import { NavList, NavTree } from './NavList';
import { RECENT_PANEL } from './navState';
import { ago, initials, paletteKey, roleLabel, useNavUi, type NavData } from './useNav';

function useMedia(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(query);
      m.addEventListener('change', cb);
      return () => m.removeEventListener('change', cb);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/**
 * Masaüstü menüsü (≥768 px): solda 68 px çalışma alanı rayı, yanında seçili alanın ekranlarını gösteren
 * 232 px bağlam paneli. ≥1024 px'te panel sabit durur (kişi daraltabilir, tercih sunucuda); daha dar
 * ekranda ya da daraltılmışken raydaki alana tıklayınca panel içeriğin üstünde açılır ve seçimden, Esc'ten
 * ya da dışarı tıklamaktan sonra kapanır.
 */
export default function DesktopNav({ nav, whoName, modulesOpen }: { nav: NavData; whoName: string; modulesOpen: boolean }) {
  const ui = useNavUi();
  const isLg = useMedia('(min-width: 1024px)');
  const docked = isLg && !nav.state.collapsed;
  const [viewing, setViewing] = useState<NavGroupId | null>(null);
  const [flyout, setFlyoutRaw] = useState(false);
  // Panel yalnız kişinin kendi eylemiyle hareket eder (bkz. nav.css data-anim).
  const [anim, setAnim] = useState(false);
  const setFlyout = (v: boolean) => {
    setAnim(true);
    setFlyoutRaw(v);
  };
  const railRef = useRef<HTMLElement>(null);
  const panelRef = useRef<HTMLElement>(null);

  const activeGroup = nav.active?.group.id ?? null;
  const shownId = viewing ?? activeGroup ?? 'kampus';
  const shown = nav.groups.find((g) => g.id === shownId) ?? nav.groups[0];
  const panelState = flyout ? 'flyout' : docked ? 'docked' : 'hidden';

  useEffect(() => {
    if (!flyout) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setFlyout(false);
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node;
      if (panelRef.current?.contains(t) || railRef.current?.contains(t)) return;
      setFlyout(false);
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('pointerdown', onDown);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('pointerdown', onDown);
    };
  }, [flyout]);

  const pickGroup = (id: NavGroupId) => {
    if (docked) {
      setViewing(id);
      return;
    }
    // Açık panelde aynı alana yeniden tıklamak paneli kapatır.
    if (flyout && shownId === id) setFlyout(false);
    else {
      setViewing(id);
      setFlyout(true);
    }
  };

  // Gizli panel klavyeyle de gezilmesin (React 18'de `inert` özniteliği yok, doğrudan konur).
  useEffect(() => {
    panelRef.current?.toggleAttribute('inert', panelState === 'hidden');
  }, [panelState]);

  const setCollapsed = (collapsed: boolean) => {
    setAnim(true);
    nav.update((s) => ({ ...s, collapsed }));
  };
  const recent = (nav.state.recent ?? []).slice(0, RECENT_PANEL);
  const isOverview = shown?.id === 'kampus';

  return (
    <>
      <nav
        ref={railRef}
        aria-label="Çalışma alanları"
        className="nav-rail glass-panel hidden flex-col items-center gap-1 overflow-y-auto overflow-x-hidden rounded-[26px] py-3 shadow-glass-float md:flex print:hidden [scrollbar-width:none]"
      >
        <Link
          to="/"
          aria-label="Kampüs ana sayfası"
          className="nav-tile mb-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-tr from-coral to-violet text-[17px] font-black text-white shadow-md"
        >
          T
        </Link>
        <button
          type="button"
          onClick={ui.openPalette}
          aria-label={`Ara veya git (${paletteKey()})`}
          title={`Ara veya git · ${paletteKey()}`}
          className="nav-tile nav-ghost flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-2xl text-muted"
        >
          <Search aria-hidden className="h-[18px] w-[18px]" />
          <span className="mt-0.5 text-[9.5px] font-bold leading-none">{paletteKey()}</span>
        </button>
        <div aria-hidden className="my-1.5 h-px w-8 shrink-0 bg-slate-200" />

        {nav.groups.map((g) => {
          const Icon = g.icon;
          const isActive = activeGroup === g.id;
          const isShown = panelState !== 'hidden' && shownId === g.id && !isActive;
          const state = isActive ? 'active' : isShown ? 'shown' : 'idle';
          const box =
            'nav-tile-box flex h-10 w-11 items-center justify-center rounded-2xl transition-colors duration-150 ' +
            (isActive
              ? 'bg-gradient-to-tr from-coral to-violet text-white shadow-[0_10px_22px_-10px_rgba(124,92,255,0.8)]'
              : isShown
                ? 'bg-white text-ink shadow-sm'
                : 'text-muted');
          const label = (
            <>
              <span className={box}>
                <Icon aria-hidden className="h-5 w-5" strokeWidth={2} />
              </span>
              <span className={`mt-1 max-w-full truncate px-0.5 text-[10.5px] leading-none ${isActive ? 'font-extrabold text-ink' : 'font-semibold text-muted'}`}>
                {g.label}
              </span>
            </>
          );
          const cls = 'nav-tile flex w-[60px] shrink-0 flex-col items-center py-1';
          return g.to ? (
            <Link
              key={g.id}
              to={g.to}
              data-state={state}
              aria-current={isActive ? 'page' : undefined}
              onClick={() => {
                setViewing(null);
                setFlyout(false);
              }}
              className={cls}
            >
              {label}
            </Link>
          ) : (
            <button
              key={g.id}
              type="button"
              data-state={state}
              aria-label={g.tag ? `${g.label} (${g.tag})` : g.label}
              aria-current={isActive ? 'true' : undefined}
              aria-expanded={!docked ? flyout && shownId === g.id : undefined}
              onClick={() => pickGroup(g.id)}
              className={cls}
            >
              {label}
            </button>
          );
        })}

        <div className="mt-auto" />
        {isLg && nav.state.collapsed && (
          <button
            type="button"
            onClick={() => {
              setCollapsed(false);
              setFlyout(false);
            }}
            aria-label="Paneli aç"
            title="Paneli aç"
            className="nav-tile nav-ghost mb-1 flex h-10 w-11 shrink-0 items-center justify-center rounded-2xl text-muted"
          >
            <PanelLeftOpen aria-hidden className="h-5 w-5" />
          </button>
        )}
        <button
          type="button"
          data-state={modulesOpen ? 'active' : 'idle'}
          onClick={ui.openModules}
          className="nav-tile flex w-[60px] shrink-0 flex-col items-center py-1"
          aria-label="Tüm modüller"
        >
          <span className={`nav-tile-box flex h-10 w-11 items-center justify-center rounded-2xl ${modulesOpen ? 'bg-gradient-to-tr from-coral to-violet text-white' : 'text-muted'}`}>
            <Grid2x2 aria-hidden className="h-5 w-5" strokeWidth={2} />
          </span>
          <span className="mt-1 text-center text-[10px] font-semibold leading-[1.1] text-muted">Tüm modüller</span>
        </button>
        <button
          type="button"
          onClick={ui.openProfile}
          title={`${whoName || 'Oturum'} · ${roleLabel(nav.role)}`}
          aria-label={`Profilim: ${whoName || 'oturum'}, ${roleLabel(nav.role)}`}
          className="nav-tile mt-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-amber-400 to-orange-500 text-[12px] font-bold text-white shadow-sm ring-2 ring-white"
        >
          {initials(whoName)}
        </button>
      </nav>

      {shown && (
        <aside
          ref={panelRef}
          data-state={panelState}
          data-anim={anim ? '1' : '0'}
          aria-label={`${shown.label} ekranları`}
          aria-hidden={panelState === 'hidden' ? true : undefined}
          className="nav-panel glass-panel hidden flex-col rounded-[26px] shadow-glass-float md:flex print:hidden"
        >
          <header className="flex items-start gap-2 border-b border-slate-200/70 px-4 pb-3 pt-4">
            <div className="min-w-0 flex-1">
              <h2 className="truncate text-[18px] font-extrabold leading-tight tracking-tight text-ink">{isOverview ? 'Tüm ekranlar' : shown.label}</h2>
              <p className="mt-0.5 truncate text-[11.5px] font-medium text-muted">{isOverview ? 'Kampüs · bütün ekranlar' : shown.hint}</p>
            </div>
            {panelState === 'docked' ? (
              <button type="button" onClick={() => setCollapsed(true)} aria-label="Paneli daralt" title="Paneli daralt" className="nav-ghost nav-tile -mr-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-muted">
                <ChevronsLeft aria-hidden className="h-4 w-4" />
              </button>
            ) : isLg ? (
              <button
                type="button"
                onClick={() => {
                  setCollapsed(false);
                  setFlyout(false);
                }}
                aria-label="Paneli sabitle"
                title="Paneli sabitle"
                className="nav-ghost nav-tile -mr-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-muted"
              >
                <PanelLeftOpen aria-hidden className="h-4 w-4" />
              </button>
            ) : (
              <button type="button" onClick={() => setFlyout(false)} aria-label="Kapat" className="nav-ghost nav-tile -mr-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-muted">
                <X aria-hidden className="h-4 w-4" />
              </button>
            )}
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 py-2 [scrollbar-width:thin]">
            {isOverview ? (
              <NavTree
                groups={nav.groups.filter((g) => g.id !== 'kampus')}
                activeId={nav.active?.item.id}
                alertCount={nav.alertCount}
                open={nav.state.open ?? {}}
                onToggle={(id, next) => nav.update((s) => ({ ...s, open: { ...(s.open ?? {}), [id]: next } }))}
                onPick={() => setFlyout(false)}
              />
            ) : (
              <NavList items={shown.items} activeId={nav.active?.item.id} alertCount={nav.alertCount} onPick={() => setFlyout(false)} />
            )}
          </div>

          <section aria-label="Son açılanlar" className="m-2 mt-0 rounded-2xl bg-white/70 px-2 pb-2 pt-2.5 ring-1 ring-slate-200/60">
            <div className="flex items-center justify-between px-1.5 pb-1">
              <h3 className="text-[10.5px] font-extrabold uppercase tracking-[0.08em] text-muted">Son açılanlar</h3>
              <button type="button" onClick={ui.openPalette} className="nav-ghost rounded-md px-1.5 text-[10.5px] font-bold text-violet" title="Son açılan 12 ekranın hepsi arama penceresinde">
                tümü
              </button>
            </div>
            {recent.length ? (
              <ul>
                {recent.map((r) => (
                  <li key={r.to}>
                    <Link to={r.to} onClick={() => setFlyout(false)} className="nav-recent block rounded-lg px-1.5 py-1">
                      <span className="block truncate text-[12.5px] font-semibold text-ink">{r.label}</span>
                      <span className="block truncate text-[10.5px] text-muted">
                        {ago(r.at)} · {r.group}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-1.5 pb-1 text-[11.5px] text-muted">Açtığınız ekranlar burada listelenir.</p>
            )}
          </section>
        </aside>
      )}
    </>
  );
}
