import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronLeft, ChevronRight, ChevronsRight, Grid2x2, Search } from 'lucide-react';
import { badgeLabel, panelActiveId, panelItems, railView, type NavCounts, type NavItem, type VisibleGroup } from './navModel';
import { initials, paletteKey, roleLabel, useNavUi, type NavData } from './useNav';

/**
 * Masaüstü menüsü (≥768 px): solda tek bir 84 px ray. Bir ana modülün ekranındayken ray yalnız o modülün
 * ekranlarını gösterir; üstteki «Ana menü» bütün ana modüllerin listesine döner. Kampüs'te ve menü dışı
 * adreslerde ana modül listesi görünür; listeden bir modül seçmek sayfayı değiştirmez, rayda o modülün
 * ekranlarını açar (göz atma). Ekran değişince ray bulunulan ekranın modülüne döner.
 *
 * Hareket: görünüm yalnız kişinin tıklamasıyla değişince 160 ms kayar (modüle girerken sağdan, çıkarken
 * soldan); ekran değişince anlıktır. Odak da kişiyle birlikte taşınır: modüle girince modül başlığına,
 * «Ana menü»ye dönünce gelinen modülün düğmesine.
 *
 * Geniş menü: raydaki büyük «Aç» düğmesi aynı görünümü 272 px'lik bir panelde, adlar tek satırda açar. Panel
 * rayın üstüne biner (sahne kaymaz), raydan sağa doğru açılır (clip-path), ok 180° döner. Fare panelden
 * çıkınca 300 ms sonra kendiliğinden kapanır; Esc, dışarı tıklama ve ekran değişimi de kapatır.
 */
export default function DesktopNav({ nav, whoName, modulesOpen }: { nav: NavData; whoName: string; modulesOpen: boolean }) {
  const ui = useNavUi();
  const loc = useLocation();
  const activeGroup = nav.active?.group.id ?? null;
  // Kişinin göz attığı görünüm yalnız seçildiği adreste geçerlidir: ekran değişince (menüden, ⌘K'dan, geri
  // tuşundan) ray aynı boyamada bulunulan ekranın modülüne döner, eski görünüm bir kare bile görünmez.
  const here = loc.pathname + loc.search;
  const [picked, setPicked] = useState<{ at: string; view: string; motion: 'in' | 'out' } | null>(null);
  // Adres değişince seçim atılır (geri tuşuyla aynı adrese dönülünce eski görünüm geri gelmesin).
  if (picked && picked.at !== here) setPicked(null);
  const browse = picked?.at === here ? picked.view : null;
  const motion = picked?.at === here ? picked.motion : null;
  const focusTo = useRef<string | null>(null);
  const [wide, setWide] = useState(false);
  const closeTimer = useRef<number | null>(null);
  const wideRef = useRef<HTMLDivElement>(null);
  const cancelClose = () => {
    if (closeTimer.current != null) window.clearTimeout(closeTimer.current);
    closeTimer.current = null;
  };
  const closeWide = (refocus = false) => {
    cancelClose();
    setWide(false);
    if (refocus) document.getElementById('nav-wide-toggle')?.focus();
  };
  const openWide = () => {
    cancelClose();
    setWide(true);
    // Klavyeyle açılınca odak panele geçer; fareyle açılınca da aynı düğmenin üstünde kalır.
    requestAnimationFrame(() => document.getElementById('nav-wide-close')?.focus({ preventScroll: true }));
  };
  // Ekran değişince panel kapanır (bağlantıya tıklanınca da buradan).
  useEffect(() => closeWide(), [here]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!wide) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && closeWide(true);
    const onDown = (e: PointerEvent) => {
      if (!wideRef.current?.contains(e.target as Node)) closeWide();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onDown);
    };
  }, [wide]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => cancelClose, []);

  const view = railView(nav.groups, activeGroup, browse);
  const viewKey = view.kind === 'module' ? view.group.id : 'modules';

  useLayoutEffect(() => {
    if (!focusTo.current) return;
    document.getElementById(focusTo.current)?.focus({ preventScroll: false });
    focusTo.current = null;
  }, [viewKey]);

  const openModule = (g: VisibleGroup) => {
    focusTo.current = wide ? null : `nav-head-${g.id}`;
    setPicked({ at: here, view: g.id, motion: 'in' });
  };
  const backToModules = () => {
    focusTo.current = !wide && view.kind === 'module' ? `nav-mod-${view.group.id}` : null;
    setPicked({ at: here, view: 'modules', motion: 'out' });
  };

  const viewBody = (wideMode: boolean) =>
    view.kind === 'modules' ? (
      <ModuleList groups={nav.groups} activeGroup={activeGroup} onOpen={openModule} wide={wideMode} />
    ) : (
      <ModuleItems
        group={view.group}
        isActiveGroup={view.group.id === activeGroup}
        onBack={backToModules}
        activeId={nav.active?.item.id}
        alertCount={nav.alertCount}
        counts={nav.counts}
        mailOverdue={nav.mailOverdue}
        wide={wideMode}
      />
    );

  return (
    <>
    <nav
      aria-label="Ana menü"
      className="nav-rail glass-panel hidden flex-col items-center gap-1 overflow-y-auto overflow-x-hidden overscroll-contain rounded-[26px] py-3 shadow-glass-float md:flex print:hidden [scrollbar-width:none]"
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
        className="nav-tile nav-ghost flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-2xl text-slate-700"
      >
        <Search aria-hidden className="h-[18px] w-[18px]" />
        <span className="mt-0.5 text-[9.5px] font-bold leading-none">{paletteKey()}</span>
      </button>
      <button
        id="nav-wide-toggle"
        type="button"
        onClick={openWide}
        aria-expanded={wide}
        aria-controls="nav-wide"
        aria-label="Menüyü genişlet"
        title="Menüyü genişlet"
        data-open={wide ? 'true' : 'false'}
        className="nav-tile nav-toggle mt-1 flex h-11 w-[76px] shrink-0 items-center justify-center rounded-2xl bg-gradient-to-r from-coral to-violet text-white shadow-[0_10px_22px_-10px_rgba(124,92,255,0.9)]"
      >
        <ChevronsRight aria-hidden className="nav-toggle-icon h-6 w-6" strokeWidth={2.5} />
      </button>
      <div aria-hidden className="my-1.5 h-px w-8 shrink-0 bg-slate-200" />

      <div key={viewKey} className="nav-view flex w-full shrink-0 flex-col items-center gap-1" data-motion={motion ?? undefined}>
        {viewBody(false)}
      </div>

      <div className="mt-auto" />
      <button
        type="button"
        data-state={modulesOpen ? 'active' : 'idle'}
        onClick={ui.openModules}
        className="nav-tile mt-2 flex w-[76px] shrink-0 flex-col items-center py-1"
        aria-label="Tüm modüller"
      >
        <span className={`nav-tile-box flex h-10 w-11 items-center justify-center rounded-2xl ${modulesOpen ? 'bg-gradient-to-tr from-coral to-violet text-white' : 'text-slate-700'}`}>
          <Grid2x2 aria-hidden className="h-5 w-5" strokeWidth={2} />
        </span>
        <span className="mt-1 text-center text-[10.5px] font-bold leading-[1.1] text-slate-700">Tüm modüller</span>
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

    <div
      id="nav-wide"
      ref={wideRef}
      role="dialog"
      aria-label="Geniş menü"
      aria-hidden={!wide}
      data-open={wide ? 'true' : 'false'}
      onPointerEnter={cancelClose}
      onPointerLeave={(e) => {
        if (!wide || e.pointerType !== 'mouse') return;
        cancelClose();
        closeTimer.current = window.setTimeout(() => setWide(false), 300);
      }}
      className="nav-wide hidden flex-col gap-1 overflow-y-auto overflow-x-hidden overscroll-contain rounded-[26px] px-2.5 py-3 md:flex print:hidden [scrollbar-width:none]"
    >
      <div className="flex shrink-0 items-center gap-2 px-1">
        <Link to="/" tabIndex={wide ? 0 : -1} aria-label="Kampüs ana sayfası" className="nav-tile flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-tr from-coral to-violet text-[17px] font-black text-white shadow-md">
          T
        </Link>
        <span className="truncate text-[15px] font-black text-ink">Menü</span>
      </div>
      <button
        id="nav-wide-close"
        type="button"
        tabIndex={wide ? 0 : -1}
        onClick={() => closeWide(true)}
        aria-expanded={wide}
        aria-controls="nav-wide"
        className="nav-tile nav-toggle mt-1 flex h-11 w-full shrink-0 items-center gap-2 rounded-2xl bg-gradient-to-r from-coral to-violet px-4 text-[13.5px] font-extrabold text-white shadow-[0_10px_22px_-10px_rgba(124,92,255,0.9)]"
      >
        <ChevronsRight aria-hidden className="nav-toggle-icon h-6 w-6 shrink-0" strokeWidth={2.5} />
        <span className="flex-1 text-left">Menüyü daralt</span>
      </button>
      <button
        type="button"
        tabIndex={wide ? 0 : -1}
        onClick={() => {
          closeWide();
          ui.openPalette();
        }}
        className="nav-row nav-ghost flex min-h-10 shrink-0 items-center gap-2.5 rounded-xl px-3 text-[13.5px] font-semibold text-slate-700"
      >
        <Search aria-hidden className="h-4 w-4 shrink-0" />
        <span className="flex-1 text-left">Ara veya git</span>
        <kbd className="rounded-md bg-slate-100 px-1.5 text-[11px] font-bold text-slate-600">{paletteKey()}</kbd>
      </button>
      <div aria-hidden className="mx-2 my-1 h-px shrink-0 bg-slate-200" />
      <div key={viewKey} className="nav-view flex w-full shrink-0 flex-col gap-1" data-motion={motion ?? undefined}>
        {viewBody(true)}
      </div>
      <div className="mt-auto" />
      <button
        type="button"
        tabIndex={wide ? 0 : -1}
        onClick={() => {
          closeWide();
          ui.openModules();
        }}
        className="nav-row nav-ghost mt-2 flex min-h-10 shrink-0 items-center gap-2.5 rounded-xl px-3 text-[13.5px] font-bold text-slate-700"
      >
        <Grid2x2 aria-hidden className="h-4 w-4 shrink-0" strokeWidth={2} />
        Tüm modüller
      </button>
      <button
        type="button"
        tabIndex={wide ? 0 : -1}
        onClick={() => {
          closeWide();
          ui.openProfile();
        }}
        className="nav-row nav-ghost flex min-h-11 shrink-0 items-center gap-2.5 rounded-xl px-2 text-left"
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-amber-400 to-orange-500 text-[12px] font-bold text-white ring-2 ring-white">{initials(whoName)}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-bold text-ink">{whoName || 'Oturum'}</span>
          <span className="block truncate text-[11.5px] font-semibold text-slate-600">{roleLabel(nav.role)}</span>
        </span>
      </button>
    </div>
    </>
  );
}

const tileBox = (on: boolean) =>
  'nav-tile-box flex h-10 w-11 items-center justify-center rounded-2xl transition-colors duration-150 ' +
  (on ? 'bg-gradient-to-tr from-coral to-violet text-white shadow-[0_10px_22px_-10px_rgba(124,92,255,0.8)]' : 'bg-white text-slate-700 ring-1 ring-slate-200/90 shadow-[0_1px_2px_rgba(27,31,42,0.06)]');

/** Ana modül listesi: Kampüs bağlantıdır; öbür modüller rayda kendi ekranlarını açar. */
function ModuleList({ groups, activeGroup, onOpen, wide = false }: { groups: VisibleGroup[]; activeGroup: string | null; onOpen: (g: VisibleGroup) => void; wide?: boolean }) {
  if (wide) return <WideModuleList groups={groups} activeGroup={activeGroup} onOpen={onOpen} />;
  return (
    <ul aria-label="Ana modüller" className="flex w-full flex-col items-center gap-1">
      {groups.map((g) => {
        const Icon = g.icon;
        const isActive = activeGroup === g.id;
        const label = (
          <>
            <span className={tileBox(isActive)}>
              <Icon aria-hidden className="h-5 w-5" strokeWidth={2} />
            </span>
            <span className={`mt-1 line-clamp-2 max-w-full break-words px-0.5 text-center text-[11px] leading-[1.15] ${isActive ? 'font-extrabold text-violet-700' : 'font-bold text-slate-700'}`}>
              {g.label}
            </span>
          </>
        );
        const cls = 'nav-tile flex w-[76px] flex-col items-center py-1';
        return (
          <li key={g.id} className="flex w-full justify-center">
            {g.to ? (
              <Link id={`nav-mod-${g.id}`} to={g.to} data-state={isActive ? 'active' : 'idle'} aria-current={isActive ? 'page' : undefined} title={g.hint} className={cls}>
                {label}
              </Link>
            ) : (
              <button
                id={`nav-mod-${g.id}`}
                type="button"
                data-state={isActive ? 'active' : 'idle'}
                onClick={() => onOpen(g)}
                title={g.hint}
                aria-label={`${g.label}${g.tag ? ` (${g.tag})` : ''}: ekranlarını göster`}
                aria-current={isActive ? 'true' : undefined}
                className={cls}
              >
                {label}
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Bir ana modülün ekranları: «Ana menü» dönüşü, modül başlığı, bölüm başlıklarıyla ekranlar. */
function ModuleItems({
  group,
  isActiveGroup,
  onBack,
  activeId: current,
  alertCount,
  counts,
  mailOverdue = 0,
  wide = false,
}: {
  group: VisibleGroup;
  isActiveGroup: boolean;
  onBack: () => void;
  activeId?: string;
  alertCount: number;
  counts?: NavCounts;
  mailOverdue?: number;
  wide?: boolean;
}) {
  if (wide)
    return (
      <WideModuleItems group={group} isActiveGroup={isActiveGroup} onBack={onBack} activeId={current} alertCount={alertCount} counts={counts} mailOverdue={mailOverdue} />
    );
  const Icon = group.icon;
  const headId = `nav-head-${group.id}`;
  const items: NavItem[] = panelItems(group.items);
  const activeId = panelActiveId(group.items, current);
  return (
    <>
      <button
        type="button"
        onClick={onBack}
        aria-label="Ana menü: bütün ana modüller"
        title="Ana menü · bütün ana modüller"
        className="nav-tile nav-ghost flex min-h-9 w-[76px] shrink-0 items-center justify-center gap-0.5 rounded-xl bg-white/80 px-1 text-[10.5px] font-bold text-slate-700 ring-1 ring-slate-200/80"
      >
        <ChevronLeft aria-hidden className="h-3.5 w-3.5 shrink-0" strokeWidth={2.5} />
        Ana menü
      </button>
      <div className="flex w-[76px] shrink-0 flex-col items-center pb-0.5 pt-1">
        <span className={tileBox(isActiveGroup)}>
          <Icon aria-hidden className="h-5 w-5" strokeWidth={2} />
        </span>
        <h2 id={headId} tabIndex={-1} className="mt-1 break-words text-center text-[12px] font-black leading-[1.15] text-ink outline-none focus-visible:rounded-md focus-visible:ring-2 focus-visible:ring-violet/40">
          {group.label}
        </h2>
        {group.tag && <span className="mt-0.5 text-center text-[9.5px] font-bold leading-tight text-emerald-700">{group.tag}</span>}
      </div>
      <ul aria-labelledby={headId} className="mx-1.5 flex w-[calc(100%-12px)] flex-col gap-0.5 rounded-2xl bg-white/90 p-1 shadow-[0_1px_3px_rgba(27,31,42,0.06)] ring-1 ring-slate-200">
        {items.map((item, i) => {
          const ItemIcon = item.icon;
          const active = item.id === activeId;
          const heading = item.section && item.section !== items[i - 1]?.section ? item.section : null;
          const count = item.badge === 'alerts' ? alertCount : item.badge ? (counts?.[item.badge] ?? 0) : 0;
          return (
            <Fragment key={item.id}>
              {heading && (
                <li className={`px-0.5 pb-0.5 text-center text-[10px] font-black leading-[1.15] text-violet-700 ${i === 0 ? 'pt-1' : 'mt-1.5 border-t border-slate-200 pt-2'}`}>
                  {heading}
                </li>
              )}
              <li>
                <Link
                  to={item.to}
                  title={item.hint ? `${item.label} · ${item.hint}` : item.label}
                  data-active={active ? '1' : '0'}
                  aria-current={active ? 'page' : undefined}
                  className={
                    'nav-row flex flex-col items-center gap-1 rounded-xl px-1 py-1.5 text-center ' +
                    (active ? 'bg-gradient-to-tr from-coral to-violet text-white shadow-[0_8px_20px_-8px_rgba(124,92,255,0.6)]' : 'text-ink')
                  }
                >
                  <span className="relative">
                    <ItemIcon aria-hidden className={`h-4 w-4 ${active ? 'text-white' : 'text-slate-600'}`} strokeWidth={2} />
                    {count > 0 && (
                      <span
                        className="absolute -right-2.5 -top-1.5 min-w-4 rounded-full bg-amberWarn px-1 text-[9px] font-extrabold tabular-nums leading-4 text-white ring-2 ring-white"
                        aria-label={badgeLabel(item.badge ?? 'alerts', count, mailOverdue)}
                      >
                        {count}
                      </span>
                    )}
                  </span>
                  <span className={`line-clamp-2 break-words text-[10.5px] leading-[1.15] ${active ? 'font-extrabold' : 'font-semibold'}`}>{item.label}</span>
                </Link>
              </li>
            </Fragment>
          );
        })}
      </ul>
    </>
  );
}

/** Geniş paneldeki ana modül listesi: kutu + ad tek satırda. */
function WideModuleList({ groups, activeGroup, onOpen }: { groups: VisibleGroup[]; activeGroup: string | null; onOpen: (g: VisibleGroup) => void }) {
  return (
    <ul aria-label="Ana modüller" className="flex w-full flex-col gap-0.5">
      {groups.map((g) => {
        const Icon = g.icon;
        const isActive = activeGroup === g.id;
        const inner = (
          <>
            <span className={tileBox(isActive).replace('h-10 w-11', 'h-9 w-9 shrink-0')}>
              <Icon aria-hidden className="h-[18px] w-[18px]" strokeWidth={2} />
            </span>
            <span className={`min-w-0 flex-1 truncate text-left text-[13.5px] ${isActive ? 'font-extrabold text-violet-700' : 'font-bold text-ink'}`}>{g.label}</span>
            {g.tag && <span className="shrink-0 text-[10.5px] font-bold text-emerald-700">{g.tag}</span>}
            {!g.to && <ChevronRight aria-hidden className="h-4 w-4 shrink-0 text-slate-400" />}
          </>
        );
        const cls = 'nav-tile nav-row flex min-h-11 w-full items-center gap-2.5 rounded-xl px-1.5';
        return (
          <li key={g.id}>
            {g.to ? (
              <Link to={g.to} data-state={isActive ? 'active' : 'idle'} data-active="0" aria-current={isActive ? 'page' : undefined} title={g.hint} className={cls}>
                {inner}
              </Link>
            ) : (
              <button type="button" data-state={isActive ? 'active' : 'idle'} data-active="0" onClick={() => onOpen(g)} title={g.hint} className={cls}>
                {inner}
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Geniş paneldeki modül ekranları: bölüm başlıkları tam metin, ekran adı ikonun yanında tek satır. */
function WideModuleItems({
  group,
  isActiveGroup,
  onBack,
  activeId: current,
  alertCount,
  counts,
  mailOverdue = 0,
}: {
  group: VisibleGroup;
  isActiveGroup: boolean;
  onBack: () => void;
  activeId?: string;
  alertCount: number;
  counts?: NavCounts;
  mailOverdue?: number;
}) {
  const Icon = group.icon;
  const items: NavItem[] = panelItems(group.items);
  const activeId = panelActiveId(group.items, current);
  return (
    <>
      <button type="button" onClick={onBack} className="nav-row nav-ghost flex min-h-9 shrink-0 items-center gap-1 rounded-xl px-2 text-[12.5px] font-bold text-slate-700">
        <ChevronLeft aria-hidden className="h-4 w-4 shrink-0" strokeWidth={2.5} />
        Ana menü
      </button>
      <div className="flex shrink-0 items-center gap-2.5 px-1.5 py-1">
        <span className={tileBox(isActiveGroup).replace('h-10 w-11', 'h-10 w-10 shrink-0')}>
          <Icon aria-hidden className="h-5 w-5" strokeWidth={2} />
        </span>
        <span className="min-w-0">
          <span className="block text-[15px] font-black leading-tight text-ink">{group.label}</span>
          {group.tag && <span className="block text-[11px] font-bold text-emerald-700">{group.tag}</span>}
        </span>
      </div>
      <ul aria-label={group.label} className="flex flex-col gap-0.5 rounded-2xl bg-white/90 p-1.5 shadow-[0_1px_3px_rgba(27,31,42,0.06)] ring-1 ring-slate-200">
        {items.map((item, i) => {
          const ItemIcon = item.icon;
          const active = item.id === activeId;
          const heading = item.section && item.section !== items[i - 1]?.section ? item.section : null;
          const count = item.badge === 'alerts' ? alertCount : item.badge ? (counts?.[item.badge] ?? 0) : 0;
          return (
            <Fragment key={item.id}>
              {heading && (
                <li className={`px-2.5 pb-1 text-[10.5px] font-black uppercase tracking-[0.06em] text-violet-700 ${i === 0 ? 'pt-1' : 'mt-1 border-t border-slate-200 pt-2.5'}`}>
                  {heading}
                </li>
              )}
              <li>
                <Link
                  to={item.to}
                  title={item.hint}
                  data-active={active ? '1' : '0'}
                  aria-current={active ? 'page' : undefined}
                  className={
                    'nav-row flex min-h-10 items-center gap-2.5 rounded-xl pr-2 text-[13.5px] ' +
                    (item.parent ? 'pl-7 ' : 'pl-2.5 ') +
                    (active ? 'bg-gradient-to-r from-coral to-violet font-bold text-white shadow-[0_8px_20px_-8px_rgba(124,92,255,0.6)]' : 'font-semibold text-ink')
                  }
                >
                  <ItemIcon aria-hidden className={`h-4 w-4 shrink-0 ${active ? 'text-white' : 'text-slate-600'}`} strokeWidth={2} />
                  <span className="min-w-0 flex-1 truncate">{item.label}</span>
                  {count > 0 && (
                    <span
                      className={`shrink-0 rounded-full px-1.5 text-[11px] font-extrabold tabular-nums leading-5 ${active ? 'bg-white/25 text-white' : 'bg-amberWarn/20 text-amber-700'}`}
                      aria-label={badgeLabel(item.badge ?? 'alerts', count, mailOverdue)}
                    >
                      {count}
                    </span>
                  )}
                </Link>
              </li>
            </Fragment>
          );
        })}
      </ul>
    </>
  );
}
