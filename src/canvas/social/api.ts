import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** M22 Sosyal medya köprü uçları: /api/v1/social/*. Portal hiçbir platforma paylaşım yapmaz; onaylı gönderi yayına
 *  hazır paket olarak iner, uzman kendi hesabından paylaşıp bağlantıyı girer. */

export type PostStatus = 'fikir' | 'taslak' | 'onayda' | 'onayli' | 'yayinlandi' | 'iptal';
export type Platform = 'instagram' | 'facebook' | 'x' | 'linkedin' | 'tiktok' | 'youtube';
export type MetricKey = 'impressions' | 'reach' | 'likes' | 'comments' | 'shares' | 'saves' | 'followers';

export type Meta = {
  platforms: Record<Platform, string>;
  statuses: Record<PostStatus, string>;
  kinds: Record<string, string>;
  metrics: Record<MetricKey, string>;
  settings: {
    limits: Record<string, number>;
    tagLimits: Record<string, number>;
    opportunityDays: number;
    leadDays: number;
    backlistQuietDays: number;
    backlistMinAgeDays: number;
    defaultHour: string;
    recipientsSet: boolean;
  };
  webWatch: boolean;
  creativeLinked: boolean;
  lastRun: { tarih?: string; eposta?: string; _at?: string | null } | null;
  modelReady: boolean;
  me: { username: string; display: string; canEdit: boolean; canApprove: boolean; canExport: boolean; canCommunity: boolean };
};

export type Account = {
  id: string;
  platform: Platform;
  platformAdi: string;
  handle: string;
  ad: string;
  imprintCrmId: string | null;
  imprintAd: string | null;
  sahip: string | null;
  ton: string | null;
  renk: string | null;
  aktif: boolean;
};

export type AssetRef = { tip: 'studio' | 'creative'; job?: string; sid?: string; id?: string; ad?: string | null; boyut?: string | null; onayli?: boolean };
export type Warning = { kod: string; metin: string };
export type DraftOption = { metin: string; etiketler: string; dusen: Array<{ cumle: string; neden: string }>; karakter: number; uzun: boolean };

export type Post = {
  id: string;
  accountId: string | null;
  account?: Account | null;
  crmBookId: string | null;
  stokKodu: string | null;
  kitapAd: string | null;
  occasionKey: string | null;
  occasionAd: string | null;
  kind: string | null;
  kindAdi: string | null;
  kindSource: 'kullanici' | 'zeki' | null;
  plannedAt: string | null;
  status: PostStatus;
  statusAdi: string;
  text: string | null;
  hashtags: string | null;
  assets: AssetRef[];
  draft: { secenekler: DraftOption[]; dusen: number; zaman: string; kim: string; platform: string } | null;
  publishedUrl: string | null;
  publishedAt: string | null;
  submittedBy: string | null;
  submittedAt: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  note: string | null;
  createdBy: string;
  uyarilar?: Warning[];
  olcumler?: Array<{ id: string; day: string; kaynak: 'dosya' | 'elle' } & Partial<Record<MetricKey, number | null>>>;
  kaynaklar?: Kaynaklar;
};

export type Calendar = {
  from: string;
  to: string;
  items: Post[];
  counts: Partial<Record<PostStatus, number>>;
  unscheduled: Post[];
  total: number;
  onayBekleyen: Post[];
  kaynaklar?: Kaynaklar;
};

export type Book = { kitapId: string | null; stokKodu: string; ad: string | null; yazar: string | null; yayineviId: string | null; yayinevi: string | null; kapak: string | null; ilkYayin: string | null };

export type Content = {
  kitap: Book & { metinler: Array<{ alan: string; ad: string; metin: string }>; youtube: string | null };
  alintilar: { crm: string[]; studyo: string[] };
  gorseller: { studyo: AssetRef[]; studyoHata: string | null; arsiv: { bagli: boolean; items: AssetRef[]; hata?: string } };
  haklar: Array<{ sozlesme: string | null; hak: string | null }>;
  gonderiler: Post[];
  kaynaklar?: Kaynaklar;
};

export type Occasion = {
  key: string;
  ad: string;
  baslangic: string;
  bitis: string;
  kalanGun: number;
  suruyor: boolean;
  yontem: string | null;
  kesinlik: string | null;
  kaynak: string;
  kitapSayisi: number;
  takvimde: number;
  kitaplar: Array<{ bookId: string; ad: string | null; stokKodu: string | null; takvimde: boolean }>;
  uyari: boolean;
};

export type Opportunities = {
  tarih: string;
  gun: number;
  hatalar: string[];
  ozelGunler: Occasion[];
  yeniKitaplar: { baslangic: string; bitis: string; items: Array<Book & { takvimde: boolean }> };
  backlist: {
    veriSonu: string | null;
    pencere: { bas: string; bit: string } | null;
    items: Array<{ sira: number; stokKodu: string; ad: string | null; yazar: string | null; yayinevi: string | null; ilkYayin: string | null; adet12: number; sonGonderi: string | null }>;
    total: number;
    page: number;
    pageSize: number;
    not: string | null;
  };
  basin: { acik: boolean; items: Array<{ baslik: string; url: string; kaynak: string; tarih: string | null; yazar: string; ton: string }> };
  kaynaklar?: Kaynaklar;
};

export type ReportRow = Partial<Record<MetricKey, number>> & { etkilesim: number; oran: number | null; gonderi?: number; gonderiBasina?: number | null };
export type Report = {
  ay: string;
  baslangic: string;
  bitis: string;
  toplam: ReportRow;
  olcuSatiri: number;
  gonderiliOlcu: number;
  hesaplar: Array<ReportRow & { accountId: string; hesap: string; platform: string | null; takipci: number | null; takipciGun: string | null }>;
  turler: Array<ReportRow & { tur: string; turAdi: string }>;
  gonderiDurum: Partial<Record<PostStatus, number>>;
  gonderiSayisi: number;
  onaySuresiSaat: number | null;
  onaySayisi: number;
  yorum: Job | null;
  kaynaklar?: Kaynaklar;
};

export type ImportRow = { id: string; accountId: string; dosya: string; satir: number; eslesen: number; ozet: { kolonlar?: Record<string, string>; atlananKolonlar?: string[]; toplam?: Partial<Record<MetricKey, number>> }; kim: string; zaman: string | null };
export type Job = { id: string; tur: string; durum: 'bekliyor' | 'calisiyor' | 'bitti' | 'hata'; adim: string | null; hata: string | null; sonuc: Record<string, unknown> | null; olusturma: string | null };
export type Event = { id: string; zaman: string | null; kim: string; ne: string; not: string | null; ayrinti: unknown };

const B = '/api/v1/social';

async function fail(res: Response): Promise<never> {
  if (res.status === 401) throw new EngineAuthError();
  const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
  const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
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
    if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;

export type PostInput = Partial<{
  accountId: string | null;
  plannedAt: string | null;
  kind: string | null;
  text: string | null;
  hashtags: string | null;
  assets: AssetRef[];
  stokKodu: string | null;
  kitapAd: string | null;
  crmBookId: string | null;
  occasionKey: string | null;
  occasionAd: string | null;
  publishedUrl: string | null;
}>;

export const socialApi = {
  meta: () => send<Meta>('GET', '/meta'),
  accounts: () => send<{ items: Account[]; total: number; kaynaklar?: Kaynaklar }>('GET', '/accounts'),
  addAccount: (b: Partial<Account>) => send<Account>('POST', '/accounts', b),
  updateAccount: (id: string, b: Partial<Account>) => send<Account>('PATCH', `/accounts/${enc(id)}`, b),
  suggestions: () =>
    send<{ items: Array<{ id: string; ad: string | null; url: string | null; instagram: string | null; ekli: boolean }>; instagramDolu: number; marka: number; kaynaklar?: Kaynaklar }>(
      'GET', '/accounts/crm-suggestions', undefined, 120_000),
  books: (q: string, page = 0) => send<{ items: Book[]; total: number; page: number; pageSize: number; kaynaklar?: Kaynaklar }>('GET', `/books${qs({ q, page })}`),
  content: (stok: string, platform?: string) => send<Content>('GET', `/books/${enc(stok)}/content${qs({ platform })}`, undefined, 180_000),
  calendar: (frm: string, to: string, account?: string) => send<Calendar>('GET', `/calendar${qs({ frm, to, account })}`),
  opportunities: (days?: number, bpage = 0) => send<Opportunities>('GET', `/opportunities${qs({ days, bpage })}`, undefined, 300_000),
  create: (b: PostInput) => send<Post>('POST', '/posts', b),
  post: (id: string) => send<Post>('GET', `/posts/${enc(id)}`),
  update: (id: string, b: PostInput) => send<Post>('PATCH', `/posts/${enc(id)}`, b),
  remove: (id: string) => send<{ ok: boolean }>('DELETE', `/posts/${enc(id)}`),
  act: (id: string, action: 'submit' | 'withdraw' | 'approve' | 'reject' | 'published' | 'cancel' | 'reopen', b: { note?: string; url?: string } = {}) =>
    send<Post>('POST', `/posts/${enc(id)}/${action}`, b),
  draft: (id: string) => send<{ job: Job }>('POST', `/posts/${enc(id)}/draft`, {}),
  jobs: (id: string) => send<{ items: Job[] }>('GET', `/posts/${enc(id)}/jobs`),
  events: (id: string) => send<{ items: Event[]; kaynaklar?: Kaynaklar }>('GET', `/posts/${enc(id)}/events`),
  addMetric: (id: string, b: Partial<Record<MetricKey, number | null>> & { day?: string }) => send<unknown>('POST', `/posts/${enc(id)}/metrics`, b),
  packageUrl: (id: string) => `${ENGINE_BASE}${B}/posts/${enc(id)}/package.zip`,
  imports: () => send<{ items: ImportRow[]; total: number; kaynaklar?: Kaynaklar }>('GET', '/imports'),
  deleteImport: (id: string) => send<{ ok: boolean }>('DELETE', `/imports/${enc(id)}`),
  upload: async (account: string, file: File, gun?: string) => {
    if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
    const res = await fetch(`${ENGINE_BASE}${B}/imports${qs({ account, filename: file.name, gun })}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file,
      signal: AbortSignal.timeout(300_000),
    });
    if (!res.ok) return fail(res);
    return (await res.json()) as { id: string; satir: number; eslesen: number; toplam: Partial<Record<MetricKey, number>>; atlananKolonlar: string[]; atlananSatir: Record<string, number> };
  },
  report: (month: string) => send<Report>('GET', `/report${qs({ month })}`),
  commentary: (month: string) => send<{ job: Job }>('POST', '/report/commentary', { month }),
  reportPdfUrl: (month: string) => `${ENGINE_BASE}${B}/report/export.pdf${qs({ month })}`,
  studioImageUrl: (job: string, sid: string, w = 320) => `${ENGINE_BASE}${B}/studio/${enc(job)}/${enc(sid)}?w=${w}`,
};

/* ------------------------------------------------------------------ biçim ve yardımcılar */

const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export const fmtPct = (v: number | null | undefined) =>
  v === null || v === undefined || !Number.isFinite(v) ? '—' : new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 1 }).format(v);
const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', weekday: 'short', timeZone: 'UTC' });
const shortFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', timeZone: 'UTC' });
const monthFmt = new Intl.DateTimeFormat('tr-TR', { month: 'long', year: 'numeric', timeZone: 'UTC' });
export const utcDay = (iso: string) => {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};
export const isoDay = (d: Date) => d.toISOString().slice(0, 10);
export const addDays = (iso: string, n: number) => isoDay(new Date(utcDay(iso).getTime() + n * 86_400_000));
export const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
/** Haftanın pazartesisi. */
export const mondayOf = (iso: string) => addDays(iso, -((utcDay(iso).getUTCDay() + 6) % 7));
export const fmtDay = (iso: string | null | undefined) => (iso ? dayFmt.format(utcDay(iso)) : '—');
export const fmtShort = (iso: string | null | undefined) => (iso ? shortFmt.format(utcDay(iso)) : '—');
export const fmtMonth = (ym: string) => monthFmt.format(utcDay(`${ym}-01`));
export const fmtStamp = (iso: string | null | undefined) =>
  iso ? new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso)) : '—';
export const timeOf = (planned: string | null) => (planned ? planned.slice(11, 16) : '');

export const STATUS_TONE: Record<PostStatus, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  fikir: 'muted',
  taslak: 'muted',
  onayda: 'warn',
  onayli: 'violet',
  yayinlandi: 'ok',
  iptal: 'err',
};

/** Hesap rengi: hesapta seçilmişse o, yoksa platformun rengi (takvimde hesaplar ayırt edilsin). */
const PLATFORM_COLOR: Record<string, string> = {
  instagram: '#c13584',
  facebook: '#1877f2',
  x: '#111827',
  linkedin: '#0a66c2',
  tiktok: '#0f766e',
  youtube: '#dc2626',
};
export const accountColor = (a: Account | null | undefined) => a?.renk || PLATFORM_COLOR[a?.platform ?? ''] || '#64748b';

/** Metin + etiket uzunluğu: köprüdeki `warnings` ile aynı hesap. */
export const charCount = (text: string | null | undefined, tags: string | null | undefined) =>
  (text ?? '').length + (tags ? tags.length + 1 : 0);
export const tagCount = (tags: string | null | undefined) => (tags ?? '').split(/\s+/).filter((t) => t.startsWith('#')).length;

export const DROP_REASON: Record<string, string> = {
  'alinti-bulunamadi': 'alıntı kaynakta birebir yok',
  'kaynaksiz-rakam': 'kaynaksız rakam',
  'kanitsiz-iddia': 'kanıtsız üstünlük iddiası',
  'teknoloji-adi': 'teknoloji adı',
};

export const EVENT_LABEL: Record<string, string> = {
  olusturuldu: 'Oluşturuldu',
  duzenlendi: 'Düzenlendi',
  'onay-dustu': 'İçerik değişti, onay düştü',
  submit: 'Onaya gönderildi',
  withdraw: 'Onaydan geri çekildi',
  approve: 'Onaylandı',
  reject: 'Geri gönderildi',
  published: 'Yayınlandı işaretlendi',
  cancel: 'İptal edildi',
  reopen: 'Yeniden açıldı',
  'zeki-taslak': 'Zeki AI taslağı yazıldı',
  'zeki-tur': 'Zeki AI içerik türünü etiketledi',
  icgoru: 'İçgörü girildi',
  bildirim: 'Bildirim',
};
