import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';

/** M23 İşbirlikleri ekranlarının köprü uçları: /api/v1/influencers/*. Ücret alanları yetkisi olmayana `null` gelir. */

export type Stage = 'teklif' | 'gonderildi' | 'icerik-bekleniyor' | 'onayda' | 'yayinda' | 'rapor' | 'odeme' | 'kapali' | 'vazgecildi';
export type Kind = 'hediye' | 'ucretli' | 'karsilikli';
export type DraftKind = 'brief' | 'iletisim' | 'sadakat';
export type PayoutStatus = 'hazir' | 'onayli' | 'odendi' | 'iptal';

export type Me = { username: string; display: string; canEdit: boolean; canApprove: boolean; canPay: boolean; canSeeFee: boolean; canExport: boolean };

export type Meta = {
  platformlar: Record<string, string>;
  konular: Record<string, string>;
  yasGruplari: Record<string, string>;
  turler: Record<Kind, string>;
  asamalar: Record<Stage, string>;
  pano: Stage[];
  odemeDurumlari: Record<PayoutStatus, string>;
  taslakTurleri: Record<DraftKind, string>;
  iletisimTercihleri: Record<string, string>;
  ayarlar: {
    weights: Record<string, number>; cooldownDays: number; jumpPct: number; contentWaitDays: number; linkGraceDays: number;
    payoutDay: number; disclosureKinds: Kind[]; giftNeedsApproval: boolean; apiEnabled: boolean;
  };
  yasalEtiket: string;
  me: Me;
  modelVar: boolean;
  eposta: { configured: boolean; sender: string | null };
};

export type Relation = {
  score: number; band: 'yok' | 'soguk' | 'ilik' | 'sicak'; parts: { yakinlik: number; siklik: number; sonuc: number };
  last: string | null; daysSince?: number; published: number; dropped: number;
};

export type Snapshot = { day: string; followers: number | null; posts: number | null; avgLikes: number | null; avgComments: number | null; source: 'api' | 'elle' };
export type Account = { id: string; platform: string; platformAdi: string; handle: string; url: string | null; verifiedByApi: boolean; latest: Snapshot | null };
export type Jump = { accountId: string; from: string; to: string; before: number; after: number; pct: number };

export type Person = {
  id: string; name: string; email: string | null; phone: string | null; city: string | null; crmContactId: string | null;
  topics: string[]; ageGroups: string[]; feeMin: number | null; feeMax: number | null; feeSet: boolean; currency: string;
  contactPref: string | null; notes: string | null; doNotContact: boolean; minor: boolean; createdBy: string; createdAt: string | null;
  updatedBy: string | null; updatedAt: string | null;
};

export type PersonRow = Person & {
  accounts: Account[]; relation: Relation; lastCollab: string | null; openCollabs: number; collabs: number; followers: number | null; jumps: Jump[];
};

export type Collab = {
  id: string; no: number; code: string; personId: string; personName: string | null; crmBookId: string | null; bookCode: string | null;
  bookTitle: string | null; kind: Kind; kindLabel: string; stage: Stage; stageLabel: string; fee: number | null; feeSet: boolean;
  crmOrderNo: string | null; duePublish: string | null; publishedUrl: string | null; publishedAt: string | null;
  disclosureOk: boolean | null; reach: number | null; engagement: number | null; resultNote: string | null; note: string | null;
  needsApproval: boolean; approvedBy: string | null; approvedAt: string | null; waitingApproval: boolean; stageAt: string | null;
  createdBy: string; createdAt: string | null; daysToPublish: number | null; linkLate: boolean; cpe: number | null;
};

export type PayoutBrief = { id: string; no: number; status: PayoutStatus; statusLabel: string; amount: number | null; logoDocNo: string | null; paidAt: string | null };

export type PersonDetail = PersonRow & {
  snapshots: Array<Snapshot & { accountId: string; by: string | null }>;
  collabs: Array<Collab & { payout: PayoutBrief | null }>;
  books: string[];
  orderNos: string[];
  totals: { collabs: number; published: number; engagement: number; spend: number | null; cpe: number | null };
  crmOrders: null | { hata: string } | { siparisler: Array<{ siparisNo: string; tarih: string | null; adet: number }>; toplamAdet: number; bulunamayan: string[] };
};

export type Draft = {
  id: string; kind: DraftKind; kindLabel: string; subject: string | null; body: string; source: 'zeki' | 'kural' | 'elle';
  dropped: Array<{ cumle: string; neden: string }>; status: 'taslak' | 'onayli'; createdBy: string; createdAt: string | null;
  approvedBy: string | null; approvedAt: string | null; sentBy: string | null; sentAt: string | null;
};

export type CollabDetail = Collab & {
  person: { id: string; name: string; email: string | null; doNotContact: boolean; minor: boolean };
  events: Array<{ at: string | null; user: string; action: string; note: string | null }>;
  drafts: Draft[];
  payout: PayoutBrief | null;
};

export type Reminder = { key: string; kind: string; collabId: string | null; personId?: string; to: string; text: string };

export type Board = {
  columns: Array<{ stage: Stage; label: string; items: Collab[] }>;
  open: number; closedRecent: Collab[]; waitingApproval: number; linkLate: number; publishSoon: number;
  month: { from: string; to: string; collabs: number; spend: number | null; budget: number | null };
  reminders: Reminder[];
};

export type Candidate = {
  personId: string; name: string; score: number; parts: Record<string, number>; reason: string; topics: string[]; ageGroups: string[];
  accounts: Array<{ platform: string; handle: string }>; followers: number | null; feeMin: number | null; feeMax: number | null;
  relation: Relation; lastCollab: string | null; minor: boolean;
};

export type Candidates = {
  book: { kitapId: string | null; stokKodu: string | null; ad: string | null; yazar: string | null; turler: string | null; raf: string | null; hedefKitle: string | null; yas: [number | null, number | null] };
  profile: { topics: string[]; topicSource: 'kural' | 'zeki' | null; topicProbability?: number; ageGroups: string[]; evidence: string | null };
  weights: Record<string, number>;
  items: Candidate[];
  excluded: Array<{ personId: string; name: string; reason: string }>;
  total: number;
  collabs: Collab[];
  modelVar: boolean;
};

export type Agg = { collabs: number; published: number; reach: number; engagement: number; spend: number | null; cpe: number | null; disclosureMissing: number };
export type Report = {
  from: string; to: string; total: Agg;
  people: Array<Agg & { personId: string; name: string }>;
  books: Array<Agg & { crmBookId: string | null; bookTitle: string | null }>;
  items: Array<Collab & { periodDay: string }>;
  crm: null | { hata: string } | { kayit: number; toplam: number; items: Array<{ id: string; ad: string | null; tutar: number; hesap: string | null; baslangic: string | null }> };
};

export type PayoutRow = {
  id: string; no: number; collabId: string; collabCode: string; personId: string; personName: string; email: string | null;
  bookTitle: string | null; kindLabel: string; stage: Stage; publishedUrl: string | null; amount: number; status: PayoutStatus;
  statusLabel: string; logoDocNo: string | null; note: string | null; createdBy: string; createdAt: string | null;
  approvedBy: string | null; approvedAt: string | null; paidAt: string | null; paidBy: string | null; owner: string;
};
export type Payouts = { month: string; items: PayoutRow[]; totals: Record<'hazir' | 'onayli' | 'odendi', number>; me: { canApprove: boolean; canPay: boolean; canExport: boolean } };

export type PersonInput = Partial<{
  name: string; email: string; phone: string; city: string; notes: string; topics: string[]; ageGroups: string[];
  contactPref: string | null; doNotContact: boolean; minor: boolean; crmContactId: string | null; feeMin: number | null; feeMax: number | null;
  accounts: Array<{ platform: string; handle: string; url?: string | null }>;
}>;

export type CollabInput = Partial<{
  personId: string; kind: Kind; fee: number | null; crmBookId: string | null; bookCode: string | null; bookTitle: string | null;
  crmOrderNo: string; duePublish: string | null; note: string; repeat: boolean; stage: Stage; reason: string;
  publishedUrl: string | null; publishedAt: string | null; disclosureOk: boolean | null; reach: number | null; engagement: number | null; resultNote: string;
}>;

const B = '/api/v1/influencers';

async function fail(res: Response): Promise<never> {
  const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
  const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
  if (res.status === 401) throw new EngineAuthError();
  if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  throw new Error(msg || httpErrorText(res.status));
}

async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 120_000): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${B}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) return fail(res);
  return (await res.json()) as T;
}

export const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;

export const inflApi = {
  meta: () => send<Meta>('GET', '/meta'),
  board: (mine = false) => send<Board>('GET', `/board${qs({ mine: mine || undefined })}`),
  people: (p: { q?: string; platform?: string; topic?: string; age?: string; idle?: number | null }) =>
    send<{ items: PersonRow[]; total: number }>('GET', `/people${qs(p)}`),
  person: (id: string) => send<PersonDetail>('GET', `/people/${enc(id)}`, undefined, 180_000),
  createPerson: (b: PersonInput) => send<{ id: string; name: string }>('POST', '/people', b),
  updatePerson: (id: string, b: PersonInput) => send<{ id: string; name: string }>('PATCH', `/people/${enc(id)}`, b),
  importCsv: (text: string, filename: string) =>
    send<{ eklenen: number; mevcut: number; olcum: number; satir: number; okunamayan: Array<{ satir: number; neden: string }> }>('POST', '/people/import', { text, filename }, 300_000),
  suggestTopics: (id: string, text: string) =>
    send<{ topic: string | null; label: string | null; probability: number | null; confident: boolean }>('POST', `/people/${enc(id)}/suggest-topics`, { text }),
  addSnapshot: (accountId: string, b: { day?: string; followers?: number | null; posts?: number | null; avgLikes?: number | null; avgComments?: number | null }) =>
    send<unknown>('POST', `/accounts/${enc(accountId)}/snapshots`, b),
  crmContacts: (p: { instagram?: string; youtube?: string; x?: string }) =>
    send<{ items: Array<{ id: string; ad: string | null; instagram: string | null; youtube: string | null; x: string | null; yazar: boolean }> }>('GET', `/crm/contacts${qs(p)}`, undefined, 120_000),
  candidates: (kitap: string, butce?: number | null) => send<Candidates>('GET', `/books/${enc(kitap)}/candidates${qs({ butce: butce ?? undefined })}`, undefined, 300_000),
  explain: (kitap: string, personIds: string[]) =>
    send<{ items: Array<{ personId: string; text: string; source: 'zeki' | 'kural'; dropped: number }> }>('POST', `/books/${enc(kitap)}/candidates/explain`, { personIds }, 600_000),
  bookCollabs: (kitap: string) => send<{ items: Collab[]; published: number; engagement: number; reach: number }>('GET', `/books/${enc(kitap)}/collabs`),
  collab: (id: string) => send<CollabDetail>('GET', `/collabs/${enc(id)}`),
  createCollab: (b: CollabInput) => send<{ id: string; no: number; personName: string; waitingApproval: boolean }>('POST', '/collabs', b),
  updateCollab: (id: string, b: CollabInput) => send<Collab>('PATCH', `/collabs/${enc(id)}`, b),
  approveCollab: (id: string, decision: 'onay' | 'ret', note?: string) => send<unknown>('POST', `/collabs/${enc(id)}/approve`, { decision, note }),
  draft: (id: string, kind: DraftKind) => send<Draft>('POST', `/collabs/${enc(id)}/draft`, { kind }, 600_000),
  editDraft: (id: string, did: string, b: { body: string; subject?: string }) => send<Draft>('PATCH', `/collabs/${enc(id)}/drafts/${enc(did)}`, b),
  approveDraft: (id: string, did: string) => send<Draft>('POST', `/collabs/${enc(id)}/drafts/${enc(did)}/approve`, {}),
  markMailed: (id: string, did: string) => send<Draft & { email: string | null }>('POST', `/collabs/${enc(id)}/mail`, { draftId: did }),
  payouts: (month?: string) => send<Payouts>('GET', `/payouts${qs({ month })}`),
  decidePayout: (id: string, b: { action: 'onayla' | 'ode' | 'geri' | 'iptal'; logoDocNo?: string; paidAt?: string; note?: string }) =>
    send<unknown>('POST', `/payouts/${enc(id)}/decide`, b),
  payoutsUrl: (month?: string) => `${ENGINE_BASE}${B}/payouts/export.xlsx${qs({ month })}`,
  report: (frm: string, to: string) => send<Report>('GET', `/report${qs({ frm, to })}`, undefined, 180_000),
  reportUrl: (frm: string, to: string) => `${ENGINE_BASE}${B}/report/export.xlsx${qs({ frm, to })}`,
};

/* ------------------------------------------------------------------ biçim */

const money2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: 'short', year: 'numeric' });

export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${money2.format(v)} ₺`);
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export function fmtDay(v: string | null | undefined): string {
  if (!v) return '—';
  const d = new Date(v.length <= 10 ? `${v}T00:00:00` : v);
  return Number.isNaN(d.getTime()) ? v : dayFmt.format(d);
}
export function fmtLeft(n: number | null | undefined): string {
  if (n === null || n === undefined) return '';
  if (n === 0) return 'bugün';
  return n > 0 ? `${n} gün kaldı` : `${-n} gün geçti`;
}

/** «1.234,5» ya da «1234.5» → sayı; boşsa null. */
export function parseNum(s: string): number | null {
  const t = s.trim().replace(/\s/g, '').replace(/₺|%/g, '');
  if (!t) return null;
  const norm = t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : t;
  const n = Number(norm);
  return Number.isFinite(n) ? n : null;
}

export const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

export const STAGE_TONE: Record<Stage, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  teklif: 'violet',
  gonderildi: 'muted',
  'icerik-bekleniyor': 'muted',
  onayda: 'warn',
  yayinda: 'ok',
  rapor: 'ok',
  odeme: 'warn',
  kapali: 'muted',
  vazgecildi: 'err',
};

export const BAND_LABEL: Record<Relation['band'], string> = { yok: 'temas yok', soguk: 'soğuk', ilik: 'ılık', sicak: 'sıcak' };
export const PART_LABEL: Record<string, string> = { konu: 'Konu', yas: 'Yaş', performans: 'Geçmiş sonuç', iliski: 'İlişki', tazelik: 'Tazelik', butce: 'Bütçe' };
