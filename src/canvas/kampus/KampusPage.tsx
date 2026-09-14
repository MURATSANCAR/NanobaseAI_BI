import { useMemo, useRef, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  Bell,
  Bot,
  BookOpen,
  Cake,
  Calendar,
  ChevronDown,
  ChevronRight,
  Coffee,
  Contact,
  DoorClosed,
  Download,
  FileCheck,
  Flag,
  Gift,
  Headphones,
  HeartHandshake,
  LayoutGrid,
  Laptop,
  LifeBuoy,
  MessageCircle,
  Mic,
  Pause,
  Phone,
  PhoneCall,
  Play,
  Plus,
  Radio,
  Search,
  Sparkle,
  Sparkles,
  Ticket,
  Truck,
} from 'lucide-react';
import groups from '../modules.json';
import { LIVE } from '../stitch/ModulesMenu';
import { useTimasSession } from '../TimasSession';
import zekiImg from '@/assets/kampus/zeki.jpg';
import denizImg from '@/assets/kampus/deniz.jpg';
import ahmetImg from '@/assets/kampus/ahmet.jpg';
import busraImg from '@/assets/kampus/busra.jpg';
import book1Img from '@/assets/kampus/book1.jpg';
import book2Img from '@/assets/kampus/book2.jpg';
import './kampus.css';

/**
 * Girişten sonraki ilk ekran: Timaş Kampüs & ZEKİ Akıllı Rehber.
 * Stitch ekranı projects/13426839861607265553/screens/a6864de4bb2047878357e34f67bda769
 * birebir JSX'e çevrildi. Tasarıma eklenen tek bölüm "Modüller": kanvas ekranlarına
 * buradan geçilir. Rehber, oda, kutlama gibi içerikler henüz bir kaynağa bağlı değil;
 * tasarımdaki metinlerdir.
 */

type Staff = {
  name: string;
  role: string;
  ext: string;
  desk: string;
  floor: '1' | '2' | '3' | '4';
  img?: string;
  initials?: string;
  tone?: string;
};

const STAFF: Staff[] = [
  { name: 'Deniz Kaya', role: 'Yayın Editörü • Edebiyat Dizisi', ext: '1042', desk: '4. Kat E-12', floor: '4', img: denizImg },
  { name: 'Ahmet Yıldız', role: 'Sanat Yönetmeni • Kapak Masası', ext: '1134', desk: '3. Kat G-04', floor: '3', img: ahmetImg },
  { name: 'Büşra Aksoy', role: 'Yayın Koordinatörü', ext: '1055', desk: '4. Kat K-01', floor: '4', img: busraImg },
  { name: 'Mustafa Demir', role: 'İnsan Kaynakları Müdürü', ext: '1045', desk: '2. Kat İK-02', floor: '2', initials: 'MD', tone: 'bg-amber-100 text-amber-800 ring-amber-300' },
  { name: 'Canan Öz', role: 'BT & Altyapı Uzmanı', ext: '1122', desk: '2. Kat BT-01', floor: '2', initials: 'CÖ', tone: 'bg-sky-100 text-sky-800 ring-sky-300' },
  { name: 'Kemal Sancak', role: 'Matbaa & Depo Şefi', ext: '1080', desk: '1. Kat Depo Giriş', floor: '1', initials: 'KS', tone: 'bg-emerald-100 text-emerald-800 ring-emerald-300' },
];

const FLOORS: Array<{ id: 'ALL' | Staff['floor']; label: string }> = [
  { id: 'ALL', label: 'Tümü' },
  { id: '4', label: '4. Kat' },
  { id: '3', label: '3. Kat' },
  { id: '2', label: '2. Kat' },
  { id: '1', label: '1. Kat / Depo' },
];

const PROMPTS = [
  { label: '📍 3. Kat Masaları', q: 'Kat 3 editör masası dahili hatlarını listele' },
  { label: '📦 Yeni Kitap Künyeleri', q: 'Matbaadan bu hafta çıkan eserlerin tam künyesini göster' },
  { label: '🌴 İzin Bakiyem', q: 'Yıllık izin bakiye durumumu ve onay akışını ver' },
  { label: '🎪 TÜYAP Sorumlusu', q: 'TÜYAP Fuarı stand lojistik sorumlusu kim?' },
];

/** Modül kutucukları: kanvasta açılan ekranlar. Yeni ekran geldikçe satır eklenir. */
const MODULE_TILES = [
  { to: '/genel-bakis', title: 'ZEKİ AI · Genel Bakış', note: 'Satış, ciro ve verine sor', tone: 'bg-orange-100 text-orange-700' },
  { to: '/panolar', title: 'Panolar', note: 'Kişisel pano ve grafikler', tone: 'bg-amber-100 text-amber-800' },
  { to: '/uyarilar', title: 'Uyarılar', note: 'Kural ve bildirimler', tone: 'bg-rose-100 text-rose-700' },
  { to: '/planli-raporlar', title: 'Planlı Raporlar', note: 'Zamanlanmış gönderimler', tone: 'bg-sky-100 text-sky-700' },
  { to: '/veri-sozlugu', title: 'Veri Sözlüğü', note: 'Kavramlar ve katalog', tone: 'bg-emerald-100 text-emerald-700' },
  { to: '/onaylar', title: 'Onaylar', note: 'Bekleyen incelemeler', tone: 'bg-purple-100 text-purple-700' },
];

type Praise = { from: string; to: string; when: string; text: string; emoji: string; likes: number; tag: string; tagTone: string; fresh?: boolean };

const PRAISE: Praise[] = [
  {
    from: 'Selin K.',
    to: 'Ahmet Yıldız',
    when: '10 dk önce',
    text: '"Yeni şiir dizisinin kapak tipografisi muazzam oldu, baskı öncesi son dakika revizyonundaki sabrın için sonsuz teşekkürler! 🎨👏"',
    emoji: '❤️',
    likes: 14,
    tag: 'Tasarım Harikası',
    tagTone: 'text-amber-800 bg-amber-50',
  },
  {
    from: 'Emre V.',
    to: 'Büşra Aksoy',
    when: '45 dk önce',
    text: '"Bologna Fuarı sözleşmelerinin sisteme 24 saat içinde eksiksiz işlenmesi büyük başarıydı. Timaş\'ta 5. yılın da kutlu olsun! 🏆✨"',
    emoji: '👏',
    likes: 29,
    tag: 'Süper Koordinasyon',
    tagTone: 'text-purple-800 bg-purple-50',
  },
];

const trNorm = (s: string) => s.toLocaleLowerCase('tr');

function Card({ id, className = '', children }: { id?: string; className?: string; children: ReactNode }) {
  return (
    <section id={id} className={`kp-card rounded-2xl border border-stone-300/80 bg-white ${className}`}>
      {children}
    </section>
  );
}

export default function KampusPage() {
  const navigate = useNavigate();
  const session = useTimasSession();
  const fullName = session.data?.username || 'Deniz Kaya';
  const firstName = fullName.split(/[\s._@]/)[0] || fullName;

  // ZEKİ kutusu: soru BI kanvasına gider, cevabı motor verir.
  const [zekiQ, setZekiQ] = useState('');
  const askZeki = (q: string) => {
    const text = q.trim();
    if (!text) return;
    navigate(`/genel-bakis?soru=${encodeURIComponent(text)}`);
  };

  // Rehber: kat süzgeci + anında arama.
  const [floor, setFloor] = useState<(typeof FLOORS)[number]['id']>('ALL');
  const [term, setTerm] = useState('');
  const directoryRef = useRef<HTMLDivElement>(null);
  const staff = useMemo(() => {
    const t = trNorm(term.trim());
    return STAFF.filter(
      (s) =>
        (floor === 'ALL' || s.floor === floor) &&
        (!t || [s.name, s.role, s.ext, s.desk, `${s.floor}. kat`].some((v) => trNorm(v).includes(t))),
    );
  }, [floor, term]);

  const [omni, setOmni] = useState('');
  const onOmni = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    const v = omni.trim();
    if (!v) return;
    // Rakam ya da kişi/kat adıysa rehberde süzülür; değilse soru ZEKİ'ye gider.
    const hits = STAFF.some((s) => [s.name, s.role, s.ext, s.desk].some((x) => trNorm(x).includes(trNorm(v))));
    if (hits || /^\d+$/.test(v)) {
      setFloor('ALL');
      setTerm(v);
      directoryRef.current?.scrollIntoView({ block: 'start' });
    } else {
      askZeki(v);
    }
  };

  const [allModules, setAllModules] = useState(false);
  const moduleGroups = groups as Array<{ title: string; modules: Array<{ id: string; title: string }> }>;
  const moduleTotal = moduleGroups.reduce((a, g) => a + g.modules.length, 0);

  const [mood, setMood] = useState<string | null>(null);
  const [booked, setBooked] = useState<Record<string, boolean>>({});
  const [greeted, setGreeted] = useState<Record<string, boolean>>({});
  const [lottery, setLottery] = useState(false);
  const [praise, setPraise] = useState(PRAISE);
  const [liked, setLiked] = useState<Record<number, boolean>>({});
  const [praiseOpen, setPraiseOpen] = useState(false);
  const [praiseTo, setPraiseTo] = useState('');
  const [praiseText, setPraiseText] = useState('');
  const [playing, setPlaying] = useState(false);

  const sendPraise = (e: React.FormEvent) => {
    e.preventDefault();
    if (!praiseTo.trim() || !praiseText.trim()) return;
    setPraise((p) => [
      { from: firstName, to: praiseTo.trim(), when: 'Şimdi', text: `"${praiseText.trim()}"`, emoji: '❤️', likes: 1, tag: 'Taze Alkış', tagTone: 'text-orange-800 bg-orange-100', fresh: true },
      ...p,
    ]);
    setLiked((l) => Object.fromEntries(Object.entries(l).map(([k, v]) => [Number(k) + 1, v])));
    setPraiseTo('');
    setPraiseText('');
    setPraiseOpen(false);
  };

  return (
    <div className="kp-root flex min-h-screen flex-col text-stone-800 antialiased selection:bg-orange-200 selection:text-orange-950">
      {/* ÜST ŞERİT */}
      <header className="sticky top-0 z-50 border-b border-stone-300/80 bg-[#faf7f2]/95 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-[1720px] items-center justify-between gap-3 px-3 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-5">
            <Link to="/" className="group flex min-w-0 items-center gap-3">
              <div className="h-10 w-10 shrink-0 rounded-xl bg-gradient-to-tr from-stone-900 via-orange-950 to-orange-600 p-[1.5px] shadow-sm">
                <div className="kp-display flex h-full w-full items-center justify-center rounded-[10px] bg-[#181512] text-lg font-black text-amber-100">T</div>
              </div>
              <div className="flex min-w-0 flex-col">
                <div className="flex items-center gap-2">
                  <span className="kp-display truncate text-sm font-bold tracking-wide text-stone-900 transition-colors group-hover:text-orange-700 sm:text-base">
                    TİMAŞ YAYIN GRUBU
                  </span>
                  <span className="kp-mono hidden rounded-full border border-orange-300 bg-orange-100 px-2 py-0.5 text-[11px] font-semibold uppercase text-orange-900 sm:inline">
                    Kampüs &amp; ZEKİ
                  </span>
                </div>
                <span className="truncate text-[11px] font-medium text-stone-500">Birlikte Üretiyor, Birlikte Okuyoruz</span>
              </div>
            </Link>
            <nav className="hidden items-center gap-1.5 border-l border-stone-200 pl-6 text-xs font-medium 2xl:flex">
              {[
                { href: '#moduller', icon: <LayoutGrid className="h-3.5 w-3.5 text-orange-600" />, label: 'Modüller' },
                { href: '#directory-hub', icon: <Phone className="h-3.5 w-3.5 text-stone-500" />, label: 'Rehber & Masalar' },
                { href: '#studios-hub', icon: <Mic className="h-3.5 w-3.5 text-emerald-600" />, label: 'Odalar & Stüdyo' },
                { href: '#praise-hub', icon: <HeartHandshake className="h-3.5 w-3.5 text-rose-500" />, label: 'Alkış Duvarı' },
                { href: '#coffee-lottery', icon: <Coffee className="h-3.5 w-3.5 text-amber-600" />, label: 'Kahve & Çekiliş' },
              ].map((n) => (
                <a key={n.href} href={n.href} className="kp-press min-h-11 sm:min-h-0 flex items-center gap-1.5 rounded-lg bg-stone-100 px-3 py-1.5 text-stone-700 hover:bg-stone-200/70">
                  {n.icon} {n.label}
                </a>
              ))}
            </nav>
          </div>

          <div className="mx-4 hidden max-w-xl flex-1 md:flex">
            <div className="relative w-full">
              <Sparkles className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
              <input
                value={omni}
                onChange={(e) => setOmni(e.target.value)}
                onKeyDown={onOmni}
                placeholder="ZEKİ'ye sor, kişi dahili numarası veya kat masası ara... (Örn: Editör Deniz / Matbaa / 1122)"
                className="w-full rounded-xl border border-stone-300 bg-white/90 py-2 pl-10 pr-24 text-xs font-medium text-stone-900 shadow-inner placeholder:text-stone-400 focus:border-orange-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-orange-400/50"
              />
              <div className="absolute right-2.5 top-1/2 flex -translate-y-1/2 items-center gap-1">
                <kbd className="kp-mono whitespace-nowrap rounded border border-stone-300 bg-stone-100 px-1.5 py-0.5 text-[11px] text-stone-600">⌘K</kbd>
                <span className="text-[11px] text-stone-300">|</span>
                <span className="kp-mono text-[11px] font-semibold text-orange-700">CANLI</span>
              </div>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            <a
              href="#podcast-hub"
              className="kp-press min-h-11 sm:min-h-0 hidden items-center gap-2 rounded-xl border border-orange-200 bg-orange-50 px-3 py-1.5 text-xs text-orange-950 hover:bg-orange-100/80 sm:flex"
            >
              <span className="h-2 w-2 animate-pulse rounded-full bg-rose-500" />
              <span className="flex items-center gap-1 font-medium">
                <Headphones className="h-3.5 w-3.5 text-orange-600" /> Sesli Bülten Bölüm #42
              </span>
            </a>
            <button type="button" title="Bildirimler" className="kp-press relative flex h-11 w-11 items-center justify-center rounded-xl border border-stone-300 bg-white text-stone-600 sm:h-auto sm:w-auto sm:p-2 hover:border-stone-400 hover:text-stone-950">
              <Bell className="h-4 w-4" />
              <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-orange-600 ring-2 ring-white" />
            </button>
            <div className="flex items-center gap-2.5 border-l border-stone-300 pl-2">
              <div className="relative">
                <img src={denizImg} alt={fullName} className="h-8 w-8 rounded-lg object-cover ring-2 ring-orange-200" />
                <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border-2 border-white bg-emerald-500" />
              </div>
              <div className="hidden flex-col text-left xl:flex">
                <span className="text-xs font-semibold leading-tight text-stone-900">{fullName}</span>
                <span className="kp-mono text-[11px] text-stone-500">Kat 4 • Edebiyat Dizisi</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* ÜÇ SÜTUNLU GÖVDE */}
      <div className="mx-auto grid w-full max-w-[1720px] flex-1 grid-cols-1 gap-5 px-3 py-5 sm:px-6 lg:grid-cols-12 lg:px-8">
        {/* SOL SÜTUN */}
        <aside className="flex min-w-0 flex-col gap-4 lg:col-span-3">
          <Card className="p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="kp-mono flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-stone-500">
                <Activity className="h-3.5 w-3.5 text-amber-500" /> Şirket Nabzı
              </span>
              <span className="kp-mono whitespace-nowrap rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-700">180 Aktif</span>
            </div>
            <div className="rounded-xl border border-amber-200/80 bg-gradient-to-br from-amber-50/70 to-orange-50/60 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-stone-900">Günün Ofis Modu:</span>
                <span className="kp-mono text-xs font-bold text-orange-700">🎨 %89 Yaratıcı</span>
              </div>
              <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-stone-200/80">
                <div className="h-full rounded-full bg-gradient-to-r from-amber-500 to-orange-600" style={{ width: '89%' }} />
              </div>
              <p className="mt-2 text-[11px] italic leading-tight text-stone-600">"Yayın kurulu haftası telaşı yerini taze matbaa kokusuna bıraktı!"</p>
              <div className="mt-2.5 flex flex-wrap items-center justify-between gap-1 border-t border-amber-200/60 pt-2 text-[11px]">
                <span className="text-stone-500">{mood ? `Modun kaydedildi ${mood}` : 'Senin modun nasıl?'}</span>
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
                      className={`kp-press flex h-11 w-11 items-center justify-center rounded-md text-lg sm:h-auto sm:w-auto sm:px-0.5 sm:text-sm ${mood === e ? 'bg-orange-100 ring-1 ring-orange-300' : ''}`}
                    >
                      {e}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </Card>

          <Card className="p-4">
            <h3 className="kp-display mb-3 flex items-center justify-between text-xs font-bold uppercase tracking-wider text-stone-500">
              <span>Hızlı Operasyon &amp; Destek</span>
              <LifeBuoy className="h-3.5 w-3.5 text-stone-400" />
            </h3>
            <div className="space-y-2 text-xs">
              {[
                { icon: <Laptop className="h-3.5 w-3.5" />, title: 'BT & Ağ Desteği Aç', note: 'Ortalama yanıt: 6 dk', box: 'bg-orange-100 text-orange-700', hover: 'hover:bg-orange-50/70 hover:border-orange-300', q: 'BT ve ağ desteği talebi açmak istiyorum' },
                { icon: <Truck className="h-3.5 w-3.5" />, title: 'Kurye & Kargo Çağır', note: 'Öğle toplama saati 14:30', box: 'bg-amber-100 text-amber-800', hover: 'hover:bg-amber-50/70 hover:border-amber-300', q: 'Kurye ve kargo çağırmak istiyorum' },
                { icon: <FileCheck className="h-3.5 w-3.5" />, title: 'Telif & Hukuk Danışma', note: 'Standart şablonlar & onay', box: 'bg-purple-100 text-purple-700', hover: 'hover:bg-purple-50/70 hover:border-purple-300', q: 'Telif ve hukuk danışma şablonları' },
              ].map((t) => (
                <button
                  key={t.title}
                  type="button"
                  onClick={() => askZeki(t.q)}
                  className={`kp-press min-h-11 sm:min-h-0 group flex w-full items-center justify-between rounded-xl border border-stone-200 bg-stone-50 p-2.5 text-left ${t.hover}`}
                >
                  <div className="flex items-center gap-2.5">
                    <div className={`flex h-7 w-7 items-center justify-center rounded-lg font-bold ${t.box}`}>{t.icon}</div>
                    <div>
                      <p className="font-semibold text-stone-900">{t.title}</p>
                      <p className="text-[11px] text-stone-500">{t.note}</p>
                    </div>
                  </div>
                  <ChevronRight className="h-3.5 w-3.5 text-stone-400 group-hover:text-orange-600" />
                </button>
              ))}
            </div>
          </Card>

          <Card id="studios-hub" className="p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <DoorClosed className="h-4 w-4 text-emerald-600" />
                <h3 className="kp-display text-xs font-bold uppercase tracking-wider text-stone-900">Kampüs Odaları &amp; Stüdyo</h3>
              </div>
              <span className="kp-mono whitespace-nowrap rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-700">CANLI</span>
            </div>
            <div className="space-y-2.5 text-xs">
              {[
                { name: 'Podcast Stüdyosu (Kat -1)', note: "Şu an BOŞ • 15:00'e kadar rezerve edilebilir", free: true },
                { name: 'Büyük Divan Salonu', note: 'DOLU: Çocuk Kitapları Yayın Kurulu', free: false },
                { name: 'Kütüphane Çalışma Odası 2', note: 'Şu an BOŞ • Sessiz Odak Alanı', free: true },
              ].map((r) => (
                <div key={r.name} className="flex items-center justify-between gap-2 rounded-xl border border-stone-200 bg-stone-50/90 p-2.5">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className={`h-2 w-2 shrink-0 rounded-full ${r.free && !booked[r.name] ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                      <span className="font-semibold text-stone-900">{r.name}</span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-stone-500">{booked[r.name] ? `${firstName} adına ayrıldı` : r.note}</p>
                  </div>
                  {r.free ? (
                    <button
                      type="button"
                      onClick={() => setBooked((b) => ({ ...b, [r.name]: !b[r.name] }))}
                      className={`kp-press min-h-11 sm:min-h-0 shrink-0 rounded-lg border whitespace-nowrap px-3 py-1 text-xs font-medium sm:px-2 sm:text-[11px] ${
                        booked[r.name] ? 'border-emerald-500 bg-emerald-50 text-emerald-700' : 'border-stone-300 bg-white hover:border-emerald-500 hover:text-emerald-700'
                      }`}
                    >
                      {booked[r.name] ? 'Ayrıldı ✓' : 'Ayırt'}
                    </button>
                  ) : (
                    <span className="kp-mono shrink-0 rounded bg-rose-50 px-1.5 py-0.5 text-[11px] font-semibold text-rose-700">16:00'da boş</span>
                  )}
                </div>
              ))}
            </div>
          </Card>

          <section id="coffee-lottery" className="kp-card relative overflow-hidden rounded-2xl border border-amber-300/80 bg-gradient-to-br from-[#fbf4e8] to-[#f7eedb] p-4">
            <div className="mb-2 flex items-center gap-2 text-amber-900">
              <Gift className="h-4 w-4 text-amber-700" />
              <h3 className="kp-display text-xs font-bold uppercase tracking-wider">Haftalık Kahve &amp; Çekiliş</h3>
            </div>
            <p className="text-xs leading-snug text-stone-700">
              Bu haftanın çekilişi: <strong>Yazar İmzalı 3 Özel Cilt Eser</strong> + Genel Yayın Yönetmeniyle Teras Kahvesi Sohbeti!
            </p>
            <div className="mt-3 flex items-center justify-between gap-2 rounded-xl border border-amber-200 bg-white/80 p-2.5 text-xs">
              <div>
                <span className="kp-mono text-[11px] font-semibold uppercase text-amber-800">Katılanlar</span>
                <p className="font-bold text-stone-900">{lottery ? 65 : 64} Çalışanımız</p>
              </div>
              <button
                type="button"
                onClick={() => setLottery(true)}
                disabled={lottery}
                className={`kp-press min-h-11 sm:min-h-0 flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium text-white shadow-sm ${
                  lottery ? 'bg-emerald-600' : 'bg-amber-600 hover:bg-amber-700'
                }`}
              >
                {lottery ? (
                  '✅ Katıldınız! (Bilet #65)'
                ) : (
                  <>
                    <Ticket className="h-3.5 w-3.5" /> Çekilişe Katıl
                  </>
                )}
              </button>
            </div>
          </section>
        </aside>

        {/* ORTA SÜTUN */}
        <main className="flex min-w-0 flex-col gap-5 lg:col-span-6">
          {/* ZEKİ sahnesi */}
          <section className="kp-card relative overflow-hidden rounded-3xl border border-stone-300/90 bg-gradient-to-br from-[#f8f4ec] via-[#f5efe4] to-[#ebe1d1] p-5 sm:p-7">
            <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-orange-300/25 blur-3xl" />
            <div className="pointer-events-none absolute -bottom-16 -left-16 h-64 w-64 rounded-full bg-amber-300/25 blur-3xl" />
            <div className="relative z-10 grid grid-cols-1 items-center gap-5 md:grid-cols-12">
              <div className="flex flex-col items-center md:col-span-5">
                <div className="relative w-full max-w-[270px] overflow-hidden rounded-2xl border border-stone-300/80 bg-[#f5efe4] shadow-md">
                  <img src={zekiImg} alt="ZEKİ AI - Timaş Kurumsal Asistanı" className="h-auto w-full object-cover" />
                  <div className="kp-mono absolute left-2.5 top-2.5 flex items-center gap-2 rounded-lg bg-stone-900/80 px-2.5 py-1 text-[11px] text-white backdrop-blur-md">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
                    <span>ZEKİ CANLI • v3.8</span>
                  </div>
                  <div className="absolute bottom-2 left-2 right-2 rounded-xl border border-stone-200/80 bg-white/90 px-3 py-1.5 text-center text-xs text-stone-800 backdrop-blur-md">
                    <span className="kp-display font-semibold text-orange-800">Timaş Kurumsal Zekası</span>
                  </div>
                </div>
              </div>

              <div className="flex min-w-0 flex-col md:col-span-7">
                <div className="mb-2 inline-flex w-fit items-center gap-1.5 rounded-full border border-orange-300 bg-orange-100/90 px-3 py-1 text-xs font-semibold text-orange-900">
                  <Bot className="h-3.5 w-3.5 text-orange-600" /> Timaş Çalışan Yapay Zeka Asistanı
                </div>
                <h2 className="kp-display text-xl font-bold leading-snug tracking-tight text-stone-900 sm:text-2xl">
                  Selam {firstName}! Ben <span className="text-orange-700">ZEKİ</span>, bugün hangi işi kolaylaştıralım?
                </h2>
                <p className="mt-1.5 text-xs leading-relaxed text-stone-600">
                  Dahili masalar, matbaa baskı takvimi, telif süreçleri, İK izinleri veya kitap arka kapak taslakları için her an buradayım.
                </p>
                <form
                  className="mt-4"
                  onSubmit={(e) => {
                    e.preventDefault();
                    askZeki(zekiQ);
                  }}
                >
                  <div className="flex items-center rounded-2xl border border-stone-300 bg-white p-1.5 shadow-sm focus-within:border-orange-500 focus-within:ring-2 focus-within:ring-orange-200">
                    <div className="pl-2.5 text-orange-600">
                      <MessageCircle className="h-4 w-4" />
                    </div>
                    <input
                      value={zekiQ}
                      onChange={(e) => setZekiQ(e.target.value)}
                      placeholder="ZEKİ'ye sor: 'Kurgu dışı yayın takvimi ne zaman?', 'Deniz Kaya kimdir?'..."
                      className="w-full min-w-0 border-0 bg-transparent px-2.5 py-1.5 text-xs text-stone-900 placeholder:text-stone-400 focus:outline-none focus:ring-0 sm:text-sm"
                    />
                    <button
                      type="submit"
                      className="kp-press min-h-11 sm:min-h-0 kp-glow flex shrink-0 items-center gap-1.5 rounded-xl bg-gradient-to-r from-orange-600 to-amber-600 px-4 py-2 text-xs font-medium text-white hover:from-orange-700 hover:to-amber-700"
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
                      className="kp-press min-h-11 sm:min-h-0 flex items-center gap-1 rounded-lg border border-stone-200 bg-white px-2.5 py-1 text-stone-700 hover:bg-stone-100 hover:text-stone-900"
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
                <div className="mt-3 flex items-start gap-2 text-[11px] text-stone-500">
                  <Sparkle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-orange-600" />
                  <span>Sorunuz ZEKİ AI Genel Bakış ekranında gerçek veriyle cevaplanır.</span>
                </div>
              </div>
            </div>
          </section>

          {/* MODÜLLER — kanvas ekranlarına geçiş */}
          <Card id="moduller" className="p-5">
            <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div className="flex items-center gap-3">
                <div className="rounded-xl border border-orange-200 bg-orange-100 p-2 text-orange-800">
                  <LayoutGrid className="h-5 w-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="kp-display text-base font-bold text-stone-900">Modüller</h2>
                    <span className="kp-mono whitespace-nowrap rounded border border-stone-200 bg-stone-100 px-2 text-[11px] font-semibold text-stone-600">
                      {MODULE_TILES.length} açık · {moduleTotal} toplam
                    </span>
                  </div>
                  <p className="text-xs text-stone-500">ZEKİ AI iş ekranlarına buradan geçin</p>
                </div>
              </div>
              <button
                type="button"
                aria-expanded={allModules}
                onClick={() => setAllModules((v) => !v)}
                className="kp-press min-h-11 sm:min-h-0 flex w-fit items-center gap-1 rounded-lg border border-stone-200 bg-stone-50 px-3 py-1.5 text-xs font-medium text-stone-700 hover:border-orange-300 hover:text-orange-700"
              >
                Tüm modüller
                <ChevronDown className={`h-3.5 w-3.5 ${allModules ? 'rotate-180' : ''}`} />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {MODULE_TILES.map((m) => (
                <Link
                  key={m.to}
                  to={m.to}
                  className="kp-lift group flex items-center justify-between gap-2 rounded-xl border border-stone-200/80 bg-stone-50/80 p-3 hover:border-orange-300 hover:bg-white"
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${m.tone}`}>
                      <Sparkles className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-xs font-bold text-stone-900 group-hover:text-orange-700">{m.title}</p>
                      <p className="truncate text-[11px] text-stone-500">{m.note}</p>
                    </div>
                  </div>
                  <ArrowRight className="h-3.5 w-3.5 shrink-0 text-stone-400 group-hover:text-orange-600" />
                </Link>
              ))}
            </div>

            {allModules && (
              <div className="kp-scroll mt-4 max-h-[420px] space-y-3 overflow-y-auto border-t border-stone-200 pr-1 pt-4">
                {moduleGroups.map((g) => (
                  <div key={g.title}>
                    <div className="kp-mono pb-1 text-[11px] font-bold uppercase tracking-wider text-stone-500">{g.title}</div>
                    <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                      {g.modules.map((m) => {
                        const to = LIVE[m.id];
                        return to ? (
                          <Link
                            key={m.id}
                            to={to}
                            className="kp-press min-h-11 sm:min-h-0 flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-[12px] font-semibold text-stone-900 hover:border-orange-300"
                          >
                            <span className="min-w-0 flex-1 truncate">{m.title}</span>
                            <span className="shrink-0 rounded bg-orange-100 px-1.5 text-[11px] font-bold text-orange-700">açık</span>
                          </Link>
                        ) : (
                          <div key={m.id} title={m.title} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[12px] text-stone-500">
                            <span className="min-w-0 flex-1 truncate">{m.title}</span>
                            <span className="shrink-0 text-[11px] text-stone-400">yakında</span>
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
                <div className="rounded-xl border border-orange-200 bg-orange-100 p-2 text-orange-800">
                  <Contact className="h-5 w-5" />
                </div>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="kp-display text-base font-bold text-stone-900">Timaş Rehber · Anında Arama &amp; Kat Planı</h2>
                    <span className="kp-mono whitespace-nowrap rounded border border-stone-200 bg-stone-100 px-2 text-[11px] font-semibold text-stone-600">180 Kişi</span>
                  </div>
                  <p className="text-xs text-stone-500">Masa, kat, dahili telefon, cep ve departman hızlı arama motoru</p>
                </div>
              </div>
              <div className="kp-scroll flex items-center gap-1 overflow-x-auto pb-1 text-xs sm:pb-0">
                {FLOORS.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    aria-pressed={floor === f.id}
                    onClick={() => setFloor(f.id)}
                    className={`kp-press min-h-11 sm:min-h-0 shrink-0 whitespace-nowrap rounded-lg px-2.5 py-1 font-medium ${
                      floor === f.id ? 'bg-orange-600 text-white' : 'bg-stone-100 text-stone-700 hover:bg-stone-200'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="relative mb-3">
              <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
              <input
                value={term}
                onChange={(e) => setTerm(e.target.value)}
                placeholder="İsim, unvan, dahili (örn: 1045) veya masa no yazarak süzün..."
                className="w-full rounded-xl border border-stone-200 bg-stone-50 py-2.5 pl-10 pr-11 text-xs text-stone-900 sm:py-2 placeholder:text-stone-400 focus:border-orange-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-orange-300"
              />
              {term && (
                <button
                  type="button"
                  aria-label="Aramayı temizle"
                  onClick={() => setTerm('')}
                  className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-sm text-stone-400 hover:text-stone-700"
                >
                  ✕
                </button>
              )}
            </div>

            <div className="kp-scroll grid max-h-[380px] grid-cols-1 gap-3 overflow-y-auto pr-1 sm:grid-cols-2">
              {staff.map((s) => (
                <div
                  key={s.ext}
                  className="flex items-start justify-between gap-2 rounded-xl border border-stone-200/80 bg-stone-50/80 p-3 transition-colors hover:border-orange-300 hover:bg-white"
                >
                  <div className="flex min-w-0 items-start gap-3">
                    {s.img ? (
                      <img src={s.img} alt={s.name} className="mt-0.5 h-9 w-9 shrink-0 rounded-xl object-cover ring-1 ring-stone-300" />
                    ) : (
                      <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-xs font-bold ring-1 ${s.tone}`}>{s.initials}</div>
                    )}
                    <div className="min-w-0">
                      <h4 className="text-xs font-bold text-stone-900">{s.name}</h4>
                      <p className="text-[11px] text-stone-500">{s.role}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <span className="kp-mono whitespace-nowrap rounded border border-orange-200 bg-orange-50 px-1.5 py-0.5 text-[11px] font-semibold text-orange-800">Dahili: {s.ext}</span>
                        <span className="rounded border border-stone-200 bg-stone-100 px-1.5 py-0.5 text-[11px] text-stone-600">{s.desk}</span>
                      </div>
                    </div>
                  </div>
                  <a href={`tel:${s.ext}`} title="Hemen Ara" className="kp-press flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-stone-100 text-stone-600 sm:h-auto sm:w-auto sm:p-1.5 hover:bg-orange-600 hover:text-white">
                    <PhoneCall className="h-3.5 w-3.5" />
                  </a>
                </div>
              ))}
              {!staff.length && <div className="col-span-full py-6 text-center text-xs text-stone-500">Eşleşen kişi yok.</div>}
            </div>

            <div className="mt-3 flex flex-col justify-between gap-2 border-t border-stone-200 pt-3 text-xs text-stone-500 sm:flex-row sm:items-center">
              <span>
                Toplam <strong>6</strong> departman • <strong>180</strong> kayıtlı çalışan
              </span>
              <span className="flex items-center gap-1 font-medium text-orange-700">
                İnteraktif Kat Planı PDF İndir <Download className="h-3.5 w-3.5" />
              </span>
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
                  <h2 className="kp-display text-base font-bold text-stone-900">Kutlamalar &amp; Alkış Duvarı</h2>
                  <p className="text-xs text-stone-500">Çalışma arkadaşlarımıza günün tebriğini ve mikro-övgüsünü iletin</p>
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
              <form onSubmit={sendPraise} className="mb-3 grid grid-cols-1 gap-2 rounded-xl border border-orange-200 bg-orange-50/70 p-3 sm:grid-cols-[1fr_2fr_auto]">
                <input
                  value={praiseTo}
                  onChange={(e) => setPraiseTo(e.target.value)}
                  placeholder="Kimi alkışlıyorsunuz?"
                  className="rounded-lg border border-stone-200 bg-white px-2.5 py-1.5 text-xs focus:border-orange-500 focus:outline-none"
                />
                <input
                  value={praiseText}
                  onChange={(e) => setPraiseText(e.target.value)}
                  placeholder="Mikro tebrik notunuz"
                  className="rounded-lg border border-stone-200 bg-white px-2.5 py-1.5 text-xs focus:border-orange-500 focus:outline-none"
                />
                <button type="submit" className="kp-press min-h-11 sm:min-h-0 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-rose-700">
                  Gönder
                </button>
              </form>
            )}

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {praise.map((p, i) => (
                <div
                  key={`${p.from}-${p.to}-${i}`}
                  className={`flex flex-col justify-between rounded-xl border p-3 ${p.fresh ? 'border-orange-200 bg-orange-50/70' : 'border-stone-200 bg-stone-50/70'}`}
                >
                  <div>
                    <div className="mb-1.5 flex items-center justify-between gap-2 text-[11px]">
                      <span className="font-bold text-stone-900">
                        {p.from} ➔ {p.to}
                      </span>
                      <span className={p.fresh ? 'kp-mono font-semibold text-orange-700' : 'text-stone-400'}>{p.when}</span>
                    </div>
                    <p className="text-xs leading-snug text-stone-700">{p.text}</p>
                  </div>
                  <div className="mt-2.5 flex items-center justify-between border-t border-stone-200/60 pt-2 text-xs">
                    <button
                      type="button"
                      aria-pressed={!!liked[i]}
                      onClick={() => setLiked((l) => ({ ...l, [i]: !l[i] }))}
                      className={`kp-press min-h-11 sm:min-h-0 flex items-center gap-1 ${liked[i] ? 'text-rose-600' : 'text-stone-500 hover:text-rose-600'}`}
                    >
                      <span>{p.emoji}</span> <span className="kp-mono font-bold">{p.likes + (liked[i] ? 1 : 0)}</span>
                    </button>
                    <span className={`kp-mono rounded px-1.5 py-0.5 text-[11px] ${p.tagTone}`}>{p.tag}</span>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* SESLİ BÜLTEN */}
          <section id="podcast-hub" className="kp-card relative overflow-hidden rounded-2xl bg-gradient-to-r from-stone-900 via-[#1f1b18] to-stone-900 p-5 text-white">
            <div className="pointer-events-none absolute bottom-0 right-0 top-0 w-1/3 bg-gradient-to-l from-orange-600/20 to-transparent" />
            <div className="relative z-10 flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
              <div className="flex min-w-0 items-center gap-3.5">
                <div className="kp-glow flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-orange-600 text-white">
                  <Radio className="h-6 w-6" />
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="kp-mono whitespace-nowrap rounded border border-orange-400/30 bg-orange-500/20 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-orange-300">
                      Haftanın Sesli Bülteni
                    </span>
                    <span className="kp-mono text-[11px] text-stone-400">14 Dk • Bölüm #42</span>
                  </div>
                  <h3 className="kp-display mt-1 text-sm font-bold text-white">"Matbaadan Raflara: Editör Masasında Bir Kitabın Doğuşu"</h3>
                  <p className="mt-0.5 text-xs text-stone-300">Konuk: Prof. Dr. M. Yılmaz &amp; Deniz Kaya (Seslendiren: ZEKİ Voice)</p>
                </div>
              </div>
              <div className="flex w-full items-center justify-end gap-3 sm:w-auto">
                <button
                  type="button"
                  aria-label={playing ? 'Duraklat' : 'Oynat'}
                  onClick={() => setPlaying((v) => !v)}
                  className="kp-press flex h-11 w-11 items-center justify-center rounded-full bg-white sm:h-10 sm:w-10 text-stone-950 shadow-md hover:bg-orange-500 hover:text-white"
                >
                  {playing ? <Pause className="h-5 w-5 fill-current" /> : <Play className="ml-0.5 h-5 w-5 fill-current" />}
                </button>
                <div className="hidden text-right sm:block">
                  <span className={`kp-mono block text-[11px] ${playing ? 'text-orange-400' : 'text-stone-400'}`}>
                    {playing ? '02:15 / 14:12 (Çalıyor)' : '00:00 / 14:12'}
                  </span>
                  <span className="text-[11px] text-orange-400">Bölüm Notları (.md)</span>
                </div>
              </div>
            </div>
            <div className="mt-4 flex h-4 items-center gap-1 border-t border-stone-800 pt-3">
              {[
                ['bg-orange-500', 'h-2', true],
                ['bg-orange-400', 'h-3', true],
                ['bg-stone-600', 'h-1.5', false],
                ['bg-orange-500', 'h-4', true],
                ['bg-stone-600', 'h-2', false],
                ['bg-orange-400', 'h-3.5', true],
                ['bg-stone-600', 'h-1', false],
                ['bg-orange-500', 'h-3', false],
                ['bg-stone-700', 'h-2', false],
                ['bg-orange-300', 'h-4', false],
              ].map(([c, h, pulse], i) => (
                <span key={i} className={`w-1 shrink-0 rounded-full ${c} ${h} ${pulse && playing ? 'animate-pulse' : ''}`} />
              ))}
              <span className="ml-2 h-1 w-full rounded-full bg-stone-800">
                <span className="block h-1 rounded-full bg-orange-500" style={{ width: playing ? '16%' : '24%' }} />
              </span>
            </div>
          </section>
        </main>

        {/* SAĞ SÜTUN */}
        <aside className="flex min-w-0 flex-col gap-5 lg:col-span-3">
          <Card id="kutlamalar" className="relative overflow-hidden p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Cake className="h-4 w-4 text-amber-600" />
                <h3 className="kp-display text-xs font-bold uppercase tracking-wider text-stone-900">Bugün Doğanlar (2)</h3>
              </div>
              <span className="kp-mono whitespace-nowrap rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800">17 Nisan</span>
            </div>
            <div className="space-y-2.5">
              {[
                { name: 'Ahmet Yıldız', note: 'Grafik • Doğum Günü 🎈', img: ahmetImg, ring: 'ring-amber-300', btn: 'bg-amber-100 text-amber-900 hover:bg-amber-200' },
                { name: 'Büşra Aksoy', note: 'Yayın Koor. • 5. Yıl 🏆', img: busraImg, ring: 'ring-sky-300', btn: 'bg-sky-100 text-sky-900 hover:bg-sky-200' },
              ].map((p) => (
                <div key={p.name} className="flex items-center justify-between gap-2 rounded-xl border border-stone-200 bg-stone-50 p-2.5">
                  <div className="flex min-w-0 items-center gap-2.5">
                    <img src={p.img} alt={p.name} className={`h-8 w-8 shrink-0 rounded-lg object-cover ring-2 ${p.ring}`} />
                    <div className="min-w-0">
                      <h4 className="text-xs font-bold text-stone-900">{p.name}</h4>
                      <p className="text-[11px] text-stone-500">{p.note}</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={greeted[p.name]}
                    onClick={() => setGreeted((g) => ({ ...g, [p.name]: true }))}
                    className={`kp-press min-h-11 sm:min-h-0 shrink-0 rounded-lg whitespace-nowrap px-3 py-1 text-xs font-medium sm:px-2 sm:text-[11px] ${greeted[p.name] ? 'bg-emerald-100 text-emerald-800' : p.btn}`}
                  >
                    {greeted[p.name] ? 'Kutlandı ✓' : 'Kutla'}
                  </button>
                </div>
              ))}
            </div>
          </Card>

          <Card id="ajanda" className="p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4 text-sky-600" />
                <h3 className="kp-display text-xs font-bold uppercase tracking-wider text-stone-900">Önemli Günler &amp; Ajanda</h3>
              </div>
              <span className="shrink-0 text-[11px] font-medium text-orange-700">Takvime Ekle</span>
            </div>
            <div className="relative space-y-3.5 border-l-2 border-stone-200 pl-3.5 text-xs">
              <div className="relative">
                <div className="absolute -left-[19px] top-1 h-2 w-2 rounded-full bg-sky-600 ring-2 ring-white" />
                <span className="kp-mono text-[11px] font-semibold uppercase text-sky-700">22 Nisan Pazartesi • 10:00</span>
                <h4 className="mt-0.5 font-bold text-stone-900">Dünya Kitap ve Telif Hakları Günü</h4>
                <p className="text-[11px] text-stone-500">Genel merkez fuayesinde mini sergi &amp; söyleşi</p>
              </div>
              <div className="relative">
                <div className="absolute -left-[19px] top-1 h-2 w-2 rounded-full bg-orange-500 ring-2 ring-white" />
                <span className="kp-mono text-[11px] font-semibold uppercase text-orange-700">26 Nisan Cuma • 15:30</span>
                <h4 className="mt-0.5 font-bold text-stone-900">Aylık Yayın Kurulu Değerlendirmesi</h4>
                <p className="text-[11px] text-stone-500">Büyük Divan Salonu &amp; Zoom Hibrit</p>
              </div>
              <div className="rounded-xl border border-orange-200 bg-orange-50/70 p-3 text-xs">
                <div className="flex items-center justify-between gap-2 font-bold text-stone-900">
                  <span className="flex items-center gap-1">
                    <Flag className="h-3.5 w-3.5 text-rose-500" /> TÜYAP Fuarı 2024
                  </span>
                  <span className="kp-mono whitespace-nowrap rounded bg-rose-100 px-1.5 py-0.5 text-[11px] text-rose-700">18 Gün</span>
                </div>
                <p className="mt-1 text-[11px] text-stone-600">Stand planı, görev listesi ve yazar imza saatleri ZEKİ AI üzerinden görüntülenebilir.</p>
              </div>
            </div>
          </Card>

          <Card id="yeni-kitaplar" className="p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-orange-600" />
                <h3 className="kp-display text-xs font-bold uppercase tracking-wider text-stone-900">Matbaadan Yeni Çıkanlar</h3>
              </div>
              <span className="kp-mono shrink-0 text-[11px] font-semibold text-stone-500">6 Yeni Baskı</span>
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              {[
                { title: 'Gecenin Sessiz Yankısı', author: 'Selin Karahan', img: book1Img, badge: 'YENİ', badgeTone: 'bg-orange-600', hover: 'hover:border-orange-300' },
                { title: 'İpek Yolunun Muhafızları', author: 'Prof. Dr. M. Yılmaz', img: book2Img, badge: '2. BASKI', badgeTone: 'bg-emerald-600', hover: 'hover:border-emerald-300' },
              ].map((b) => (
                <div key={b.title} className={`kp-cover min-w-0 rounded-xl border border-stone-200 bg-stone-50 p-2 transition-colors ${b.hover}`}>
                  <div className="relative mb-1.5 aspect-[2/3] w-full overflow-hidden rounded-lg bg-stone-200">
                    <img src={b.img} alt={b.title} className="h-full w-full object-cover" />
                    <span className={`kp-mono absolute left-1 top-1 rounded px-1 text-[11px] font-bold text-white ${b.badgeTone}`}>{b.badge}</span>
                  </div>
                  <h5 className="truncate text-[11px] font-bold text-stone-900">{b.title}</h5>
                  <p className="truncate text-[11px] text-stone-500">{b.author}</p>
                </div>
              ))}
            </div>
          </Card>

          <div className="flex items-center justify-between gap-2 rounded-2xl border border-stone-300/80 bg-stone-100/90 p-3.5 text-xs">
            <div className="flex min-w-0 items-center gap-2">
              <span className="text-base">🍲</span>
              <div className="min-w-0">
                <span className="block font-bold text-stone-900">Yemekhane Bugün (12:00-14:00)</span>
                <span className="text-[11px] text-stone-500">Yayla Çorbası • Fırın Tavuk Rosto • Bulgur</span>
              </div>
            </div>
            <span className="shrink-0 text-[11px] font-semibold text-orange-700">Detay</span>
          </div>
        </aside>
      </div>

      {/* ALT BİLGİ */}
      <footer className="mt-auto border-t border-stone-300/80 bg-white/70 px-4 py-4 text-xs text-stone-500 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-[1720px] flex-col items-center justify-between gap-3 text-center sm:flex-row sm:text-left">
          <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
            <span className="kp-display font-semibold text-stone-800">TİMAŞ YAYIN GRUBU</span>
            <span>•</span>
            <span>Kampüs Portalı</span>
            <span>•</span>
            <span className="font-medium text-orange-700">Birlikte Üretiyor, Birlikte Okuyoruz</span>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1">
            <span>Dahili Rehber (.xls)</span>
            <span>İK İzin Formları</span>
            <span>Telif &amp; Hukuk Şablonları</span>
            <span>KVKK</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
