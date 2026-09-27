import {
  HeartHandshake,
  ArrowLeftRight,
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
  Stethoscope,
  TrendingUp,
  Swords,
  Target,
  Library,
  Radar,
  Bell,
  BookA,
  BookImage,
  BookOpen,
  BookPlus,
  BookUser,
  BriefcaseBusiness,
  Braces,
  CalendarClock,
  ChartColumn,
  ClipboardCheck,
  Factory,
  Contact,
  CornerDownRight,
  FileChartColumn,
  FileSignature,
  FileText,
  Gauge,
  History,
  House,
  Landmark,
  Languages,
  LayoutDashboard,
  ListChecks,
  LayoutGrid,
  Megaphone,
  Newspaper,
  NotebookPen,
  PenLine,
  Plug,
  Printer,
  Route,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  SpellCheck,
  UserCog,
  UserPen,
  UsersRound,
  type LucideIcon,
} from 'lucide-react';

/**
 * Portalın TEK menü tanımı. Masaüstü ray + bağlam paneli, telefon alt çubuğu + menü sayfası, ⌘K komut
 * paleti ve «Son açılanlar» hep buradan okur; menü her ekranda aynıdır. Yalnız koddaki gerçek rotalar
 * yazılır — menüde olmayan detay sayfaları (Kitap 360, yazar giriş projesi, stüdyo iş sayfaları) buraya
 * öğe olarak girmez, `also` ile en yakın menü öğesine bağlanır ki doğru öğe etkin görünsün.
 */

export type NavGroupId = 'kampus' | 'analiz' | 'finans' | 'editoryal' | 'kayitlar' | 'pazarlama' | 'yonetim';
export type NavFeature = 'webWatch';
export type NavBadge = 'alerts';

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
      { id: 'yazar-giris', label: 'Yazar giriş süreci', to: '/yazar-giris', icon: Route, section: 'Günlük', hint: 'Yeni kitap başvuruları ve projeler', keywords: ['başvuru', 'proje', 'dosya'] },
      { id: 'yayin-kurulu', label: 'Yayın kurulu', to: '/yayin-kurulu', icon: UsersRound, section: 'Günlük', hint: 'Kurul gündemi ve kararları', keywords: ['kurul', 'toplantı'] },
      { id: 'gorevlerim', label: 'Görevlerim', to: '/gorevlerim', icon: ListChecks, section: 'Günlük', hint: 'Size atanan editörlük işleri ve terminleri', keywords: ['görev', 'termin', 'pano', 'iş listesi'] },
      { id: 'redaksiyon', label: 'Redaksiyon', to: '/redaksiyon', icon: PenLine, section: 'Yayına hazırlık', hint: 'Metin işleme ve üsluplandırma', keywords: ['redaksiyon', 'metin'] },
      { id: 'ceviri', label: 'Çeviri', to: '/ceviri', icon: Languages, section: 'Yayına hazırlık', hint: 'Çeviri işleri, terim bankası ve kalite raporu', keywords: ['çeviri', 'tercüme', 'terim', 'segment', 'kalite'] },
      { id: 'ceviri-masam', label: 'Çeviri masam', to: '/ceviri/masam', icon: NotebookPen, section: 'Yayına hazırlık', hint: 'Çevirmenin ve inceleyenin kendi ekranı', keywords: ['çevirmen', 'segment', 'xliff'] },
      { id: 'cevirmenler', label: 'Çevirmenler', to: '/kisiler?rol=cevirmen', icon: UserPen, section: 'Yayına hazırlık', hint: 'CRM\'deki çevirmenler ve çevirdikleri kitaplar', keywords: ['tercüme', 'çevirmen'] },
      { id: 'son-okuma', label: 'Son okuma', to: '/son-okuma', icon: SpellCheck, section: 'Yayına hazırlık', hint: 'Baskı öncesi son denetim', keywords: ['yazım', 'denetim', 'okuma'] },
      { id: 'kitap-tasarim', label: 'Kitap tasarım', to: '/kitap-tasarim', icon: BookImage, section: 'Yayına hazırlık', hint: 'Sayfa, kapak ve baskı provası', keywords: ['stüdyo', 'kapak', 'mizanpaj', 'resim'] },
      { id: 'serbest-calisanlar', label: 'Serbest çalışanlar', to: '/serbest-calisanlar', icon: BriefcaseBusiness, section: 'Yayına hazırlık', hint: 'Çizer ve serbest çalışan havuzu, iş paketleri, kapasite, hakediş', keywords: ['çizer', 'freelancer', 'illüstratör', 'hakediş', 'iş paketi', 'kapasite'] },
      { id: 'uretim', label: 'Üretim yönetimi', to: '/uretim', icon: Factory, section: 'Üretim', hint: 'Baskı takvimi, matbaa takibi ve gecikmeler; depo girişi Logo\'dan', keywords: ['üretim', 'matbaa', 'baskı takvimi', 'depo girişi', 'gecikme', 'bandrol', 'baskı çıkışı'] },
    ],
  },
  {
    id: 'kayitlar',
    label: 'Kayıtlar',
    hint: 'Kişiler, sözleşmeler, atamalar',
    icon: BookUser,
    items: [
      { id: 'kisiler', label: 'Kişiler', to: '/kisiler', icon: Contact, hint: 'Yazar, çevirmen, çizer ve serbest çalışanlar', keywords: ['yazar', 'çizer', 'rehber'] },
      { id: 'yazar-iliskileri', label: 'Yazar ilişkileri', to: '/yazar-iliskileri', icon: HeartHandshake, hint: 'Yazar kartı, randevu ve görüşme notu, aday havuzu, ilişki ısısı', keywords: ['randevu', 'görüşme', 'aday', 'potansiyel yazar', 'ısı haritası'] },
      { id: 'basin-web', label: 'Basın ve web', to: '/basin-web', icon: Newspaper, hint: 'Açık kaynaklarda yazar ve kitap haberleri', feature: 'webWatch', keywords: ['haber', 'basın'] },
      { id: 'telif-sozlesme', label: 'Sözleşmeler', to: '/telif-sozlesme', icon: FileSignature, hint: 'Telif ve sözleşme kayıtları', keywords: ['telif', 'sözleşme'] },
      { id: 'editor-atama', label: 'Editör atama', to: '/editor-atama', icon: UserCog, hint: 'Atama, iş yükü, takvim ve kategori kuralları', keywords: ['editörler', 'atama', 'iş yükü', 'takvim', 'kural'] },
    ],
  },
  {
    id: 'pazarlama',
    label: 'Pazarlama',
    hint: 'SEO & GEO',
    icon: Megaphone,
    items: [
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
      { id: 'seo-sema', label: 'Şema denetimi', to: '/seo-geo/sema', icon: Braces, section: 'İş', hint: 'Ürün sayfalarının yapısal verisi', keywords: ['şema'] },
      { id: 'seo-llms', label: 'Yapay zekâ tarama dosyası', to: '/seo-geo/llms', icon: FileText, section: 'İş', hint: 'Yapay zekâ motorlarına siteyi anlatan dosya', keywords: ['llms.txt', 'llms'] },
      { id: 'seo-crm', label: 'Haklar ve CRM', to: '/seo-geo/crm-haklar', icon: ShieldCheck, section: 'İş', hint: 'Kitabın CRM kartı, internette gösterim hakkı ve yayın durumu', keywords: ['telif', 'hak', 'crm', 'sözleşme', 'google kitaplar'] },
      { id: 'seo-urun', label: 'Ürün denetimi', to: '/seo-geo/urun-denetimi', icon: ClipboardCheck, section: 'İş', hint: 'Ürün açıklaması ve başlık önerileri', keywords: ['ürün'] },
      { id: 'seo-gecmis', label: 'Karar geçmişi', to: '/seo-geo/gecmis', icon: History, section: 'İş', hint: 'Onaylanan ve reddedilen öneriler', keywords: ['geçmiş'] },
      { id: 'seo-baglanti', label: 'Bağlantılar', to: '/seo-geo/baglantilar', icon: Plug, section: 'Ayar', hint: 'Site ve arama hesabı bağlantıları', keywords: ['bağlantı'] },
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
  const allowed = (g: NavGroup, i: NavItem) =>
    !needsPagePermission(g, i) || pages === 'all' || (pages !== null && pages.has(`sayfa:${i.id}`));
  const keep = (g: NavGroup) => (i: NavItem) =>
    (!i.adminOnly || role.isAdmin) && (!i.feature || flags[i.feature] === true) && allowed(g, i);
  const groups = NAV.filter((g) => !g.adminOnly || role.isAdmin)
    .map((g) => ({ ...g, items: g.items.filter(keep(g)), defaultOpen: true } as VisibleGroup))
    .filter((g) => g.items.length > 0);
  if (!role.isEditor || role.isAdmin) return groups;
  const order: NavGroupId[] = ['kampus', 'editoryal', 'kayitlar', 'analiz', 'finans', 'pazarlama'];
  const closed = new Set<NavGroupId>(['analiz', 'finans', 'pazarlama']);
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

