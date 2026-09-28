import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** Rakam uçlarının cevabında sorgu bilgisi (`<SqlInfo k={d.kaynaklar} …/>`). */
export type WithK = { kaynaklar?: Kaynaklar };

/** M42 Platform ve kanallar: /api/v1/channels/*. Marj alanları `ozellik:kanal.marj` yoksa cevapta hiç gelmez (isteğe bağlı). */

export type Period = { yil: number; ay: number; ayAdi: string; gunPayi: number; kismiAy: boolean; veriSonu: string | null };

export type Metrics = {
  netCiro: number;
  netAdet: number;
  satisCiro: number;
  iadeCiro: number;
  satisAdet: number;
  iadeAdet: number;
  brutSatis: number;
  iskonto: number;
  iskontoOrani: number | null;
  iadeOrani: number | null;
  iadeAdetOrani: number | null;
  maliyetsizSatir: number;
  maliyetsizCiro: number;
  // marj yetkisiyle
  maliyet?: number;
  maliyetliCiro?: number;
  brutKar?: number;
  marj?: number | null;
  maliyetKapsami?: number | null;
  iadeSonrasiBrutKar?: number;
  iadeSonrasiMarj?: number | null;
  ekMaliyetOrani?: number;
  katki?: number;
  katkiMarj?: number | null;
  m9?: M9Fill;
};

export type M9Fill = {
  tamamlananCiro: number;
  tamamlananMaliyet: number;
  marj: number | null;
  kapsam: number | null;
  bilinmeyenKitap: number;
  bilinmeyenCiro: number;
  kaynaklar: Record<string, number>;
};

export type CrmTarget = {
  kaynak: string;
  bolgeler: string[];
  yillik: number;
  beklenen: number;
  gerceklesen: number;
  oran: number | null;
  aylik: Array<{ ay: number; hedef: number; gercek: number | null }>;
};

export type PlatformCard = {
  platform: string;
  label: string;
  grupSayisi: number;
  donem: Metrics;
  buAy: Metrics;
  gecenYil: Metrics | null;
  degisim: number | null;
  marjFarki?: number | null;
  payEticaret: number | null;
  paySirket: number | null;
  hedef: CrmTarget | null;
};

export type Scorecard = {
  period: Period;
  gecenYilOkundu: boolean;
  platforms: PlatformCard[];
  toplam: {
    eticaret: Metrics;
    eticaretGecenYil: Metrics | null;
    sirket: Metrics;
    sirketGecenYil: Metrics | null;
    eticaretPay: number | null;
    d2cPay: number | null;
  };
  platformDisi: { grupSayisi: number; donem: Metrics | null };
  kanallar: Array<{ kanal: string; donem: Metrics; paySirket: number | null }>;
};

export type ReadStatus = {
  running: boolean;
  step: string | null;
  error: string | null;
  dataEnd: string | null;
  years: Record<string, { kanal: number; cari: number; kitap: number; _at?: string | null }>;
  cards: { count?: number; yeni?: number; crmError?: string | null };
  crm: { error?: string | null };
};

export type ChannelsMeta = {
  platforms: Array<{ key: string; label: string }>;
  cardPlatforms: string[];
  d2c: string;
  unmapped: string;
  suggestionTypes: Record<string, string>;
  months: string[];
  years: number[];
  defaultYear: number | null;
  data: ReadStatus;
  missingScope: number[];
  settings: { specodes: string[]; returnThreshold: number; discountRise: number; orderDays: number; d2cMinAdet: number; d2cIndex: number; recipients: number };
  extraCosts: Record<string, number>;
  alerts: { items?: Array<{ platform: string; label: string; tur: string; metin: string }>; tarih?: string };
  siteConnected: boolean;
  modelReady: boolean;
  me: {
    username: string;
    display: string;
    canMargin: boolean;
    canMap: boolean;
    canDecide: boolean;
    canSuggest: boolean;
    canImport: boolean;
    canExport: boolean;
    pages: Record<'kanallar' | 'matris' | 'd2c' | 'eslesme', boolean>;
  };
};

export type ChannelDetail = {
  platform: string;
  label: string;
  period: Period;
  gecenYilOkundu: boolean;
  donem: Metrics;
  gecenYil: Metrics | null;
  degisim: number | null;
  aylik: Array<{ ay: number; ayAdi: string; buYil: Metrics | null; gecenYil: Metrics | null }>;
  cariler: Array<{ grup: string; ad: string; kanal: string | null; donem: Metrics; crmSiparis: Record<string, number> | null }>;
  crmSiparisGun: number | null;
  hedef: CrmTarget | null;
  imports: ImportRow[];
  m9Bagli: boolean;
};

export type BookRow = {
  stokKodu: string;
  ad: string;
  satisAdet: number;
  iadeAdet: number;
  netAdet: number;
  netCiro: number;
  iadeOrani: number | null;
  brutKar?: number;
  marj?: number | null;
  maliyetsizAdet: number;
};

export type Page<T> = { items: T[]; total: number; page: number; pageSize: number; period: Period };

export type MatrixPage = Page<{ stokKodu: string; ad: string; toplam: number; kanallar: Record<string, { alim: number; iade: number; net: number }> }> & {
  columns: Array<{ platform: string; label: string; net: number }>;
  sort: string;
};

export type Targets = {
  period: Period;
  crm: Record<string, CrmTarget>;
  bolgeler: Array<{ kod: string; ad: string; yillik: number; satir: number; platform: string | null }>;
  crmYilKodu: number | null;
  m46: null | {
    plan?: { id: string; title?: string; scenario?: string } | null;
    hata?: string;
    yontem?: string;
    platformlar?: Record<string, { hedefAdet: number; hedefCiro: number; beklenenAdet: number; gerceklesenAdet: number; oran: number | null; genelPay: number }>;
  };
};

export type SimRow = {
  brutSatis: number;
  iskonto: number;
  iskontoOrani: number | null;
  netSatis: number;
  iade: number;
  netCiro: number;
  maliyetliCiro: number;
  maliyet: number;
  brutKar: number;
  marj: number | null;
};

export type Simulation = {
  platform: string;
  label: string;
  period: Period;
  iskontoPuan: number;
  hacimYuzde: number;
  once: SimRow;
  sonra: SimRow;
  fark: { brutKar: number; netCiro: number; marjPuan: number | null };
  basabasHacim: number | null;
  maliyetKapsami: number | null;
  maliyetsizCiro: number;
  varsayim: string;
  yorum?: string | null;
};

export type Suggestion = {
  id: string;
  platform: string;
  tur: string;
  baslik: string;
  payload: Record<string, unknown>;
  gerekce: string | null;
  durum: 'taslak' | 'onayli' | 'red';
  olusturan: string;
  olusturma: string | null;
  kararVeren: string | null;
  kararTarihi: string | null;
  kararNotu: string | null;
};

export type Account = {
  cariKodu: string;
  platform: string | null;
  durum: 'bekliyor' | 'aday' | 'onayli';
  yontem: 'ad' | 'zeki' | 'elle' | null;
  olasilik: number | null;
  aday: { emin?: boolean; olasiliklar?: Record<string, number>; platform?: string | null } | null;
  unvan: string | null;
  kanal: string | null;
  crmAd: string | null;
  onaylayan: string | null;
  onayTarihi: string | null;
  not: string | null;
};

export type ImportRow = {
  id: string;
  platform: string;
  dosya: string | null;
  donemBas: string | null;
  donemBit: string | null;
  satir: number;
  eslesen: number;
  kolonlar: { atlanan?: string[]; kisiselOlabilir?: string[]; taninan?: Record<string, string> };
  yukleyen: string;
  tarih: string | null;
};

export type SellThrough = ImportRow & {
  items: Array<{ stokKodu: string; ad: string; kanalSatis: number; kanalStok: number | null; kanalaSatis: number; oran: number | null }>;
  eslesmeyen: number;
  kanalaSatisAylari: string[];
};

export type D2C = {
  period: Period;
  eslendi: boolean;
  gruplar: string[];
  d2c: PlatformCard | null;
  toplam: Scorecard['toplam'];
  site: { bagli: boolean; neden?: string; siparis?: number; ciro?: number; musteri?: number; tekrarOrani?: number | null; musteriBasinaCiro?: number | null; sepetOrtalamasi?: number | null; not?: string };
  esik: { minAdet: number; indeks: number };
  kitaplar: Array<{ stokKodu: string; ad: string; d2cAdet: number; pazarYeriAdet: number; d2cPay: number | null; indeks: number }>;
  genelD2cPay?: number | null;
  oneriler?: Suggestion[];
  not?: string;
};

const B = '/api/v1/channels';

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
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;

export type YM = { yil?: number; ay?: number };

export const channelsApi = {
  meta: () => send<ChannelsMeta & WithK>('GET', '/meta'),
  status: () => send<ReadStatus>('GET', '/status'),
  refresh: (yil?: number) => send<ReadStatus & { started: boolean }>('POST', `/refresh${qs({ yil })}`),
  scorecard: (p: YM) => send<Scorecard & WithK>('GET', `/scorecard${qs(p)}`),
  channel: (platform: string, p: YM) => send<ChannelDetail & WithK>('GET', `/channel/${enc(platform)}${qs(p)}`),
  books: (platform: string, p: YM & { q?: string; sort?: string; page?: number }) =>
    send<Page<BookRow> & { sort: string } & WithK>('GET', `/channel/${enc(platform)}/books${qs(p)}`),
  returns: (platform: string, p: YM & { aylar?: number; page?: number }) =>
    send<Page<BookRow> & { aralik: { bas: string; bit: string; ay: number } } & WithK>('GET', `/channel/${enc(platform)}/returns${qs(p)}`),
  matrix: (p: YM & { q?: string; page?: number; sort?: string }) => send<MatrixPage & WithK>('GET', `/matrix${qs(p)}`),
  targets: (yil?: number) => send<Targets & WithK>('GET', `/targets${qs({ yil })}`),
  simulate: (b: { platform: string; yil?: number; ay?: number; iskontoPuan: number; hacimYuzde?: number; yorum?: boolean }) =>
    send<Simulation & WithK>('POST', '/simulate', b, 180_000),
  setExtraCost: (platform: string, oran: number | null) => send<{ oran: number | null }>('PUT', `/settings/ek-maliyet/${enc(platform)}`, { oran }),
  accounts: () => send<{ items: Account[]; counts: Record<string, number>; cards: ReadStatus['cards']; specodes: string[] } & WithK>('GET', '/accounts'),
  setAccount: (code: string, b: { platform?: string | null; onay?: boolean; not?: string }) =>
    send<Account & { okumaBasladi: boolean }>('PUT', `/accounts/${enc(code)}`, b),
  propose: (cariler?: string[]) => send<{ ad: number; zeki: number; eminDegil: number; kalan: number; atlandi: string | null }>('POST', '/accounts/propose', { cariler }, 300_000),
  kanalCodes: () => send<{ yil: number | null; items: Array<{ kod: string; netCiro: number; platform: string | null; eticaret: boolean }> } & WithK>('GET', '/accounts/kanal-kodlari'),
  setKanalCode: (kod: string, platform: string | null) => send<{ okumaBasladi: boolean }>('PUT', `/accounts/kanal-kodlari/${enc(kod)}`, { platform }),
  regions: () =>
    send<{ items: Array<{ kod: string; ad: string; yil: number | null; yillik: number; platform: string | null; aday: string | null }>; crmError: string | null } & WithK>('GET', '/accounts/bolgeler'),
  setRegion: (kod: string, platform: string | null) => send<{ platform: string | null }>('PUT', `/accounts/bolgeler/${enc(kod)}`, { platform }),
  d2c: (p: YM) => send<D2C & WithK>('GET', `/d2c${qs(p)}`),
  suggestSet: (kitaplar: string[], p: YM) => send<Suggestion>('POST', '/d2c/suggest', { kitaplar, ...p }, 180_000),
  suggestions: (p: { platform?: string; tur?: string; durum?: string }) => send<{ items: Suggestion[]; types: Record<string, string> } & WithK>('GET', `/suggestions${qs(p)}`),
  addDiscountSuggestion: (b: { platform: string; yil?: number; ay?: number; iskontoPuan: number; hacimYuzde?: number; not?: string; yorum?: string | null }) =>
    send<Suggestion>('POST', '/suggestions', { tur: 'iskonto', ...b }),
  decide: (id: string, karar: 'onayli' | 'red', not?: string) => send<Suggestion>('POST', `/suggestions/${enc(id)}/decision`, { karar, not }),
  imports: (platform?: string) => send<{ items: ImportRow[] } & WithK>('GET', `/imports${qs({ platform })}`),
  importFile: async (platform: string, file: File, donemBas?: string, donemBit?: string): Promise<ImportRow> => {
    if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
    const res = await fetch(`${ENGINE_BASE}${B}/imports${qs({ platform, filename: file.name, donem_bas: donemBas, donem_bit: donemBit })}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file,
      signal: AbortSignal.timeout(600_000),
    });
    if (!res.ok) return fail(res);
    return (await res.json()) as ImportRow;
  },
  importDetail: (id: string) => send<SellThrough & WithK>('GET', `/imports/${enc(id)}`),
  deleteImport: (id: string) => send<{ ok: boolean }>('DELETE', `/imports/${enc(id)}`),
  exportUrl: (liste: 'karne' | 'kitaplar' | 'iadeler' | 'matris' | 'eslesme', p: YM & { platform?: string; q?: string; aylar?: number } = {}) =>
    `${ENGINE_BASE}${B}/export/${liste}.xlsx${qs(p)}`,
};

/** Sunucu platform anahtarını biliyor; ekran adı meta'dan, yoksa anahtarın kendisi. */
export function platformName(meta: ChannelsMeta | undefined, key: string): string {
  if (key === meta?.unmapped || key === 'eslenmemis') return 'Eşlenmemiş e-ticaret carileri';
  return meta?.platforms.find((p) => p.key === key)?.label ?? key;
}

/** Marjın yanında her zaman: maliyeti girilmemiş satırın payı. */
export function coverageText(m: Metrics): string {
  if (m.maliyetKapsami === undefined) return '';
  const share = m.maliyetKapsami === null ? '—' : `%${Math.round(m.maliyetKapsami * 100)}`;
  return `Marj maliyeti girilmiş satırlardan (cironun ${share}'i); ${m.maliyetsizSatir.toLocaleString('tr-TR')} satır maliyetsiz`;
}
