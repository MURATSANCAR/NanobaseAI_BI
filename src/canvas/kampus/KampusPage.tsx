import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Shell, { ZoomStage } from '../stitch/Shell';
import { railFor } from '../stitch/screens';
import {
  Activity,
  Download,
  ArrowRight,
  Bell,
  Bot,
  ChevronDown,
  Contact,
  HeartHandshake,
  LayoutGrid,
  MessageCircle,
  Mic,
  Phone,
  PhoneCall,
  Plus,
  Search,
  Sparkle,
  Sparkles,
} from 'lucide-react';
import groups from '../modules.json';
import { LIVE } from '../stitch/ModulesMenu';
import { useTimasSession } from '../TimasSession';
import { useIsAdmin } from '../useAdmin';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED, EngineAuthError, greetingsApi, peopleApi, prefsApi, type Person } from '../engine';
import { relative } from '../format';
import PersonAvatar from './PersonAvatar';
import ProfileDialog, { useMyProfile } from './ProfileDialog';
import RoomsCard from '../rooms/RoomsCard';
import DbTimingBadge from '../DbTiming';
import zekiImg from '@/assets/kampus/zeki.jpg';
import './kampus.css';

/**
 * Girişten sonraki ilk ekran: Timaş Kampüs & ZEKİ Akıllı Rehber.
 * Stitch ekranı projects/13426839861607265553/screens/a6864de4bb2047878357e34f67bda769
 * birebir JSX'e çevrildi. Tasarıma eklenen tek bölüm "Modüller": kanvas ekranlarına
 * buradan geçilir. Rehber CRM'deki gerçek, etkin kullanıcılardan gelir (dizinle kesiştirilir). Alkış duvarı ve zil
 * sunucudaki kutlama kayıtlarını gösterir; günün modu kişinin tercihine yazılır. Tasarımdaki sesli bülten, çekiliş,
 * doğum günü, ajanda, yeni kitap ve yemekhane kartları bir kaynağa bağlanamadığı için 2026-09-17'de kaldırıldı:
 * çalışmayan düğme bırakılmaz.
 */

/** Rehberde kat süzgeci: kat bilgisi CRM/dizin ya da kişinin profilinden gelir; düğmeler veriden türetilir. */
const ALL_FLOORS = 'ALL';

/** "4. Kat E-12" gibi serbest metinden sıralanabilir kat etiketi. */
const floorKey = (f: string) => f.trim();

/** ZEKİ yalnız finans/satış verisine cevap verir (chat_scope); örnekler de o kapsamdan. */
const PROMPTS = [
  { label: '💰 Bu yıl net ciro', q: 'Bu yıl net ciro ne kadar?' },
  { label: '🏬 En çok satan 5 kanal', q: 'Bu yıl en çok satış yapılan 5 kanalı göster' },
  { label: '📈 Aylara göre ciro', q: 'Bu yıl aylara göre net ciro' },
  { label: '🧾 İade oranı', q: 'Bu yıl iade oranı yüzde kaç?' },
];

/** Modül kutucukları: kanvasta açılan ekranlar. Yeni ekran geldikçe satır eklenir. */
const MODULE_TILES = [
  { to: '/genel-bakis', title: 'ZEKİ AI · Genel Bakış', note: 'Satış, ciro ve verine sor', tone: 'bg-violet/10 text-violet' },
  { to: '/panolar', title: 'Panolar', note: 'Kişisel pano ve grafikler', tone: 'bg-amber-100 text-amber-800' },
  { to: '/uyarilar', title: 'Uyarılar', note: 'Kural ve bildirimler', tone: 'bg-rose-100 text-rose-700' },
  { to: '/planli-raporlar', title: 'Planlı Raporlar', note: 'Zamanlanmış gönderimler', tone: 'bg-sky-100 text-sky-700' },
  { to: '/veri-sozlugu', title: 'Veri Sözlüğü', note: 'Kavramlar ve katalog', tone: 'bg-emerald-100 text-emerald-700', adminOnly: true },
  { to: '/onaylar', title: 'Onaylar', note: 'Bekleyen incelemeler', tone: 'bg-purple-100 text-purple-700', adminOnly: true },
  { to: '/yonetim', title: 'Yönetim', note: 'Ayarlar, tanımlar, değişiklik kaydı', tone: 'bg-slate-200 text-slate-700', adminOnly: true },
];

const trNorm = (s: string) => s.toLocaleLowerCase('tr');

function Card({ id, className = '', children }: { id?: string; className?: string; children: ReactNode }) {
  return (
    <section id={id} className={`kp-card rounded-3xl border border-white/80 bg-white/90 ${className}`}>
      {children}
    </section>
  );
}

export default function KampusPage() {
  const navigate = useNavigate();
  const session = useTimasSession();
  const fullName = session.data?.displayName || session.data?.username || '';
  const firstName = fullName.split(/[\s._@]/)[0] || fullName;

  // ZEKİ kutusu: soru BI kanvasına gider, cevabı motor verir.
  const [zekiQ, setZekiQ] = useState('');
  const askZeki = (q: string) => {
    const text = q.trim();
    if (!text) return;
    navigate(`/genel-bakis?soru=${encodeURIComponent(text)}`);
  };

  // Rehber: CRM'deki gerçek, etkin kullanıcılar. Kat süzgeci + anında arama.
  const people = useQuery({ queryKey: ['people'], queryFn: peopleApi.list, enabled: ENGINE_ENABLED, retry: false, staleTime: 5 * 60_000 });
  const everyone = people.data?.items ?? [];
  const floors = useMemo(
    () => [...new Set(everyone.map((p) => floorKey(p.floor)).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'tr', { numeric: true })),
    [everyone],
  );
  const units = useMemo(() => new Set(everyone.map((p) => p.unit).filter(Boolean)).size, [everyone]);
  const [floor, setFloor] = useState<string>(ALL_FLOORS);
  const [term, setTerm] = useState('');
  const directoryRef = useRef<HTMLDivElement>(null);
  const haystack = (p: Person) => [p.name, p.title, p.unit, p.extension, p.floor, p.desk ?? '', p.mobile, p.phone, p.email, p.username];
  const staff = useMemo(() => {
    const t = trNorm(term.trim());
    return everyone.filter(
      (p) => (floor === ALL_FLOORS || floorKey(p.floor) === floor) && (!t || haystack(p).some((v) => trNorm(v).includes(t))),
    );
  }, [everyone, floor, term]);

  // Sağ üstteki kişi: tıklanınca profil penceresi.
  const [profileOpen, setProfileOpen] = useState(false);
  const me = useMyProfile(ENGINE_ENABLED);

  const [omni, setOmni] = useState('');
  const onOmni = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    const v = omni.trim();
    if (!v) return;
    // Rakam ya da kişi/kat adıysa rehberde süzülür; değilse soru ZEKİ'ye gider.
    const hits = everyone.some((p) => haystack(p).some((x) => trNorm(x).includes(trNorm(v))));
    if (hits || /^\d+$/.test(v)) {
      setFloor(ALL_FLOORS);
      setTerm(v);
      directoryRef.current?.scrollIntoView({ block: 'start' });
    } else {
      askZeki(v);
    }
  };

  const [allModules, setAllModules] = useState(false);
  const moduleGroups = groups as Array<{ title: string; modules: Array<{ id: string; title: string }> }>;
  const moduleTotal = moduleGroups.reduce((a, g) => a + g.modules.length, 0);
  // Yönetim, Veri Sözlüğü ve Onaylar kutucukları yalnız yöneticide çıkar.
  const isAdmin = useIsAdmin();
  const moduleTiles = MODULE_TILES.filter((m) => !m.adminOnly || isAdmin);

  // Günün modu: kişinin tercihinde saklanır (prefs kampus:mood); önceden yalnız sekme belleğindeydi, "kaydedildi" yazıyordu.
  const qc = useQueryClient();
  const moodQ = useQuery({ queryKey: ['prefs', 'kampus:mood'], queryFn: () => prefsApi.get<string>('kampus:mood'), enabled: ENGINE_ENABLED, retry: false, staleTime: 5 * 60_000 });
  const [moodLocal, setMoodLocal] = useState<string | null>(null);
  const mood = moodLocal ?? moodQ.data?.value ?? null;
  const setMood = (e: string) => {
    setMoodLocal(e);
    if (!ENGINE_ENABLED) return;
    prefsApi.put('kampus:mood', e).then(
      () => void qc.invalidateQueries({ queryKey: ['prefs', 'kampus:mood'] }),
      (err) => toast.error('Mod kaydedilemedi', { description: err instanceof Error ? err.message : undefined }),
    );
  };

  // Alkış / kutlama: sunucuda tutulur; alan kişinin ekranında bildirim çıkar, duvarda herkes görür.
  const greetings = useQuery({ queryKey: ['greetings'], queryFn: greetingsApi.state, enabled: ENGINE_ENABLED, retry: false, refetchInterval: 60_000 });
  const wall = greetings.data?.wall ?? [];
  const received = greetings.data?.received ?? [];
  const unseen = greetings.data?.inbox?.length ?? 0;
  const [notifOpen, setNotifOpen] = useState(false);
  useEffect(() => {
    if (!notifOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setNotifOpen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [notifOpen]);

  const [praiseOpen, setPraiseOpen] = useState(false);
  const [praiseTo, setPraiseTo] = useState('');
  const [praiseText, setPraiseText] = useState('');
  const [praiseBusy, setPraiseBusy] = useState(false);
  const sendPraise = async (e: React.FormEvent) => {
    e.preventDefault();
    const to = praiseTo.trim();
    const text = praiseText.trim();
    if (!to || !text || praiseBusy) return;
    if (!ENGINE_ENABLED) {
      toast.error('Motor bağlı değil; alkış gönderilemez.');
      return;
    }
    setPraiseBusy(true);
    try {
      const r = await greetingsApi.send(to, text);
      toast.success(r.created ? `${to} alkışlandı` : `${to} bugün zaten alkışlanmış`, {
        description: r.created ? 'Ekranına bildirim düştü, duvarda görünüyor.' : 'Aynı kişiye günde bir alkış gider.',
      });
      setPraiseTo('');
      setPraiseText('');
      setPraiseOpen(false);
      void qc.invalidateQueries({ queryKey: ['greetings'] });
    } catch (err) {
      toast.error('Alkış gönderilemedi', { description: err instanceof Error ? err.message : undefined });
    } finally {
      setPraiseBusy(false);
    }
  };

  // Alt bilgi: rehberi dosya olarak indir (Excel'in Türkçe ayarla açtığı ; ayraçlı, BOM'lu CSV).
  const downloadDirectory = () => {
    const cols: Array<[string, (p: Person) => string]> = [
      ['Ad Soyad', (p) => p.name],
      ['Ünvan', (p) => p.title],
      ['Birim', (p) => p.unit],
      ['Dahili', (p) => p.extension],
      ['Kat', (p) => p.floor],
      ['Masa', (p) => p.desk ?? ''],
      ['Cep', (p) => p.mobile],
      ['Telefon', (p) => p.phone],
      ['E-posta', (p) => p.email],
    ];
    const cell = (v: string) => `"${(v ?? '').replace(/"/g, '""')}"`;
    const lines = [cols.map(([h]) => cell(h)).join(';'), ...everyone.map((p) => cols.map(([, f]) => cell(f(p))).join(';'))];
    const blob = new Blob([`﻿${lines.join('\r\n')}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dahili-rehber-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Shell
      head={{
        tenant: 'Timaş Yayınları',
        section: 'Kampüs & ZEKİ',
        crumb: 'Kampüs',
        source: 'Birlikte Üretiyor, Birlikte Okuyoruz',
        presence: `${firstName} çevrimiçi`,
      }}
      rail={railFor('/')}
    >
      {/* Kanvas ekranlarıyla aynı sahne: ortak kabuk (zemin, yazı, ray), içerik kendi içinde kayar. */}
      <main className="kp-root absolute bottom-2 left-14 right-2 top-16 overflow-y-auto overscroll-contain text-ink/80 antialiased selection:bg-violet/20 selection:text-ink sm:bottom-6 sm:left-[92px] sm:right-6 sm:top-[84px]">
      <ZoomStage className="h-full">
        {/* ARAÇ ÇUBUĞU: arama, bülten, bildirim, kişi */}
        <div className="glass-panel mx-auto flex w-full max-w-[1720px] items-center gap-2 rounded-2xl px-2 py-2 shadow-glass-float sm:gap-3 sm:rounded-3xl sm:px-3">
          <div className="relative min-w-0 flex-1">
            <Sparkles className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-violet" />
            <input
              value={omni}
              onChange={(e) => setOmni(e.target.value)}
              onKeyDown={onOmni}
              aria-label="ZEKİ'ye sor ya da rehberde ara"
              placeholder="ZEKİ'ye sor, kişi, dahili numara ya da kat masası ara… (örn. Deniz / Matbaa / 1122)"
              className="w-full rounded-xl border border-slate-200/70 bg-white/90 py-2 pl-10 pr-3 text-base font-medium text-ink placeholder:text-muted/70 focus:border-violet focus:bg-white focus:outline-none focus:ring-2 focus:ring-violet/25 sm:rounded-2xl sm:pr-20 sm:text-xs"
            />
            <span className="kp-mono pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 items-center gap-1.5 text-[11px] font-bold text-violet sm:flex">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-violet" />
              CANLI
            </span>
          </div>
          <nav aria-label="Kampüs bölümleri" className="hidden items-center gap-1 text-xs font-semibold 2xl:flex">
            {[
              { href: '#moduller', icon: <LayoutGrid className="h-3.5 w-3.5 text-violet" />, label: 'Modüller' },
              { href: '#directory-hub', icon: <Phone className="h-3.5 w-3.5 text-muted" />, label: 'Rehber' },
              { href: '#studios-hub', icon: <Mic className="h-3.5 w-3.5 text-mintSuccess" />, label: 'Odalar' },
              { href: '#praise-hub', icon: <HeartHandshake className="h-3.5 w-3.5 text-coral" />, label: 'Alkış' },
            ].map((n) => (
              <a key={n.href} href={n.href} className="kp-press flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-ink/80 hover:bg-white">
                {n.icon} {n.label}
              </a>
            ))}
          </nav>
          <div className="relative shrink-0">
            <button
              type="button"
              title="Bildirimler"
              aria-label={unseen ? `Bildirimler (${unseen} yeni)` : 'Bildirimler'}
              aria-haspopup="dialog"
              aria-expanded={notifOpen}
              onClick={() => setNotifOpen((v) => !v)}
              className="kp-press relative flex h-11 w-11 items-center justify-center rounded-xl text-muted hover:bg-white hover:text-ink sm:h-9 sm:w-9"
            >
              <Bell className="h-4 w-4" />
              {unseen > 0 && <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-coral ring-2 ring-white" />}
            </button>
            {notifOpen && (
              <>
                <button type="button" aria-label="Bildirimleri kapat" onClick={() => setNotifOpen(false)} className="fixed inset-0 z-40 cursor-default" />
                <div role="dialog" aria-label="Bildirimler" className="glass-panel absolute right-0 top-full z-50 mt-2 w-[min(92vw,360px)] rounded-2xl p-3 shadow-glass-float">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="kp-display text-xs font-bold uppercase tracking-wider text-ink">Sana gelen kutlamalar</span>
                    <span className="kp-mono text-[11px] text-muted">son 30 gün</span>
                  </div>
                  {greetings.isLoading ? (
                    <p className="text-xs text-muted">Yükleniyor…</p>
                  ) : received.length === 0 ? (
                    <p className="text-xs text-muted">Henüz kutlama yok. Alkış duvarından arkadaşlarını alkışlayabilirsin.</p>
                  ) : (
                    <ul className="max-h-72 space-y-1.5 overflow-y-auto">
                      {received.map((g) => (
                        <li key={g.id} className="rounded-xl border border-slate-200/70 bg-white/80 p-2 text-xs">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-bold text-ink">{g.from}</span>
                            <span className="kp-mono shrink-0 text-[11px] text-muted">{relative(g.at)}</span>
                          </div>
                          <p className="mt-0.5 text-ink/80">{g.occasion || 'Seni kutladı 🎉'}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            )}
          </div>
          <button
            type="button"
            onClick={() => setProfileOpen(true)}
            aria-haspopup="dialog"
            aria-expanded={profileOpen}
            title="Profilim"
            className="kp-press flex min-h-11 shrink-0 items-center gap-2 rounded-xl border-l border-slate-200/70 pl-2 pr-1 hover:bg-white sm:min-h-9 sm:pl-3 sm:pr-2"
          >
            <PersonAvatar
              username={session.data?.username ?? ''}
              name={me.data?.displayName || fullName}
              photoVersion={me.data?.photoVersion ?? null}
              className="h-8 w-8 rounded-full text-[11px]"
            />
            <span className="hidden flex-col text-left xl:flex">
              <span className="text-xs font-bold leading-tight text-ink">{me.data?.displayName || fullName}</span>
              <span className="text-[11px] text-muted">{me.data?.crm?.title || me.data?.crm?.unit || 'Profilim'}</span>
            </span>
          </button>
        </div>

      <ProfileDialog open={profileOpen} onClose={() => setProfileOpen(false)} />

      {/* ÜÇ SÜTUNLU GÖVDE */}
      <div className="mx-auto grid w-full max-w-[1720px] grid-cols-1 gap-4 py-4 sm:gap-5 lg:grid-cols-12">
        {/* SOL SÜTUN */}
        <aside className="flex min-w-0 flex-col gap-4 lg:col-span-3">
          <Card className="p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="kp-mono flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
                <Activity className="h-3.5 w-3.5 text-amber-500" /> Şirket Nabzı
              </span>
              <span className="kp-mono whitespace-nowrap rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-700">{people.data ? `${people.data.total} Aktif` : '…'}</span>
            </div>
            <div className="rounded-xl border border-violet/15 bg-gradient-to-br from-coral/5 to-violet/5 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-ink">Günün modun</span>
                <span className="kp-mono text-xs font-bold text-violet">{mood ?? '—'}</span>
              </div>
              <div className="mt-2.5 flex flex-wrap items-center justify-between gap-1 border-t border-slate-200/60 pt-2 text-[11px]">
                <span className="text-muted">{mood ? 'Modun kaydedildi.' : 'Senin modun nasıl?'}</span>
                <div className="flex items-center gap-0.5 sm:gap-1.5">
                  {[
                    ['🔥', 'Alev Aldık'],
                    ['☕', 'Kahve Lazım'],
                    ['✨', 'İlham Dolu'],
                    ['🧘‍♂️', 'Odaklandım'],
                  ].map(([e, t]) => (
                    <button
                      key={e}
                      type="button"
                      title={t}
                      aria-pressed={mood === e}
                      onClick={() => setMood(e)}
                      className={`kp-press flex h-11 w-11 items-center justify-center rounded-md text-lg sm:h-auto sm:w-auto sm:px-0.5 sm:text-sm ${mood === e ? 'bg-violet/10 ring-1 ring-violet/25' : ''}`}
                    >
                      {e}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </Card>

        </aside>

        {/* ORTA SÜTUN */}
        <main className="flex min-w-0 flex-col gap-5 lg:col-span-6">
          {/* ZEKİ sahnesi */}
          <section className="kp-card relative overflow-hidden rounded-3xl border border-slate-200/70 glass-panel p-5 sm:p-7">
            <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-coral/20 blur-3xl" />
            <div className="pointer-events-none absolute -bottom-16 -left-16 h-64 w-64 rounded-full bg-violet/20 blur-3xl" />
            <div className="relative z-10 grid grid-cols-1 items-center gap-5 md:grid-cols-12">
              <div className="flex flex-col items-center md:col-span-5">
                <div className="relative w-full max-w-[270px] overflow-hidden rounded-3xl border border-white/80 bg-white/90/70 shadow-md">
                  <img src={zekiImg} alt="ZEKİ AI - Timaş Kurumsal Asistanı" className="h-auto w-full object-cover" />
                  <div className="kp-mono absolute left-2.5 top-2.5 flex items-center gap-2 rounded-lg bg-ink/80 px-2.5 py-1 text-[11px] text-white backdrop-blur-md">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
                    <span>ZEKİ CANLI</span>
                  </div>
                  <div className="absolute bottom-2 left-2 right-2 rounded-xl border border-slate-200/70 bg-white/90 px-3 py-1.5 text-center text-xs text-ink/80 backdrop-blur-md">
                    <span className="kp-display font-semibold text-violet">Timaş Kurumsal Zekası</span>
                  </div>
                </div>
              </div>

              <div className="flex min-w-0 flex-col md:col-span-7">
                <div className="mb-2 inline-flex w-fit items-center gap-1.5 rounded-full border border-violet/30 bg-violet/10 px-3 py-1 text-xs font-semibold text-violet">
                  <Bot className="h-3.5 w-3.5 text-violet" /> Timaş Çalışan Yapay Zeka Asistanı
                </div>
                <h2 className="kp-display text-xl font-bold leading-snug tracking-tight text-ink sm:text-2xl">
                  Selam {firstName}! Ben <span className="text-violet">ZEKİ</span>, bugün hangi işi kolaylaştıralım?
                </h2>
                <p className="mt-1.5 text-xs leading-relaxed text-muted">
                  Satış, ciro, iade, tahsilat ve cari sorularını Logo verisinden cevaplarım; kişi ve dahili aramak için üstteki arama kutusu var.
                </p>
                <form
                  className="mt-4"
                  onSubmit={(e) => {
                    e.preventDefault();
                    askZeki(zekiQ);
                  }}
                >
                  <div className="flex items-center rounded-2xl border border-slate-200 bg-white p-1.5 shadow-sm focus-within:border-violet focus-within:ring-2 focus-within:ring-violet/25">
                    <div className="pl-2.5 text-violet">
                      <MessageCircle className="h-4 w-4" />
                    </div>
                    <input
                      value={zekiQ}
                      onChange={(e) => setZekiQ(e.target.value)}
                      placeholder="ZEKİ'ye sor: 'Bu ay net ciro ne?', 'En çok satan 5 kanal'..."
                      className="w-full min-w-0 border-0 bg-transparent px-2.5 py-1.5 text-xs text-ink placeholder:text-muted/70 focus:outline-none focus:ring-0 sm:text-sm"
                    />
                    <button
                      type="submit"
                      className="kp-press min-h-11 sm:min-h-0 kp-glow flex shrink-0 items-center gap-1.5 rounded-xl bg-gradient-to-r from-coral to-violet px-4 py-2 text-xs font-bold text-white hover:brightness-105"
                    >
                      <span>Sor</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </form>
                <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
                  {PROMPTS.map((p) => (
                    <button
                      key={p.label}
                      type="button"
                      onClick={() => askZeki(p.q)}
                      className="kp-press min-h-11 sm:min-h-0 flex items-center gap-1 rounded-lg border border-slate-200/70 bg-white px-2.5 py-1 text-ink/80 hover:bg-slate-100 hover:text-ink"
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
                <div className="mt-3 flex items-start gap-2 text-[11px] text-muted">
                  <Sparkle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet" />
                  <span>Sorunuz ZEKİ AI Genel Bakış ekranında gerçek veriyle cevaplanır.</span>
                </div>
              </div>
            </div>
          </section>

          {/* MODÜLLER — kanvas ekranlarına geçiş */}
          <Card id="moduller" className="p-5">
            <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div className="flex items-center gap-3">
                <div className="rounded-xl border border-violet/20 bg-violet/10 p-2 text-violet">
                  <LayoutGrid className="h-5 w-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="kp-display text-base font-bold text-ink">Modüller</h2>
                    <span className="kp-mono whitespace-nowrap rounded border border-slate-200/70 bg-slate-100 px-2 text-[11px] font-semibold text-muted">
                      {moduleTiles.length} açık · {moduleTotal} toplam
                    </span>
                  </div>
                  <p className="text-xs text-muted">ZEKİ AI iş ekranlarına buradan geçin</p>
                </div>
              </div>
              <button
                type="button"
                aria-expanded={allModules}
                onClick={() => setAllModules((v) => !v)}
                className="kp-press min-h-11 sm:min-h-0 flex w-fit items-center gap-1 rounded-lg border border-slate-200/70 bg-slate-50/80 px-3 py-1.5 text-xs font-medium text-ink/80 hover:border-violet/30 hover:text-violet"
              >
                Tüm modüller
                <ChevronDown className={`h-3.5 w-3.5 ${allModules ? 'rotate-180' : ''}`} />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {moduleTiles.map((m) => (
                <Link
                  key={m.to}
                  to={m.to}
                  className="kp-lift group flex items-center justify-between gap-2 rounded-xl border border-slate-200/70 bg-slate-50/80 p-3 hover:border-violet/30 hover:bg-white"
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${m.tone}`}>
                      <Sparkles className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-xs font-bold text-ink group-hover:text-violet">{m.title}</p>
                      <p className="truncate text-[11px] text-muted">{m.note}</p>
                    </div>
                  </div>
                  <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted/70 group-hover:text-violet" />
                </Link>
              ))}
            </div>

            {allModules && (
              <div className="kp-scroll mt-4 max-h-[420px] space-y-3 overflow-y-auto border-t border-slate-200/70 pr-1 pt-4">
                {moduleGroups.map((g) => (
                  <div key={g.title}>
                    <div className="kp-mono pb-1 text-[11px] font-bold uppercase tracking-wider text-muted">{g.title}</div>
                    <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                      {g.modules.map((m) => {
                        const to = LIVE[m.id];
                        return to ? (
                          <Link
                            key={m.id}
                            to={to}
                            className="kp-press min-h-11 sm:min-h-0 flex items-center gap-2 rounded-lg border border-slate-200/70 bg-white px-2 py-1.5 text-[12px] font-semibold text-ink hover:border-violet/30"
                          >
                            <span className="min-w-0 flex-1 truncate">{m.title}</span>
                            <span className="shrink-0 rounded bg-violet/10 px-1.5 text-[11px] font-bold text-violet">açık</span>
                          </Link>
                        ) : (
                          <div key={m.id} title={m.title} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[12px] text-muted">
                            <span className="min-w-0 flex-1 truncate">{m.title}</span>
                            <span className="shrink-0 text-[11px] text-muted/70">yakında</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* REHBER */}
          <Card id="directory-hub" className="scroll-mt-20 p-5">
            <div ref={directoryRef} className="scroll-mt-20" />
            <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div className="flex items-center gap-3">
                <div className="rounded-xl border border-violet/20 bg-violet/10 p-2 text-violet">
                  <Contact className="h-5 w-5" />
                </div>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="kp-display text-base font-bold text-ink">Timaş Rehber · Anında Arama &amp; Kat Planı</h2>
                    <span className="kp-mono whitespace-nowrap rounded border border-slate-200/70 bg-slate-100 px-2 text-[11px] font-semibold text-muted">{people.data ? `${people.data.total} Kişi` : '…'}</span>
                  </div>
                  <p className="text-xs text-muted">CRM’deki etkin kullanıcılar · kat, dahili, cep ve birim araması</p>
                </div>
              </div>
              <div className="kp-scroll flex items-center gap-1 overflow-x-auto pb-1 text-xs sm:pb-0">
                {floors.length > 0 &&
                  [{ id: ALL_FLOORS, label: 'Tümü' }, ...floors.map((f) => ({ id: f, label: f }))].map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      aria-pressed={floor === f.id}
                      onClick={() => setFloor(f.id)}
                      className={`kp-press min-h-11 sm:min-h-0 shrink-0 whitespace-nowrap rounded-lg px-2.5 py-1 font-medium ${
                        floor === f.id ? 'bg-violet text-white' : 'bg-slate-100 text-ink/80 hover:bg-slate-200'
                      }`}
                    >
                      {f.label}
                    </button>
                  ))}
              </div>
            </div>

            <div className="relative mb-3">
              <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted/70" />
              <input
                value={term}
                onChange={(e) => setTerm(e.target.value)}
                placeholder="İsim, unvan, birim, dahili ya da e-posta yazarak süzün…"
                className="w-full rounded-xl border border-slate-200/70 bg-slate-50/80 py-2.5 pl-10 pr-11 text-xs text-ink sm:py-2 placeholder:text-muted/70 focus:border-violet focus:bg-white focus:outline-none focus:ring-2 focus:ring-violet/25"
              />
              {term && (
                <button
                  type="button"
                  aria-label="Aramayı temizle"
                  onClick={() => setTerm('')}
                  className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-sm text-muted/70 hover:text-ink/80"
                >
                  ✕
                </button>
              )}
            </div>

            <div className="kp-scroll grid max-h-[380px] grid-cols-1 gap-3 overflow-y-auto pr-1 sm:grid-cols-2">
              {people.isLoading && <div className="col-span-full py-6 text-center text-xs text-muted">Rehber CRM’den okunuyor…</div>}
              {people.error && (
                <div className="col-span-full py-6 text-center text-xs text-rose-700">
                  {people.error instanceof EngineAuthError ? 'Oturum gerekli.' : people.error instanceof Error ? people.error.message : 'Rehber okunamadı.'}
                </div>
              )}
              {staff.map((p) => {
                const call = p.extension || p.phone || p.mobile;
                return (
                  <div
                    key={p.id || p.username}
                    className="flex items-start justify-between gap-2 rounded-xl border border-slate-200/70 bg-slate-50/80 p-3 transition-colors hover:border-violet/30 hover:bg-white"
                  >
                    <div className="flex min-w-0 items-start gap-3">
                      <PersonAvatar username={p.username} name={p.name} photoVersion={p.photoVersion} className="mt-0.5 h-9 w-9 rounded-xl text-xs" />
                      <div className="min-w-0">
                        <h4 className="truncate text-xs font-bold text-ink">{p.name}</h4>
                        <p className="truncate text-[11px] text-muted">{[p.title, p.unit].filter(Boolean).join(' • ') || p.email || p.username}</p>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5">
                          {p.extension && (
                            <span className="kp-mono whitespace-nowrap rounded border border-violet/20 bg-violet/5 px-1.5 py-0.5 text-[11px] font-semibold text-violet">Dahili: {p.extension}</span>
                          )}
                          {(p.floor || p.desk) && (
                            <span className="rounded border border-slate-200/70 bg-slate-100 px-1.5 py-0.5 text-[11px] text-muted">{[p.floor, p.desk].filter(Boolean).join(' ')}</span>
                          )}
                          {p.mobile && <span className="kp-mono whitespace-nowrap text-[11px] text-muted">{p.mobile}</span>}
                        </div>
                      </div>
                    </div>
                    {call ? (
                      <a href={`tel:${call.replace(/\s+/g, '')}`} title={`Ara: ${call}`} aria-label={`${p.name} ara`} className="kp-press flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-muted sm:h-auto sm:w-auto sm:p-1.5 hover:bg-violet hover:text-white">
                        <PhoneCall className="h-3.5 w-3.5" />
                      </a>
                    ) : p.email ? (
                      <a href={`mailto:${p.email}`} title={p.email} aria-label={`${p.name} e-posta`} className="kp-press flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-muted sm:h-auto sm:w-auto sm:p-1.5 hover:bg-violet hover:text-white">
                        <MessageCircle className="h-3.5 w-3.5" />
                      </a>
                    ) : null}
                  </div>
                );
              })}
              {people.data && !staff.length && <div className="col-span-full py-6 text-center text-xs text-muted">Eşleşen kişi yok.</div>}
            </div>

            <div className="mt-3 flex flex-col justify-between gap-2 border-t border-slate-200/70 pt-3 text-xs text-muted sm:flex-row sm:items-center">
              <span>
                {people.data ? (
                  <>
                    {units > 0 && (
                      <>
                        <strong>{units}</strong> birim •{' '}
                      </>
                    )}
                    <strong>{people.data.total}</strong> etkin kullanıcı
                    {people.data.truncated && ' (liste kesildi)'}
                    {!people.data.adChecked && ' · dizin denetlenemedi'}
                    {people.data.db && <DbTimingBadge timing={people.data.db} className="mt-0.5 flex" />}
                  </>
                ) : (
                  'Kaynak: CRM'
                )}
              </span>
              <button type="button" onClick={() => setProfileOpen(true)} className="kp-press flex items-center gap-1 font-medium text-violet">
                Dahili ve katını ekle <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </Card>

          {/* ALKIŞ DUVARI */}
          <Card id="praise-hub" className="p-5">
            <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div className="flex items-center gap-2.5">
                <div className="rounded-xl border border-rose-200 bg-rose-50 p-2 text-rose-600">
                  <HeartHandshake className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="kp-display text-base font-bold text-ink">Kutlamalar &amp; Alkış Duvarı</h2>
                  <p className="text-xs text-muted">Çalışma arkadaşlarımıza günün tebriğini ve mikro-övgüsünü iletin</p>
                </div>
              </div>
              <button
                type="button"
                aria-expanded={praiseOpen}
                onClick={() => setPraiseOpen((v) => !v)}
                className="kp-press min-h-11 sm:min-h-0 flex w-fit items-center gap-1 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100"
              >
                <Plus className="h-3.5 w-3.5" /> Alkış Gönder
              </button>
            </div>

            {praiseOpen && (
              <form onSubmit={sendPraise} className="mb-3 grid grid-cols-1 gap-2 rounded-xl border border-violet/20 bg-violet/5 p-3 sm:grid-cols-[1fr_2fr_auto]">
                <input
                  value={praiseTo}
                  onChange={(e) => setPraiseTo(e.target.value)}
                  list="kp-people"
                  required
                  aria-label="Kimi alkışlıyorsunuz?"
                  placeholder="Kimi alkışlıyorsunuz? (rehberden ad soyad)"
                  className="rounded-lg border border-slate-200/70 bg-white px-2.5 py-1.5 text-xs focus:border-violet focus:outline-none"
                />
                <datalist id="kp-people">
                  {everyone.map((p) => (
                    <option key={p.id} value={p.name} />
                  ))}
                </datalist>
                <input
                  value={praiseText}
                  onChange={(e) => setPraiseText(e.target.value)}
                  required
                  maxLength={200}
                  aria-label="Tebrik notu"
                  placeholder="Mikro tebrik notunuz"
                  className="rounded-lg border border-slate-200/70 bg-white px-2.5 py-1.5 text-xs focus:border-violet focus:outline-none"
                />
                <button type="submit" disabled={praiseBusy} className="kp-press min-h-11 sm:min-h-0 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-rose-700 disabled:opacity-60">
                  {praiseBusy ? 'Gönderiliyor…' : 'Gönder'}
                </button>
              </form>
            )}

            {greetings.isLoading ? (
              <p className="text-xs text-muted">Yükleniyor…</p>
            ) : greetings.error ? (
              <p className="text-xs text-rose-700">{greetings.error instanceof EngineAuthError ? 'Oturum gerekli.' : 'Alkış duvarı yüklenemedi.'}</p>
            ) : wall.length === 0 ? (
              <p className="rounded-xl border border-dashed border-slate-200 p-4 text-center text-xs text-muted">Son 30 günde alkış yok. İlkini sen gönder.</p>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {wall.map((g) => (
                  <div key={g.id} className="flex flex-col justify-between rounded-xl border border-slate-200/70 bg-slate-50/80 p-3">
                    <div className="mb-1.5 flex items-center justify-between gap-2 text-[11px]">
                      <span className="font-bold text-ink">
                        {g.from} ➔ {g.to}
                      </span>
                      <span className="kp-mono shrink-0 text-muted/70">{relative(g.at)}</span>
                    </div>
                    <p className="text-xs leading-snug text-ink/80">{g.occasion || 'Kutladı 🎉'}</p>
                  </div>
                ))}
              </div>
            )}
          </Card>

        </main>

        {/* SAĞ SÜTUN */}
        <aside className="flex min-w-0 flex-col gap-5 lg:col-span-3">
          <RoomsCard />
        </aside>
      </div>

      {/* ALT BİLGİ */}
      <footer className="glass-panel mx-auto mb-2 w-full max-w-[1720px] rounded-2xl px-4 py-3 text-xs text-muted shadow-glass-float sm:rounded-3xl sm:px-6">
        <div className="mx-auto flex max-w-[1720px] flex-col items-center justify-between gap-3 text-center sm:flex-row sm:text-left">
          <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
            <span className="kp-display font-semibold text-ink/80">TİMAŞ YAYIN GRUBU</span>
            <span>•</span>
            <span>Kampüs Portalı</span>
            <span>•</span>
            <span className="font-medium text-violet">Birlikte Üretiyor, Birlikte Okuyoruz</span>
          </div>
          <button
            type="button"
            onClick={downloadDirectory}
            disabled={everyone.length === 0}
            className="kp-press flex min-h-11 items-center gap-1.5 rounded-xl px-3 font-semibold text-violet hover:bg-white disabled:text-muted sm:min-h-0 sm:py-1.5"
            title="Rehberdeki herkesi CSV olarak indir (Excel açar)"
          >
            <Download className="h-3.5 w-3.5" /> Dahili Rehber (CSV)
          </button>
        </div>
      </footer>
      </ZoomStage>
      </main>
    </Shell>
  );
}
