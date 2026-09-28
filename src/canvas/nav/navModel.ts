import {
  Activity,
  Headset,
  Server,
  Handshake,
  HeartHandshake,
  CalendarHeart,
  MessageSquareReply,
  Inbox,
  ArrowLeftRight,
  BookCopy,
  FileBarChart,
  Lightbulb,
  MessageCircleQuestion,
  NotebookTabs,
  ShoppingBag,
  Youtube,
  Archive,
  BellRing,
  CalendarDays,
  Link2,
  MessageSquareText,
  Network,
  Quote,
  ScanSearch,
  Split,
  UserRoundCheck,
  Video,
  BadgeCheck,
  BadgeDollarSign,
  Stethoscope,
  TrendingUp,
  Swords,
  Target,
  Truck,
  Gavel,
  Waypoints,
  Store,
  Grid3x3,
  Globe,
  Library,
  Radar,
  Bell,
  BookA,
  Calculator,
  BookImage,
  BookOpen,
  BookPlus,
  BookUser,
  BriefcaseBusiness,
  Building2,
  Braces,
  CalendarClock,
  CalendarRange,
  ChartColumn,
  ClipboardCheck,
  ClipboardList,
  Rocket,
  Factory,
  Contact,
  CornerDownRight,
  FileChartColumn,
  FileSignature,
  FileText,
  FolderTree,
  Gauge,
  Gift,
  History,
  House,
  Images,
  Landmark,
  Languages,
  LayoutDashboard,
  ListChecks,
  LayoutGrid,
  Mail,
  MapPinned,
  Megaphone,
  Newspaper,
  NotebookPen,
  Palette,
  PenLine,
  Plug,
  Printer,
  Route,
  School,
  Search,
  Settings,
  ShieldCheck,
  LockKeyhole,
  SlidersHorizontal,
  Share2,
  Sparkles,
  SpellCheck,
  UserCog,
  UserPen,
  UsersRound,
  Wallet,
  type LucideIcon,
  ShieldAlert,
} from 'lucide-react';

/**
 * Portalın TEK menü tanımı. Masaüstü ray + bağlam paneli, telefon alt çubuğu + menü sayfası, ⌘K komut
 * paleti ve «Son açılanlar» hep buradan okur; menü her ekranda aynıdır. Yalnız koddaki gerçek rotalar
 * yazılır — menüde olmayan detay sayfaları (Kitap 360, yazar giriş projesi, stüdyo iş sayfaları) buraya
 * öğe olarak girmez, `also` ile en yakın menü öğesine bağlanır ki doğru öğe etkin görünsün.
 */

export type NavGroupId = 'kampus' | 'analiz' | 'finans' | 'editoryal' | 'kayitlar' | 'satis' | 'pazarlama' | 'altyapi' | 'yonetim';
export type NavGroupId = 'kampus' | 'analiz' | 'finans' | 'editoryal' | 'kayitlar' | 'satis' | 'pazarlama' | 'ik' | 'yonetim';
export type NavGroupId = 'kampus' | 'analiz' | 'finans' | 'editoryal' | 'kayitlar' | 'satis' | 'pazarlama' | 'platform' | 'yonetim';
export type NavFeature = 'webWatch';
export type NavBadge = 'alerts' | 'mailbox';

/** Rozet sayıları: uyarılar (eşiği aşmış kural) ve kurumsal e-posta (bana atanan açık ileti). */
export type NavCounts = Partial<Record<NavBadge, number>>;

/** Rozetin ekran okuyucu metni. `overdue`: süresi aşan ileti sayısı (e-posta rozetinde). */
export function badgeLabel(badge: NavBadge, count: number, overdue = 0): string {
  if (badge === 'mailbox') return overdue > 0 ? `${count} ileti size atanmış, ${overdue} tanesinin süresi aşmış` : `${count} ileti size atanmış`;
  return `${count} uyarı eşiği aşmış`;
}

export type NavItem = {
  id: string;
  label: string;
  /** Hedef adres; sorgu parçası da olabilir (ör. `/kisiler?rol=cevirmen`). */
  to: string;
  icon: LucideIcon;
  /** Panelde öğenin üstündeki alt başlık (ör. «Günlük»). Aynı başlık art arda gelen öğelerde bir kez yazılır. */
  section?: string;
  /** Palette ve arama için kısa açıklama. */
  hint: string;
  /** Aramada ek eşleşme sözcükleri (eski adlar dahil: kullanıcı eski adı yazınca da bulsun). */
  keywords?: string[];
  /** Menüde olmayan alt/detay rotaları: bu önekler altındaki sayfalarda da bu öğe etkin görünür. */
  also?: string[];
  /** Başka bir öğenin altında (girintili) görünür; yalnız görünüm. */
  parent?: string;
  adminOnly?: boolean;
  /** Ortamda kapalıysa öğe hiç görünmez (ör. müşteri ortamında basın ve web). */
  feature?: NavFeature;
  badge?: NavBadge;
};

export type NavGroup = {
  id: NavGroupId;
  /** Raydaki ve paneldeki ad. */
  label: string;
  hint: string;
  icon: LucideIcon;
  items: NavItem[];
  /** Kampüs gibi tek ekranlı alan: rayda doğrudan bağlantıdır, paneli yoktur. */
  to?: string;
  adminOnly?: boolean;
  /** Sayfaları açıkça verilir (İK): «bütün sayfalar» yalnız yöneticide bu grubu açar. */
  explicit?: boolean;
};

export const NAV: NavGroup[] = [
  {
    id: 'kampus',
    label: 'Kampüs',
    hint: 'Ana sayfa, rehber ve duyurular',
    icon: House,
    to: '/',
    items: [{ id: 'kampus', label: 'Kampüs', to: '/', icon: House, hint: 'Ana sayfa, rehber ve duyurular', keywords: ['ana sayfa', 'rehber', 'dahili'] }],
  },
  {
    id: 'analiz',
    label: 'Analiz',
    hint: 'Göstergeler, panolar ve uyarılar',
    icon: ChartColumn,
    items: [
      { id: 'genel-bakis', label: 'Genel bakış', to: '/genel-bakis', icon: LayoutDashboard, hint: 'Finansal göstergeler ve ZEKİ AI\'a soru', keywords: ['ciro', 'soru', 'sor'] },
      { id: 'panolar', label: 'Panolar', to: '/panolar', icon: LayoutGrid, hint: 'Kişisel pano kartları', keywords: ['pano', 'panom', 'kart'] },
      { id: 'planli-raporlar', label: 'Planlı raporlar', to: '/planli-raporlar', icon: CalendarClock, hint: 'E-postayla giden zamanlı raporlar', keywords: ['rapor', 'excel'] },
      { id: 'uyarilar', label: 'Uyarılar', to: '/uyarilar', icon: Bell, hint: 'Eşik kuralları ve bildirimler', badge: 'alerts', keywords: ['uyarı', 'kural', 'eşik'] },
    ],
  },
  {
    id: 'finans',
    label: 'Finans',
    hint: 'Denetim, yönetim raporları ve bütçe',
    icon: Landmark,
    items: [
      {
        id: 'finansal-raporlar',
        label: 'Finansal raporlar',
        to: '/finansal-raporlar',
        icon: Wallet,
        hint: 'Gelir tablosu, bütçe–gerçekleşme, kârlılık, 13 haftalık nakit ve vergi takvimi',
        keywords: ['gelir tablosu', 'kâr zarar', 'kârlılık', 'nakit', 'nakit akışı', 'vergi takvimi', 'beyanname', 'katkı payı', 'mutabakat'],
      },
      { id: 'finansal-denetim', label: 'Finansal denetim', to: '/finansal-denetim', icon: ShieldCheck, hint: 'Logo kayıtlarının denetimi', keywords: ['denetim', 'muhasebe', 'risk'] },
      { id: 'yonetim-raporlari', label: 'Yönetim raporları', to: '/yonetim-raporlari', icon: FileChartColumn, hint: 'Karar raporları', keywords: ['rapor'] },
      {
        id: 'baski-oneri',
        label: 'Baskı önerisi',
        to: '/yonetim-raporlari/baski-oneri',
        icon: Printer,
        parent: 'yonetim-raporlari',
        hint: 'Yeniden basılacak kitap önerileri',
        keywords: ['yeni baskı öneri', 'baskı', 'tahmin'],
      },
      {
        id: 'fiyatlama',
        label: 'Fiyatlama ve maliyet',
        to: '/fiyatlama',
        icon: Calculator,
        hint: 'Kitap maliyeti, başabaş, kapak fiyatı önerisi ve gerçekleşen marj',
        keywords: ['fiyat', 'maliyet', 'başabaş', 'kapak fiyatı', 'marj', 'birim maliyet', 'zam'],
      },
      {
        id: 'ilk-baski',
        label: 'İlk baskı tahmini',
        to: '/ilk-baski',
        icon: BookPlus,
        hint: 'Yeni kitabın satış senaryoları ve ilk baskı adedi',
        keywords: ['ilk baskı', 'satış tahmini', 'yeni kitap', 'emsal', 'senaryo', 'üretim adedi'],
      },
      {
        id: 'butce',
        label: 'Bütçe ve hedefler',
        to: '/butce',
        icon: Target,
        hint: 'Kitap bazlı satış hedefleri, departman bütçesi, senaryolar ve sapma uyarısı',
        keywords: ['bütçe', 'hedef', 'satış hedefi', 'senaryo', 'sapma', 'departman'],
      },
      {
        id: 'risk-uyum',
        label: 'Risk ve uyum',
        to: '/risk-uyum',
        icon: ShieldAlert,
        hint: 'Risk kaydı ve ısı haritası, göstergeler, uyum takvimi, sigorta ve iş sürekliliği, kurul brifingi',
        keywords: ['risk', 'uyum', 'kvkk', 'sigorta', 'poliçe', 'iş sürekliliği', 'bcp', 'gösterge', 'kri', 'ısı haritası', 'telif uyumu'],
      },
    ],
  },
  {
    id: 'editoryal',
    label: 'Editoryal',
    hint: 'Masam, yayına hazırlık',
    icon: BookOpen,
    items: [
      // Kitap 360 (/kitap/:id) Masam'daki aramadan açılır; orada Masam etkin görünür.
      { id: 'editoryal', label: 'Masam', to: '/editoryal', icon: LayoutDashboard, section: 'Günlük', hint: 'Editoryal akış ve dosya takibi', also: ['/kitap'], keywords: ['editoryal süreç', 'kitap ara'] },
      { id: 'basvurular', label: 'Başvurular', to: '/basvurular', icon: Inbox, section: 'Günlük', hint: 'Yeni kitap başvuruları, editör raporu, kurul kararı ve arşiv', keywords: ['başvuru', 'dosya', 'kuyruk', 'red', 'arşiv', 'kurul raporu', 'editör raporu'] },
      { id: 'yazar-giris', label: 'Yazar giriş süreci', to: '/yazar-giris', icon: Route, section: 'Günlük', hint: 'Yeni kitap başvuruları ve projeler', keywords: ['başvuru', 'proje', 'dosya'] },
      { id: 'yayin-kurulu', label: 'Yayın kurulu', to: '/yayin-kurulu', icon: UsersRound, section: 'Günlük', hint: 'Kurul oturumları, üye oyu ve kararlar', keywords: ['kurul', 'toplantı', 'oy', 'oturum'] },
      { id: 'gorevlerim', label: 'Görevlerim', to: '/gorevlerim', icon: ListChecks, section: 'Günlük', hint: 'Size atanan editörlük işleri ve terminleri', keywords: ['görev', 'termin', 'pano', 'iş listesi'] },
      { id: 'redaksiyon', label: 'Redaksiyon', to: '/redaksiyon', icon: PenLine, section: 'Yayına hazırlık', hint: 'Metin işleme ve üsluplandırma', keywords: ['redaksiyon', 'metin'] },
      { id: 'ceviri', label: 'Çeviri', to: '/ceviri', icon: Languages, section: 'Yayına hazırlık', hint: 'Çeviri işleri, terim bankası ve kalite raporu', keywords: ['çeviri', 'tercüme', 'terim', 'segment', 'kalite'] },
      { id: 'ceviri-masam', label: 'Çeviri masam', to: '/ceviri/masam', icon: NotebookPen, section: 'Yayına hazırlık', hint: 'Çevirmenin ve inceleyenin kendi ekranı', keywords: ['çevirmen', 'segment', 'xliff'] },
      { id: 'cevirmenler', label: 'Çevirmenler', to: '/kisiler?rol=cevirmen', icon: UserPen, section: 'Yayına hazırlık', hint: 'CRM\'deki çevirmenler ve çevirdikleri kitaplar', keywords: ['tercüme', 'çevirmen'] },
      { id: 'son-okuma', label: 'Son okuma', to: '/son-okuma', icon: SpellCheck, section: 'Yayına hazırlık', hint: 'Baskı öncesi son denetim', keywords: ['yazım', 'denetim', 'okuma'] },
      { id: 'kitap-tasarim', label: 'Kitap tasarım', to: '/kitap-tasarim', icon: BookImage, section: 'Yayına hazırlık', hint: 'Sayfa, kapak ve baskı provası', keywords: ['stüdyo', 'kapak', 'mizanpaj', 'resim'] },
      { id: 'kapak-arsivi', label: 'Kapak arşivi', to: '/kitap-tasarim/kapak-arsivi', icon: Images, section: 'Yayına hazırlık', parent: 'kitap-tasarim', hint: 'Timaş kapakları, kategori ve alt kategoriye göre', keywords: ['kapak', 'örnek', 'arşiv', 'görsel', 'kategori'] },
      { id: 'serbest-calisanlar', label: 'Serbest çalışanlar', to: '/serbest-calisanlar', icon: BriefcaseBusiness, section: 'Yayına hazırlık', hint: 'Çizer ve serbest çalışan havuzu, iş paketleri, kapasite, hakediş', keywords: ['çizer', 'freelancer', 'illüstratör', 'hakediş', 'iş paketi', 'kapasite'] },
      { id: 'uretim', label: 'Üretim yönetimi', to: '/uretim', icon: Factory, section: 'Üretim', hint: 'Baskı takvimi, matbaa takibi ve gecikmeler; depo girişi Logo\'dan', keywords: ['üretim', 'matbaa', 'baskı takvimi', 'depo girişi', 'gecikme', 'bandrol', 'baskı çıkışı'] },
    ],
  },
  {
    id: 'kayitlar',
    label: 'Kayıtlar',
    hint: 'Kişiler, sözleşmeler, atamalar, kategori ağacı',
    icon: BookUser,
    items: [
      { id: 'kisiler', label: 'Kişiler', to: '/kisiler', icon: Contact, hint: 'Yazar, çevirmen, çizer ve serbest çalışanlar', keywords: ['yazar', 'çizer', 'rehber'] },
      { id: 'yazar-iliskileri', label: 'Yazar ilişkileri', to: '/yazar-iliskileri', icon: HeartHandshake, hint: 'Yazar kartı, randevu ve görüşme notu, aday havuzu, ilişki ısısı', keywords: ['randevu', 'görüşme', 'aday', 'potansiyel yazar', 'ısı haritası'] },
      { id: 'basin-web', label: 'Basın ve web', to: '/basin-web', icon: Newspaper, hint: 'Açık kaynaklarda yazar ve kitap haberleri', feature: 'webWatch', keywords: ['haber', 'basın'] },
      { id: 'telif-sozlesme', label: 'Sözleşmeler', to: '/telif-sozlesme', icon: FileSignature, hint: 'Telif ve sözleşme kayıtları', keywords: ['telif', 'sözleşme'] },
      { id: 'telif-donem', label: 'Telif dönemi', to: '/telif-donem', icon: Calculator, parent: 'telif-sozlesme', hint: 'Dönem telif koşusu, istisnalar, beyanname, ödeme listesi, avans ve yenilemeler', keywords: ['telif', 'hakediş', 'beyanname', 'avans', 'yenileme', 'royalty', 'ödeme listesi', 'stopaj'] },
      { id: 'haklar', label: 'Haklar ve lisanslar', to: '/haklar', icon: Languages, parent: 'telif-sozlesme', hint: 'Kitabın hak kartı, dil/ülke hakları, verilen lisanslar', keywords: ['hak', 'lisans', 'çeviri hakkı', 'telif satış', 'yabancı hak'] },
      { id: 'editor-atama', label: 'Editör atama', to: '/editor-atama', icon: UserCog, hint: 'Atama, iş yükü, takvim ve kategori kuralları', keywords: ['editörler', 'atama', 'iş yükü', 'takvim', 'kural'] },
      { id: 'kategori-agaci', label: 'Kategori ağacı', to: '/kategori-agaci', icon: FolderTree, hint: 'Kitap profili, kategori mimarisi ve tutarsızlıklar', keywords: ['kategori', 'kitaplık', 'tür', 'tema', 'etiket', 'künye', 'profil', 'web kategorisi', 'tutarsızlık'] },
      {
        id: 'kurumsal-eposta',
        label: 'Kurumsal e-posta',
        to: '/kurumsal-eposta',
        icon: Mail,
        hint: 'Genel kutuya gelen iletiler, atama ve yanıt süreleri',
        badge: 'mailbox',
        keywords: ['e-posta', 'eposta', 'mail', 'timas@', 'genel kutu', 'gelen kutusu', 'şikâyet', 'başvuru', 'iş başvurusu', 'sla', 'yanıt'],
      },
    ],
  },
  {
    // M29–M33 ortak çalışma alanı (ilk dağılım, saha, okul tanıtım, kurumsal satış, ihale); ilk açan M29.
    id: 'satis',
    label: 'Satış ve saha',
    hint: 'İlk dağılım, saha satışı ve kurumsal satış',
    icon: Waypoints,
    items: [
      {
        id: 'ilk-dagilim',
        label: 'İlk dağılım',
        to: '/ilk-dagilim',
        icon: Truck,
        section: 'Planlama',
        hint: 'Yeni kitabın bölge, kanal ve müşteri dağılımı; sevk listesi ve ilk 8 hafta takibi',
        keywords: ['dağılım', 'sevk', 'sevk listesi', 'bölge', 'bmt', 'bölgem', 'depo girişi', 'yeni kitap', 'iade'],
      },
      { id: 'saha', label: 'Saha ve tahsilat', to: '/saha', icon: MapPinned, section: 'Saha', hint: 'Bugünün ziyaret sırası, müşteri brifingi, vadesi geçmiş alacak ve CRM tahsilat onayı', keywords: ['bmt', 'ziyaret', 'tahsilat', 'vadesi geçmiş', 'yaşlandırma', 'brifing', 'ödeme planı', 'saha satış', 'bayi', 'kitapçı'] },
      { id: 'bayi-risk', label: 'Bayi riski', to: '/bayi-risk', icon: ShieldCheck, section: 'Saha', hint: 'Bayi ve kitapçı risk skoru (A/B/C/D), alacak yaşlandırması, limit önerisi ve ziyaret öncesi risk brifi', keywords: ['bayi', 'kitapçı', 'alacak', 'vade', 'limit', 'tahsilat', 'risk', 'segment', 'yaşlandırma', 'karşılıksız çek'] },
      {
        id: 'okul-tanitim',
        label: 'Okul tanıtım',
        to: '/okul-tanitim',
        icon: School,
        section: 'Saha',
        hint: 'Okul ziyaret planı, okul kartı, kademeye uygun katalog, bayi eşleştirme ve ziyaret raporu',
        keywords: ['okul', 'ziyaret', 'öğretmen', 'katalog', 'bayi eşleştirme', 'okul örneği', 'akademik takvim'],
      },
      {
        id: 'musteri-iliskileri',
        label: 'Müşteri ilişkileri',
        to: '/musteri-iliskileri',
        icon: HeartHandshake,
        section: 'Müşteri',
        hint: 'Cari değeri, nedenleri yazılı kayıp riski, temsilci portföyü ve aksiyon kaydı',
        keywords: ['müşteri', 'cari', 'kayıp riski', 'churn', 'portföy', 'aksiyon', 'segment', 'değer', 'crm', 'bayi', 'kitapçı', 'dağıtıcı'],
      },
      {
        id: 'musteri-veri-sagligi',
        label: 'CRM veri sağlığı',
        to: '/musteri-iliskileri/veri-sagligi',
        icon: Stethoscope,
        section: 'Müşteri',
        hint: 'Logo bağı olmayan, tekrar olasılığı olan, sahipsiz cari kayıtları ve izin çelişkileri; CRM\'de düzeltilecek listesi',
        keywords: ['veri sağlığı', 'veri kalitesi', 'tekrar kayıt', 'logo bağı', 'sahipsiz', 'ortak hesap', 'izin', 'kvkk', 'iys'],
      },
      {
        id: 'kurumsal-satis',
        label: 'Kurumsal ve B2B',
        to: '/kurumsal-satis',
        icon: Building2,
        section: 'Kurumsal',
        hint: 'Kurum fırsatları, tema paketi ve teklif, dönemsel hatırlatma, sipariş vermeyen bayiler',
        keywords: ['kurumsal satış', 'teklif', 'fırsat', 'paket', 'kurum', 'b2b', 'bayi', 'hediye kitap', 'hatırlatma', 'kitapsiparis'],
      },
      {
        id: 'ihale',
        label: 'İhale takibi',
        to: '/ihale',
        icon: Gavel,
        section: 'Kurumsal',
        hint: 'Okul, kütüphane ve kamu ihaleleri: şartname–katalog eşleştirme, teklif tablosu, belge ve karar takibi',
        keywords: ['ihale', 'ekap', 'şartname', 'teklif', 'kamu', 'okul', 'kütüphane', 'belediye', 'milli eğitim', 'teminat', 'doğrudan temin'],
      },
    ],
  },
  {
    id: 'pazarlama',
    label: 'Pazarlama',
    hint: 'Plan, içerik, SEO & GEO, set ve hediye',
    icon: Megaphone,
    items: [
      // M18: ay planı bölümün ilk öğesi; föy sayfası saha temsilcisine de açık (telefon alt menüsünde görünür).
      { id: 'pazarlama-aylik', label: 'Aylık plan', to: '/pazarlama/aylik-plan', icon: CalendarClock, section: 'Planlama', hint: 'Ayın yeni kitap, backlist, özel gün ve B2B kampanyası takvimi; çakışmalar ve bütçe dağılımı', keywords: ['aylık plan', 'pazarlama takvimi', 'backlist', 'özel gün', 'kampanya', 'çakışma', 'bütçe'] },
      { id: 'pazarlama-foy', label: 'Satış föyleri', to: '/pazarlama/foy', icon: FileText, section: 'Planlama', hint: 'Yeni kitapların tek sayfalık satış föyü: fiyat, barkod, hedef kitle, neden satılır; aylık paket', keywords: ['föy', 'tanıtım', 'satış'] },
      // Plan ekranı (/pazarlama/plan/:id) menüde yok; açıkken «Yeni kitap planı» etkin görünür.
      { id: 'pazarlama-yeni-kitap', label: 'Yeni kitap planı', to: '/pazarlama/yeni-kitap', icon: ClipboardList, section: 'Planlama', hint: 'Yayına hazırlanan kitapların pazarlama planı, bütçe, takvim ve materyalleri', also: ['/pazarlama/plan'], keywords: ['pazarlama planı', 'yeni kitap', 'lansman', 'föy', 'basın bülteni', 'emsal', 'bütçe'] },
      {
        id: 'pazarlama-set-hediye',
        label: 'Set ve hediye',
        to: '/pazarlama/set-hediye',
        icon: Gift,
        section: 'Üretim',
        hint: 'Setler (satış, stok, marj), set önerisi, açılacak kart listesi, kurumsal hediye teklifi, promosyon ürünleri',
        keywords: ['set', 'hediye', 'promosyon', 'kurumsal hediye', 'ajanda', 'defter', 'toplama set', 'birlikte alınan'],
      },
      { id: 'pazarlama-icerik', label: 'Görsel ve metin', to: '/pazarlama/icerik', icon: Palette, section: 'Üretim', hint: 'Sosyal medya, reklam ve site görselleri; Zeki AI metin varyantları, onay ve arşiv', keywords: ['görsel', 'banner', 'sosyal medya', 'reklam metni', 'hashtag', 'video senaryosu', 'influencer'] },
      // H2 Okuyucu veri tabanı: kart (/okurlar/kisi/:id), segmentler, yüklemeler aynı öğenin altında.
      { id: 'okurlar', label: 'Okurlar', to: '/okurlar', icon: Contact, section: 'Okur ve müşteri', hint: 'Tekil okur, izinler ve segmentler', keywords: ['okur', 'müşteri', 'segment', 'izin', 'iys', 'kvkk', 'bülten listesi', 'etkinlik katılımcı', 'fuar listesi', 'kopya kayıt'] },
      // M37 Okur topluluğu: yalnız sayı (kişi adı yok). H2 «Okurlar» öğesi aynı bölüme eklenir.
      { id: 'okur-toplulugu', label: 'Okur kitlesi', to: '/okur-toplulugu', icon: UsersRound, section: 'Okur ve müşteri', hint: 'Okur kaynağı, KVKK ve İYS izin sağlığı, yaklaşan programlar (yalnız sayı)', keywords: ['okur', 'topluluk', 'kvkk', 'iys', 'izin', 'kitle', 'e-bülten'] },
      { id: 'okur-segmentler', label: 'Okur segmentleri', to: '/okur-toplulugu/segmentler', icon: SlidersHorizontal, section: 'Okur ve müşteri', hint: 'Segment kuralı, büyüklük, amaç ve KVKK onayı', keywords: ['segment', 'hedef kitle', 'kvkk onayı', 'ilgi alanı'] },
      { id: 'okur-programlar', label: 'Topluluk programları', to: '/okur-toplulugu/programlar', icon: CalendarHeart, section: 'Okur ve müşteri', hint: 'Okuma kulübü, imza günü, anket takvimi ve geçmiş etkinlikler', keywords: ['okuma kulübü', 'imza günü', 'etkinlik', 'anket', 'duyuru'] },
      { id: 'okur-yorumlar', label: 'Yorum cevapları', to: '/okur-toplulugu/yorumlar', icon: MessageSquareReply, section: 'Okur ve müşteri', hint: 'Cevapsız okur yorumları ve Zeki AI cevap taslağı', keywords: ['yorum', 'cevap', 'okur yorumu', 'puan'] },
      // Lansman ekranı (/pazarlama/lansman/:id) alt yol olarak «Lansman» öğesini etkin gösterir.
      { id: 'pazarlama-lansman', label: 'Lansman', to: '/pazarlama/lansman', icon: Rocket, section: 'Planlama', hint: 'Yayın haftası ve ilk ay: kontrol listesi, sipariş ve satış izleme, stok uyarısı, D+7 ve D+30 raporu', keywords: ['lansman', 'yayın günü', 'yayın ayı', 'ilk hafta', 'imza günü', 'etkinlik', 'medya yansıması', 'stok uyarısı'] },
      { id: 'pazarlama-backlist', label: 'Backlist', to: '/pazarlama/backlist', icon: History, section: 'Planlama', hint: 'Uyuyan backlist kitapların fırsat sıralaması, özel gün gündemi, aktivasyon planı ve kampanya etkisi', keywords: ['uyuyan', 'eski kitap', 'kampanya', 'özel gün'] },
      { id: 'basin-iliskileri', label: 'Basın ilişkileri', to: '/basin-iliskileri', icon: Megaphone, section: 'İletişim', hint: 'Bülten, medya kişileri ve yansımalar', keywords: ['basın', 'pr', 'halkla ilişkiler', 'gazeteci', 'bülten', 'yansıma', 'medya kiti', 'röportaj'] },
      { id: 'reklam', label: 'Reklam', to: '/reklam', icon: BadgeDollarSign, section: 'Kampanya', hint: 'Harcama, getiri ve bütçe', keywords: ['reklam', 'dijital pazarlama', 'google ads', 'meta', 'instagram', 'tiktok', 'harcama', 'roas', 'tbm', 'kampanya', 'brief'] },
      // M22: gönderi, fırsat, rapor ve hesap ekranları /sosyal-medya altında; hepsinde «Sosyal medya» etkin görünür.
      { id: 'sosyal-medya', label: 'Sosyal medya', to: '/sosyal-medya', icon: Share2, section: 'İletişim', hint: 'Takvim, onay ve performans', keywords: ['sosyal medya', 'instagram', 'paylaşım', 'takvim', 'gönderi', 'hashtag', 'özel gün', 'içgörü'] },
      // M23: kişi kartı, aday listesi, rapor ve ödemeler /isbirlikleri/* altında; menüde tek öğe.
      { id: 'isbirlikleri', label: 'İşbirlikleri', to: '/isbirlikleri', icon: Handshake, section: 'İletişim', hint: 'İçerik üreticileri, gönderim ve sonuç', keywords: ['influencer', 'içerik üreticisi', 'bookstagram', 'booktube', 'booktok', 'işbirliği', 'brief', 'hediye kitap', 'cpe', 'etkileşim'] },
      { id: 'katalog-bulten', label: 'Katalog ve bülten', to: '/katalog-bulten', icon: BookOpen, section: 'Kampanya', hint: 'Dönemsel katalog ve e-bülten', keywords: ['katalog', 'bülten', 'e-bülten', 'newsletter', 'segment', 'konu satırı', 'bayi kataloğu', 'tasarım paketi', 'iys'] },
      { id: 'etkinlikler', label: 'Fuar ve etkinlik', to: '/etkinlikler', icon: CalendarRange, section: 'Etkinlik', hint: 'Fuar, imza günü, söyleşi ve ödüller', keywords: ['fuar', 'tüyap', 'imza günü', 'söyleşi', 'etkinlik', 'ödül', 'stant', 'fuar sonucu', 'ajanda'] },
      // M28: kişi kartı, kurumlar, hediye programı, projeler ve rapor alt adresleri (/kurumsal-iliskiler/…) bu öğenin altında.
      { id: 'kurumsal-iliskiler', label: 'Kurumsal ilişkiler', to: '/kurumsal-iliskiler', icon: Landmark, section: 'İlişkiler', hint: 'Kanaat önderleri, kurumlar ve kamu projeleri', keywords: ['kanaat önderi', 'hediye kitap', 'kamu projesi', 'belediye', 'milli eğitim', 'kütüphane bağışı', 'okuma kampanyası', 'akademisyen', 'teklif dosyası'] },
      { id: 'seo-geo', label: 'SEO özeti', to: '/seo-geo', icon: Gauge, section: 'İzleme', hint: 'Arama ve yapay zekâ görünürlüğü özeti', keywords: ['seo', 'geo', 'genel bakış'] },
      { id: 'seo-arama', label: 'Arama ve kelimeler', to: '/seo-geo/anahtar-kelimeler', icon: Search, section: 'İzleme', hint: 'Google arama sorguları', keywords: ['anahtar kelime', 'google'] },
      { id: 'seo-firsat', label: 'Fırsatlar ve etki', to: '/seo-geo/firsatlar', icon: TrendingUp, section: 'İzleme', hint: 'Yakın sıradaki sorgular ve onaylanan değişikliğin etkisi', keywords: ['fırsat', 'etki', 'tıklama', 'sıra'] },
      { id: 'seo-bing', label: 'Bing ve IndexNow', to: '/seo-geo/bing', icon: Radar, section: 'İzleme', hint: 'Bing arama verisi ve değişen sayfaların bildirimi', keywords: ['bing', 'indexnow', 'chatgpt'] },
      { id: 'seo-rakip', label: 'Rakipler', to: '/seo-geo/rakipler', icon: Swords, section: 'İzleme', hint: 'Aynı kitap aramasında rakip sitelerin Google sırası', keywords: ['rakip', 'd&r', 'kitapyurdu'] },
      { id: 'seo-izleme', label: 'İzleme ve rapor', to: '/seo-geo/izleme', icon: BellRing, section: 'İzleme', hint: 'Tıklama düşüşü, 404, robots ve yapay zekâ uyarıları; haftalık rapor', keywords: ['uyarı', 'rapor', 'izleme'] },
      { id: 'seo-kaynak', label: 'Yapay zekânın kaynakları', to: '/seo-geo/kaynaklar', icon: Quote, section: 'İzleme', hint: 'Yapay zekâ cevaplarında kaynak gösterilen siteler ve hedef listesi', keywords: ['kaynak', 'pr', 'atıf'] },
      { id: 'seo-yarisan', label: 'Yarışan sayfalar', to: '/seo-geo/yarisan', icon: Split, section: 'İzleme', hint: 'Aynı aramada birbirinin sırasını düşüren sayfalar', keywords: ['yarışan', 'kannibalizasyon'] },
      { id: 'seo-tarama', label: 'Google taraması', to: '/seo-geo/google-taramasi', icon: ScanSearch, section: 'İzleme', hint: 'Googlebot’un son taraması, dizin durumu ve bot istekleri', keywords: ['googlebot', 'dizin', 'tarama', 'bot'] },
      { id: 'seo-geri-baglanti', label: 'Gelen bağlantılar', to: '/seo-geo/geri-baglantilar', icon: Link2, section: 'İzleme', hint: 'Timaş’a bağlantı veren siteler', keywords: ['backlink', 'bağlantı'] },
      { id: 'seo-eslesme', label: 'Sorgu–sayfa eşlemesi', to: '/seo-geo/sorgu-sayfa', icon: Target, section: 'İzleme', hint: 'Her önemli arama için hedef sayfa ve boşluklar', keywords: ['eşleme', 'hedef sayfa', 'boşluk'] },
      { id: 'seo-soru', label: 'Soru önerileri', to: '/seo-geo/soru-onerileri', icon: Lightbulb, section: 'İzleme', hint: 'Yapay zekâ ölçümü için okur sorusu adayları', keywords: ['soru', 'geo', 'öneri'] },
      { id: 'seo-youtube', label: 'YouTube', to: '/seo-geo/youtube', icon: Youtube, section: 'İzleme', hint: 'Tanıtım videolarının izlenmesi ve açıklamadaki site bağlantısı', keywords: ['youtube', 'video'] },
      { id: 'seo-aylik', label: 'Aylık rapor', to: '/seo-geo/aylik-rapor', icon: FileBarChart, section: 'İzleme', hint: 'Yönetim için aylık SEO/GEO raporu (PDF)', keywords: ['aylık', 'rapor', 'pdf'] },
      { id: 'seo-ai', label: 'Yapay zekâ görünürlüğü', to: '/seo-geo/ai-gorunurluk', icon: Sparkles, section: 'İzleme', hint: 'Yapay zekâ cevaplarında Timaş', keywords: ['ai görünürlük', 'geo'] },
      { id: 'seo-sayfalar', label: 'Yazar ve kategori', to: '/seo-geo/sayfalar', icon: BookUser, section: 'İş', hint: 'Yazar ve kategori sayfaları', keywords: ['sayfa'] },
      { id: 'seo-yonlendirme', label: 'Yönlendirmeler', to: '/seo-geo/yonlendirmeler', icon: CornerDownRight, section: 'İş', hint: 'Kırık adres yönlendirmeleri', keywords: ['301', 'yönlendirme'] },
      { id: 'seo-teknik', label: 'Teknik sağlık', to: '/seo-geo/teknik', icon: Stethoscope, section: 'İş', hint: 'Canonical, yönlendirme, sitemap, yapay zekâ botları, görsel ve hız', keywords: ['teknik', 'hız', 'sitemap', 'robots', 'core web vitals'] },
      { id: 'seo-kimlik', label: 'Kimlik ve bilgi paneli', to: '/seo-geo/kimlik', icon: BadgeCheck, section: 'İş', hint: 'Wikidata, kurum şeması, Google Kitaplar hazırlığı', keywords: ['wikidata', 'bilgi paneli', 'google kitaplar'] },
      { id: 'seo-rehber', label: 'Rehber içerikler', to: '/seo-geo/rehberler', icon: Library, section: 'İş', hint: 'Okur sorularına cevap veren liste ve rehber taslakları', keywords: ['rehber', 'liste', 'içerik'] },
      { id: 'seo-takvim', label: 'Sezon takvimi', to: '/seo-geo/takvim', icon: CalendarDays, section: 'İş', hint: 'Özel günler, geçen yılın arama artışı ve kitap hazırlığı', keywords: ['özel gün', 'sezon', 'takvim'] },
      { id: 'seo-ic-baglanti', label: 'Site içi bağlantılar', to: '/seo-geo/ic-baglantilar', icon: Network, section: 'İş', hint: 'Bağlantı almayan kitaplar, derinlik ve yazar–kitap bağları', keywords: ['iç bağlantı', 'yetim sayfa'] },
      { id: 'seo-yorum', label: 'Okur yorumları', to: '/seo-geo/yorumlar', icon: MessageSquareText, section: 'İş', hint: 'Yorumsuz çok satanlar ve puan şeması', keywords: ['yorum', 'puan'] },
      { id: 'seo-video', label: 'Video', to: '/seo-geo/video', icon: Video, section: 'İş', hint: 'Tanıtım videoları, video şeması ve video sitemap', keywords: ['video', 'youtube'] },
      { id: 'seo-kalkan', label: 'Satıştan kalkan kitaplar', to: '/seo-geo/satistan-kalkan', icon: Archive, section: 'İş', hint: 'Baskısı biten ya da hakkı bizde olmayan kitap sayfaları ne olmalı', keywords: ['baskısı bitti', '410', '301'] },
      { id: 'seo-yazar-sayfa', label: 'Yazar sayfaları', to: '/seo-geo/yazar-sayfalari', icon: UserRoundCheck, section: 'İş', hint: 'Yazar sayfalarında biyografi, kimlik ve güven sinyalleri', keywords: ['yazar', 'biyografi', 'eeat'] },
      { id: 'seo-isler', label: 'İş listesi', to: '/seo-geo/is-listesi', icon: ListChecks, section: 'İş', hint: 'Bütün SEO ekranlarının yapılacakları tek sırada; kim yapacak, etkisi ne', keywords: ['iş listesi', 'yapılacaklar', 'görev'] },
      { id: 'seo-karne', label: 'Kitap karnesi', to: '/seo-geo/kitap', icon: NotebookTabs, section: 'İş', hint: 'Bir kitabın bütün SEO durumu tek sayfada', keywords: ['kitap', 'karne', 'durum'] },
      { id: 'seo-biyografi', label: 'Yazar biyografileri', to: '/seo-geo/yazar-biyografi', icon: UserPen, section: 'İş', hint: 'CRM özgeçmişinden yazar sayfası biyografisi taslakları', keywords: ['biyografi', 'özgeçmiş', 'yazar'] },
      { id: 'seo-sss', label: 'Kitap soru–cevapları', to: '/seo-geo/sss', icon: MessageCircleQuestion, section: 'İş', hint: 'Kitap sayfası için soru–cevap taslakları', keywords: ['sss', 'soru cevap', 'faq'] },
      { id: 'seo-benzer', label: 'Benzer kitaplar', to: '/seo-geo/benzer-kitaplar', icon: BookCopy, section: 'İş', hint: 'CRM emsal kitaplarından site içi bağlantı önerileri', keywords: ['benzer', 'emsal', 'ilgili ürün'] },
      { id: 'seo-alisveris', label: 'Google Alışveriş hazırlığı', to: '/seo-geo/alisveris', icon: ShoppingBag, section: 'İş', hint: 'Ürün akışı denetimi: ISBN, fiyat, stok, görsel', keywords: ['alışveriş', 'merchant', 'gtin'] },
      { id: 'seo-sema', label: 'Şema denetimi', to: '/seo-geo/sema', icon: Braces, section: 'İş', hint: 'Ürün sayfalarının yapısal verisi', keywords: ['şema'] },
      { id: 'seo-llms', label: 'Yapay zekâ tarama dosyası', to: '/seo-geo/llms', icon: FileText, section: 'İş', hint: 'Yapay zekâ motorlarına siteyi anlatan dosya', keywords: ['llms.txt', 'llms'] },
      { id: 'seo-crm', label: 'Haklar ve CRM', to: '/seo-geo/crm-haklar', icon: ShieldCheck, section: 'İş', hint: 'Kitabın CRM kartı, internette gösterim hakkı ve yayın durumu', keywords: ['telif', 'hak', 'crm', 'sözleşme', 'google kitaplar'] },
      { id: 'seo-urun', label: 'Ürün denetimi', to: '/seo-geo/urun-denetimi', icon: ClipboardCheck, section: 'İş', hint: 'Ürün açıklaması ve başlık önerileri', keywords: ['ürün'] },
      { id: 'seo-gecmis', label: 'Karar geçmişi', to: '/seo-geo/gecmis', icon: History, section: 'İş', hint: 'Onaylanan ve reddedilen öneriler', keywords: ['geçmiş'] },
      { id: 'seo-baglanti', label: 'Bağlantılar', to: '/seo-geo/baglantilar', icon: Plug, section: 'Ayar', hint: 'Site ve arama hesabı bağlantıları', keywords: ['bağlantı'] },
    ],
  },
  {
    // Altyapı ve destek (M48–M51): yönetici alanı değil, sayfa yetkisiyle açılır; BT personeli yönetici olmayabilir.
    id: 'altyapi',
    label: 'Altyapı ve destek',
    hint: 'Sistem durumu, veri güvenliği, müşteri hizmetleri ve Zeki AI kalitesi',
    icon: Server,
    items: [
      {
        id: 'sistem-durumu',
        label: 'Sistem durumu',
        to: '/sistem-durumu',
        icon: Activity,
        hint: 'Logo, CRM, giriş, Zeki AI, e-posta ve ağ bağlantısının durumu; olaylar ve zamanlanmış işler',
        keywords: ['bt', 'altyapı', 'kesinti', 'bağlantı', 'olay', 'veri sonu', 'sürüm', 'zamanlanmış iş'],
      },
      {
        id: 'veri-guvenligi',
        label: 'Veri güvenliği',
        to: '/veri-guvenligi',
        icon: LockKeyhole,
        hint: 'Giriş ve erişim kaydı, güvenlik uyarıları, hesap hijyeni, kişisel veri envanteri ve saklama süreleri',
        keywords: ['güvenlik', 'kvkk', 'giriş kaydı', 'oturum', 'erişim', 'dışa aktarma', 'kişisel veri', 'saklama', 'hesap', 'denetim izi'],
      },
      {
        id: 'musteri-destek',
        label: 'Müşteri hizmetleri',
        to: '/musteri-destek',
        icon: Headset,
        hint: 'Talep kuyruğu ve SLA, müşteri bağlamı (sipariş, kargo, fatura), bayi görünümü, konu eğilimi ve SSS açıkları',
        keywords: ['destek', 'talep', 'şikâyet', 'sla', 'kargo takip', 'sipariş durumu', 'müşteri', 'okur', 'bayi', 'sss', 'memnuniyet', 'csat'],
      },
      {
        id: 'zeki-kalite',
        label: 'Zeki AI kalitesi',
        to: '/zeki-kalite',
        icon: BadgeCheck,
        hint: 'Zeki AI karnesi, kalite koşuları ve bozulan sorular, hata sınıfları, kullanıcı geri bildirimi, sürümler',
        keywords: ['zeki', 'kalite', 'karne', 'doğruluk', 'geri bildirim', 'yanlış cevap', 'test seti', 'sürüm', 'model'],
      },
    ],

    // İnsan Kaynakları (M55–M58; İK-0 ortak kayıtlar). Sayfaları açıkça verilir, «Herkes» rolüne girmez.
    id: 'ik',
    label: 'İnsan Kaynakları',
    hint: 'İşe alım, pozisyonlar, İK belgeleri ve KVKK kayıtları',
    icon: Contact,
    explicit: true,
    items: [
      { id: 'ik-ise-alim', label: 'İşe alım panosu', to: '/ik/ise-alim', icon: ClipboardList, section: 'İşe alım', hint: 'Başvurular aşamalarıyla, aday kartı, kanıtlı özgeçmiş özeti ve mülakat notları', keywords: ['aday', 'başvuru', 'özgeçmiş', 'cv', 'mülakat', 'işe alım', 'ik'] },
      { id: 'ik-pozisyonlar', label: 'Pozisyonlar', to: '/ik/pozisyonlar', icon: BriefcaseBusiness, section: 'İşe alım', hint: 'Pozisyon kartı, yetkinlikler, ilan taslağı, mülakat soru seti ve onay', keywords: ['kadro', 'ilan', 'yetkinlik', 'pozisyon'] },
      { id: 'ik-belgeler', label: 'Belgeler', to: '/ik/belgeler', icon: FileText, section: 'İşe alım', hint: 'İlan, davet, teklif, ret ve «başvurunuz alındı» şablonları', keywords: ['şablon', 'teklif mektubu', 'ret mektubu'] },
      { id: 'ik-kayitlar', label: 'Çalışan ve KVKK kayıtları', to: '/ik/kayitlar', icon: ShieldCheck, section: 'Temel', hint: 'Çalışan ve birim kaydı, aydınlatma metni, açık rıza, saklama süresi, imha tutanağı, erişim kaydı', keywords: ['kvkk', 'çalışan', 'birim', 'rıza', 'imha', 'saklama'] },
    ],

    // M40–M42 ortak çalışma alanı (pazar yerleri ve D2C); ilk açan M42 «Kanallar». M40 Trendyol ve M41 Amazon kendi bölümleriyle eklenir.
    id: 'platform',
    label: 'Platform',
    hint: 'Pazar yerleri, D2C ve kanal kârlılığı',
    icon: Store,
    items: [
      { id: 'kanallar', label: 'Kanal karnesi', to: '/kanallar', icon: Store, section: 'Kanallar', hint: 'Pazar yerleri ve timas.com.tr: kanala satış, iskonto, iade, marj ve hedef gerçekleşmesi; kanal detayı ve iskonto simülasyonu', keywords: ['kanal', 'pazar yeri', 'hepsiburada', 'kitapyurdu', 'd&r', 'idefix', 'amazon', 'trendyol', 'e-ticaret', 'iskonto', 'iade', 'marj', 'kârlılık', 'karne'] },
      { id: 'kanal-matris', label: 'Kitap × kanal', to: '/kanallar/matris', icon: Grid3x3, section: 'Kanallar', hint: 'Hangi kanal hangi kitabı alıyor, hangisi iade ediyor', keywords: ['matris', 'kitap kanal', 'alım', 'iade'] },
      { id: 'kanal-d2c', label: 'D2C büyüme', to: '/kanallar/d2c', icon: Globe, section: 'Kanallar', hint: 'timas.com.tr payı, sitede güçlü kitaplar ve D2C\'ye özel set önerisi', keywords: ['d2c', 'site', 'timas.com.tr', 'sadakat', 'set'] },
      { id: 'kanal-eslesme', label: 'Cari eşleme', to: '/kanallar/eslesme', icon: Link2, section: 'Kanallar', hint: 'Logo carisi, kanal kodu ve CRM hedef bölgesi ↔ platform', keywords: ['eşleme', 'cari', 'platform', 'bölge'] },
    ],
  },
  {
    id: 'yonetim',
    label: 'Yönetim',
    hint: 'Yalnız yöneticiler',
    icon: Settings,
    adminOnly: true,
    items: [
      { id: 'veri-sozlugu', label: 'Veri sözlüğü', to: '/veri-sozlugu', icon: BookA, hint: 'Ölçüler, alanlar ve tanımlar', adminOnly: true, keywords: ['katalog', 'sözlük'] },
      { id: 'onaylar', label: 'Onaylar', to: '/onaylar', icon: ShieldCheck, hint: 'Terim inceleme ve onay', adminOnly: true, keywords: ['onay', 'inceleme'] },
      { id: 'es-anlamlilar', label: 'Eş anlamlılar', to: '/es-anlamlilar', icon: ArrowLeftRight, hint: 'Alan adlarının gündelik karşılıkları', adminOnly: true, keywords: ['eş anlam', 'kelime'] },
      { id: 'portal-ayarlari', label: 'Portal ayarları', to: '/yonetim', icon: SlidersHorizontal, hint: 'Bağlantılar, yetki ve bildirim ayarları', adminOnly: true, keywords: ['yönetim', 'ayar', 'yetki'] },
    ],
  },
];

/* ------------------------------------------------------------------ görünürlük ve rol */

export type NavRole = { isAdmin: boolean; isEditor: boolean };
export type NavFlags = Partial<Record<NavFeature, boolean>>;

export type VisibleGroup = NavGroup & {
  /** «Çalışma alanım» gibi grup etiketi (editör rolünde Editoryal). */
  tag?: string;
  /** Gruplu listede (telefon menüsü, Kampüs paneli) varsayılan açık mı. Kişinin kendi seçimi bunu ezer. */
  defaultOpen: boolean;
};

/** Menü öğesi rolle açılan bir sayfa mı: Kampüs herkese, Yönetim yöneticiye açık; geri kalanı `sayfa:<id>` yetkisi ister. */
export const needsPagePermission = (group: NavGroup, item: NavItem) => group.id !== 'kampus' && !group.adminOnly && !item.adminOnly;

/** Kişinin göreceği menü: yetki ve ortam bayrağına göre süzülmüş, role göre sıralanmış.
 *  Yönetici her şeyi + Yönetim grubunu görür. Editör AD grubundaki kişi (yönetici değilse) Editoryal'i en
 *  üstte «Çalışma alanım» etiketiyle ve Kayıtlar'la açık görür; Analiz, Finans ve Pazarlama daraltılmış
 *  gelir (gizlenmez). Ortamda kapalı özellik (bayrak false ya da henüz bilinmiyor) hiç görünmez. */
export function visibleNav(
  role: NavRole,
  flags: NavFlags = {},
  pages: 'all' | ReadonlySet<string> | null = 'all',
): VisibleGroup[] {
  // pages: kişinin görebildiği `sayfa:<id>` anahtarları (köprü karar verir); null = henüz bilinmiyor → rol sayfaları gizli.
  // Açıkça verilen grup (İK) «bütün sayfalar» ile yalnız yöneticide açılır: köprü yanıtı okunamayınca ('all') herkese görünmez.
  const allowed = (g: NavGroup, i: NavItem) =>
    !needsPagePermission(g, i) ||
    (pages === 'all' ? !g.explicit || role.isAdmin : pages !== null && pages.has(`sayfa:${i.id}`));
  const keep = (g: NavGroup) => (i: NavItem) =>
    (!i.adminOnly || role.isAdmin) && (!i.feature || flags[i.feature] === true) && allowed(g, i);
  const groups = NAV.filter((g) => !g.adminOnly || role.isAdmin)
    .map((g) => ({ ...g, items: g.items.filter(keep(g)), defaultOpen: true } as VisibleGroup))
    .filter((g) => g.items.length > 0);
  if (!role.isEditor || role.isAdmin) return groups;
  const order: NavGroupId[] = ['kampus', 'editoryal', 'kayitlar', 'analiz', 'finans', 'satis', 'pazarlama', 'altyapi'];
  const closed = new Set<NavGroupId>(['analiz', 'finans', 'satis', 'pazarlama', 'altyapi']);
  const order: NavGroupId[] = ['kampus', 'editoryal', 'kayitlar', 'analiz', 'finans', 'satis', 'pazarlama', 'ik'];
  const closed = new Set<NavGroupId>(['analiz', 'finans', 'satis', 'pazarlama', 'ik']);
  const order: NavGroupId[] = ['kampus', 'editoryal', 'kayitlar', 'analiz', 'finans', 'satis', 'pazarlama', 'platform'];
  const closed = new Set<NavGroupId>(['analiz', 'finans', 'satis', 'pazarlama', 'platform']);
  return order
    .map((id) => groups.find((g) => g.id === id))
    .filter((g): g is VisibleGroup => !!g)
    .map((g) => ({ ...g, defaultOpen: !closed.has(g.id), tag: g.id === 'editoryal' ? 'Çalışma alanım' : undefined }));
}

/** Kişinin çalışma alanı: editörde Editoryal, diğerlerinde Analiz (telefon menüsünün ilk seçimi). */
export function homeGroup(role: NavRole): NavGroupId {
  return role.isEditor && !role.isAdmin ? 'editoryal' : 'analiz';
}

/* ------------------------------------------------------------------ etkin öğe */

const splitTo = (to: string): [string, URLSearchParams] => {
  const i = to.indexOf('?');
  return i < 0 ? [to, new URLSearchParams()] : [to.slice(0, i), new URLSearchParams(to.slice(i + 1))];
};

const underPath = (path: string, base: string) => (base === '/' ? path === '/' : path === base || path.startsWith(base + '/'));

/** Adres için etkin menü öğesi: en uzun eşleşen yol kazanır; sorgu parametresi de tutan öğe (ör. «Çevirmenler»
 *  = /kisiler?rol=cevirmen) yalın yoldan (Kişiler) önce gelir. Alt rotalar (`/kitap-tasarim/:iş/kapak`) ve
 *  `also` önekleri de sayılır. Hiçbir öğe tutmazsa null (menü etkinsiz kalır, sayfa yine açılır). */
export function matchActive(groups: NavGroup[], pathname: string, search = ''): { group: NavGroup; item: NavItem } | null {
  const path = pathname.replace(/\/+$/, '') || '/';
  const params = new URLSearchParams(search);
  let best: { group: NavGroup; item: NavItem; score: number } | null = null;
  for (const group of groups) {
    for (const item of group.items) {
      const [base, want] = splitTo(item.to);
      const bases = [base, ...(item.also ?? [])];
      let pathScore = -1;
      for (const b of bases) if (underPath(path, b)) pathScore = Math.max(pathScore, b === base ? b.length : b.length - 0.5);
      if (pathScore < 0) continue;
      let qScore = 0;
      let ok = true;
      want.forEach((v, k) => {
        if (params.get(k) === v) qScore += 1000;
        else ok = false;
      });
      if (!ok) continue;
      const score = pathScore + qScore;
      if (!best || score > best.score) best = { group, item, score };
    }
  }
  return best ? { group: best.group, item: best.item } : null;
}

/** Bir bağlantı adresinin (sorgu parçası dahil) rolle açılan menü sayfası; Kampüs, Yönetim ve menü dışı adreste null. */
export function permissionItemFor(to: string): NavItem | null {
  const [path, params] = splitTo(to);
  const hit = matchActive(NAV, path, params.toString());
  return hit && needsPagePermission(hit.group, hit.item) ? hit.item : null;
}

/** Arama/filtre için Türkçe harfleri sadeleştirir: «Çeviri» ≈ «ceviri», «İ/ı» ≈ «i». */
export const trFold = (s: string) =>
  s
    .toLocaleLowerCase('tr')
    .replace(/ı/g, 'i')
    .replace(/\u0307/g, '')
    .replace(/ş/g, 's')
    .replace(/ğ/g, 'g')
    .replace(/ü/g, 'u')
    .replace(/ö/g, 'o')
    .replace(/ç/g, 'c')
    .replace(/â/g, 'a')
    .replace(/î/g, 'i')
    .replace(/û/g, 'u');

/** Her sözcüğü metnin bir yerinde geçiyor mu; sıralama için ilk geçişin konumuna göre puan (0 = yok). */
export function scoreText(haystack: string, query: string): number {
  const h = trFold(haystack);
  const words = trFold(query).split(/\s+/).filter(Boolean);
  if (!words.length) return 1;
  let score = 1;
  for (const w of words) {
    const at = h.indexOf(w);
    if (at < 0) return 0;
    // Sözcük başında eşleşme daha değerli.
    score += at === 0 || /\s/.test(h[at - 1]) ? 2 : 1;
  }
  return score / (1 + h.length / 100);
}

/** Palete ve menü aramasına giren ekran listesi. */
export function flatItems(groups: VisibleGroup[]): Array<{ group: VisibleGroup; item: NavItem }> {
  return groups.flatMap((group) => group.items.map((item) => ({ group, item })));
}

