import {
  ArrowLeftRight,
  Bell,
  BookA,
  BookImage,
  BookOpen,
  BookUser,
  Braces,
  CalendarClock,
  ChartColumn,
  ClipboardCheck,
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
  LayoutGrid,
  Megaphone,
  Newspaper,
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
      { id: 'genel-bakis', label: 'Genel bakış', to: '/genel-bakis', icon: LayoutDashboard, hint: 'Finansal göstergeler ve Zeki AI\'a soru', keywords: ['ciro', 'soru', 'sor'] },
      { id: 'panolar', label: 'Panolar', to: '/panolar', icon: LayoutGrid, hint: 'Kişisel pano kartları', keywords: ['pano', 'panom', 'kart'] },
      { id: 'planli-raporlar', label: 'Planlı raporlar', to: '/planli-raporlar', icon: CalendarClock, hint: 'E-postayla giden zamanlı raporlar', keywords: ['rapor', 'excel'] },
      { id: 'uyarilar', label: 'Uyarılar', to: '/uyarilar', icon: Bell, hint: 'Eşik kuralları ve bildirimler', badge: 'alerts', keywords: ['uyarı', 'kural', 'eşik'] },
    ],
  },
  {
    id: 'finans',
    label: 'Finans',
    hint: 'Denetim ve yönetim raporları',
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
      { id: 'redaksiyon', label: 'Redaksiyon', to: '/redaksiyon', icon: PenLine, section: 'Yayına hazırlık', hint: 'Metin işleme ve üsluplandırma', keywords: ['redaksiyon', 'metin'] },
      { id: 'cevirmenler', label: 'Çevirmenler', to: '/kisiler?rol=cevirmen', icon: Languages, section: 'Yayına hazırlık', hint: 'Çevirmenler ve çevirdikleri kitaplar', keywords: ['çeviri', 'tercüme'] },
      { id: 'son-okuma', label: 'Son okuma', to: '/son-okuma', icon: SpellCheck, section: 'Yayına hazırlık', hint: 'Baskı öncesi son denetim', keywords: ['yazım', 'denetim', 'okuma'] },
      { id: 'kitap-tasarim', label: 'Kitap tasarım', to: '/kitap-tasarim', icon: BookImage, section: 'Yayına hazırlık', hint: 'Sayfa, kapak ve baskı provası', keywords: ['stüdyo', 'kapak', 'mizanpaj', 'resim'] },
    ],
  },
  {
    id: 'kayitlar',
    label: 'Kayıtlar',
    hint: 'Kişiler, sözleşmeler, atamalar',
    icon: BookUser,
    items: [
      { id: 'kisiler', label: 'Kişiler', to: '/kisiler', icon: Contact, hint: 'Yazar, çevirmen, çizer ve serbest çalışanlar', keywords: ['yazar', 'çizer', 'rehber'] },
      { id: 'basin-web', label: 'Basın ve web', to: '/basin-web', icon: Newspaper, hint: 'Açık kaynaklarda yazar ve kitap haberleri', feature: 'webWatch', keywords: ['haber', 'basın'] },
      { id: 'telif-sozlesme', label: 'Sözleşmeler', to: '/telif-sozlesme', icon: FileSignature, hint: 'Telif ve sözleşme kayıtları', keywords: ['telif', 'sözleşme'] },
      { id: 'editor-atama', label: 'Editör atama', to: '/editor-atama', icon: UserCog, hint: 'Editörler ve üstlendikleri projeler', keywords: ['editörler', 'atama'] },
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
      { id: 'seo-ai', label: 'Yapay zekâ görünürlüğü', to: '/seo-geo/ai-gorunurluk', icon: Sparkles, section: 'İzleme', hint: 'Yapay zekâ cevaplarında Timaş', keywords: ['ai görünürlük', 'geo'] },
      { id: 'seo-sayfalar', label: 'Yazar ve kategori', to: '/seo-geo/sayfalar', icon: BookUser, section: 'İş', hint: 'Yazar ve kategori sayfaları', keywords: ['sayfa'] },
      { id: 'seo-yonlendirme', label: 'Yönlendirmeler', to: '/seo-geo/yonlendirmeler', icon: CornerDownRight, section: 'İş', hint: 'Kırık adres yönlendirmeleri', keywords: ['301', 'yönlendirme'] },
      { id: 'seo-sema', label: 'Şema denetimi', to: '/seo-geo/sema', icon: Braces, section: 'İş', hint: 'Ürün sayfalarının yapısal verisi', keywords: ['şema'] },
      { id: 'seo-llms', label: 'Yapay zekâ tarama dosyası', to: '/seo-geo/llms', icon: FileText, section: 'İş', hint: 'Yapay zekâ motorlarına siteyi anlatan dosya', keywords: ['llms.txt', 'llms'] },
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

/** Kişinin göreceği menü: yetki ve ortam bayrağına göre süzülmüş, role göre sıralanmış.
 *  Yönetici her şeyi + Yönetim grubunu görür. Editör AD grubundaki kişi (yönetici değilse) Editoryal'i en
 *  üstte «Çalışma alanım» etiketiyle ve Kayıtlar'la açık görür; Analiz, Finans ve Pazarlama daraltılmış
 *  gelir (gizlenmez). Ortamda kapalı özellik (bayrak false ya da henüz bilinmiyor) hiç görünmez. */
export function visibleNav(role: NavRole, flags: NavFlags = {}): VisibleGroup[] {
  const keep = (i: NavItem) => (!i.adminOnly || role.isAdmin) && (!i.feature || flags[i.feature] === true);
  const groups = NAV.filter((g) => !g.adminOnly || role.isAdmin)
    .map((g) => ({ ...g, items: g.items.filter(keep), defaultOpen: true } as VisibleGroup))
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

