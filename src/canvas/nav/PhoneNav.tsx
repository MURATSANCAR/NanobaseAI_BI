import { useLayoutEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Drawer } from '@base-ui/react/drawer';
import { Bell, ChevronLeft, ChevronRight, Grid2x2, House, LayoutDashboard, LayoutGrid, Menu, Search, SendHorizontal, Sparkles, X } from 'lucide-react';
import { panelActiveId, panelItems, railView } from './navModel';
import { NavList } from './NavList';
import { initials, roleLabel, useNavUi, type NavData } from './useNav';

/**
 * Telefon menüsü (<768 px): sol ray yok. Alt çubuk: Kampüs · Masam · ZEKİ AI · Uyarılar · Menü.
 * «Menü» alttan açılan sayfadır (arama; bir ana modülün ekranındayken yalnız o modülün ekranları ve «Ana
 * menü» dönüşü, Kampüs'te ana modül listesi; tüm modüller, profil). Listeden modül seçmek sayfayı
 * değiştirmez, o modülün ekranlarını gösterir. «ZEKİ AI» soruyu alır, cevap Genel bakış'ta açılır.
 */
export default function PhoneNav({ nav, whoName }: { nav: NavData; whoName: string }) {
  const ui = useNavUi();
  const loc = useLocation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [question, setQuestion] = useState('');
  const activeGroup = nav.active?.group.id ?? null;
  // Menü sayfasında göz atılan görünüm; sayfa her açılışta bulunulan ekranın modülüyle başlar.
  const [browse, setBrowse] = useState<string | null>(null);
  const [motion, setMotion] = useState<'in' | 'out' | null>(null);
  const focusTo = useRef<string | null>(null);
  const view = railView(nav.groups, activeGroup, browse);
  const viewKey = view.kind === 'module' ? view.group.id : 'modules';
  useLayoutEffect(() => {
    if (!focusTo.current) return;
    document.getElementById(focusTo.current)?.focus();
    focusTo.current = null;
  }, [viewKey]);
  const openMenu = (open: boolean) => {
    if (open) {
      setBrowse(null);
      setMotion(null);
    }
    setMenuOpen(open);
  };

  const at = (p: string) => loc.pathname === p;
  const ask = () => {
    const q = question.trim();
    if (!q) return;
    setAskOpen(false);
    setQuestion('');
    navigate(`/genel-bakis?soru=${encodeURIComponent(q)}`);
  };

  const btn = 'nav-bar-btn flex min-w-0 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold';
  const tone = (on: boolean) => (on ? 'text-violet font-extrabold' : 'text-muted');

  return (
    <>
      <nav aria-label="Ana menü" className="nav-bar glass-dock grid grid-cols-5 items-center rounded-[22px] px-1 shadow-dock-shadow md:hidden print:hidden">
        <Link to="/" className={`${btn} ${tone(at('/'))}`} aria-current={at('/') ? 'page' : undefined}>
          <span className="flex h-7 items-center">
            <House aria-hidden className="h-[22px] w-[22px]" />
          </span>
          Kampüs
        </Link>
        <Link to="/editoryal" className={`${btn} ${tone(at('/editoryal'))}`} aria-current={at('/editoryal') ? 'page' : undefined}>
          <span className={`flex h-7 w-11 items-center justify-center rounded-full ${at('/editoryal') ? 'bg-violet/15' : ''}`}>
            <LayoutDashboard aria-hidden className="h-[22px] w-[22px]" />
          </span>
          Masam
        </Link>
        <button type="button" onClick={() => setAskOpen(true)} className={`${btn} -mt-7 text-ink`} aria-label="ZEKİ AI'a sor">
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-tr from-coral to-violet text-white shadow-[0_12px_26px_-10px_rgba(124,92,255,0.9)] ring-4 ring-white">
            <Sparkles aria-hidden className="h-6 w-6" />
          </span>
          <span className="font-extrabold">ZEKİ AI</span>
        </button>
        <Link to="/uyarilar" className={`${btn} ${tone(at('/uyarilar'))}`} aria-current={at('/uyarilar') ? 'page' : undefined}>
          <span className="relative flex h-7 items-center">
            <Bell aria-hidden className="h-[22px] w-[22px]" />
            {nav.alertCount > 0 && (
              <span className="absolute -right-2.5 -top-0.5 min-w-[18px] rounded-full bg-coral px-1 text-center text-[10.5px] font-extrabold leading-[18px] text-white ring-2 ring-white">
                {nav.alertCount}
              </span>
            )}
          </span>
          Uyarılar
        </Link>
        <button type="button" onClick={() => openMenu(true)} className={`${btn} ${tone(menuOpen)}`} aria-haspopup="dialog" aria-expanded={menuOpen}>
          <span className="flex h-7 items-center">
            <Menu aria-hidden className="h-[22px] w-[22px]" />
          </span>
          Menü
        </button>
      </nav>

      <Drawer.Root open={menuOpen} onOpenChange={openMenu} swipeDirection="down">
        <Drawer.Portal>
          <Drawer.Backdrop className="nav-scrim" />
          <Drawer.Viewport className="nav-viewport">
            <Drawer.Popup className="nav-sheet font-canvas text-ink">
              <div aria-hidden className="mx-auto mt-2.5 h-1.5 w-10 shrink-0 rounded-full bg-slate-300" />
              <div className="flex items-center gap-3 px-4 pb-2 pt-2">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-violet/10 text-violet">
                  <LayoutGrid aria-hidden className="h-5 w-5" />
                </span>
                <Drawer.Title className="flex-1 text-[20px] font-extrabold tracking-tight">Menü</Drawer.Title>
                <Drawer.Close className="nav-bar-btn flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 text-muted" aria-label="Kapat">
                  <X aria-hidden className="h-5 w-5" />
                </Drawer.Close>
              </div>
              <div className="px-4">
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    ui.openPalette();
                  }}
                  className="flex min-h-12 w-full items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 text-left text-[15px] text-muted"
                >
                  <Search aria-hidden className="h-5 w-5 shrink-0" />
                  Ekran, kitap veya kişi ara
                </button>
              </div>
              <Drawer.Content className="min-h-0 flex-1 touch-auto overflow-y-auto overflow-x-hidden overscroll-contain px-3 pb-[max(16px,env(safe-area-inset-bottom))] pt-3">
                <div key={viewKey} className="nav-view" data-motion={motion ?? undefined}>
                  {view.kind === 'module' ? (
                    <>
                      <button
                        type="button"
                        onClick={() => {
                          focusTo.current = `nav-sheet-mod-${view.group.id}`;
                          setMotion('out');
                          setBrowse('modules');
                        }}
                        className="nav-row flex min-h-11 items-center gap-1 rounded-xl pl-1.5 pr-3 text-[14px] font-bold text-violet"
                        aria-label="Ana menü: bütün ana modüller"
                      >
                        <ChevronLeft aria-hidden className="h-5 w-5" />
                        Ana menü
                      </button>
                      <div className="flex items-center gap-2.5 px-3 pb-2 pt-1">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-coral to-violet text-white">
                          <view.group.icon aria-hidden className="h-[18px] w-[18px]" />
                        </span>
                        <div className="min-w-0">
                          <h3 id="nav-sheet-head" tabIndex={-1} className="truncate text-[17px] font-extrabold tracking-tight outline-none">
                            {view.group.label}
                          </h3>
                          {view.group.tag && <p className="text-[12px] font-bold text-emerald-700">{view.group.tag}</p>}
                        </div>
                      </div>
                      <NavList items={panelItems(view.group.items)} activeId={panelActiveId(view.group.items, nav.active?.item.id)} alertCount={nav.alertCount} counts={nav.counts} mailOverdue={nav.mailOverdue} onPick={() => setMenuOpen(false)} variant="sheet" />
                    </>
                  ) : (
                    <>
                      <h3 className="px-3 pb-1 text-[10.5px] font-extrabold uppercase tracking-[0.08em] text-muted/80">Ana modüller</h3>
                      <ul className="flex flex-col gap-0.5">
                        {nav.groups.map((g) => {
                          const on = g.id === activeGroup;
                          const rowCls =
                            'nav-row flex min-h-12 w-full items-center gap-3 rounded-xl px-3 text-left text-[15px] ' +
                            (on ? 'bg-violet/10 font-extrabold text-ink' : 'font-semibold text-ink/80');
                          const body = (
                            <>
                              <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${on ? 'bg-gradient-to-tr from-coral to-violet text-white' : 'bg-slate-100 text-muted'}`}>
                                <g.icon aria-hidden className="h-4 w-4" />
                              </span>
                              <span className="min-w-0 flex-1">
                                <span className="block truncate">{g.label}</span>
                                {g.tag && <span className="block text-[12px] font-bold text-emerald-700">{g.tag}</span>}
                              </span>
                              <ChevronRight aria-hidden className="h-4 w-4 shrink-0 text-muted/60" />
                            </>
                          );
                          return (
                            <li key={g.id}>
                              {g.to ? (
                                <Link id={`nav-sheet-mod-${g.id}`} to={g.to} onClick={() => setMenuOpen(false)} aria-current={on ? 'page' : undefined} className={rowCls}>
                                  {body}
                                </Link>
                              ) : (
                                <button
                                  id={`nav-sheet-mod-${g.id}`}
                                  type="button"
                                  onClick={() => {
                                    focusTo.current = 'nav-sheet-head';
                                    setMotion('in');
                                    setBrowse(g.id);
                                  }}
                                  aria-label={`${g.label}${g.tag ? ` (${g.tag})` : ''}: ekranlarını göster`}
                                  aria-current={on ? 'true' : undefined}
                                  className={rowCls}
                                >
                                  {body}
                                </button>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    </>
                  )}
                </div>
                <div className="mt-3 border-t border-slate-200/80 pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      ui.openModules();
                    }}
                    className="nav-row flex min-h-12 w-full items-center gap-2.5 rounded-xl px-3 text-left text-[15px] font-semibold text-ink/80"
                  >
                    <Grid2x2 aria-hidden className="h-4 w-4 text-muted" />
                    <span className="flex-1">Tüm modüller</span>
                    <ChevronRight aria-hidden className="h-4 w-4 text-muted/60" />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      ui.openProfile();
                    }}
                    className="nav-row flex min-h-14 w-full items-center gap-3 rounded-xl px-3 text-left"
                  >
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-amber-400 to-orange-500 text-[12px] font-bold text-white">
                      {initials(whoName)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[15px] font-bold">{whoName || 'Oturum'}</span>
                      <span className="block text-[12px] text-muted">{roleLabel(nav.role)} · profilim</span>
                    </span>
                    <ChevronRight aria-hidden className="h-4 w-4 text-muted/60" />
                  </button>
                </div>
              </Drawer.Content>
            </Drawer.Popup>
          </Drawer.Viewport>
        </Drawer.Portal>
      </Drawer.Root>

      <Drawer.Root open={askOpen} onOpenChange={setAskOpen} swipeDirection="down">
        <Drawer.Portal>
          <Drawer.Backdrop className="nav-scrim" />
          <Drawer.Viewport className="nav-viewport">
            <Drawer.Popup className="nav-sheet font-canvas text-ink">
              <div aria-hidden className="mx-auto mt-2.5 h-1.5 w-10 shrink-0 rounded-full bg-slate-300" />
              <div className="px-4 pb-[max(20px,env(safe-area-inset-bottom))] pt-3">
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-tr from-coral to-violet text-white">
                    <Sparkles aria-hidden className="h-5 w-5" />
                  </span>
                  <Drawer.Title className="flex-1 text-[19px] font-extrabold tracking-tight">ZEKİ AI'a sor</Drawer.Title>
                  <Drawer.Close className="nav-bar-btn flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 text-muted" aria-label="Kapat">
                    <X aria-hidden className="h-5 w-5" />
                  </Drawer.Close>
                </div>
                <Drawer.Description className="mt-2 text-[13px] leading-snug text-muted">
                  Satış ve finans verisine dair sorunuzu yazın; cevap Genel bakış ekranında açılır.
                </Drawer.Description>
                <form
                  className="mt-3 flex items-center gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    ask();
                  }}
                >
                  <input
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder="örn. bu ay kanal bazında net ciro"
                    enterKeyHint="send"
                    aria-label="Soru"
                    className="min-h-12 min-w-0 flex-1 rounded-2xl border border-slate-200 bg-white px-4 text-[16px] font-medium outline-none focus:border-violet focus:ring-2 focus:ring-violet/25"
                  />
                  <button
                    type="submit"
                    disabled={!question.trim()}
                    aria-label="Gönder"
                    className="nav-bar-btn flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-tr from-coral to-violet text-white disabled:opacity-40"
                  >
                    <SendHorizontal aria-hidden className="h-5 w-5" />
                  </button>
                </form>
              </div>
            </Drawer.Popup>
          </Drawer.Viewport>
        </Drawer.Portal>
      </Drawer.Root>
    </>
  );
}
