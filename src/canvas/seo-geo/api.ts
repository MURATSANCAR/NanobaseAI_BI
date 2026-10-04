import { ENGINE_BASE, ENGINE_ENABLED, freshHeaders } from '../engine';
import type { Kaynaklar } from '../components/sqlInfo';

/** SEO & GEO modülünün köprü uçları: /api/v1/seo-geo/*. */

export type Severity = 'kritik' | 'yüksek' | 'orta' | 'düşük';
/** `field`: sorunu modelin düzelttiği alan; null ise elle çözülür (görsel, ISBN). */
export type Issue = { rule: string; severity: Severity; title: string; detail: string; why: string; weight: number; field: SeoField | null };
/** `gonderildi`/`hata`/`geri_alindi` eski kayıtlar içindir; T-soft'a yazma kapandı (2026-09-25). */
export type ProposalStatus = 'hazir' | 'onaylandi' | 'reddedildi' | 'gonderildi' | 'hata' | 'geri_alindi';
export const SEO_FIELDS = ['SeoTitle', 'SeoDescription', 'SearchKeywords', 'Details'] as const;
export type SeoField = (typeof SEO_FIELDS)[number];
export type Fields = Partial<Record<SeoField, string>>;

export type SyncState = { running: boolean; kind: string | null; done: number; total: number | null; startedAt: string | null; error: string | null };
export type SearchRow = { keys: string[]; clicks: number; impressions: number; ctr: number; position: number };
export type SearchReport = {
  start: string | null;
  end: string | null;
  savedAt: string | null;
  rows: SearchRow[];
  /** ZEKI-50: `kayit` = gece saklanan özet, `google` = seçilen aralık için şimdi okundu. */
  source?: 'kayit' | 'google' | null;
  /** Tarih seçicinin sınırları: en yeni kesin gün, Google'ın tuttuğu en eski gün, saklanan aralık. */
  bounds?: { latest: string; earliest: string; stored: { start: string; end: string; savedAt: string | null } | null };
  /** Aralık kırpıldıysa ya da karşılaştırma yapılamadıysa nedeni. */
  notes?: string[];
  compare?: { kind: SearchCompare; start: string; end: string; savedAt: string | null; source: 'kayit' | 'google'; rows: SearchRow[] };
};
export type SearchCompare = 'onceki' | 'gecen_yil';
export type SearchRange = { start?: string; end?: string; compare?: SearchCompare | '' };

export type Overview = {
  products: number;
  activeAverage: number | null;
  failing: number;
  failingThreshold: number;
  rules: Array<{ rule: string; title: string; severity: Severity; count: number }>;
  proposals: Partial<Record<ProposalStatus, number>>;
  approvedThisWeek: number;
  /** Puanı 70 altındaki en çok satan 10 kitap. */
  priority: Array<{ id: string; name: string; score: number; sales: number; views: number }>;
  /** Her zaman false: T-soft'a yazma yok. */
  tsoftWrite: false;
  lastSync: { startedAt: string; finishedAt: string | null; count: number | null; error: string | null } | null;
  sync: SyncState;
  batch: { running: boolean; done: number; failed: number; queue: number | null; startedAt: string | null; finishedAt: string | null; error: string | null };
  search: SearchReport | null;
  connections: { tsoft: boolean; google: boolean; serviceAccount: string | null; gscSite: string | null; ga4: boolean; merchant: boolean };
  crm: CrmSummary;
};

/** CRM hak kararı: bütün telif alış sözleşmelerinde internette gösterim hakkı var mı. Ön süzgeçtir; kesin söz telif biriminin. */
export type CrmRights = 'var' | 'incele' | 'eksik' | 'yok' | 'koruma_disi' | 'set' | 'kitap_degil';
export type CrmFlag = 'bizim_degil' | 'cekildi' | 'geri_istendi' | 'devredildi' | 'iptal';
export type CrmContract = {
  name: string | null;
  parties: string[];
  inForce: boolean;
  ends: string | null;
  openEnded: boolean;
  internet: boolean;
  ebook: boolean;
  zbook: boolean;
  audiobook: boolean;
  publicDomain: boolean;
  note: string | null;
};
export type CrmBook = {
  ean: string;
  bookId: string;
  name: string | null;
  rights: CrmRights;
  rightsWhy: string;
  statusLabel: string | null;
  statusFlag: CrmFlag | null;
  kind: string | null;
  tsoftActive: boolean;
  isbn: string | null;
  ebookIsbn: string | null;
  originalTitle: string | null;
  originalLanguage: string | null;
  firstPublished: string | null;
  firstCountry: string | null;
  audience: string | null;
  ageFrom: number | null;
  ageTo: number | null;
  authors: string | null;
  illustrators: string | null;
  translators: string | null;
  previousPublisher: string | null;
  previewPdf: string | null;
  video: string | null;
  genres: string | null;
  webCategories: string | null;
  keywords: string | null;
  hashtags: string | null;
  pages: number | null;
  spot: string | null;
  summary: string | null;
  promo: string | null;
  highlights: string | null;
  quotes: string | null;
  contracts: CrmContract[];
  inForce: number;
};
export type CrmSummary = {
  books: number;
  products?: number;
  unmatched?: number;
  rights?: Record<CrmRights, number>;
  flags?: Partial<Record<CrmFlag, number>>;
  preview?: number;
  video?: number;
  lastRead?: string | null;
  state: { running: boolean; count: number | null; startedAt: string | null; finishedAt: string | null; error: string | null };
};
export type CrmRow = Omit<ProductRow, 'issues'> & {
  crm: Pick<CrmBook, 'bookId' | 'name' | 'rights' | 'rightsWhy' | 'statusLabel' | 'statusFlag' | 'previewPdf' | 'video' | 'originalTitle' | 'inForce'> | null;
};
export type CrmFilter = CrmRights | 'durum' | 'eslesmedi' | 'onizleme' | 'video';

export type ProductRow = {
  id: string;
  code: string;
  name: string;
  brand: string;
  active: boolean;
  score: number;
  issues: Issue[];
  image: string | null;
  barcode: string | null;
  url: string | null;
  syncedAt: string;
  /** T-soft toplam satış adedi ve görüntülenme: öncelik sırası bunlarla. */
  sales: number;
  views: number;
  proposal?: ProposalStatus | null;
};

export type Proposal = {
  id: string;
  productId: string;
  status: ProposalStatus;
  fields: Fields;
  before: Fields;
  scoreBefore: number | null;
  scoreAfter: number | null;
  model: string | null;
  createdBy: string | null;
  createdAt: string;
  decidedBy: string | null;
  decidedAt: string | null;
  note: string | null;
  sentAt: string | null;
  result: string | null;
  productName?: string | null;
  /** Önerideki, kaynak kayıtta geçmeyen sayı ve özel adlar (gerçeklik denetimi). */
  unsupported?: string[];
  /** Fırsat ekranından istendiyse hedef arama sorgusu (Search Console satırı). */
  target?: ProposalTarget | null;
  /** Hedef sorgunun kelimeleri başlıkta / meta açıklamada / arama kelimelerinde geçiyor mu (bilgi; onay insanda). */
  targetCheck?: { query: string; words: string[]; inTitle: boolean; inMeta: boolean; inKeywords: boolean; missingTitle: string[]; missingMeta: string[] } | null;
};
export type ProposalTarget = { query: string; page?: string | null; position?: number | null; impressions?: number | null; clicks?: number | null; kind?: string | null };

export type ProductDetail = ProductRow & {
  current: Record<SeoField, string>;
  details: { words: number; shortDescription: string };
  /** Yönetim ekranındaki eşikler; sayaçlar bunlarla renklenir. */
  limits: { title_min: number; title_max: number; meta_min: number; meta_max: number; desc_min_words: number };
  /** CRM kitap kartı (barkodla eşleşirse). */
  crm: CrmBook | null;
  proposals: Proposal[];
};

export type Confidence = 'kesin' | 'yüksek' | 'orta' | 'yok';
export type Redirect = {
  id: string;
  link: string;
  url: string;
  current: string | null;
  target: string | null;
  targetType: string | null;
  confidence: Confidence;
  reason: string | null;
  alternatives: Array<{ link: string; type: string; score: number }>;
  status: 'bekliyor' | 'onaylandi' | 'reddedildi';
  chosen: string | null;
  decidedBy: string | null;
  decidedAt: string | null;
  note: string | null;
};

export type PageKind = 'model' | 'category' | 'brand';
export type PageRow = { id: string; name: string; link: string; url: string; books: number; sales: number; score: number; issues: number; proposal: ProposalStatus | null };
export type PageField = 'SeoTitle' | 'SeoDescription' | 'Intro';
export type PageDetail = {
  type: PageKind;
  id: string;
  name: string;
  link: string;
  url: string;
  current: Record<PageField, string>;
  facts: {
    books: number;
    sales: number;
    top: Array<{ name: string; author: string; sales: number }>;
    cats: string[];
    brands: string[];
    authors: string[];
    wikidata: { description?: string; born?: number; wikidata?: string; wikipedia?: string | null } | null;
  };
  score: number;
  issues: Array<Omit<Issue, 'field'> & { field: PageField }>;
  limits: ProductDetail['limits'];
  proposals: Array<Omit<Proposal, 'fields'> & { fields: Partial<Record<PageField, string>> }>;
};

export type SchemaReport = {
  checked: number;
  activeProducts: number;
  lastChecked: string | null;
  organization: { name?: string; description?: string; url?: string; sameAs?: unknown } | null;
  crawl: { running: boolean; done: number; queue: number | null; startedAt: string | null; finishedAt: string | null; error: string | null };
  checks: Array<{ id: string; severity: Severity; title: string; why: string; count: number }>;
  total: number;
  items: Array<{ id: string; url: string; status: number; issues: string[]; checkedAt: string; name: string; sales: number }>;
};

export type GeoResult = { ok: boolean; mentioned: boolean | null; cited: boolean | null; books: string[]; sources: Array<{ url: string; title: string }>; answer: string | null; error: string | null; askedAt: string; model: string | null };
export type GeoEngine = { id: string; label: string; configured: boolean; free: boolean; daily: number; usedToday: number; model: string };
export type Question = { id: string; text: string; category: string | null; createdBy: string | null; createdAt: string; results?: Record<string, GeoResult> };

/** Okuma cevaplarında sorgu bilgisi (köprünün SEO ara katmanı ekler): `<SqlInfo k={d.kaynaklar} …/>`. */
export type WithK = { kaynaklar?: Kaynaklar };

/** CRM kitap kartına yazılan (ya da deneme kipinde yazılacak) görünmez SEO alanları. */
export type CrmWriteStatus = 'yazildi' | 'yaziliyor' | 'deneme' | 'hata' | 'geri_alindi' | 'degisiklik_yok';
export type CrmWrite = {
  id: string;
  productId: string;
  name: string | null;
  bookId: string;
  status: CrmWriteStatus;
  mode: 'deneme' | 'acik';
  error: string | null;
  by: string | null;
  at: string | null;
  checkedAt: string | null;
  crmOk: boolean | null;
  onSite: boolean | null;
  fields: Record<string, string | number>;
  before: Record<string, string | number | null>;
};
export type CrmWrites = { mode: 'kapali' | 'deneme' | 'acik'; counts: Partial<Record<CrmWriteStatus, number>>; items: CrmWrite[] };

export async function call<T>(path: string, init: { method?: 'GET' | 'POST' | 'DELETE'; body?: unknown; timeout?: number } = {}): Promise<T & WithK> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const method = init.method ?? 'GET';
  const response = await fetch(`${ENGINE_BASE}/api/v1/seo-geo/${path}`, {
    method,
    credentials: 'include',
    headers: init.body !== undefined ? { 'Content-Type': 'application/json' } : method === 'GET' ? freshHeaders() : undefined,
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    signal: AbortSignal.timeout(init.timeout ?? 60_000),
  });
  if (!response.ok) {
    if (response.status === 401) throw new Error('Bu ekran için oturum açmanız gerekiyor.');
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new Error(typeof detail === 'string' ? detail : detail?.message || 'SEO sunucusu yanıt vermedi.');
  }
  return response.json();
}

export const qs = (o: Record<string, string | number | undefined>) =>
  Object.entries(o)
    .filter(([, v]) => v !== undefined && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join('&');

export const seoApi = {
  overview: () => call<Overview>('overview'),
  me: () => call<{ user: string; canApprove: boolean }>('me'),
  sync: () => call<{ started: boolean; sync: SyncState }>('sync', { method: 'POST' }),
  products: (p: { rule?: string; status?: string; q?: string; start?: number; limit?: number; order?: 'oncelik' | 'score' | 'name' }) =>
    call<{ total: number; start: number; items: ProductRow[] }>(`products?${qs(p)}`),
  product: (id: string) => call<ProductDetail>(`products/${encodeURIComponent(id)}`),
  // Model önerisi kuyrukta bekleyebilir; kısa zaman aşımı yanlış hata gösterir.
  propose: (id: string) => call<Proposal>(`products/${encodeURIComponent(id)}/propose`, { method: 'POST', timeout: 300_000 }),
  /** Fırsat sorgusu için öneri (tek tık): akış aynı, T-soft'a gönderim yok; hedef sorgu öneriyle kaydedilir. */
  proposeFor: (id: string, target: ProposalTarget) =>
    call<Proposal>(`products/${encodeURIComponent(id)}/propose`, { method: 'POST', body: target, timeout: 300_000 }),
  decide: (id: string, body: { action: 'approve' | 'reject'; fields?: Fields; note?: string }) =>
    call<Proposal>(`proposals/${id}/decide`, { method: 'POST', body, timeout: 120_000 }),
  bulkApprove: (ids: string[], note = '') =>
    call<{ items: Array<{ id: string; status: string; result?: string; skipped?: boolean }> }>('proposals/bulk-approve', { method: 'POST', body: { ids, note }, timeout: 600_000 }),
  batch: (budget = 3600) => call<{ started: boolean }>(`proposals/batch?budget=${budget}`, { method: 'POST' }),
  history: (start = 0) => call<{ total: number; items: Proposal[] }>(`history?${qs({ start, limit: 50 })}`),
  crmWrites: () => call<CrmWrites>('crm-writes?limit=500'),
  crmUndo: (id: string) => call<{ id: string; status: string }>(`crm-writes/${id}/undo`, { method: 'POST' }),
  search: (kind: 'daily' | 'queries' | 'pages', range: SearchRange = {}) => {
    const q = qs({ start: range.start, end: range.end, compare: range.compare || undefined });
    // Kayıtlı aralığın dışı Search Console'dan okunur; uzun aralıkta sorgu listesi birkaç sayfa sürebilir.
    return call<SearchReport>(`search/${kind}${q ? `?${q}` : ''}`, { timeout: q ? 180_000 : 60_000 });
  },
  searchRefresh: () => call<{ counts: Record<string, number> }>('search/refresh', { method: 'POST', timeout: 300_000 }),
  llms: () => call<{ llms: string; full: string; books: number; brands: number; authors: number; listedSellers: number; sellers: number; site: string; current: Record<string, { status: number | null; text?: string | null; error?: string }> }>('llms'),
  redirects: (p: { confidence?: string; status?: string; q?: string; start?: number; limit?: number }) =>
    call<{ total: number; items: Redirect[]; counts: Record<string, number> }>(`redirects?${qs(p)}`),
  decideRedirect: (id: string, body: { action: 'approve' | 'reject'; target?: string; note?: string }) =>
    call<Redirect>(`redirects/${id}/decide`, { method: 'POST', body }),
  approveRedirects: (confidence: 'kesin' | 'yüksek') =>
    call<{ approved: number }>(`redirects/approve-confidence?confidence=${encodeURIComponent(confidence)}`, { method: 'POST' }),
  redirectCsvUrl: () => `${ENGINE_BASE}/api/v1/seo-geo/redirects/export.csv`,
  pages: (p: { type: PageKind; q?: string; start?: number; limit?: number }) =>
    call<{ total: number; withBooks: number; items: PageRow[] }>(`pages?${qs(p)}`),
  page: (type: PageKind, id: string) => call<PageDetail>(`pages/${type}/${encodeURIComponent(id)}`),
  proposePage: (type: PageKind, id: string) => call<Proposal>(`pages/${type}/${encodeURIComponent(id)}/propose`, { method: 'POST', timeout: 300_000 }),
  decidePage: (id: string, body: { action: 'approve' | 'reject'; fields?: Partial<Record<PageField, string>>; note?: string }) =>
    call<Proposal>(`pages/proposals/${id}/decide`, { method: 'POST', body }),
  schema: (p: { issue?: string; start?: number; limit?: number }) => call<SchemaReport>(`schema?${qs(p)}`),
  schemaCrawl: (budget = 3600) => call<{ started: boolean }>(`schema/crawl?budget=${budget}`, { method: 'POST' }),
  themeRequestUrl: () => `${ENGINE_BASE}/api/v1/seo-geo/schema/theme-request.md`,
  questions: () => call<{ items: Question[]; measuring: boolean; engines: GeoEngine[]; run: { running: boolean; done: number; failed: number; startedAt: string | null; finishedAt: string | null; error: string | null } }>('questions'),
  measure: () => call<{ started: boolean }>('questions/measure', { method: 'POST' }),
  addQuestion: (text: string, category: string) => call<{ id: string }>('questions', { method: 'POST', body: { text, category } }),
  deleteQuestion: (id: string) => call<{ deleted: boolean }>(`questions/${id}`, { method: 'DELETE' }),
  crm: (p: { filter?: CrmFilter | ''; q?: string; start?: number; limit?: number }) =>
    call<{ total: number; start: number; items: CrmRow[]; summary: CrmSummary }>(`crm?${qs(p)}`),
  crmSync: () => call<{ started: boolean; state: CrmSummary['state'] }>('crm/sync', { method: 'POST' }),
};

export const RIGHTS_LABEL: Record<CrmRights, string> = {
  var: 'Hak var',
  incele: 'İncelenmeli',
  eksik: 'Hak eksik',
  yok: 'Sözleşme kaydı yok',
  koruma_disi: 'Koruma dışı eser',
  set: 'Set (içindeki kitaplar)',
  kitap_degil: 'Kitap değil',
};
export const RIGHTS_TONE: Record<CrmRights, 'good' | 'mid' | 'bad' | 'violet'> = {
  var: 'good',
  incele: 'mid',
  eksik: 'bad',
  yok: 'mid',
  koruma_disi: 'violet',
  set: 'violet',
  kitap_degil: 'violet',
};
export const FLAG_LABEL: Record<CrmFlag, string> = {
  bizim_degil: 'Artık bizim ürünümüz değil',
  cekildi: 'Satıştan çekildi',
  geri_istendi: 'Geri istendi',
  devredildi: 'Hakları devredildi',
  iptal: 'İptal edilmiş',
};

export const FIELD_LABEL: Record<SeoField, string> = {
  SeoTitle: 'SEO başlığı',
  SeoDescription: 'Meta açıklama',
  SearchKeywords: 'Arama kelimeleri',
  Details: 'Ürün açıklaması',
};

export const STATUS_LABEL: Record<ProposalStatus, string> = {
  hazir: 'Onay bekliyor',
  onaylandi: 'Onaylandı',
  // Eski kayıtlar: T-soft'a yazma 2026-09-25'te kapandı; bugün hiçbir öneri gönderilmez.
  gonderildi: 'Gönderildi (eski kayıt)',
  reddedildi: 'Reddedildi',
  hata: 'Gönderilemedi (eski kayıt)',
  geri_alindi: 'Geri alındı (eski kayıt)',
};

export const fmt = (n: number | null | undefined, digits = 0) =>
  n == null ? '—' : n.toLocaleString('tr-TR', { maximumFractionDigits: digits, minimumFractionDigits: digits });

export const dateTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';

export const scoreTone = (s: number) => (s >= 80 ? 'good' : s >= 50 ? 'mid' : 'bad');
