import { send } from '../engine';

/** M51 Müşteri hizmetleri köprü istemcisi (`/api/v1/support/*`). Talep kaydı NanobaseAI Destek masasındadır; portal masayı
 *  yalnız okur. Müşteri bağlamı canlı CRM'den (sipariş, sevkiyat, kargo) ve Logo'dan (fatura, iade — veri sonu tarihiyle).
 *  Zeki AI taslağı hiçbir yere gönderilmez; temsilci masadan kendisi gönderir. */

const B = '/api/v1/support';
const enc = encodeURIComponent;
export const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};

export type SupportClass = {
  klass: string;
  label: string;
  description: string;
  active: boolean;
  sort: number;
  slaFirstHours: number | null;
  slaResolveHours: number | null;
  escalateTo: string | null;
  updatedBy: string | null;
  updatedAt: string | null;
};

export type Meta = {
  me: {
    username: string;
    display: string;
    admin: boolean;
    canContext: boolean;
    canSuggest: boolean;
    canFaq: boolean;
    canAll: boolean;
    canSettings: boolean;
    dataCari: boolean;
    dataSatis: boolean;
  };
  destek: { configured: boolean; link: string | null };
  classes: SupportClass[];
  urgency: string[];
  gapStates: Array<{ key: string; label: string }>;
  settings: Record<string, unknown>;
  runs: { classify: Record<string, unknown>; night: Record<string, unknown> };
  zekiQuestions: string[];
  factKeys: Record<string, string>;
};

export type Order = {
  id: string;
  no: string | null;
  tarih: string | null;
  durum: number;
  durumAd: string;
  tip: string | null;
  adet: number | null;
  bekleyen: number | null;
  acik: boolean;
  riskte: boolean;
  riskSebep: string | null;
  sevkTarihi: string | null;
  tamamlandi: string | null;
  tutar: number | null;
  kdvliTutar: number | null;
  takipNo: string | null;
  takipUrl: string | null;
  kargoFirma: string | null;
  digerNo: string[];
};

export type Shipment = {
  id: string;
  no: string | null;
  orderId: string | null;
  tarih: string | null;
  tamamlandi: boolean;
  tur: string | null;
  faturaNo: string | null;
  tutar: number | null;
  logoda: boolean;
  logo?: Invoice;
};

export type Cargo = {
  takipNo: string | null;
  irsaliyeNo: string | null;
  firma: string | null;
  cikisSube: string | null;
  varisSube: string | null;
  aliciSehir: string | null;
  irsTarihi: string | null;
  teslimTarihi: string | null;
  teslimSaati: string | null;
  iadeDurumu: string | null;
  sevkAdeti: number | null;
  desi: number | null;
  tutar: number | null;
  orderIds: string[];
};

export type Invoice = { no: string | null; tarih: string | null; tur: number; turAd: string; iade: boolean; tutar: number | null };
export type Account = { id: string; unvan: string | null; cariKodu: string | null; kanal: string | null };
export type PastTicket = { ref: string; subject: string | null; status: string | null; category: string | null; opened: string | null; url: string | null };

export type Context = {
  asOf: string;
  match: {
    contacts: Array<{ id: string; ad: string | null; accountId: string | null; cariKodu: string | null }>;
    webusers: Array<{ id: string; ad: string | null; accountId: string | null }>;
    accounts: Account[];
  };
  needsChoice: boolean;
  account?: Account | null;
  orders: Order[];
  shipments: Shipment[];
  cargo: Cargo[];
  invoices: Invoice[];
  tickets: PastTicket[];
  logo: { dataEnd: string | null; since: string; note: string | null } | null;
  summary?: { orders: number; open: number; risk: number; pending: number };
  hidden: string[];
  warnings: string[];
  orderHints?: string[];
};

export type Dealer = Context & {
  open: Order[];
  risk: Order[];
  recent: Order[];
  dealerSummary?: { open: number; pending: number; risk: number; riskAmount: number; shipped30: number; oldestOpen: string | null };
  balance?: { bakiye: number; vadesiGecmis: number; k90?: number; year: number; dataEnd: string | null; approx: boolean } | null;
};

export type QueueItem = {
  ref: string;
  subject: string | null;
  status: string | null;
  priority: string | null;
  team: string | null;
  opened: string | null;
  sla: 'asildi' | 'yaklasiyor' | 'icinde' | null;
  due: string | null;
  assigned: string[];
  mine: boolean;
  klass: string | null;
  klassGuess: string | null;
  urgency: string | null;
  hasDraft: boolean;
  url: string | null;
};

export type Quality = {
  configured: boolean;
  window: { from: string; to: string };
  previousWindow: { from: string; to: string };
  opened: number;
  openedPrevious: number;
  resolved: number;
  byStatus: Record<string, number>;
  openNow: number;
  sla: { asildi: number; yaklasiyor: number; icinde: number; yok: number };
  dueToday: number;
  firstResponseMedianMin: number | null;
  firstResponseCount: number;
  resolutionMedianHours: number | null;
  resolutionCount: number;
  csat: number | null;
  csatCount: number;
  channel: { portal: number; eposta: number };
  topics: Array<{ klass: string; label: string; count: number; previous: number }>;
  weekly: Array<{ week: string; counts: Record<string, number> }>;
  repeat: { count: number; days: number; rate: number | null };
  zeki: { classified: number; unsure: number; waiting: number; corrected: number; noFaq: number; drafts: number; sentAsIs: number };
  agents: Array<{ agent: string; open: number }> | null;
};

export type FaqMatch = { source: 'destek' | 'crm' | 'portal'; id: string; title: string; score: number; excerpt: string; url: string | null };
export type FaqResult = { method: 'embedding' | 'lexical' | null; matches: FaqMatch[]; best: number | null; threshold: number | null };

export type Insight = {
  ticket: string;
  klass: string | null;
  klassP: number | null;
  klassMargin: number | null;
  klassGuess: string | null;
  klassBy: string | null;
  urgency: string | null;
  urgencyP: number | null;
  faq: FaqResult | null;
  draft: string | null;
  draftAt: string | null;
  finalSent: boolean | null;
  editRatio: number | null;
};

export type Gap = {
  id: string;
  klass: string;
  label: string;
  tickets: number;
  samples: string[];
  question: string | null;
  draft: string | null;
  status: string;
  statusLabel: string;
  windowDays: number | null;
  approvedBy: string | null;
  approvedAt: string | null;
  updatedAt: string | null;
};

export type Draft = {
  ticket: string;
  draft: string;
  facts: Record<string, string>;
  dropped: number;
  used: string[];
  warnings: string[];
  insight: Insight | null;
};

export type ContextQuery = { email?: string; phone?: string; order?: string; account?: string; code?: string; ticket?: string };

export const supportApi = {
  meta: () => send<Meta>('GET', `${B}/meta`),
  context: (q: ContextQuery) => send<Context>('GET', `${B}/context${qs(q)}`),
  dealers: (q: string, offset = 0) =>
    send<{ items: Account[]; hasMore: boolean; nextOffset: number | null }>('GET', `${B}/dealers${qs({ q, offset, size: 25 })}`),
  dealer: (id: string) => send<Dealer>('GET', `${B}/dealer/${enc(id)}`),
  queue: (scope: 'mine' | 'all') => send<{ configured: boolean; scope: string; items: QueueItem[]; agentMapped?: boolean }>('GET', `${B}/queue${qs({ scope })}`),
  quality: (from: string, to: string) => send<Quality>('GET', `${B}/quality${qs({ from, to })}`),
  insight: (ref: string) => send<{ insight: Insight | null }>('GET', `${B}/insights/${enc(ref)}`),
  classify: (ticket: string) => send<{ insight: Insight | null }>('POST', `${B}/classify`, { ticket }),
  setClass: (ref: string, klass: string, urgency?: string) => send<{ insight: Insight }>('PUT', `${B}/insights/${enc(ref)}/class`, { klass, urgency }),
  draft: (ticket: string, extra: { order?: string; account?: string } = {}) => send<Draft>('POST', `${B}/draft`, { ticket, ...extra }),
  outcome: (ref: string, sent: boolean, finalText?: string) => send<{ insight: Insight }>('POST', `${B}/drafts/${enc(ref)}/outcome`, { sent, finalText }),
  faqMatch: (q: string) => send<FaqResult>('GET', `${B}/faq/match${qs({ q })}`),
  gaps: () => send<{ items: Gap[]; canEdit: boolean; night: Record<string, unknown> }>('GET', `${B}/faq/gaps`),
  patchGap: (id: string, body: Partial<Pick<Gap, 'question' | 'draft' | 'status' | 'label'>>) => send<Gap>('PATCH', `${B}/faq/gaps/${enc(id)}`, body),
  classes: () => send<{ items: SupportClass[]; canEdit: boolean }>('GET', `${B}/classes`),
  saveClass: (klass: string, body: Partial<SupportClass>) => send<SupportClass>('PUT', `${B}/classes/${enc(klass)}`, body),
};

/* ------------------------------------------------------------------ biçim */

const nf0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 });
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : nf0.format(v));
export const fmtNum = (v: number | null | undefined) => (v === null || v === undefined ? '—' : nf2.format(v));
export const fmtTl = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${nf2.format(v)} ₺`);
export const fmtDay = (iso: string | null | undefined) => {
  if (!iso) return '—';
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : iso;
};
/** Dakika → «45 dk» / «3,5 sa» / «2,1 gün». */
export const fmtMinutes = (m: number | null | undefined) => {
  if (m === null || m === undefined) return '—';
  if (m < 90) return `${nf0.format(m)} dk`;
  if (m < 60 * 36) return `${nf2.format(Math.round((m / 60) * 10) / 10)} sa`;
  return `${nf2.format(Math.round((m / 1440) * 10) / 10)} gün`;
};
export const fmtPct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `%${nf0.format(v * 100)}`);

export const SLA_LABEL: Record<string, { label: string; tone: 'err' | 'warn' | 'ok' | 'muted' }> = {
  asildi: { label: 'SLA aşıldı', tone: 'err' },
  yaklasiyor: { label: 'SLA yaklaşıyor', tone: 'warn' },
  icinde: { label: 'Süre içinde', tone: 'ok' },
  yok: { label: 'SLA yok', tone: 'muted' },
};

/** Değişim: bu dönem / önceki dönem − 1; önceki 0 ise null. */
export const change = (cur: number, prev: number) => (prev > 0 ? cur / prev - 1 : null);

/** Tarih aralığı: bugün dahil son `days` gün (İstanbul günü). */
export function lastDays(days: number): { from: string; to: string } {
  const now = new Date(new Date().toLocaleString('en-US', { timeZone: 'Europe/Istanbul' }));
  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const start = new Date(now);
  start.setDate(start.getDate() - (days - 1));
  return { from: iso(start), to: iso(now) };
}

/** Bağlam araması: tek kutudan yazılanın türünü tahmin eder (e-posta, telefon, sipariş no ya da cari kodu). */
export function guessQuery(raw: string): ContextQuery | null {
  const s = raw.trim();
  if (!s) return null;
  if (/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(s)) return { email: s };
  const digits = s.replace(/\D/g, '');
  if (/^[+\d\s()\-.]+$/.test(s) && digits.length >= 10 && digits.length <= 13) return { phone: s };
  if (/^\d{3}([.\-]\d+)+$/.test(s)) return { code: s };
  return { order: s };
}
