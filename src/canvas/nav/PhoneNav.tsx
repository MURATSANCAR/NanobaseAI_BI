import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Drawer } from '@base-ui/react/drawer';
import { Bell, ChevronRight, Grid2x2, House, LayoutDashboard, LayoutGrid, Search, SendHorizontal, Sparkles, X } from 'lucide-react';
import { homeGroup, type NavGroupId } from './navModel';
import { NavList } from './NavList';
import { initials, roleLabel, useNavUi, type NavData } from './useNav';

/**
 * Telefon menüsü (<768 px): sol ray yok. Alt çubuk: Kampüs · Masam · Zeki AI · Uyarılar · Menü.
 * «Menü» alttan açılan sayfadır (arama, çalışma alanı çipleri, seçili alanın ekranları, tüm modüller,
 * profil). «Zeki AI» soruyu alır, cevap Genel bakış'ta açılır (Kampüs'teki kutuyla aynı yol).
 */
export default function PhoneNav({ nav, whoName }: { nav: NavData; whoName: string }) {
  const ui = useNavUi();
  const loc = useLocation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [question, setQuestion] = useState('');
  const groups = nav.groups.filter((g) => g.id !== 'kampus');
  const [chip, setChip] = useState<NavGroupId | null>(null);
  const activeGroup = nav.active?.group.id;
  const chipId = chip ?? (activeGroup && activeGroup !== 'kampus' ? activeGroup : homeGroup(nav.role));
  const shown = groups.find((g) => g.id === chipId) ?? groups[0];

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
          <House aria-hidden className="h-[22px] w-[22px]" />
          Kampüs
        </Link>
        <Link to="/editoryal" className={`${btn} ${tone(at('/editoryal'))}`} aria-current={at('/editoryal') ? 'page' : undefined}>
          <span className={`flex h-7 w-11 items-center justify-center rounded-full ${at('/editoryal') ? 'bg-violet/15' : ''}`}>
            <LayoutDashboard aria-hidden className="h-[22px] w-[22px]" />
          </span>
          Masam
        </Link>
        <button type="button" onClick={() => setAskOpen(true)} className={`${btn} -mt-7 text-ink`} aria-label="Zeki AI'a sor">
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-tr from-coral to-violet text-white shadow-[0_12px_26px_-10px_rgba(124,92,255,0.9)] ring-4 ring-white">
            <Sparkles aria-hidden className="h-6 w-6" />
          </span>
          <span className="font-extrabold">Zeki AI</span>
        </button>
        <Link to="/uyarilar" className={`${btn} ${tone(at('/uyarilar'))}`} aria-current={at('/uyarilar') ? 'page' : undefined}>
          <span className="relative">
            <Bell aria-hidden className="h-[22px] w-[22px]" />
            {nav.alertCount > 0 && (
              <span className="absolute -right-2 -top-1.5 min-w-[18px] rounded-full bg-coral px-1 text-center text-[10.5px] font-extrabold leading-[18px] text-white ring-2 ring-white">
                {nav.alertCount}
              </span>
            )}
          </span>
          Uyarılar
        </Link>
        <button type="button" onClick={() => setMenuOpen(true)} className={`${btn} ${tone(menuOpen)}`} aria-haspopup="dialog" aria-expanded={menuOpen}>
          <LayoutGrid aria-hidden className="h-[22px] w-[22px]" />
          Menü
        </button>
      </nav>

      <Drawer.Root open={menuOpen} onOpenChange={setMenuOpen} swipeDirection="down">
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
              <div role="tablist" aria-label="Çalışma alanı" className="nav-chips mt-3 flex shrink-0 gap-2 overflow-x-auto px-4 pb-1">
                {groups.map((g) => {
                  const on = g.id === shown?.id;
                  return (
                    <button
                      key={g.id}
                      type="button"
                      role="tab"
                      aria-selected={on}
                      onClick={() => setChip(g.id)}
                      className={
                        'nav-bar-btn min-h-11 shrink-0 rounded-full px-4 text-[14px] font-bold ' +
                        (on ? 'bg-gradient-to-r from-coral to-violet text-white shadow-md' : 'bg-slate-100 text-ink/80')
                      }
                    >
                      {g.label}
                    </button>
                  );
                })}
              </div>
              <Drawer.Content className="min-h-0 flex-1 touch-auto overflow-y-auto overscroll-contain px-3 pb-[max(16px,env(safe-area-inset-bottom))] pt-2">
                {shown?.tag && <p className="px-3 pb-1 text-[12px] font-bold text-emerald-700">{shown.tag}</p>}
                {shown && <NavList items={shown.items} activeId={nav.active?.item.id} alertCount={nav.alertCount} onPick={() => setMenuOpen(false)} variant="sheet" />}
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
                  <Drawer.Title className="flex-1 text-[19px] font-extrabold tracking-tight">Zeki AI'a sor</Drawer.Title>
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
