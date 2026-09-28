import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** M21 Dijital pazarlama ve reklam: köprü uçları /api/v1/ads/*. Platformlara hiçbir şey gönderilmez. */

export type Platform = 'google' | 'meta' | 'tiktok' | 'pazaryeri' | 'diger';
export type LinkStatus = 'yok' | 'oneri' | 'onayli';
export type SuggestionStatus = 'yeni' | 'onaylandi' | 'uygulandi' | 'reddedildi' | 'gecersiz';

export type Account = {
  id: string;
  platform: Platform;
  platformAdi: string;
  ad: string;
  paraBirimi: string;
  eslem: Record<string, string> | null;
  sonGun?: string | null;
};

export type Meta = {
  platforms: Record<Platform, string>;
  kinds: Record<string, string>;
  statuses: Record<SuggestionStatus, string>;
  linkStatuses: Record<LinkStatus, string>;
  linkSources: Record<string, string>;
  fields: Record<string, string>;
  required: string[];
  briefStatuses: Record<string, string>;
  approvalKinds: string[];
  settings: {
    ecomChannels: string[];
    stockDays: number | null;
    activeDays: number;
    noDataDays: number;
    perfWindowDays: number;
    rules: Record<string, boolean>;
    m15Channels: Record<string, string>;
    maxUploadMb: number;
  };
  logo: { veriSonu?: string; zaman?: string; pencere?: { bas: string; bit: string }; _at?: string } | null;
  refresh: { durum: 'calisiyor' | 'bitti' | 'hata'; kim?: string; hata?: string; bitti?: string; basladi?: string } | null;
  lastRun: { tarih?: string; _at?: string; logoHata?: string } | null;
  modelReady: boolean;
  accounts: Account[];
  me: { username: string; display: string; canEdit: boolean; canApprove: boolean; canExport: boolean };
};

export type Metrics = {
  harcama: number;
  gosterim: number | null;
  tiklama: number | null;
  donusum: number | null;
  donusumDegeri: number | null;
  tbm: number | null;
  tiklamaOrani: number | null;
  platformRoas: number | null;
};

export type Stock = { bakiye: number; gunlukSatis: number | null; gun: number | null; tarih: string | null };

export type CampaignRow = Metrics & {
  id: string;
  ad: string;
  platform: Platform;
  platformAdi: string;
  hesap: string | null;
  durum: string | null;
  stokKodu: string | null;
  kitapAdi: string | null;
  bag: LinkStatus;
  bagAdi: string;
  bagGuven: number | null;
  seri: string | null;
  sonGun: string | null;
};

export type Campaign = CampaignRow & {
  hesapId: string;
  platformKimlik: string | null;
  kitapId: string | null;
  bagKaynak: string | null;
  bagKaynakAdi: string | null;
  bagAyrinti: { adaylar?: Array<{ stokKodu: string; ad: string | null; yazar: string | null; skor: number }>; not?: string; model?: { olasilik: number | null } } | null;
  bagYapan: string | null;
  ilkGun: string | null;
};

export type Suggestion = {
  id: string;
  tur: string;
  turAdi: string;
  onayGerekir: boolean;
  kampanyaId: string | null;
  kampanya: string | null;
  platformAdi: string | null;
  stokKodu: string | null;
  kitapAdi: string | null;
  veri: Record<string, unknown>;
  gerekce: string;
  zekiNotu: string | null;
  durum: SuggestionStatus;
  durumAdi: string;
  zaman: string;
  karar: string | null;
  kararNotu: string | null;
  uygulayan: string | null;
};

export type BookRow = Metrics & {
  stokKodu: string;
  ad: string | null;
  kampanya: number;
  satis: { eticaretCiro: number; eticaretAdet: number; toplamCiro: number; toplamAdet: number } | null;
  verim: number | null;
  harcamaVeriIcinde: number;
  stok: Stock | null;
  m15: { planlar: string[]; tutar: number } | null;
  yayinDurumu: string | null;
  satisDisi: boolean;
};

export type Overview = {
  donem: { bas: string; bit: string; kanal: string | null };
  veriSonu: string | null;
  verimDonemi: { bas: string; bit: string } | null;
  gosterge: Metrics & { eticaretCiro: number | null; eticaretAdet: number | null; verim: number | null; harcamaVeriIcinde: number };
  digerParaBirimi: Record<string, number>;
  kanallar: Array<Metrics & { kanal: Platform; kanalAdi: string; pay: number | null }>;
  kampanyalar: CampaignRow[];
  kitaplar: BookRow[];
  bagsiz: { harcama: number; pay: number | null };
  gunluk: Array<{ gun: string; harcama: number; eticaretCiro: number | null }>;
  oneriler: Suggestion[];
  uyarilar: string[];
  kaynaklar?: Kaynaklar;
};

export type Preview = {
  dosyaAdi: string;
  baslikSatiri: number;
  kolonlar: string[];
  ornek: Array<Array<string | number>>;
  eslem: Record<string, string>;
  eslemKaynagi: 'kayitli' | 'sozluk' | 'elle';
  eksik: string[];
  satirSayisi: number;
  zeki: Record<string, { kolon: string; olasilik: number | null }>;
  zekiHata?: string;
  deneme?: Trial;
};

export type Trial = {
  satir: number;
  hataSayisi: number;
  hatalar: string[];
  ozetSatiri: number;
  gunlukDegil: number;
  ondalik: string;
  kampanya: number;
  toplam: Record<string, number>;
  bas: string | null;
  bit: string | null;
};

export type ImportRow = {
  id: string;
  hesapId: string;
  hesap: string | null;
  platform: Platform | null;
  dosya: string | null;
  satir: number;
  kampanyaGun: number;
  kampanya: number;
  toplamHarcama: number;
  paraBirimiToplam: Record<string, number>;
  bas: string | null;
  bit: string | null;
  uyarilar: string[];
  yukleyen: string;
  zaman: string;
  gecerliKampanyaGun?: number;
  gecerliHarcama?: number;
};

export type BudgetCell = { ay: string; kanal: Platform; plan: number | null; not: string | null; harcama: number; kalan: number | null; tahmin: number | null; asim: boolean };
export type Budget = {
  yil: number;
  aylar: string[];
  kanallar: Record<Platform, string>;
  hucreler: BudgetCell[];
  m15: {
    satirlar: Array<{ planId: string; plan: string; stokKodu: string | null; kanal: string; kanalAdi: string; tutar: number; bas: string | null; bit: string | null; aylar: Record<string, number> }>;
    ay: Array<{ ay: string; kanal: string; tutar: number }>;
    kanalEsleme: Record<string, string>;
  };
  crm: Array<{ ay: string; tutar: number }>;
  toplam: { plan: number; harcama: number; m15: number; crm: number };
  uyarilar?: string[];
  kaynaklar?: Kaynaklar;
};

export type Brief = {
  id: string;
  stokKodu: string | null;
  kitapAdi: string | null;
  istek: string | null;
  metin: string | null;
  durum: 'hazirlaniyor' | 'taslak' | 'onayli' | 'hata';
  durumAdi: string;
  denetim: { dusenSayisi?: number } | null;
  hata: string | null;
  olusturan: string;
  olusturma: string;
  onaylayan: string | null;
};

export type BookHit = { stokKodu: string; ad: string | null; yazar: string | null; ean: string | null; durum: string | null; satisDisi: boolean };

export type CrmRecords = {
  donem: { bas: string; bit: string };
  reklamPlanlari: {
    toplam: number;
    onaysiz: number;
    donemde: Array<{ id: string; ad: string | null; tutar: number | null; bas: string | null; bit: string | null; durum: string | null; mecra: string | null; tip: string | null; kitaplar: Array<{ stokKodu: string | null; ad: string | null }> }>;
  };
  butceKayitlari: { items: Array<{ id: string; ad: string | null; tipAdi: string | null; tutar: number; baslangic: string | null; bitis: string | null; mecra: string | null; reklam: boolean }>; toplam: number; reklamToplam: number };
  kaynaklar?: Kaynaklar;
};

const B = '/api/v1/ads';

export class RowsError extends Error {
  constructor(message: string, public hatalar: string[], public hataSayisi: number) {
    super(message);
  }
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
  if (res.status === 401) throw new EngineAuthError();
  const j = res.ok ? null : ((await res.json().catch(() => null)) as { detail?: { message?: string; hatalar?: string[]; hataSayisi?: number } | string } | null);
  const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
  if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  if (!res.ok) {
    if (j && typeof j.detail === 'object' && j.detail?.hatalar) throw new RowsError(msg || 'Dosya okunamadı.', j.detail.hatalar, j.detail.hataSayisi ?? 0);
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

/** Dosyayı base64'e çevirir (köprü JSON gövdesiyle alır). */
export async function fileToBase64(file: File): Promise<string> {
  const buf = new Uint8Array(await file.arrayBuffer());
  let bin = '';
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return btoa(bin);
}

export type Period = { frm: string; to: string; kanal?: string };

export const adsApi = {
  meta: () => send<Meta>('GET', '/meta'),
  overview: (p: Period) => send<Overview>('GET', `/overview${qs(p)}`, undefined, 180_000),
  campaigns: (p: Period & { bag?: string; q?: string }) =>
    send<{ items: Array<Campaign>; total: number; bagSayilari: Record<LinkStatus, number>; kaynaklar?: Kaynaklar }>('GET', `/campaigns${qs(p)}`),
  link: (id: string, b: { stokKodu?: string; onayla?: boolean; kaldir?: boolean; seri?: string | null }) => send<Campaign>('PATCH', `/campaigns/${enc(id)}`, b),
  rematch: (id: string) => send<Campaign>('POST', `/campaigns/${enc(id)}/match`, {}, 180_000),
  books: (q: string) => send<{ items: BookHit[]; total: number; shown: number; kaynaklar?: Kaynaklar }>('GET', `/books${qs({ q })}`, undefined, 180_000),
  accounts: () => send<{ items: Account[] }>('GET', '/accounts'),
  newAccount: (b: { platform: Platform; ad: string; paraBirimi?: string }) => send<Account>('POST', '/accounts', b),
  preview: (b: { dosyaAdi: string; icerik: string; hesapId?: string; eslem?: Record<string, string>; baslikSatiri?: number }) => send<Preview>('POST', '/imports/preview', b, 180_000),
  commit: (b: { dosyaAdi: string; icerik: string; hesapId: string; eslem: Record<string, string>; baslikSatiri: number }) =>
    send<ImportRow>('POST', '/imports', b, 300_000),
  imports: () => send<{ items: ImportRow[]; total: number; kaynaklar?: Kaynaklar }>('GET', '/imports'),
  undoImport: (id: string) => send<ImportRow & { silinenKampanyaGun: number }>('DELETE', `/imports/${enc(id)}`),
  budget: (year: number) => send<Budget>('GET', `/budget${qs({ year })}`, undefined, 180_000),
  putBudget: (items: Array<{ ay: string; kanal: Platform; plan: number | null; not?: string | null }>) =>
    send<Budget & { degisen: number }>('PUT', '/budget', { items }),
  suggestions: (durum = 'acik') => send<{ items: Suggestion[]; total: number }>('GET', `/suggestions${qs({ durum })}`),
  decide: (id: string, karar: 'onayla' | 'reddet' | 'uygulandi', not?: string) =>
    send<Suggestion>('POST', `/suggestions/${enc(id)}/decide`, { karar, not }),
  briefs: () => send<{ items: Brief[]; total: number; kaynaklar?: Kaynaklar }>('GET', '/briefs'),
  brief: (id: string) => send<Brief>('GET', `/briefs/${enc(id)}`),
  newBrief: (stokKodu: string, not?: string) => send<Brief>('POST', '/briefs', { stokKodu, not }, 180_000),
  saveBrief: (id: string, b: { metin?: string; onayla?: boolean }) => send<Brief>('PATCH', `/briefs/${enc(id)}`, b),
  deleteBrief: (id: string) => send<{ ok: boolean }>('DELETE', `/briefs/${enc(id)}`),
  crm: (p: Period) => send<CrmRecords>('GET', `/crm${qs(p)}`, undefined, 180_000),
  refresh: () => send<{ basladi: boolean; not?: string }>('POST', '/refresh', {}),
  summary: (p: Period) => send<{ metin: string | null; dusenSayisi: number }>('POST', '/report/summary', p, 300_000),
  pdfUrl: (p: Period) => `${ENGINE_BASE}${B}/report/export.pdf${qs(p)}`,
  xlsxUrl: (p: Period) => `${ENGINE_BASE}${B}/report/export.xlsx${qs(p)}`,
};

/* ------------------------------------------------------------------ biçim */

const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const dec2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${int0.format(v)} ₺`);
export const fmtMoney2 = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${dec2.format(v)} ₺`);
export const fmtRatio = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? '—' : dec2.format(v));
export const fmtPct = (v: number | null | undefined) =>
  v === null || v === undefined || !Number.isFinite(v) ? '—' : new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 1 }).format(v);

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
const utc = (iso: string) => {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};
export const fmtDay = (iso: string | null | undefined) => (iso ? dayFmt.format(utc(iso)) : '—');
export const monthName = (ym: string) =>
  new Intl.DateTimeFormat('tr-TR', { month: 'long', timeZone: 'UTC' }).format(utc(`${ym}-01`));

export const iso = (d: Date) => d.toISOString().slice(0, 10);

export const SUGGESTION_TONE: Record<SuggestionStatus, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  yeni: 'warn',
  onaylandi: 'violet',
  uygulandi: 'ok',
  reddedildi: 'muted',
  gecersiz: 'muted',
};

export const LINK_TONE: Record<LinkStatus, 'ok' | 'warn' | 'muted'> = { onayli: 'ok', oneri: 'warn', yok: 'muted' };
