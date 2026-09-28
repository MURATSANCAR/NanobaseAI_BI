import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';

/** M43 Depo ve stok ekranlarının köprü uçları: /api/v1/stock/*. */

export type StockState = 'stoksuz' | 'bitecek' | 'yeterli' | 'fazla' | 'olu' | 'satissiz' | 'pasif';
export type DiffClass = 'aktarim' | 'kismen' | 'crm_yok' | 'logo_yok' | 'sayim';

export type Card = {
  kartId: string;
  ad: string | null;
  baskiNo: number | null;
  asama: string;
  asamaEtiket: string;
  adet: number | null;
  baskiPlan: string | null;
  depoPlan: string | null;
  tur: string | null;
};

export type Item = {
  stokKodu: string;
  ad: string | null;
  yazar: string | null;
  yayinevi: string | null;
  kitaplik: string | null;
  statu: string | null;
  bakiye: number;
  logoVar: boolean;
  ambarlar: Array<{ no: number; ad: string; adet: number }>;
  crmRaf: number | null;
  rafSayisi: number;
  satisHizi: number | null;
  yillikSatis: number | null;
  gun: number | null;
  tukenmeTarihi: string | null;
  tukenmeAy: number | string | null;
  baskiOneri: string | null;
  durum: StockState;
  durumEtiket: string;
  kritikGun: number;
  baskiUyarisi: boolean;
  yenidenSiparisNoktasi: number | null;
  rspAltinda: boolean;
  esik: { id: string; guvenlikGun: number; yenidenSiparisAdet: number | null; onaylayan: string | null; onayTarihi: string | null } | null;
  bekleyenCrm: number | null;
  bekleyenLogo: number | null;
  bekleyenUrun: number | null;
  devirHizi: number | null;
  sonHareket: string | null;
  netSatis12: number | null;
  eosStok: number | null;
  uretim: Card | null;
  uretimSayisi: number;
  aktarimBekleyen: number | null;
  aktarimFis: number;
  fark: number | null;
  farkSinif: DiffClass | null;
  farkEtiket: string | null;
  tahmin: { baslangic: string | null; g30: number; g60: number; g90: number } | null;
  /** Yalnız maliyet yetkisiyle gelir. */
  birimMaliyet?: number | null;
  maliyetKaynak?: string | null;
  stokDegeri?: number | null;
  oneri?: { id: string; hedef: string | null; hedefEtiket: string | null; gerekce: string | null } | null;
};

export type Page<T> = { items: T[]; total: number; page: number; pageSize: number };
export type Value = { toplam: number; maliyetli: number; maliyetsiz: number } | null;

export type Meta = {
  states: Record<StockState, string>;
  diffClasses: Record<DiffClass, string>;
  errorClasses: string[];
  suggestionKinds: Record<string, string>;
  targets: Record<string, string>;
  thresholdStates: Record<string, string>;
  params: { runoutDays: number; safetyDays: number; leadDays: number | null; excessDays: number; deadDays: number; pickDays: number };
  sonKosu: Record<string, unknown> | null;
  refreshing: boolean;
  sources: Array<{ id: string; baglanti: string; baslik: string; aciklama: string }>;
  me: { username: string; display: string; canDecide: boolean; canApprove: boolean; canCost: boolean; canPeople: boolean; canExport: boolean };
};

export type Overview = {
  veriSonu: string | null;
  okuma: number | null;
  baskiSuresi: number;
  baskiSuresiKaynak: string;
  toplamStok: number;
  stokluKitap: number;
  stoksuzAktif: number;
  bitecek: number;
  bitecekGun: number;
  kartsizKritik: number;
  aktarimHatasi: number;
  aktarimBekleyen: number;
  farkliKitap: number;
  fazla: number;
  hareketsiz: number;
  satissiz: number;
  durumlar: Array<{ key: StockState; label: string; adet: number }>;
  bugun: { bitecek: Page<Item>; aktarim: Page<Transfer>; fark: Page<Item> };
  uyarilar: string[];
  yenileniyor: boolean;
  deger?: Value;
};

export type ItemPage = Page<Item> & { yayinevleri: string[]; ambarlar: Array<{ no: number; ad: string }>; veriSonu: string | null };

export type Shelf = {
  stokKodu: string;
  rafId: string | null;
  raf: string | null;
  rafTipi: string | null;
  satisaAcik: boolean;
  yerlesim: string | null;
  depoId: string | null;
  depo: string | null;
  depoNo: string | null;
  adet: number;
};

export type Threshold = {
  id: string;
  stokKodu: string;
  ad?: string | null;
  depoNo: string | null;
  guvenlikGun: number;
  yenidenSiparisAdet: number | null;
  kaynak: string;
  durum: string;
  durumEtiket: string;
  gerekce: string | null;
  olusturan: string;
  onaylayan: string | null;
  onayTarihi: string | null;
  olusturma: string | null;
};

export type Proposal = {
  stokKodu: string;
  ad: string | null;
  guvenlikGun: number;
  yenidenSiparisAdet: number;
  bakiye: number;
  satisHizi: number;
  gun: number | null;
  baskiSuresi: number;
  gerekce: string;
};

export type Suggestion = {
  id: string;
  tur: string;
  turEtiket: string;
  stokKodu: string;
  veri: Record<string, unknown> & { ad?: string | null };
  gerekce: string | null;
  durum: string;
  durumEtiket: string;
  hedef: string | null;
  hedefEtiket: string | null;
  kararVeren: string | null;
  kararTarihi: string | null;
  kararNotu: string | null;
  olusturma: string | null;
};

export type Note = { id: string; stokKodu: string; not: string; yazan: string; yazanAd: string | null; tarih: string | null };

export type ItemDetail = Item & {
  raflar: Shelf[];
  uretimKartlari: Card[];
  notlar: Note[];
  esikler: Threshold[];
  esikOnerisi: Proposal | null;
  oneriler: Suggestion[];
  gecmis: Array<{ gun: string; bakiye: number | null; crmRaf: number | null; satisHizi: number | null }>;
  veriSonu: string | null;
  baskiSuresi: number;
  baskiSuresiKaynak: string;
  hareketPenceresi: [string, string] | null;
  tahminBaslangic: string | null;
};

export type Transfer = {
  id: string;
  fisNo: string | null;
  belgeNo: string | null;
  fisTarihi: string | null;
  olusturma: string | null;
  yasGun: number | null;
  islemTuru: number;
  islemTuruEtiket: string;
  islemTipiEtiket: string | null;
  durumEtiket: string;
  depo: string | null;
  hata: boolean;
  mesaj: string | null;
  satir: number;
  miktar: number;
  sinif: string | null;
  sinifOlasilik: number | null;
};

export type PickLine = {
  asamalar: Array<{ key: string; label: string; adet: number; ortancaSaat: number | null; enEskiSaat: number | null }>;
  sureler: Array<{ from: string; to: string; label: string; ortancaSaat: number | null; siparis: number }>;
  acik: Page<{ id: string; no: string | null; asama: string; asamaEtiket: string; depo: string | null; oncelik: string | null; asamaSaat: number | null; koli: number | null; depoyaDusus: string | null; toplayan?: string | null }>;
  kisiler?: Array<{ toplayan: string; siparis: number; ortancaSaat: number | null }>;
  kisiGorunur: boolean;
  pencereGun: number;
};

const B = '/api/v1/stock';
const enc = encodeURIComponent;

/** İlk okuma Logo ve CRM'den birkaç dakika sürebilir; sonra 5 dk önbellekten gelir. */
async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 600_000): Promise<T> {
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
  const msg = j ? (typeof j.detail === 'string' ? j.detail : j.detail?.message) : undefined;
  if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  if (!res.ok) throw new Error(msg || httpErrorText(res.status));
  return (await res.json()) as T;
}

const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const stockApi = {
  meta: () => send<Meta>('GET', '/meta'),
  sources: () => send<{ sources: Array<{ id: string; baglanti: string; baslik: string; aciklama: string; sql: string | null }> }>('GET', '/sources'),
  overview: () => send<Overview>('GET', '/overview'),
  names: () => send<{ items: Array<{ value: string; label: string }> }>('GET', '/names'),
  items: (f: { q?: string; yayinevi?: string; depo?: string; durum?: string; sira?: string; sayfa?: number }) =>
    send<ItemPage>('GET', `/items${qs(f)}`),
  item: (code: string) => send<ItemDetail>('GET', `/items/${enc(code)}`),
  addNote: (code: string, text: string) => send<Note>('POST', `/items/${enc(code)}/notes`, { not: text }),
  deleteNote: (id: string) => send<{ ok: boolean }>('DELETE', `/notes/${enc(id)}`),
  runningOut: (f: { gun?: number; sayfa?: number; kartsiz?: boolean }) =>
    send<Page<Item> & { gun: number; baskiSuresi: number; baskiSuresiKaynak: string; guvenlikGun: number; veriSonu: string | null }>('GET', `/running-out${qs(f)}`),
  excess: (f: { tur?: string; sayfa?: number }) =>
    send<Page<Item> & { toplamAdet: number; deger: Value; fazlaGun: number; hareketPenceresi: [string, string] | null; veriSonu: string | null }>('GET', `/excess${qs(f)}`),
  diff: (f: { sinif?: string; sayfa?: number }) =>
    send<Page<Item> & { siniflar: Array<{ key: DiffClass; label: string; adet: number }>; veriSonu: string | null; not: string }>('GET', `/diff${qs(f)}`),
  transfers: (f: { tur?: string; sinif?: string; sayfa?: number }) =>
    send<Page<Transfer> & { siniflar: Array<{ key: string; adet: number }>; hata: number; bekliyor: number }>('GET', `/transfer-errors${qs(f)}`),
  pickLine: (sayfa: number) => send<PickLine>('GET', `/pick-line${qs({ sayfa })}`),
  suggestions: (f: { tur?: string; durum?: string; hedef?: string; sayfa?: number }) => send<Page<Suggestion>>('GET', `/suggestions${qs(f)}`),
  decide: (id: string, karar: 'kabul' | 'red', not?: string) => send<Suggestion>('POST', `/suggestions/${enc(id)}/decision`, { karar, not }),
  thresholds: (durum: string, sayfa: number) => send<Page<Threshold | Proposal>>('GET', `/thresholds${qs({ durum, sayfa })}`),
  saveThreshold: (b: { stokKodu: string; guvenlikGun: number; yenidenSiparisAdet?: number | null; gerekce?: string; kaynak?: string; onayla?: boolean }) =>
    send<Threshold>('POST', '/thresholds', b),
  approveThreshold: (id: string, not?: string) => send<Threshold>('POST', `/thresholds/${enc(id)}/approve`, { not }),
  rejectThreshold: (id: string, not: string) => send<Threshold>('POST', `/thresholds/${enc(id)}/reject`, { not }),
  bulletin: () => send<{ metin: string | null; kaynak?: string; veriSonu?: string | null; _at?: string }>('GET', '/bulletin'),
  exportUrl: (liste: string, f: Record<string, string | number | undefined> = {}) =>
    `${ENGINE_BASE}${B}/export/${enc(liste)}.xlsx${qs(f)}`,
};

const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const dec1 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
const money = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
export const n0 = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export const n1 = (v: number | null | undefined) => (v === null || v === undefined ? '—' : dec1.format(v));
export const tl = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${money.format(v)} ₺`);
export const gunText = (g: number | null | undefined) => (g === null || g === undefined ? 'satış yok' : `${int0.format(Math.floor(g))} gün`);

export const STATE_TONE: Record<StockState, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  stoksuz: 'err',
  bitecek: 'warn',
  yeterli: 'ok',
  fazla: 'violet',
  olu: 'muted',
  satissiz: 'muted',
  pasif: 'muted',
};
