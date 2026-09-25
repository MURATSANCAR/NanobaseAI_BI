import { ENGINE_BASE, ENGINE_ENABLED, freshHeaders } from '../engine';

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
export type SearchReport = { start: string | null; end: string | null; savedAt: string | null; rows: Array<{ keys: string[]; clicks: number; impressions: number; ctr: number; position: number }> };

export type Overview = {
  products: number;
  activeAverage: number | null;
  failing: number;
  failingThreshold: number;
  rules: Array<{ rule: string; title: string; severity: Severity; count: number }>;
  proposals: Partial<Record<ProposalStatus, number>>;
  approvedThisWeek: number;
  /** Her zaman false: T-soft'a yazma yok. */
  tsoftWrite: false;
  lastSync: { startedAt: string; finishedAt: string | null; count: number | null; error: string | null } | null;
  sync: SyncState;
  batch: { running: boolean; done: number; failed: number; queue: number | null; startedAt: string | null; finishedAt: string | null; error: string | null };
  search: SearchReport | null;
  connections: { tsoft: boolean; google: boolean; serviceAccount: string | null; gscSite: string | null; ga4: boolean; merchant: boolean };
};

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
};

export type ProductDetail = ProductRow & {
  current: Record<SeoField, string>;
  details: { words: number; shortDescription: string };
  /** Yönetim ekranındaki eşikler; sayaçlar bunlarla renklenir. */
  limits: { title_min: number; title_max: number; meta_min: number; meta_max: number; desc_min_words: number };
  proposals: Proposal[];
};

export type Question = { id: string; text: string; category: string | null; createdBy: string | null; createdAt: string };

async function call<T>(path: string, init: { method?: 'GET' | 'POST' | 'DELETE'; body?: unknown; timeout?: number } = {}): Promise<T> {
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

const qs = (o: Record<string, string | number | undefined>) =>
  Object.entries(o)
    .filter(([, v]) => v !== undefined && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join('&');

export const seoApi = {
  overview: () => call<Overview>('overview'),
  me: () => call<{ user: string; canApprove: boolean }>('me'),
  sync: () => call<{ started: boolean; sync: SyncState }>('sync', { method: 'POST' }),
  products: (p: { rule?: string; status?: string; q?: string; start?: number; limit?: number }) =>
    call<{ total: number; start: number; items: ProductRow[] }>(`products?${qs(p)}`),
  product: (id: string) => call<ProductDetail>(`products/${encodeURIComponent(id)}`),
  // Model önerisi kuyrukta bekleyebilir; kısa zaman aşımı yanlış hata gösterir.
  propose: (id: string) => call<Proposal>(`products/${encodeURIComponent(id)}/propose`, { method: 'POST', timeout: 300_000 }),
  decide: (id: string, body: { action: 'approve' | 'reject'; fields?: Fields; note?: string }) =>
    call<Proposal>(`proposals/${id}/decide`, { method: 'POST', body, timeout: 120_000 }),
  bulkApprove: (ids: string[], note = '') =>
    call<{ items: Array<{ id: string; status: string; result?: string; skipped?: boolean }> }>('proposals/bulk-approve', { method: 'POST', body: { ids, note }, timeout: 600_000 }),
  batch: (budget = 3600) => call<{ started: boolean }>(`proposals/batch?budget=${budget}`, { method: 'POST' }),
  history: (start = 0) => call<{ total: number; items: Proposal[] }>(`history?${qs({ start, limit: 50 })}`),
  search: (kind: 'daily' | 'queries' | 'pages') => call<SearchReport>(`search/${kind}`),
  searchRefresh: () => call<{ counts: Record<string, number> }>('search/refresh', { method: 'POST', timeout: 300_000 }),
  llms: () => call<{ llms: string; full: string; books: number; brands: number; authors: number; listedSellers: number; sellers: number; site: string; current: Record<string, { status: number | null; text?: string | null; error?: string }> }>('llms'),
  questions: () => call<{ items: Question[]; measuring: boolean }>('questions'),
  addQuestion: (text: string, category: string) => call<{ id: string }>('questions', { method: 'POST', body: { text, category } }),
  deleteQuestion: (id: string) => call<{ deleted: boolean }>(`questions/${id}`, { method: 'DELETE' }),
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
  gonderildi: 'Gönderildi',
  reddedildi: 'Reddedildi',
  hata: 'Gönderilemedi',
  geri_alindi: 'Geri alındı',
};

export const fmt = (n: number | null | undefined, digits = 0) =>
  n == null ? '—' : n.toLocaleString('tr-TR', { maximumFractionDigits: digits, minimumFractionDigits: digits });

export const dateTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';

export const scoreTone = (s: number) => (s >= 80 ? 'good' : s >= 50 ? 'mid' : 'bad');
