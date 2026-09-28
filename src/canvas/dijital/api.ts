import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** M36 Dijital yayın ve e-kitap ekranlarının köprü uçları: /api/v1/dijital/*. */

export type Right = 'var' | 'kismi' | 'incele' | 'eksik' | 'yok' | 'koruma_disi' | 'set' | 'kitap_degil';
export type ListingState = 'bilinmiyor' | 'hazirlaniyor' | 'yuklendi' | 'yayinda' | 'reddedildi' | 'kaldirildi';
export type Format = 'ekitap' | 'sesli';

export type Me = {
  username: string; display: string; admin: boolean; canWrite: boolean; canImport: boolean; canRights: boolean;
  canPrice: boolean; canExport: boolean; canSales: boolean;
};

export type RefreshInfo = {
  ok?: boolean; at?: string; _at?: string; sure?: number; kitap?: number; notlar?: string[]; error?: string; hakKaynagi?: string;
  running?: boolean; since?: number | null;
};

export type Meta = {
  haklar: Record<Right, string>;
  bicimler: Record<Format, string>;
  platformDurumlari: Record<ListingState, string>;
  platformTurleri: Record<string, string>;
  dagitim: Record<string, string>;
  studyo: Record<string, string>;
  kararlar: Record<string, string>;
  notAdlari: Record<string, string>;
  crmAlanlari: Record<string, string>;
  ayarlar: { oppMinQty: number; audioMinQty: number; audioGenres: string[]; matchMinProb: number; importMaxMb: number };
  okuma: RefreshInfo;
  modelVar: boolean;
  me: Me;
  kaynaklar?: Kaynaklar;
};

export type Chip = { platformId: number; platform: string; tur: string; durum: ListingState; durumAdi: string; tarih: string | null };

export type TitleRow = {
  kitapId: string; ad: string | null; yazar: string | null; stokKodu: string | null; isbn: string | null; eIsbn: string | null;
  ekitapStokKodu: string | null; ekitapBarkod: string | null; tip: number | null; tipAdi: string | null; yayinDurumu: string | null;
  hedefKitle: string | null; epubCrm: boolean; uretimDurumu: string | null; studioDurumu: string; studioDurumuAdi: string;
  studioDenetim: string | null; hakEkitap: Right | null; hakEkitapAdi: string | null; hakSesli: Right | null; hakSesliAdi: string | null;
  hakNotu: boolean; ekitapVar: boolean; sesliVar: boolean; basiliFiyat: number | null; dijitalFiyat: number | null;
  basili12Adet: number | null; logoDijital12Adet: number | null; firsatPuani: number | null; sesliFirsatPuani: number | null;
  baskiDegisim: { tarih: string; tur: string } | null; platformlar: Chip[];
};

export type Contract = {
  id: string; ad: string | null; taraflar: string[]; yururlukte: boolean; bitis: string | null; suresiz: boolean; ekitap: boolean;
  sesli: boolean; zkitap: boolean; iletim: boolean; korumaDisi: boolean; not: string | null;
  notOkuma: { sonuc: string | null; sonucAdi: string; olasilik: number | null } | null;
  hakHaritasi?: HakHaritasi | null;
};

/** M54 ile ortak yapılandırılmış hak haritası (alanlar alıntılı; onay telif biriminde). */
export type HakHaritasi = {
  alanlar: Record<string, unknown>; ozet: string; durum: 'oneri' | 'onayli' | 'reddedildi'; durumAdi: string;
  kaynak: 'zeki' | 'kural' | 'insan'; onayli: boolean;
};

export type TitleDetail = TitleRow & {
  ean: string | null; turler: string | null; ilkYayin: string | null; uretimTarih: string | null; studioIs: string | null;
  studioEIsbn: string | null; hakEkitapGerekce: string | null; hakSesliGerekce: string | null; hakKaynak: string;
  sozlesmeler: Contract[]; basili12Ciro: number | null; logoDijital12Ciro: number | null; firsatGerekcesi: string | null;
  sesliFirsatGerekcesi: string | null; fiyatGerekce: string | null; fiyatOnaylayan: string | null; fiyatTarih: string | null;
  okundu: string | null;
  kararlar: Array<{ sozlesmeId: string; bicim: Format; bicimAdi: string; karar: string; kararAdi: string; gerekce: string; yazan: string; tarih: string }>;
  platformGecmisi: Array<{ platform: string; durum: ListingState; durumAdi: string; tarih: string | null; kaynak: string; not: string | null; fiyat: number | null; yazan: string; zaman: string }>;
  crmIslenecek: Pending[];
  satis?: { platform: Array<{ donem: string; platform: string; adet: number; netTl: number | null }>; logo: Array<{ donem: string; adet: number; ciro: number }> };
  uyari?: string | null;
  kaynaklar?: Kaynaklar;
};

export type Pending = {
  id: number; kitapId: string; ad: string | null; stokKodu: string | null; alan: string; alanAdi: string; deger: string;
  kaynak: string | null; durum: 'acik' | 'kapandi'; acildi: string | null; kapandi: string | null;
};

export type Overview = {
  kpi: Record<'kitap' | 'dijitalde' | 'hakliDijitalYok' | 'firsat' | 'sesliFirsat' | 'hakRiski' | 'incele' | 'ekitapKaydi' | 'sesliKaydi'
    | 'epubCrmEvet' | 'epubStudyoHazir' | 'yeniBaski' | 'crmIslenecek', number>;
  hakDagilimi: { ekitap: Record<string, number>; sesli: Record<string, number> };
  hakAdlari: Record<string, string>;
  sonRapor: { donem: string; platform: string | null } | null;
  sozlesme: { yururlukte?: number; ekitap?: number; sesli?: number; iletim?: number; notlu?: number; okundu?: string };
  logo: { veriSonu?: string; pencere?: [string, string] };
  okuma: RefreshInfo;
  ayarlar: { oppMinQty: number; audioMinQty: number; audioGenres: string[] };
  kaynaklar?: Kaynaklar;
};

export type Page<T> = { items: T[]; total: number; page: number; pageSize: number; kaynaklar?: Kaynaklar };
export type Opportunity = TitleRow & { gerekce: string | null; puan: number | null };
export type RiskRow = TitleRow & {
  hakEkitapGerekce: string | null; hakSesliGerekce: string | null; notOkuma: string | null; riskBicim: Format[];
  notluSozlesmeler: Array<{ id: string; ad: string | null; taraflar: string[]; not: string; hakHaritasi?: HakHaritasi | null }>;
};

export type Platform = {
  id: number; ad: string; tur: string; turAdi: string; dagitim: string; dagitimAdi: string; paraBirimi: string;
  raporGunu: number | null; aktif: boolean;
};

export type Candidate = { kitapId: string; ad: string | null; yazar: string | null; stokKodu: string | null; benzerlik: number; olasilik: number | null; oneri?: boolean };
export type SaleRow = {
  id: number; sira: number; donem: string; tur: 'satir' | 'ozet'; kimlik: string | null; baslik: string | null; yazar: string | null;
  kitapId: string | null; kitapAd: string | null; stokKodu: string | null; eslesme: 'kural' | 'zeki' | 'elle' | null; anahtar: string | null;
  olasilik: number | null; adaylar: Candidate[]; adet: number | null; brut: number | null; net: number | null; paraBirimi: string | null;
  kur: number | null; netTl: number | null;
};
export type ImportSummary = {
  id: string; platformId: number; platform: string | null; donem: string; dosya: string | null; yukleyen: string | null; satir: number;
  eslesen: number; eslesmeyen: number; durum: 'onizleme' | 'onaylandi' | 'iptal'; olusturma: string | null; onaylayan: string | null;
  onay: string | null; kurlar: Record<string, number>;
};
export type ImportDetail = ImportSummary & {
  kolonlar: Record<string, number | null>; baslik: string[]; atilanKolonlar: string[]; bosSatir: number; ozetSatir: number;
  toplamlar: Record<string, { satir: number; adet: number; net: number; brut: number }>; paraBirimleri: string[];
  eslestirme: { durum: 'suruyor' | 'bitti' | 'hata'; bitti?: number; toplam?: number; satir?: number; modelSorulan?: number; model?: boolean; mesaj?: string } | null;
  roller: string[]; satirlar: SaleRow[]; kaynaklar?: Kaynaklar;
};

export type Sales = {
  aylik: Array<{ donem: string; platformId: number; platform: string; adet: number; netTl: number | null; satir: number }>;
  kitaplar: Array<{ kitapId: string; ad: string | null; stokKodu: string | null; hedefKitle: string | null; adet: number; netTl: number | null; basili12Adet: number | null }>;
  eslesmeyen: Array<{ id: number; importId: string; sira: number; donem: string; platform: string | null; kimlik: string | null; baslik: string | null; yazar: string | null; adet: number | null; netTl: number | null; adaylar: Candidate[] }>;
  logoEkitap: Array<{ donem: string; adet: number; ciro: number }>;
  logoPencere: [string, string] | null;
  logoVeriSonu: string | null;
  dijitalBasiliOran: Array<{ hedefKitle: string; dijitalAdet: number; basiliAdet: number; oran: number | null }>;
  kaynaklar?: Kaynaklar;
};

const B = '/api/v1/dijital';

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

const qs = (p: Record<string, string | number | boolean | undefined | null>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== null && v !== '' && v !== false) s.set(k, String(v));
  const t = s.toString();
  return t ? `?${t}` : '';
};
const enc = encodeURIComponent;

export const dijitalApi = {
  meta: () => send<Meta>('GET', '/meta'),
  overview: () => send<Overview>('GET', '/overview'),
  refresh: () => send<{ started: boolean }>('POST', '/refresh', {}),
  titles: (p: { hak?: string; durum?: string; q?: string; tur?: string; platform?: number; page?: number }) =>
    send<Page<TitleRow>>('GET', `/titles${qs(p)}`),
  title: (id: string) => send<TitleDetail>('GET', `/titles/${enc(id)}`),
  setListing: (id: string, platformId: number, b: { durum: ListingState; tarih?: string; not?: string; fiyat?: string }) =>
    send<TitleDetail>('PUT', `/titles/${enc(id)}/listings/${platformId}`, b),
  setPrice: (id: string, b: { fiyat: string | null; gerekce?: string }) => send<TitleDetail>('PUT', `/titles/${enc(id)}/price`, b),
  opportunities: (p: { tur: Format; q?: string; page?: number }) => send<Page<Opportunity> & { tur: Format }>('GET', `/opportunities${qs(p)}`),
  opportunitiesCsv: (tur: Format, q = '') => `${ENGINE_BASE}${B}/opportunities/export.csv${qs({ tur, q })}`,
  risks: () => send<{ risk: RiskRow[]; incele: RiskRow[]; kararlar: Record<string, string>; notAdlari: Record<string, string>; kaynaklar?: Kaynaklar }>('GET', '/rights-risks'),
  decide: (b: { kitapId: string; sozlesmeId: string; bicim: Format; karar: string; gerekce: string }) => send<TitleDetail>('POST', '/rights-decisions', b),
  pending: (durum = 'acik') => send<{ items: Pending[]; alanlar: Record<string, string>; kaynaklar?: Kaynaklar }>('GET', `/crm-pending${qs({ durum })}`),
  platforms: () => send<{ items: Platform[]; kaynaklar?: Kaynaklar }>('GET', '/platforms'),
  createPlatform: (b: Partial<Platform>) => send<Platform>('POST', '/platforms', b),
  updatePlatform: (id: number, b: Partial<Platform>) => send<Platform>('PATCH', `/platforms/${id}`, b),
  imports: () => send<{ items: ImportSummary[]; kaynaklar?: Kaynaklar }>('GET', '/imports'),
  importDetail: (id: string) => send<ImportDetail>('GET', `/imports/${enc(id)}`),
  upload: async (file: File, platform: number, donem: string): Promise<ImportDetail> => {
    if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
    const res = await fetch(`${ENGINE_BASE}${B}/imports${qs({ platform, donem, filename: file.name })}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file,
      signal: AbortSignal.timeout(600_000),
    });
    if (!res.ok) return fail(res);
    return (await res.json()) as ImportDetail;
  },
  remap: (id: string, kolonlar: Record<string, number | null>) => send<ImportDetail>('PATCH', `/imports/${enc(id)}`, { kolonlar }),
  match: (id: string) => send<{ started: boolean; model?: boolean }>('POST', `/imports/${enc(id)}/match`, {}),
  rows: (id: string, satirlar: Array<{ id: number; kitapId: string | null; kaynak: 'zeki' | 'elle' }>) =>
    send<ImportDetail>('POST', `/imports/${enc(id)}/rows`, { satirlar }),
  acceptStrong: (id: string) => send<ImportDetail>('POST', `/imports/${enc(id)}/accept-strong`, {}),
  commit: (id: string, kurlar: Record<string, string>) => send<ImportDetail>('POST', `/imports/${enc(id)}/commit`, { kurlar }),
  remove: (id: string) => send<{ id: string; silindi?: boolean; iptal?: boolean }>('DELETE', `/imports/${enc(id)}`),
  sales: (p: { donem?: string; platform?: number }) => send<Sales>('GET', `/sales${qs(p)}`),
  salesCsv: (p: { donem?: string; platform?: number }) => `${ENGINE_BASE}${B}/sales/export.csv${qs(p)}`,
};

/* ------------------------------------------------------------------ biçim */

const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const money2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct0 = new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 1 });

export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export const fmtMoney = (v: number | null | undefined, cur = '₺') => (v === null || v === undefined ? '—' : `${money2.format(v)} ${cur}`);
export const fmtPct = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? '—' : pct0.format(v));

export const RIGHT_TONE: Record<Right, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  var: 'ok', kismi: 'violet', incele: 'warn', eksik: 'err', yok: 'err', koruma_disi: 'ok', set: 'muted', kitap_degil: 'muted',
};
export const LISTING_TONE: Record<ListingState, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  bilinmiyor: 'muted', hazirlaniyor: 'warn', yuklendi: 'violet', yayinda: 'ok', reddedildi: 'err', kaldirildi: 'muted',
};

/** Bu ayın bir önceki ayı: YYYY-AA (rapor yüklemede varsayılan dönem). */
export function lastMonth(): string {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}
