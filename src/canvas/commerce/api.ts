import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';
import { XLSX_PARAM, xlsxUrl } from '../components/excel';

/** Rakam uçlarının cevabında sorgu bilgisi (`<SqlInfo k={d.kaynaklar} …/>`). */
export type WithK = { kaynaklar?: Kaynaklar };

/**
 * H3 E-ticaret müşteri yönetimi ekranlarının köprü uçları: /api/v1/commerce/*.
 * Site siparişi T-soft'tan yalnız okunur; ekranda kişi adı yok (müşteri «MÜ-…» etiketiyle), kişisel veri yalnız yetkiyle
 * ve o an okunur. Portal T-soft'a, CRM'e, Logo'ya yazmaz; ileti göndermez.
 */

export type Channel = 'email' | 'sms' | 'call';
export type Segment = 'ilk' | 'aktif' | 'sadik' | 'kayip' | 'siparissiz';
export type Period = 'dun' | 'hafta' | 'ay';
export type TriggerKind = 'yeni-kitap' | 'geri-kazanim' | 'ikinci-siparis' | 'terk-sepeti';
export type RunStatus = 'onay-bekliyor' | 'onayli' | 'geri-gonderildi' | 'aktarildi';

export type Freshness = {
  okAt: string | null; stale: boolean; error: string | null; lastOrder: string | null; full: boolean | null;
  missing: string[]; fields: Record<string, string>; memberError: string | null; orders: number | null;
  invalid: number | null; unkeyed: number | null; members: number | null; olderThanSince: number | null;
};

export type Job = { running: boolean; startedAt: string | null; finishedAt: string | null; error: string | null; result: Record<string, number> | null; full: boolean };

export type Meta = {
  me: { username: string; display: string; canTrigger: boolean; canSettings: boolean; canApprove: boolean; canList: boolean; canPersonal: boolean };
  segments: Record<Segment, string>;
  kinds: Record<TriggerKind, string>;
  runStatuses: Record<RunStatus, string>;
  channels: Record<Channel | 'kvkk', string>;
  excludeLabels: Record<string, string>;
  settings: Settings;
  settingLabels: Record<keyof Settings, string>;
  exportEnabled: boolean;
  requireKvkk: boolean;
  okSources: string[];
  freshness: Freshness;
  job: Job;
  modelVar: boolean;
  tsoftConfigured: boolean;
};

export type Settings = {
  activeDays: number; loyalOrders: number; loyalRevenue: number; controlShare: number; resultWindowDays: number;
  resultLagDays: number; dropPct: number; newBookDays: number; lookbackDays: number; minViews: number;
};

export type WindowStats = {
  siparis: number; ciro: number; sepet: number | null; musteri: number; yeni: number; tekrar: number; iptal: number;
  misafir: number; anahtarsiz: number;
};

export type SegmentCount = { segment: Segment; label: string; musteri: number; ciro: number; siparis: number; pay: number | null };

export type Overview = {
  period: { key: Period; label: string; from: string; to: string; prevFrom: string; prevTo: string };
  cur: WindowStats;
  prev: WindowStats;
  change: Partial<Record<'siparis' | 'ciro' | 'sepet' | 'musteri' | 'yeni', number | null>>;
  top: Array<{ barkod: string; ad: string | null; adet: number; tutar: number; siparis: number }>;
  freshness: Freshness;
  drop: { gun: string; siparis: number; onceki4: number[]; ortalama: number; dusus: number | null; uyari: boolean };
  logo: {
    bagli: boolean; neden?: string; yil?: number; ay?: number; ayAdi?: string; kismiAy?: boolean; veriSonu?: string | null;
    netCiro?: number; siteCiro?: number; fark?: number; farkOrani?: number | null; not?: string; ayKaydi?: string;
    siteDonem?: { from: string; to: string };
  };
  segments: SegmentCount[];
};

export type Move = { from: Segment | null; fromLabel: string; to: Segment; toLabel: string; musteri: number };

export type Rfm = {
  rows: string[]; cols: string[]; matrix: Array<{ r: number; f: number; musteri: number; ciro: number }>;
  segments: SegmentCount[]; moves: { days: number; items: Move[]; kaybettigi: Record<Segment, number> };
  rules: { activeDays: number; loyalOrders: number; loyalRevenue: number };
};

export type CustomerRow = {
  key: string; etiket: string; segment: Segment; segmentLabel: string; siparis: number; ciro: number;
  ilkSiparis: string | null; sonSiparis: string | null; il: string | null; misafir: boolean; uye: boolean; uyelik: string | null;
  r: number | null; f: number | null; m: number | null; segmentTarihi: string | null;
};

export type CustomerCard = CustomerRow & {
  siparisler: Array<{
    no: string; tarih: string | null; durum: string | null; gecerli: boolean; tutar: number; indirim: number | null; kargo: number | null;
    kupon: string | null; odeme: string | null; utmKaynak: string | null; utmKampanya: string | null; misafir: boolean;
    satirlar: Array<{ barkod: string | null; ad: string | null; adet: number; tutar: number; kitap: string | null }>;
  }>;
  iadeIptal: number;
  gecisler: Array<{ from: Segment | null; fromLabel: string; to: Segment; toLabel: string; at: string | null }>;
  kategoriler: Array<{ id: string; ad: string; adet: number }>;
  siteIzni: Array<{ channel: string; status: 'izinli' | 'ret'; at: string | null; detail: string | null }>;
  okur: string | null;
  izin: Record<Channel | 'kvkk', 'izinli' | 'ret' | 'bilinmiyor'> | null;
  kisisel: { ad?: string | null; eposta?: string | null; cep?: string | null; bulunamadi?: boolean } | null;
};

export type FunnelRow = { barkod: string; ad: string | null; goruntulenme: number | null; siparis: number; adet: number; tutar: number; oran: number | null };
export type Funnel = { days: number; coveredDays: number; minViews: number; total: number; page: number; pageSize: number; items: FunnelRow[]; weakCount: number; not: string };

export type Run = {
  id: string; triggerId: string; triggerName: string | null; kind: TriggerKind; kindLabel: string; params: Record<string, unknown>;
  channel: Channel; channelLabel: string; at: string | null; createdBy: string; candidates: number; linked: number; reachable: number;
  target: number; control: number; controlShare: number; excluded: Record<string, number>; status: RunStatus; statusLabel: string;
  approvedBy: string | null; approvedAt: string | null; decisionNote: string | null; exportId: string | null; exportedBy: string | null;
  exportedAt: string | null; exportedCount: number | null;
};

export type Trigger = {
  id: string; name: string; kind: TriggerKind; kindLabel: string; params: Record<string, unknown>; channel: Channel; channelLabel: string;
  controlShare: number; status: string; owner: string; createdAt: string | null; updatedBy: string | null; updatedAt: string | null;
  lastRun: Run | null;
};

export type Preview = {
  candidates: number; linked: number; reachable: number; target: number; control: number; excluded: Record<string, number>;
  info: { aciklama?: string; kitap?: string; dugumAdi?: string }; channel: Channel; kaynaklar?: Kaynaklar;
};

export type NewBook = { barkod: string; ad: string | null; kitap: string; acilis: string | null; dugum: string | null; dugumAdi: string | null };

export type GroupResult = { kisi: number; alan: number; siparis: number; ciro: number; kisiBasinaCiro: number | null };
export type CampaignResult = {
  hedef: GroupResult; kontrol: GroupResult;
  lift: { hedefOran: number | null; kontrolOran: number | null; fark: number | null; alt: number | null; ust: number | null; anlamli: boolean; goreli: number | null };
  ekAlan: number | null; ekCiro: number | null; kesin: boolean; uyarilar: string[]; pencere: { from: string; to: string }; aktarilan: number | null;
};
export type Campaign = {
  id: string; name: string; runId: string; start: string | null; end: string | null; createdBy: string; createdAt: string | null;
  result: CampaignResult | null; resultAt: string | null; final: boolean; comment: string | null; commentAt: string | null; run?: Run;
};

export type Paged<T> = { items: T[]; total: number; page: number; pageSize: number };

const B = '/api/v1/commerce';

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

/** Listeyi CSV olarak indirir; sayılar başlıktan döner. */
async function download(path: string, body: unknown): Promise<{ count: number | null; excluded: number | null }> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${B}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(900_000),
  });
  if (!res.ok) return fail(res);
  const blob = await res.blob();
  const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? (path.includes(XLSX_PARAM) ? 'eticaret-listesi.xlsx' : 'eticaret-listesi.csv');
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
  const n = (h: string) => (res.headers.get(h) != null ? Number(res.headers.get(h)) : null);
  return { count: n('X-Readers-Count'), excluded: n('X-Readers-Excluded') };
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

export const commerceApi = {
  meta: () => send<Meta & WithK>('GET', '/meta'),
  overview: (period: Period) => send<Overview & WithK>('GET', `/overview${qs({ period })}`),
  status: () => send<Job>('GET', '/status'),
  refresh: (full = false) => send<Job & { started: boolean }>('POST', '/refresh', { full }),
  rfm: (days = 30) => send<Rfm & WithK>('GET', `/customers/rfm${qs({ days })}`),
  customers: (segment: string, page = 0, sort = 'son') => send<Paged<CustomerRow> & WithK>('GET', `/customers${qs({ segment, page, sort })}`),
  customer: (key: string, personal = false) => send<CustomerCard & WithK>('GET', `/customers/${enc(key)}${qs({ kisisel: personal })}`, undefined, 300_000),
  funnel: (days: number, page = 0, weak = false) => send<Funnel & WithK>('GET', `/products/funnel${qs({ days, page, zayif: weak })}`),
  newBooks: () => send<{ items: NewBook[]; kaynak: string; not: string | null; gun: number } & WithK>('GET', '/triggers/new-books'),
  triggers: () => send<{ items: Trigger[] } & WithK>('GET', '/triggers'),
  createTrigger: (b: { name: string; kind: TriggerKind; params: Record<string, unknown>; channel: Channel; controlShare: number }) =>
    send<Trigger>('POST', '/triggers', b),
  archiveTrigger: (id: string) => send<Trigger>('PATCH', `/triggers/${enc(id)}`, { archive: true }),
  preview: (id: string) => send<Preview & WithK>('POST', `/triggers/${enc(id)}/preview`, {}, 300_000),
  run: (id: string) => send<Run>('POST', `/triggers/${enc(id)}/run`, {}, 300_000),
  runs: (durum = '', page = 0) => send<Paged<Run> & WithK>('GET', `/runs${qs({ durum, page })}`),
  approve: (id: string, note?: string) => send<Run>('POST', `/runs/${enc(id)}/approve`, { note }),
  reject: (id: string, note: string) => send<Run>('POST', `/runs/${enc(id)}/reject`, { note }),
  exportRun: (id: string, purpose: string, excel = false) => {
    const p = `/runs/${enc(id)}/export`;
    return download(excel ? xlsxUrl(p) : p, { purpose });
  },
  campaigns: () => send<{ items: Campaign[] } & WithK>('GET', '/campaigns'),
  createCampaign: (b: { runId: string; name: string; start?: string; end?: string }) => send<Campaign>('POST', '/campaigns', b),
  campaign: (id: string) => send<Campaign & WithK>('GET', `/campaigns/${enc(id)}`),
  comment: (id: string) => send<Campaign>('POST', `/campaigns/${enc(id)}/comment`, {}, 180_000),
  settings: () => send<{ values: Settings; labels: Record<keyof Settings, string>; defaults: Settings; limits: Record<keyof Settings, [number, number]> }>('GET', '/settings'),
  saveSettings: (b: Partial<Record<keyof Settings, number | null>>) => send<{ values: Settings }>('PUT', '/settings', b),
};

// ------------------------------------------------------------------ biçimler

const dayFmt = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: '2-digit', month: 'short', year: 'numeric' });
const nf = new Intl.NumberFormat('tr-TR');
const money = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
/** Tarih: yalnız gün («2026-09-20» gibi saatsiz değer yerel gün olarak okunur, saat dilimi kaydırmaz). */
export const fmtDay = (iso: string | null | undefined) => {
  if (!iso) return '—';
  const d = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T12:00:00+03:00`) : new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : dayFmt.format(d);
};
export const fmtInt = (n: number | null | undefined) => (n == null ? '—' : nf.format(Math.round(n)));
export const fmtTl = (n: number | null | undefined) => (n == null ? '—' : `${money.format(n)} ₺`);
/** Oran → «%12,5». Payda yoksa tire. */
export const fmtRatio = (r: number | null | undefined, digits = 1) =>
  r == null ? '—' : `%${(r * 100).toLocaleString('tr-TR', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
/** Değişim → «+%4,2» / «−%3,0». */
export const fmtChange = (r: number | null | undefined) => {
  if (r == null) return '—';
  const s = Math.abs(r * 100).toLocaleString('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return `${r >= 0 ? '+' : '−'}%${s}`;
};

export const SEGMENT_TONE: Record<Segment, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  ilk: 'violet',
  aktif: 'ok',
  sadik: 'ok',
  kayip: 'err',
  siparissiz: 'muted',
};
export const RUN_TONE: Record<RunStatus, 'ok' | 'warn' | 'muted' | 'violet'> = {
  'onay-bekliyor': 'warn',
  onayli: 'ok',
  'geri-gonderildi': 'muted',
  aktarildi: 'violet',
};

/** Matris hücresinin yoğunluğu (0–1): en kalabalık hücreye göre. Renk tek başına anlam taşımaz; sayı hücrede yazar. */
export function cellShade(n: number, max: number): number {
  if (!max || n <= 0) return 0;
  return Math.min(1, Math.max(0.08, n / max));
}

/** Tetik parametrelerinin kısa açıklaması (liste kartı için). */
export function paramText(kind: TriggerKind, p: Record<string, unknown>): string {
  if (kind === 'geri-kazanim') return `Son sipariş ${p.minGun}–${p.maxGun} gün önce · en az ${p.minSiparis ?? 1} sipariş`;
  if (kind === 'ikinci-siparis') return `Tek sipariş, ${p.minGun}–${p.maxGun} gün önce`;
  if (kind === 'yeni-kitap') {
    const level: Record<string, string> = { yaprak: 'aynı kategori', altalt: 'alt-alt kategori', alt: 'alt kategori', ana: 'ana kategori' };
    return `Barkod ${p.barkod} · ${level[String(p.duzey)] ?? String(p.duzey)} · en az ${p.minAdet ?? 1} kitap`;
  }
  return '';
}
