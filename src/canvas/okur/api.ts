import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** M37 Okur topluluğu ekranlarının köprü uçları: /api/v1/okur/*. Yalnız sayı; kişi adı, e-posta, telefon gelmez. */

export type SegmentState = 'taslak' | 'onay_bekliyor' | 'onaylandi' | 'reddedildi' | 'suresi_doldu';
export type Channel = 'eposta' | 'sms' | 'ikisi' | 'yok';
export type ProgramType = 'okuma_kulubu' | 'imza_gunu' | 'anket' | 'cevrimici';
export type ProgramState = 'taslak' | 'planlandi' | 'tamamlandi' | 'iptal';
export type ReviewState = 'cevapsiz' | 'taslak' | 'cevaplandi';
export type Flag = 'ozel' | 'degil' | 'bilinmiyor';

export type Me = { username: string; display: string; canSegment: boolean; canApprove: boolean; canProgram: boolean; canReview: boolean; canExport: boolean };

export type OkurMeta = {
  segmentDurumlari: Record<SegmentState, string>;
  kanallar: Record<Channel, string>;
  programTurleri: Record<ProgramType, string>;
  programDurumlari: Record<ProgramState, string>;
  yorumDurumlari: Record<ReviewState, string>;
  isaretler: Record<Flag, string>;
  ayarlar: { sensitiveOpen: boolean; flagProb: number; segmentMaxDays: number; purposeMin: number; programRemindDays: number; eventsExcludeVisits: boolean; eventTypes: string[] };
  me: Me;
  cekirdek: { bagli: boolean; mesaj: string | null; kuralAlanlari: unknown[] };
  modelVar: boolean;
};

export type InventoryRow = {
  kaynak: string; kayitTipi: string; toplam: number; kvkkOnayli: number | null; iysOnayli: number | null; epostaIzinli: number | null;
  smsIzinli: number | null; ilgiAlaniDolu: number | null; silinebilir: number | null; cocukOlasi: number | null;
};
export type Unavailable = { bagli: false; mesaj: string };
export type Inventory = { bagli: true; toplam: number; tekil: number | null; satirlar: InventoryRow[]; tazelik: Array<{ kaynak?: string; sonOkuma?: string }> } | Unavailable;
export type ConsentItem = { tur: string; ad: string; sayi: number; aciklama?: string | null };
export type Consent = ({ bagli: true; items: ConsentItem[]; toplam: number; onceki?: number | null } | (Unavailable & { items?: ConsentItem[] })) & { kaynaklar?: Kaynaklar };
export type TrendPoint = { tarih: string; toplam?: number | null; kvkkOnayli?: number | null; iysOnayli?: number | null; epostaIzinli?: number | null; smsIzinli?: number | null; izinCeliskisi?: number | null };

export type Program = {
  id: string; tur: ProgramType; turAdi: string; ad: string; tarih: string | null; saat: string | null; kalanGun: number | null;
  sehir: string | null; yer: string | null; kitapId: string | null; kitapAdi: string | null; yazarAdi: string | null;
  segmentId: string | null; segment: { id: string; ad: string; durum: SegmentState; durumAdi: string; onayli: boolean; toplam: number | null; izinli: number | null } | null;
  durum: ProgramState; durumAdi: string; duyuruTaslagi: string | null; duyuruKaynak: 'zeki' | 'elle' | null; katilimci: number | null;
  sorumlu: string | null; notlar: string | null; olusturan: string; olusturma: string | null; guncelleyen: string | null; guncelleme: string | null;
  kaynaklar?: Kaynaklar;
};

export type Overview = {
  envanter: Inventory;
  izin: Consent;
  segmentSayilari: Partial<Record<SegmentState, number>>;
  yaklasanProgramlar: Program[];
  yorum: (Record<ReviewState | 'toplam', number> & { zaman?: string }) | null;
  egilim: { noktalar: TrendPoint[] };
  kaynaklar?: Kaynaklar;
};

export type Measure = { toplam: number; izinli: number | null; eposta: number | null; sms: number | null; zaman?: string | null };
export type Kvkk = { ok: boolean; engel: Array<{ id: string; ad: string; isaret: Flag; mesaj: string }>; uyari: Array<{ id: string; ad: string; isaret: Flag; mesaj: string }> };

export type Segment = {
  id: string; ad: string; kural: Record<string, unknown>; kuralCumlesi: string | null; amac: string | null; kanal: Channel; kanalAdi: string;
  sureBitis: string | null; durum: SegmentState; durumAdi: string; surum: number; ilgiAlanlari: string[]; sonOlcum: Measure | null;
  yazan: string; yazmaZamani: string | null; guncelleyen: string | null; guncelleme: string | null; gonderen: string | null;
  gondermeZamani: string | null; onaylayan: string | null; onayZamani: string | null; onayNotu: string | null;
  olcumler?: Array<{ tarih: string; toplam: number; izinli: number | null; eposta: number | null; sms: number | null }>;
  programlar?: Array<{ id: string; ad: string; tarih: string | null; durum: ProgramState }>;
  kvkk?: Kvkk;
  kaynaklar?: Kaynaklar;
};

export type Interest = { id: string; ad: string; okur: number | null; isaret: Flag; isaretAdi: string; olasilik: number | null; isaretKaynak: 'zeki' | 'insan' | null; kararVeren: string | null; gerekce: string | null; kullanilabilir: boolean };

export type Review = {
  id: string; productId: string | null; urun: string | null; puan: number | null; tarih: string | null; onayli: boolean; baslik: string | null;
  metin: string; sitedeCevap: boolean; durum: ReviewState; durumAdi: string; taslak: string | null; taslakKaynak: 'zeki' | 'elle' | null;
  taslakYazan: string | null; taslakTarih: string | null;
};

export type EventRow = { id: string; ad: string | null; durum: number | null; durumAdi: string | null; tarih: string | null; tip: string; il: string | null; yazar: string | null; kitap: string | null; katilimci: number | null; satilan: number | null };
export type EventGroup = { ad: string; etkinlik: number; katilimci: number; satilan: number };
export type EventsSummary = {
  yil: number; yillar: number[]; toplam: number; durumlar: Record<string, number>; tamamlanan: number; katilimci: number; satilan: number;
  katilimciBos: number; tipler: EventGroup[]; iller: EventGroup[]; yazarlar: EventGroup[]; etkinlikler: EventRow[]; ziyaretHaric: boolean; tipSuzgeci: string[];
  kaynaklar?: Kaynaklar;
};

export type Book = { id: string; ad: string | null; stokKodu: string | null; yazar: string | null };

export type SegmentInput = Partial<{ ad: string; kural: Record<string, unknown>; amac: string; kanal: Channel; sureBitis: string | null }>;
export type ProgramInput = Partial<{
  tur: ProgramType; ad: string; tarih: string | null; saat: string | null; sehir: string; yer: string; kitapId: string | null; kitapAdi: string | null;
  yazarAdi: string; segmentId: string | null; durum: ProgramState; duyuruTaslagi: string; katilimci: number | null; sorumlu: string; notlar: string;
}>;

const B = '/api/v1/okur';

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

export const okurApi = {
  meta: () => send<OkurMeta>('GET', '/meta'),
  overview: () => send<Overview>('GET', '/overview'),
  consent: () => send<Consent>('GET', '/consent-health'),
  categories: () => send<{ bagli: boolean; mesaj?: string; items: Interest[]; hassasAcik: boolean; sayilar?: Record<Flag, number>; kaynaklar?: Kaynaklar }>('GET', '/categories'),
  classify: () => send<Record<string, number>>('POST', '/categories/classify', {}, 600_000),
  flag: (id: string, b: { ad: string; isaret: Flag; gerekce: string }) => send<{ isaret: Flag }>('POST', `/categories/${enc(id)}/decision`, b),

  segments: (durum = '') => send<{ items: Segment[]; total: number; durumSayilari: Partial<Record<SegmentState, number>>; kaynaklar?: Kaynaklar }>('GET', `/segments${qs({ durum })}`),
  segment: (id: string) => send<Segment>('GET', `/segments/${enc(id)}`),
  createSegment: (b: SegmentInput) => send<Segment>('POST', '/segments', b),
  updateSegment: (id: string, b: SegmentInput) => send<Segment>('PATCH', `/segments/${enc(id)}`, b),
  deleteSegment: (id: string) => send<{ ok: boolean }>('DELETE', `/segments/${enc(id)}`),
  previewRule: (kural: Record<string, unknown>) => send<{ olcum: Measure | null; kvkk: Kvkk; kuralCumlesi: string | null; kaynaklar?: Kaynaklar }>('POST', '/segments/preview-rule', { kural }, 300_000),
  measure: (id: string) => send<Segment>('POST', `/segments/${enc(id)}/preview`, {}, 300_000),
  submit: (id: string) => send<Segment>('POST', `/segments/${enc(id)}/submit`, {}),
  withdraw: (id: string) => send<Segment>('POST', `/segments/${enc(id)}/withdraw`, {}),
  decide: (id: string, karar: 'onayla' | 'reddet', not: string) => send<Segment>('POST', `/segments/${enc(id)}/decision`, { karar, not }),

  programs: (p: { from?: string; to?: string; durum?: string; tur?: string } = {}) => send<{ items: Program[]; total: number; kaynaklar?: Kaynaklar }>('GET', `/programs${qs(p)}`),
  createProgram: (b: ProgramInput) => send<Program>('POST', '/programs', b),
  updateProgram: (id: string, b: ProgramInput) => send<Program>('PATCH', `/programs/${enc(id)}`, b),
  deleteProgram: (id: string) => send<{ ok: boolean }>('DELETE', `/programs/${enc(id)}`),
  draftProgram: (id: string) => send<Program>('POST', `/programs/${enc(id)}/draft`, {}, 300_000),
  books: (q: string) => send<{ items: Book[] }>('GET', `/books${qs({ q })}`),
  events: (yil?: number) => send<EventsSummary>('GET', `/events-summary${qs({ yil })}`, undefined, 180_000),

  reviews: (durum = '', yenile = false) => send<{ items: Review[]; sayilar: Record<ReviewState | 'toplam', number>; seo: { yorum: number; urun: number } | null; kaynaklar?: Kaynaklar }>('GET', `/reviews${qs({ durum, yenile: yenile || undefined })}`, undefined, 180_000),
  draftReview: (id: string) => send<{ id: string; durum: ReviewState; taslak: string | null }>('POST', `/reviews/${enc(id)}/draft`, {}, 300_000),
  markReview: (id: string, b: { durum: ReviewState; taslak?: string; productId?: string | null }) => send<{ id: string; durum: ReviewState; taslak: string | null }>('POST', `/reviews/${enc(id)}/mark`, b),
};

const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const pct0 = new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 0 });

export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
/** Pay / toplam; toplam yoksa ya da pay bilinmiyorsa tire. */
export const fmtShare = (part: number | null | undefined, total: number | null | undefined) =>
  part === null || part === undefined || !total ? '—' : pct0.format(part / total);
export function fmtDay(v: string | null | undefined): string {
  if (!v) return '—';
  const d = new Date(`${v.slice(0, 10)}T12:00:00`);
  return Number.isNaN(d.getTime()) ? v : d.toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric' });
}

export const SEGMENT_TONE: Record<SegmentState, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  taslak: 'muted', onay_bekliyor: 'warn', onaylandi: 'ok', reddedildi: 'err', suresi_doldu: 'muted',
};
export const PROGRAM_TONE: Record<ProgramState, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  taslak: 'muted', planlandi: 'violet', tamamlandi: 'ok', iptal: 'err',
};
export const REVIEW_TONE: Record<ReviewState, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  cevapsiz: 'warn', taslak: 'violet', cevaplandi: 'ok',
};
export const FLAG_TONE: Record<Flag, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = { degil: 'ok', ozel: 'err', bilinmiyor: 'warn' };
