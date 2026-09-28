import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** M20 Basın, medya ve halkla ilişkiler: köprü uçları /api/v1/pr/*. */

export type KitStatus = 'taslak' | 'onayda' | 'onayli' | 'geri' | 'kapali';
export type SendStatus = 'hazir' | 'gonderildi' | 'cevap' | 'haber' | 'olumsuz' | 'cevapsiz';
export type Tone = 'olumlu' | 'notr' | 'olumsuz' | 'ilgisiz';
export type Part = 'national' | 'local' | 'pitch' | 'openings';

export type Meta = {
  outletTypes: Record<string, string>;
  regions: Record<string, string>;
  kitStatuses: Record<KitStatus, string>;
  channels: Record<string, string>;
  sendStatuses: Record<SendStatus, string>;
  tones: Record<Tone, string>;
  coverageSources: Record<string, string>;
  coverageStates: Record<string, string>;
  parts: Record<Part, string>;
  settings: { followUpDays: number; reportWeekday: number; webWatch: boolean; recipientsSet: boolean; smtpSet: boolean };
  lastRun: Record<string, unknown> | null;
  modelReady: boolean;
  me: { username: string; display: string; canEdit: boolean; canApprove: boolean; canSend: boolean; canExport: boolean };
};

export type Book = {
  kitapId: string;
  stokKodu: string | null;
  ad: string | null;
  yazar: string | null;
  yayinevi: string | null;
  kitaplik: string | null;
  hedefKitle: string | null;
  turler: string | null;
  yayinTarihi: string | null;
  onem: number | null;
  onemAdi: string | null;
  kapak: string | null;
  fiyat?: number | null;
  sayfa?: number | null;
  metinler?: Array<{ alan: string; ad: string; metin: string }>;
  yazarlar?: Array<{ id: string | null; ad: string | null }>;
};

export type KitHead = {
  id: string;
  crmBookId: string;
  stokKodu: string | null;
  bookTitle: string;
  author: string | null;
  publishDate: string | null;
  status: KitStatus;
  statusLabel: string;
  owner: string | null;
  version: number;
  submittedBy: string | null;
  submittedAt: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  rejectNote: string | null;
  updatedAt: string | null;
  sendCount?: number;
  sentCount?: number;
  coverageCount?: number;
};

export type Send = {
  id: string;
  kitId: string;
  contactKey: string;
  contactName: string | null;
  outlet: string | null;
  channel: string;
  channelLabel: string;
  status: SendStatus;
  statusLabel: string;
  pitch: string | null;
  pitchSource: string | null;
  approved: boolean;
  approvedBy: string | null;
  sentAt: string | null;
  followUpAt: string | null;
  overdue: boolean;
  crmOrderNo: string | null;
  mailStatus: string | null;
  mailedAt: string | null;
  note: string | null;
  createdBy: string;
  doNotContact?: boolean;
  bookTitle?: string;
};

export type Coverage = {
  id: string;
  source: 'elle' | 'web' | 'crm-arsiv';
  sourceLabel: string;
  state: 'kayitli' | 'aday' | 'reddedildi';
  stateLabel: string;
  url: string | null;
  title: string;
  publishedAt: string | null;
  outlet: string | null;
  outletType: string | null;
  contactKey: string | null;
  crmBookId: string | null;
  bookTitle: string | null;
  authorName: string | null;
  kitId: string | null;
  sendId: string | null;
  tone: Tone | null;
  toneLabel: string | null;
  toneSource: string | null;
  toneProb: number | null;
  summary: string | null;
  note: string | null;
  readOnly: boolean;
};

export type Job = { id: string; kind: string; status: 'bekliyor' | 'calisiyor' | 'bitti' | 'hata'; step: string | null; error: string | null; result: Record<string, unknown> | null };

export type Draft = { metin: string | null; dusenSayisi?: number; dusen?: Array<{ cumle: string; neden: string }>; zaman?: string };

export type Kit = KitHead & {
  releaseNational: string | null;
  releaseLocal: string | null;
  pitchTemplate: string | null;
  sources: Partial<Record<Part, string>>;
  draft: Partial<Record<Part, Draft>>;
  assets: Record<string, unknown>;
  sends: Send[];
  coverage: Coverage[];
  job: Job | null;
  me?: { isSubmitter: boolean };
  kaynaklar?: Kaynaklar;
};

export type Contact = {
  key: string;
  source: 'crm' | 'portal';
  crmContactId: string | null;
  name: string;
  outlet: string | null;
  outletType: string | null;
  role: string | null;
  email: string | null;
  phone: string | null;
  topics: string[];
  region: string | null;
  doNotContact: boolean;
  dncReason: string | null;
  note: string | null;
  crm: { mecra: string | null; kurum: string | null; unvan: string | null; iys: boolean | null; haberSayisi: number } | null;
  history?: { sends?: number; positive?: number; negative?: number; coverage?: number; last?: string | null };
  score?: number;
  reasons?: string[];
  lastContact?: string | null;
  inList?: boolean;
};

export type ArchiveNews = {
  id: string;
  baslik: string | null;
  link: string | null;
  tarih: string | null;
  mecra: string | null;
  muhabir: string | null;
  gorusulen: string | null;
  yazar: string | null;
  yayinlandi: boolean;
  books: Array<{ kitapId: string | null; ad: string | null }>;
};

export type PageOf<T> = { items: T[]; total: number; page: number; pageSize: number; kaynaklar?: Kaynaklar };

export type Home = {
  month: string;
  books: Array<Book & { kit: KitHead | null }>;
  booksError: string | null;
  kpi: { books: number; noKit: number; pending: number; overdue: number; recent: number; candidates: number };
  pending: KitHead[];
  overdue: Send[];
  recentCoverage: Coverage[];
  webWatch: boolean;
  kaynaklar?: Kaynaklar;
};

export type BookDetail = {
  book: Book;
  kits: KitHead[];
  openKit: KitHead | null;
  archive: ArchiveNews[];
  archiveNote: string | null;
  promoOrders: Array<{ siparisNo: string | null; tarih: string | null; cari: string | null; adet: number }>;
  promoTotal: number;
  promoNote: string | null;
  m15Release: { id: string; metin: string; onaylayan: string | null } | null;
  kaynaklar?: Kaynaklar;
};

export type Report = {
  from: string;
  to: string;
  sends: { total: number; byStatus: Record<string, number>; byChannel: Record<string, number>; answered: number; answerRate: number | null };
  coverage: {
    total: number;
    byTone: Record<string, number>;
    byOutletType: Record<string, number>;
    bySource: Record<string, number>;
    outlets: Array<{ name: string; count: number }>;
    books: Array<{ crmBookId: string | null; title: string | null; count: number }>;
    authors: Array<{ name: string; count: number }>;
    items: Coverage[];
  };
  archive: { total: number | null; note?: string };
  pendingCandidates: number;
  comment?: { metin: string | null; dusenSayisi: number } | null;
  kaynaklar?: Kaynaklar;
};

export type Preview = {
  title?: string | null;
  publishedAt?: string | null;
  outlet?: string | null;
  summary?: string | null;
  error?: string;
  disabled?: boolean;
  duplicate?: { id: string; state: string };
  books?: Array<{ crmBookId: string; bookTitle: string; author: string | null; kitId: string }>;
  contacts?: Array<{ key: string; name: string; outlet: string | null }>;
};

const B = '/api/v1/pr';

async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 120_000): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${B}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401) throw new EngineAuthError();
  if (res.status === 403) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  }
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new Error(msg || httpErrorText(res.status));
  }
  return (await res.json()) as T;
}

const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;

export const prApi = {
  meta: () => send<Meta>('GET', '/meta'),
  home: (ay: string, yenile = false) => send<Home>('GET', `/home${qs({ ay, yenile })}`, undefined, 180_000),
  searchBooks: (q: string, page = 0) => send<PageOf<Book>>('GET', `/books${qs({ q, page })}`),
  book: (id: string, yenile = false) => send<BookDetail>('GET', `/books/${enc(id)}${qs({ yenile })}`, undefined, 180_000),
  createKit: (crmBookId: string) => send<Kit>('POST', '/kits', { crmBookId }, 180_000),
  kit: (id: string) => send<Kit>('GET', `/kits/${enc(id)}`),
  updateKit: (id: string, b: Partial<Record<'releaseNational' | 'releaseLocal' | 'pitchTemplate' | 'owner', string | null>> & Record<string, unknown>) =>
    send<Kit>('PATCH', `/kits/${enc(id)}`, b),
  draft: (id: string, parts?: Part[]) => send<{ job: Job }>('POST', `/kits/${enc(id)}/draft`, { parts }),
  job: (jid: string) => send<Job>('GET', `/jobs/${enc(jid)}`),
  submit: (id: string) => send<Kit>('POST', `/kits/${enc(id)}/submit`, {}),
  withdraw: (id: string) => send<Kit>('POST', `/kits/${enc(id)}/withdraw`, {}),
  approve: (id: string, note?: string) => send<Kit>('POST', `/kits/${enc(id)}/approve`, { note }),
  reject: (id: string, note: string) => send<Kit>('POST', `/kits/${enc(id)}/reject`, { note }),
  close: (id: string) => send<Kit>('POST', `/kits/${enc(id)}/close`, {}),
  reopen: (id: string) => send<Kit>('POST', `/kits/${enc(id)}/reopen`, {}),
  events: (id: string) => send<{ items: Array<{ at: string; who: string; what: string; new: unknown }>; kaynaklar?: Kaynaklar }>('GET', `/kits/${enc(id)}/events`),
  suggest: (id: string, page = 0, q = '') =>
    send<PageOf<Contact> & { note: string | null; rule: string }>('GET', `/kits/${enc(id)}/suggest-contacts${qs({ page, q })}`, undefined, 180_000),
  addSends: (id: string, contactKeys: string[], channel = 'eposta') =>
    send<{ added: string[]; skipped: Array<{ key: string; name: string; neden: string }>; kit: Kit }>('POST', `/kits/${enc(id)}/sends`, { contactKeys, channel }),
  updateSend: (sid: string, b: Record<string, unknown>) => send<Send>('PATCH', `/sends/${enc(sid)}`, b),
  deleteSend: (sid: string) => send<{ id: string }>('DELETE', `/sends/${enc(sid)}`),
  approveSend: (sid: string) => send<Send>('POST', `/sends/${enc(sid)}/approve`, {}),
  pitch: (sid: string) => send<{ job: Job }>('POST', `/sends/${enc(sid)}/pitch`, {}),
  sendJob: (sid: string) => send<{ job: Job | null }>('GET', `/sends/${enc(sid)}/job`),
  mail: (sid: string, bulten: 'ulusal' | 'yerel' | 'yok', subject?: string) => send<Send>('POST', `/sends/${enc(sid)}/mail`, { bulten, subject }),
  contacts: (p: { q?: string; tur?: string; etiket?: string; kaynak?: string; izin?: string; page?: number; yenile?: boolean }) =>
    send<PageOf<Contact> & { note: string | null; tags: string[]; all: number }>('GET', `/contacts${qs(p)}`, undefined, 180_000),
  contact: (key: string) =>
    send<{ contact: Contact; history: Contact['history']; archive: ArchiveNews[]; sends: Send[]; coverage: Coverage[]; note: string | null; kaynaklar?: Kaynaklar }>(
      'GET', `/contacts/${enc(key)}`, undefined, 180_000),
  createContact: (b: Record<string, unknown>) => send<Contact>('POST', '/contacts', b),
  updateContact: (key: string, b: Record<string, unknown>) => send<Contact>('PATCH', `/contacts/${enc(key)}`, b),
  deleteContact: (key: string) => send<{ key: string }>('DELETE', `/contacts/${enc(key)}`),
  coverage: (p: { frm?: string; to?: string; kitap?: string; kaynak?: string; ton?: string; q?: string; durum?: string; kisi?: string; page?: number }) =>
    send<PageOf<Coverage> & { note: string | null; counts: Record<string, number>; webWatch: boolean }>('GET', `/coverage${qs(p)}`, undefined, 180_000),
  preview: (url: string) => send<Preview>('POST', '/coverage/preview', { url }, 60_000),
  addCoverage: (b: Record<string, unknown>) => send<Coverage & { job?: Job }>('POST', '/coverage', b),
  updateCoverage: (id: string, b: Record<string, unknown>) => send<Coverage>('PATCH', `/coverage/${enc(id)}`, b),
  deleteCoverage: (id: string) => send<{ id: string }>('DELETE', `/coverage/${enc(id)}`),
  report: (frm: string, to: string, yorum = false) => send<Report>('GET', `/report${qs({ frm, to, yorum })}`, undefined, 180_000),
  pdfUrl: (frm: string, to: string) => `${ENGINE_BASE}${B}/report/export.pdf${qs({ frm, to })}`,
  xlsxUrl: (frm: string, to: string) => `${ENGINE_BASE}${B}/report/export.xlsx${qs({ frm, to })}`,
};

/* ------------------------------------------------------------------ biçim */

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
const utc = (iso: string) => {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};
export const fmtDay = (iso: string | null | undefined) => (iso ? dayFmt.format(utc(iso)) : '—');
export const fmtStamp = (iso: string | null | undefined) =>
  iso ? new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Istanbul' }).format(new Date(iso)) : '—';
export const monthLabel = (ym: string) =>
  new Intl.DateTimeFormat('tr-TR', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(utc(`${ym}-01`));
export const isoDay = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);

export const KIT_TONE: Record<KitStatus, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  taslak: 'muted',
  onayda: 'warn',
  onayli: 'ok',
  geri: 'err',
  kapali: 'muted',
};
export const SEND_TONE: Record<SendStatus, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  hazir: 'muted',
  gonderildi: 'violet',
  cevap: 'ok',
  haber: 'ok',
  olumsuz: 'err',
  cevapsiz: 'warn',
};
export const TONE_TONE: Record<Tone, 'ok' | 'warn' | 'err' | 'muted'> = { olumlu: 'ok', notr: 'muted', olumsuz: 'err', ilgisiz: 'warn' };

export const SOURCE_LABEL = (k: string | null | undefined): string => {
  if (!k) return '—';
  if (k === 'zeki') return 'Zeki AI';
  if (k === 'kullanici') return 'Elle';
  if (k === 'sablon') return 'Şablondan';
  if (k.startsWith('m15:')) return 'Pazarlama planında onaylı';
  if (k.startsWith('crm:')) return 'CRM kitap kartı';
  return k;
};

export const EVENT_LABEL: Record<string, string> = {
  olusturuldu: 'Dosya açıldı',
  duzenlendi: 'Metin ya da sahip değişti',
  'zeki-taslak': 'Zeki AI taslağı yazıldı',
  'onaya-gonderildi': 'Onaya gönderildi',
  'geri-cekildi': 'Onaydan geri çekildi',
  onaylandi: 'Onaylandı',
  'geri-gonderildi': 'Geri gönderildi',
  kapatildi: 'Kapatıldı',
  'yeniden-acildi': 'Yeniden açıldı',
  'liste-eklendi': 'Listeye kişi eklendi',
  'liste-cikarildi': 'Listeden kişi çıkarıldı',
  satir: 'Gönderim satırı güncellendi',
  'satir-onay': 'Satır onaylandı',
  eposta: 'E-posta',
};

export const DROP_REASON: Record<string, string> = {
  'alinti-bulunamadi': 'alıntı kaynakta birebir yok',
  'kaynaksiz-rakam': 'kaynaksız rakam',
  'kanitsiz-iddia': 'kanıtsız üstünlük iddiası',
  'teknoloji-adi': 'yasak ad',
};
