import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** M24 Katalog ve bülten: /api/v1/catalog-newsletter/*. Portal toplu e-posta göndermez; segment ucu yalnız sayı döner. */

export type CatalogStatus = 'taslak' | 'onayda' | 'onayli' | 'yayinda' | 'arsiv';
export type NewsletterStatus = 'taslak' | 'onayda' | 'onayli' | 'gonderildi' | 'arsiv';

export type PoolStatus = {
  okuma: string | null;
  logoSon: string | null;
  kitap: number;
  notlar: string[];
  fiyatFarkli: number | null;
  tsoftUrun: number | null;
  yenileniyor: boolean;
  hata: string | null;
};

export type SpecialDay = { key: string; ad: string; baslangic: string | null; bitis: string | null; tarihNeden: string | null; kitapSayisi: number };

export type Meta = {
  turler: Record<string, string>;
  durumlar: Record<CatalogStatus, string>;
  bultenDurumlari: Record<NewsletterStatus, string>;
  fiyatKaynaklari: Record<string, string>;
  stokKaynaklari: Record<string, string>;
  ayarlar: {
    fiyatKaynagi: string;
    fiyatGerekce: string;
    stokKaynagi: string;
    kritikAy: number;
    hedefAy: number;
    yeniAy: number;
    agirliklar: Record<string, number>;
    kelime: number;
    pdfSayfa: number;
    kvkkSart: boolean;
    konuSayisi: number;
    izinKurali: string;
  };
  havuz: PoolStatus;
  ozelGunler: SpecialDay[];
  hedefler: string[];
  markalar: string[];
  ilgiBayraklari: Record<string, string>;
  ilgiAlanlari: Array<{ id: string; ad: string; etkin: boolean }>;
  bekleyen: { katalogOnayda: number; bultenOnayda: number };
  sonKosu: { zaman?: string; kritik?: number; eposta?: string; havuzHata?: string } | null;
  modelVar: boolean;
  me: { username: string; display: string; canCatalog: boolean; canNewsletter: boolean; canApprove: boolean; canSegment: boolean; canExport: boolean };
  kaynaklar?: Kaynaklar;
};

export type Filters = {
  hedef: string[];
  yasMin: number | null;
  yasMax: number | null;
  marka: string[];
  anahtar: string | null;
  ozelGun: string | null;
  yalnizOzelGun: boolean;
  yalnizYeni: boolean;
};

export type Alert = { tur: string; seviye: 'kritik' | 'bilgi'; baslik: string; metin: string; deger: unknown };

export type CatalogRow = {
  id: string;
  tur: string;
  turAdi: string;
  baslik: string;
  donem: string | null;
  tema: string | null;
  durum: CatalogStatus;
  durumAdi: string;
  fiyatKaynagi: string;
  fiyatKaynagiAdi: string;
  stokTarihi: string | null;
  guncelleme: string | null;
  olusturan: string;
  kitap: number;
  kritik: number;
  bilgi: number;
  oneCikan: number;
};

export type CatalogItem = {
  crmKitapId: string;
  stokKodu: string | null;
  ad: string | null;
  yazar: string | null;
  marka: string | null;
  isbn: string | null;
  hedef: string | null;
  yasBas: number | null;
  yasBit: number | null;
  sira: number;
  oneCikan: boolean;
  sayfa: string | null;
  gerekce: string | null;
  gerekceZeki: string | null;
  metin: string | null;
  metinKaynagi: string | null;
  metinVar: boolean;
  fiyat: number | null;
  fiyatDayanak: number | null;
  stokAdet: number | null;
  stokAy: number | null;
  satisYok: boolean;
  yillik: number | null;
  kapak: string | null;
  webUrl: string | null;
  uyarilar: Alert[];
  kritik: number;
};

export type Catalog = Omit<CatalogRow, 'kitap' | 'kritik' | 'bilgi' | 'oneCikan'> & {
  suzgec: Filters;
  gonderen: string | null;
  onaylayan: string | null;
  onayZamani: string | null;
  not: string | null;
  kitaplar: CatalogItem[];
  ozet: { kitap: number; oneCikan: number; kritik: number; uyariliKitap: number; bilgi: number; fiyatsiz: number; kapaksiz: number };
  havuz: { okuma: string | null; logoSon: string | null; notlar: string[] } | null;
  kaynaklar?: Kaynaklar;
};

export type Candidate = {
  id: string;
  stok: string | null;
  ad: string | null;
  yazar: string | null;
  marka: string | null;
  hedef: string | null;
  ilkYayin: string | null;
  fiyat: number | null;
  stokAdet: number | null;
  stokAy: number | null;
  satisYok: boolean;
  yillik: number | null;
  puan: number;
  parcalar: Record<string, number | null>;
  gerekce: string;
  ozelGun: boolean;
};

export type Suggestions = {
  items: Candidate[];
  total: number;
  elenen: Record<string, number>;
  page: number;
  pageSize: number;
  ilgiEslesen?: number | null;
  kaynaklar?: Kaynaklar;
};

export type Job = { id: string; tur: string; durum: 'bekliyor' | 'calisiyor' | 'bitti' | 'hata'; adim: string | null; sonuc: Record<string, number> | null; hata: string | null };

export type Segment = { ilgiBayraklari: string[]; ilgiAlanlari: string[]; yasMin: number | null; yasMax: number | null; haberdar: boolean };

export type SegmentCount = {
  izinli: number;
  aday: number;
  izinsiz: number;
  dagilim: { topluEpostaReddi: number; epostaReddi: number; iysOnayiYok: number; adresYok: number; kvkkOnayli: number; izinliVeKvkk: number };
  kural: string;
  kvkkSart: boolean;
  tanim: string;
  zaman: string;
  kaynaklar?: Kaynaklar;
};

export type Result = {
  id: string;
  kaynak: 'crm' | 'dosya' | 'elle';
  gonderilen: number | null;
  acilan: number | null;
  tiklanan: number | null;
  abonelikIptal: number | null;
  geriDonen: number | null;
  not: string | null;
  kim: string | null;
  zaman: string | null;
  acilmaOrani: number | null;
  tiklamaOrani: number | null;
};

export type NewsletterRow = {
  id: string;
  baslik: string;
  segment: Segment;
  segmentBuyuklugu: number | null;
  ozelGun: string | null;
  planlanan: string | null;
  durum: NewsletterStatus;
  durumAdi: string;
  konu: string | null;
  gonderimTarihi: string | null;
  guncelleme: string | null;
  kitap: number;
  sonuc: Result | null;
};

export type NewsletterItem = {
  crmKitapId: string;
  stokKodu: string | null;
  ad: string | null;
  yazar: string | null;
  sira: number;
  gerekce: string | null;
  metin: string | null;
  metinKaynagi: string | null;
  fiyat: number | null;
  kapak: string | null;
  webUrl: string | null;
  satistanKalkti: boolean;
  havuzdaYok: boolean;
};

export type Newsletter = Omit<NewsletterRow, 'kitap' | 'sonuc'> & {
  segmentDagilim: { aday: number; izinsiz: number; dagilim: SegmentCount['dagilim']; kural: string } | null;
  segmentZamani: string | null;
  konular: string[];
  giris: string | null;
  dusen: Array<{ cumle: string; neden: string; yer?: string }>;
  gonderen: string | null;
  onaylayan: string | null;
  not: string | null;
  crmKampanya: string | null;
  kitaplar: NewsletterItem[];
  html: string | null;
  sonuclar: Result[];
  kaynaklar?: Kaynaklar;
};

export type CrmCampaign = {
  id: string;
  ad: string | null;
  tur: string | null;
  etkin: boolean;
  baslangic: string | null;
  bitis: string | null;
  olusturma: string | null;
  toplam: number | null;
  okunan: number | null;
  tiklanan: number | null;
  karaListe: number | null;
  gonderimKaydi: number;
  sonGonderim: string | null;
};

export type Report = {
  items: Array<{ id: string; baslik: string; durumAdi: string; gonderimTarihi: string | null; segmentBuyuklugu: number | null; konu: string | null; crmKampanya: string | null; sonuc: Result | null }>;
  toplam: { gonderilen: number; acilan: number; tiklanan: number; acilmaOrani: number | null; tiklamaOrani: number | null; bulten: number };
  crm: CrmCampaign[] | null;
  crmHata?: string;
  kaynaklar?: Kaynaklar;
};

const B = '/api/v1/catalog-newsletter';

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
  const j = res.ok ? null : ((await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null);
  const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
  if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  if (!res.ok) throw new Error(msg || httpErrorText(res.status));
  return (await res.json()) as T;
}

const enc = encodeURIComponent;

export const cnApi = {
  meta: () => send<Meta>('GET', '/meta'),
  refreshPool: () => send<{ started: boolean }>('POST', '/pool/refresh', {}),
  catalogs: (durum: string) => send<{ items: CatalogRow[]; total: number; kaynaklar?: Kaynaklar }>('GET', `/catalogs?durum=${enc(durum)}`),
  createCatalog: (b: { tur: string; baslik: string; donem?: string; tema?: string; fiyatKaynagi?: string; suzgec?: Partial<Filters> }) =>
    send<Catalog>('POST', '/catalogs', b),
  catalog: (id: string) => send<Catalog>('GET', `/catalogs/${enc(id)}`),
  updateCatalog: (id: string, b: Partial<{ baslik: string; tur: string; donem: string; tema: string; fiyatKaynagi: string; suzgec: Filters }>) =>
    send<Catalog>('PATCH', `/catalogs/${enc(id)}`, b),
  deleteCatalog: (id: string) => send<{ ok: boolean }>('DELETE', `/catalogs/${enc(id)}`),
  suggest: (id: string, page: number, suzgec?: Filters) => send<Suggestions>('POST', `/catalogs/${enc(id)}/suggest`, { page, suzgec }, 180_000),
  setItems: (id: string, items: Array<{ crmKitapId: string; oneCikan?: boolean; sayfa?: string | null; gerekce?: string; metin?: string | null }>) =>
    send<Catalog>('PUT', `/catalogs/${enc(id)}/items`, { items }),
  accept: (id: string, bookId: string, tur: string) => send<Catalog>('POST', `/catalogs/${enc(id)}/items/${enc(bookId)}/accept`, { tur }),
  zeki: (id: string, o: { metin: boolean; gerekce: boolean; yeniden?: boolean }) => send<Job>('POST', `/catalogs/${enc(id)}/zeki`, o),
  job: (id: string) => send<Job>('GET', `/jobs/${enc(id)}`),
  catalogAction: (id: string, action: string, note?: string) => send<Catalog>('POST', `/catalogs/${enc(id)}/${action}`, { note }),
  xlsxUrl: (id: string) => `${ENGINE_BASE}${B}/catalogs/${enc(id)}/export.xlsx`,
  packageUrl: (id: string) => `${ENGINE_BASE}${B}/catalogs/${enc(id)}/package.zip`,
  pdfUrl: (id: string, perPage: number) => `${ENGINE_BASE}${B}/catalogs/${enc(id)}/preview.pdf?perPage=${perPage}`,

  newsletters: (durum: string) => send<{ items: NewsletterRow[]; total: number; kaynaklar?: Kaynaklar }>('GET', `/newsletters?durum=${enc(durum)}`),
  createNewsletter: (b: { baslik: string; ozelGun?: string | null; planlanan?: string | null; segment?: Segment }) => send<Newsletter>('POST', '/newsletters', b),
  newsletter: (id: string) => send<Newsletter>('GET', `/newsletters/${enc(id)}`),
  updateNewsletter: (id: string, b: Partial<{ baslik: string; segment: Segment; ozelGun: string | null; planlanan: string | null; konu: string; giris: string; crmKampanya: string; gonderimTarihi: string }>) =>
    send<Newsletter>('PATCH', `/newsletters/${enc(id)}`, b),
  deleteNewsletter: (id: string) => send<{ ok: boolean }>('DELETE', `/newsletters/${enc(id)}`),
  count: (segment: Segment, newsletterId?: string) => send<SegmentCount>('POST', '/segments/count', { segment, newsletterId }, 180_000),
  suggestNl: (id: string, page: number) => send<Suggestions>('POST', `/newsletters/${enc(id)}/suggest`, { page }, 180_000),
  setNlItems: (id: string, items: Array<{ crmKitapId: string; gerekce?: string; metin?: string | null }>) =>
    send<Newsletter>('PUT', `/newsletters/${enc(id)}/items`, { items }),
  draft: (id: string) => send<Job>('POST', `/newsletters/${enc(id)}/draft`, {}),
  nlAction: (id: string, action: string, note?: string) => send<Newsletter>('POST', `/newsletters/${enc(id)}/${action}`, { note }),
  addResult: (id: string, b: { kaynak: 'dosya' | 'elle' | 'crm'; dosya?: string; sayilar?: Record<string, number | null>; not?: string }) =>
    send<Result>('POST', `/newsletters/${enc(id)}/results`, b),
  deleteResult: (id: string, rid: string) => send<{ ok: boolean }>('DELETE', `/newsletters/${enc(id)}/results/${enc(rid)}`),
  htmlUrl: (id: string) => `${ENGINE_BASE}${B}/newsletters/${enc(id)}/html`,
  report: () => send<Report>('GET', '/report', undefined, 180_000),
};

/* ------------------------------------------------------------------ biçim */

const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const dec1 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
const money = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export const fmtMonths = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${dec1.format(v)} ay`);
export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${money.format(v)} ₺`);
export const fmtPct = (v: number | null | undefined) =>
  v === null || v === undefined || !Number.isFinite(v) ? '—' : new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 1 }).format(v);
const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
export const fmtDay = (iso: string | null | undefined) => {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return dayFmt.format(new Date(Date.UTC(y, m - 1, d)));
};
export const fmtStamp = (iso: string | null | undefined) =>
  iso ? new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso)) : '—';

export const STATUS_TONE: Record<string, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  taslak: 'muted',
  onayda: 'warn',
  onayli: 'ok',
  yayinda: 'violet',
  gonderildi: 'violet',
  arsiv: 'muted',
};

export const DROP_REASON: Record<string, string> = {
  'alinti-bulunamadi': 'alıntı kaynakta birebir yok',
  'kaynaksiz-rakam': 'kaynaksız rakam',
  'kanitsiz-iddia': 'kanıtsız üstünlük iddiası',
  'teknoloji-adi': 'teknoloji adı',
};

export const EMPTY_FILTERS: Filters = { hedef: [], yasMin: null, yasMax: null, marka: [], anahtar: null, ozelGun: null, yalnizOzelGun: false, yalnizYeni: false };
export const EMPTY_SEGMENT: Segment = { ilgiBayraklari: [], ilgiAlanlari: [], yasMin: null, yasMax: null, haberdar: false };
