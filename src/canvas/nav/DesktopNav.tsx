import { Fragment, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, Grid2x2, Search } from 'lucide-react';
import type { NavGroupId, NavItem } from './navModel';
import { initials, paletteKey, roleLabel, useNavUi, type NavData } from './useNav';

/**
 * Masaüstü menüsü (≥768 px): solda tek bir 84 px ray. Alanlar (Analiz, Finans…) rayın içinde akordeon
 * gibi açılıp kapanır; aynı anda bir alan açıktır. Açılan alan, bulunulan ekranın alanıdır; kişi başka
 * alanı açabilir ya da açık alanı kapatabilir. Ayrı ekran paneli yoktur.
 */
export default function DesktopNav({ nav, whoName, modulesOpen }: { nav: NavData; whoName: string; modulesOpen: boolean }) {
  const ui = useNavUi();
  const activeGroup = nav.active?.group.id ?? null;
  const [open, setOpen] = useState<NavGroupId | null>(activeGroup);
  // Açılıp kapanma yalnız kişinin tıklamasıyla hareket eder; ekran değişince alanın açılması anlıktır.
  const [anim, setAnim] = useState(false);

  useEffect(() => {
    setAnim(false);
    setOpen(activeGroup);
  }, [activeGroup]);

  const toggle = (id: NavGroupId) => {
    setAnim(true);
    setOpen((cur) => (cur === id ? null : id));
  };

  return (
    <nav
      aria-label="Çalışma alanları"
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
        className="nav-tile nav-ghost flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-2xl text-muted"
      >
        <Search aria-hidden className="h-[18px] w-[18px]" />
        <span className="mt-0.5 text-[9.5px] font-bold leading-none">{paletteKey()}</span>
      </button>
      <div aria-hidden className="my-1.5 h-px w-8 shrink-0 bg-slate-200" />

      {nav.groups.map((g) => {
        const Icon = g.icon;
        const isActive = activeGroup === g.id;
        const isOpen = !g.to && open === g.id;
        const state = isActive ? 'active' : isOpen ? 'shown' : 'idle';
        const box =
          'nav-tile-box flex h-10 w-11 items-center justify-center rounded-2xl transition-colors duration-150 ' +
          (isActive
            ? 'bg-gradient-to-tr from-coral to-violet text-white shadow-[0_10px_22px_-10px_rgba(124,92,255,0.8)]'
            : isOpen
              ? 'bg-white text-ink shadow-sm'
              : 'text-muted');
        const label = (
          <>
            <span className={box}>
              <Icon aria-hidden className="h-5 w-5" strokeWidth={2} />
            </span>
            <span className={`mt-1 flex max-w-full items-center gap-0.5 px-0.5 text-[10.5px] leading-none ${isActive ? 'font-extrabold text-ink' : 'font-semibold text-muted'}`}>
              <span className="truncate">{g.label}</span>
              {!g.to && <ChevronDown aria-hidden className="nav-chevron h-3 w-3 shrink-0" data-open={isOpen ? '1' : '0'} strokeWidth={2.5} />}
            </span>
          </>
        );
        const cls = 'nav-tile flex w-[76px] shrink-0 flex-col items-center py-1';
        if (g.to) {
          return (
            <Link key={g.id} to={g.to} data-state={state} aria-current={isActive ? 'page' : undefined} className={cls}>
              {label}
            </Link>
          );
        }
        const subId = `nav-sub-${g.id}`;
        return (
          <Fragment key={g.id}>
            <button
              type="button"
              data-state={state}
              aria-label={g.tag ? `${g.label} (${g.tag})` : g.label}
              aria-expanded={isOpen}
              aria-controls={subId}
              onClick={() => toggle(g.id)}
              className={cls}
            >
              {label}
            </button>
            <SubList id={subId} items={g.items} open={isOpen} anim={anim} activeId={nav.active?.item.id} alertCount={nav.alertCount} />
          </Fragment>
        );
      })}

      <div className="mt-auto" />
      <button
        type="button"
        data-state={modulesOpen ? 'active' : 'idle'}
        onClick={ui.openModules}
        className="nav-tile mt-2 flex w-[76px] shrink-0 flex-col items-center py-1"
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
  );
}

/** Bir alanın ekranları, rayın içinde: simge + iki satıra sığan ad. Alt başlıklar («Günlük», «İş») ince
 *  bir çizgiyle ayrılır. Kapalıyken klavyeyle de gezilmez. */
function SubList({
  id,
  items,
  open,
  anim,
  activeId,
  alertCount,
}: {
  id: string;
  items: NavItem[];
  open: boolean;
  anim: boolean;
  activeId?: string;
  alertCount: number;
}) {
  const [el, setEl] = useState<HTMLDivElement | null>(null);
  // React 18'de `inert` özniteliği yok, doğrudan konur.
  useEffect(() => {
    el?.toggleAttribute('inert', !open);
  }, [el, open]);

  return (
    <div ref={setEl} id={id} className="nav-sub w-full shrink-0" data-open={open ? '1' : '0'} data-anim={anim ? '1' : '0'}>
      <div className="min-h-0 overflow-hidden">
        <ul className="mx-1.5 mb-1 flex flex-col gap-0.5 rounded-2xl bg-white/55 p-1 ring-1 ring-slate-200/60">
          {items.map((item, i) => {
            const Icon = item.icon;
            const active = item.id === activeId;
            const newSection = i > 0 && item.section !== items[i - 1].section;
            const count = item.badge === 'alerts' ? alertCount : 0;
            return (
              <li key={item.id}>
                {newSection && <div aria-hidden className="mx-auto my-1 h-px w-8 bg-slate-200" />}
                <Link
                  to={item.to}
                  title={item.hint ? `${item.label} · ${item.hint}` : item.label}
                  data-active={active ? '1' : '0'}
                  aria-current={active ? 'page' : undefined}
                  className={
                    'nav-row flex flex-col items-center gap-1 rounded-xl px-1 py-1.5 text-center ' +
                    (active ? 'bg-gradient-to-tr from-coral to-violet text-white shadow-[0_8px_20px_-8px_rgba(124,92,255,0.6)]' : 'text-ink/75')
                  }
                >
                  <span className="relative">
                    <Icon aria-hidden className={`h-4 w-4 ${active ? 'text-white' : 'text-muted'}`} strokeWidth={2} />
                    {count > 0 && (
                      <span
                        className="absolute -right-2.5 -top-1.5 min-w-4 rounded-full bg-amberWarn px-1 text-[9px] font-extrabold tabular-nums leading-4 text-white ring-2 ring-white"
                        aria-label={`${count} uyarı eşiği aşmış`}
                      >
                        {count}
                      </span>
                    )}
                  </span>
                  <span className={`line-clamp-2 break-words text-[10px] leading-[1.15] ${active ? 'font-bold' : 'font-semibold'}`}>{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
