import { ENGINE_BASE, send } from '../engine';

/** M52 Tedarik ve baskı köprü istemcisi (`/api/v1/supply/*`). Kartlar M12'den, kağıt alanları CRM'den, tedarikçi borcu
 *  ve baskı faturası Logo'dan (yalnız okuma). Borç ve maliyet alanları yetkisi olmayana boş gelir. */

const B = '/api/v1/supply';
const enc = encodeURIComponent;

export type CellState = 'asim' | 'referans-ustu' | 'normal' | 'olculemedi' | 'bos';

export type Capacity = { id: string; matbaa: string; ay: string | null; kapasiteAdet: number | null; kapasiteForma: number | null; not: string | null; byName: string; at: string | null };

export type CardBrief = {
  id: string;
  kitap: string | null;
  stokKodu: string | null;
  baskiNo: number | null;
  ilkBaski: boolean;
  urunTipi: string | null;
  matbaa: string | null;
  adet: number | null;
  forma: number | null;
  formaYuku: number | null;
  sayfa: number | null;
  oncelik: string | null;
  bekleme: string | null;
  asama: string;
  asamaAdi: string;
  planBaski: string | null;
  planDosya: string | null;
  planDepo: string | null;
  yayin: string | null;
  gecikme: number;
  onay: string | null;
  birimFiyat?: number | null;
  faturaTutari?: number | null;
  m9Maliyet?: { maliyet: number | null; kaynak: string | null; tarih: string | null } | null;
  depo?: string;
  bekleyenGun?: number;
};

export type Reference = { adet: number; jobs: number; forma: number; ay: string; aylar: number } | null;
export type Cell = {
  jobs: number; adet: number; forma: number; cards: CardBrief[]; kapasite: Capacity | null; durum: CellState; oran: number | null;
  gecenYil: { jobs: number; adet: number } | null;
};
export type LoadRow = { matbaa: string; referans: Reference; kapasiteVar: boolean; hucreler: Record<string, Cell> };
export type Month = { key: string; label: string };

export type Demand = {
  baskiOneri: Array<{ stokKodu: string; kitap: string | null; oneri: string; oneriAdet: number | null; tukenme: number | null; stok: number | null; yayinevi: string | null }>;
  ilkBaski: Array<{ stokKodu: string | null; kitap: string | null; adet: number | null; yayinAyi: string | null }>;
  baskiOneriAdet: number;
  ilkBaskiAdet: number;
  seviyeler: string[];
  hata: string | null;
  raporVar: boolean;
};

export type Conflict = {
  matbaa: string; ay: string; ayAdi: string; durum: CellState; oran: number | null; jobs: number; adet: number; forma: number;
  kapasite: Capacity | null; referans: Reference; cards: CardBrief[];
};

export type LoadTable = {
  aylar: Month[];
  satirlar: LoadRow[];
  toplam: Record<string, { jobs: number; adet: number; forma: number; gecenYil: { jobs: number; adet: number } | null }>;
  ufukDisi: number;
  oranEsigi: number;
  referansNotu: string;
  cakismalar: Conflict[];
  plan: Demand;
  degisiklikler: { toplam: number; sebepler: Array<{ sebep: string; adet: number }>; acikKartDegisiklik: Record<string, number>; kartsiz: number };
  uyarilar: string[];
  asOf: string;
};

export type LogoMeta = { firma: string; yil: number; veriSonu: string | null; yaslandirmaTarihi: string } | null;

export type Overview = {
  asOf: string;
  today: string;
  yuk: { aylar: Month[]; toplam: LoadTable['toplam']; satirlar: Array<Omit<LoadRow, 'hucreler'> & { hucreler: Record<string, Omit<Cell, 'cards'>> }>; acikIs: number; acikAdet: number };
  cakisma: number;
  cakismaAsim: number;
  kagit: { buAyKg: number; olcu: 'brut' | 'net'; kapsam: { dolu: number; bos: number } };
  plan: Demand;
  oneri: number;
  logo: LogoMeta;
  uyarilar: string[];
  odeme30?: { toplam: number; satir: number; vadesiGecmis: number; fifoNotu: string };
  faturasiz?: { kart: number; fatura: number };
  maliyet?: { aylar: Month[]; seri: Record<string, CostPoint>; egilim: number | null; sonDonem: number | null; oncekiDonem: number | null };
};

export type Meta = {
  settings: {
    loadMonths: number; paperMonths: number; paperMeasure: 'brut' | 'net'; paperLeadDays: number; paperBuyer: string; overloadRatio: number;
    unbilledGraceDays: number; supplierPrefix: string; printerSpecodes: string[]; paperSpecodes: string[]; trendMonths: number;
    pageBands: number[]; agingAsOf: string;
  };
  printers: string[];
  kinds: Record<string, string>;
  states: Record<string, string>;
  linkMethods: Record<string, string>;
  exports: Record<string, string>;
  fifoNote: string;
  referenceNote: string;
  me: { username: string; display: string; admin: boolean; canDebt: boolean; canCost: boolean; canCapacity: boolean; canDecide: boolean; canMatch: boolean; canExport: boolean };
};

export type PaperRow = {
  ay: string; ayAdi: string; cins: string | null; cinsAdi: string; gramaj: number | null; kg: number; digerKg: number; toplam: number; kart: number;
  eksikOlcu: number; parcalar: Record<string, number>; ebatlar: Record<string, number>;
};
export type PriceItem = { kod: string; ad: string; birim: string; miktar: number; tutar: number; ortalama: number | null; ilk: number | null; son: number | null; degisim: number | null; aylar: Record<string, { birimFiyat: number; miktar: number }> };
export type Paper = {
  aylar: Month[]; satirlar: PaperRow[]; cinsler: Array<{ cins: string | null; cinsAdi: string; gramaj: number | null; kg: number; aylar: Record<string, number> }>;
  olcu: 'brut' | 'net'; kapsam: { dolu: number; bos: number }; kagitsizKartlar: CardBrief[]; toplamKg: number; fiyat: PriceItem[] | null; alici: string; uyarilar: string[];
};

export type Buckets = { k_1_30: number; k_31_60: number; k_61_90: number; k_90p: number };
export type Ahead = { g_0_30: number; g_31_60: number; g_61_90: number; g_90p: number };
export type Karne = { printer: string; jobs: number; open: number; done: number; onTimeRate: number | null; measured: number; leadDays: number | null; unitPrice?: number | null; unitRecent?: number | null; unitTrend?: number | null; qualityRate: number | null; score?: number };
export type SupplierRow = {
  kod: string; unvan: string; ozelKod: string | null; tur: 'matbaa' | 'kagit' | 'diger'; turKaynak: string; crmMatbaa: string[]; acikIs: number; karne: Karne[];
  bakiye?: number; vadesiGecmis?: number; plansiz?: number; gelmemis?: number; kovalar?: Buckets; gelecek?: Ahead; alisBuYil?: number; alis12?: number; fatura12?: number;
};
export type MapEntry = { cari: string | null; kaynak: 'veri' | 'elle' | 'belirsiz'; pay: number | null; is: number; adaylar: Array<{ cari: string; is: number }>; by?: string; at?: string };
export type Suppliers = {
  items: SupplierRow[]; eslesme: Record<string, MapEntry>; eslesmeyen: Array<MapEntry & { matbaa: string }>;
  ozelKodlar: Array<{ ozelKod: string | null; cari: number }>; ayar: { matbaa: string[]; kagit: string[]; onEk: string };
  logo: LogoMeta; fifoNotu: string; uyarilar: string[]; borcGorunur: boolean; maliyetGorunur: boolean;
};
export type OpenLine = { vade: string; tutar: number; acik: number; gun: number; faturaNo: string | null; faturaTarihi: string | null };
export type Aging = Buckets & Ahead & { bakiye: number; gelmemis: number; vadesiGecmis: number; plansiz: number; katalogVadesiGecmis: number; acikSatir: OpenLine[] };
export type SupplierDetail = {
  kod: string; unvan: string; ozelKod: string | null; tur: string; turKaynak: string; crmMatbaa: string[];
  yaslandirma: Aging | null; alis: { buYil: number; son12: number; fatura12: number; aylik: Record<string, number> } | null;
  faturalar: Array<{ tarih: string | null; no: string | null; tur: number; tutar: number; kdv: number; aciklama: string | null }> | null;
  acikIsler: CardBrief[]; bitenIsler: CardBrief[]; karne: Karne[]; logo: LogoMeta; fifoNotu: string; borcGorunur: boolean; maliyetGorunur: boolean;
};
export type Payments = {
  gun: number; satirlar: Array<OpenLine & { kod: string; unvan: string; tur: string }>; toplam: number; haftalik: Array<{ hafta: string; tutar: number }>;
  vadesiGecmis: Array<{ kod: string; unvan: string; tur: string; vadesiGecmis: number; plansiz: number; kovalar: Buckets }>; vadesiGecmisToplam: number;
  logo: LogoMeta; fifoNotu: string;
};
export type Link = { id: string; firma: string; satirRef: string; faturaNo: string | null; kartId: string | null; yontem: string; yontemAdi: string; olasilik: number | null; adaylar: Candidate[]; durum: 'oneri' | 'onayli' | 'ret'; durumAdi: string };
export type Candidate = { kartId: string; kitap: string | null; baskiNo: number | null; stokKodu: string | null; matbaa: string | null; adet: number | null; depo: string | null; puan: number };
export type Unbilled = {
  kartlar: CardBrief[];
  faturalar: Array<{ firma: string; satirRef: string; faturaNo: string | null; tarih: string; cariKod: string | null; cari: string | null; stok: string | null; adet: number; tutar?: number; oneri: Link | null }>;
  aylik: Array<{ matbaa: string; ay: string; ayAdi: string; depoAdet: number; faturaAdet: number; fark: number }>;
  bekleme: { gun: number; kaynak: 'veri' | 'ayar'; ortanca: number | null; ornek: number };
  logo: LogoMeta; uyarilar: string[]; tutarGorunur: boolean;
};
export type CostPoint = { agirlikliBirim: number; ortancaBirim: number; sayfa100: number | null; is: number; adet: number; tutar: number };
export type CostTrend = {
  kirilim: string; aylar: Month[];
  gruplar: Array<{ grup: string; is: number; adet: number; agirlikliBirim: number | null; sonDonem: number | null; oncekiDonem: number | null; egilim: number | null; aylar: Record<string, CostPoint> }>;
  kagit: PriceItem[]; uyarilar: string[];
};
export type Suggestion = {
  id: string; tur: 'yuk' | 'kagit' | 'eskalasyon' | 'sartname'; turAdi: string; kartId: string | null; baslik: string | null;
  veri: Record<string, unknown>; metin: string | null; durum: string; durumAdi: string; kararVeren: string | null; kararTarihi: string | null; kararNotu: string | null; olusturma: string | null;
};
export type Incoming = {
  gecmis: Array<{ ay: string; ayAdi: string; adet: number; fis: number }>;
  plan: Array<{ ay: string; ayAdi: string; adet: number; is: number }>;
  planiGecmis: { adet: number; is: number };
  depo: { kapasiteAdet: number | null; stokAdet: number | null; kaynak: string } | null;
};

export const supplyApi = {
  meta: () => send<Meta>('GET', `${B}/meta`),
  overview: () => send<Overview>('GET', `${B}/overview`),
  load: (aylar?: number) => send<LoadTable>('GET', `${B}/load${aylar ? `?aylar=${aylar}` : ''}`),
  paper: (aylar?: number) => send<Paper>('GET', `${B}/paper${aylar ? `?aylar=${aylar}` : ''}`),
  suppliers: () => send<Suppliers>('GET', `${B}/suppliers`),
  supplier: (code: string) => send<SupplierDetail>('GET', `${B}/suppliers/${enc(code)}`),
  payments: (gun: number, tur = '') => send<Payments>('GET', `${B}/payments?gun=${gun}${tur ? `&tur=${enc(tur)}` : ''}`),
  unbilled: () => send<Unbilled>('GET', `${B}/unbilled`),
  cost: (kirilim: string) => send<CostTrend>('GET', `${B}/cost-trend?kirilim=${enc(kirilim)}`),
  incoming: (aylar = 6) => send<Incoming>('GET', `${B}/incoming?aylar=${aylar}`),
  suggestions: (tur = '', durum = '') => send<{ items: Suggestion[] }>('GET', `${B}/suggestions?tur=${enc(tur)}&durum=${enc(durum)}`),
  decide: (id: string, karar: 'kabul' | 'ret', not?: string) => send<Suggestion>('POST', `${B}/suggestions/${enc(id)}/decision`, { karar, not }),
  draft: (tur: 'sartname' | 'eskalasyon', kartId: string) => send<Suggestion>('POST', `${B}/drafts`, { tur, kartId }),
  capacity: () => send<{ items: Capacity[]; printers: string[]; referansNotu: string }>('GET', `${B}/capacity`),
  saveCapacity: (b: { matbaa: string; ay?: string | null; kapasiteAdet?: string; kapasiteForma?: string; not?: string }) => send<Capacity>('PUT', `${B}/capacity`, b),
  deleteCapacity: (id: string) => send<{ ok: boolean }>('DELETE', `${B}/capacity/${enc(id)}`),
  supplierMap: () => send<{ items: Record<string, MapEntry>; printers: string[] }>('GET', `${B}/supplier-map`),
  saveSupplierMap: (b: { matbaa: string; cari?: string | null; kaldir?: boolean }) => send<{ matbaa: string }>('PUT', `${B}/supplier-map`, b),
  link: (b: { firma: string; satirRef: string; kartId: string | null; karar: 'onay' | 'ret'; faturaNo?: string | null }) => send<Link>('POST', `${B}/invoice-links`, b),
  exportUrl: (liste: string, q = '') => `${ENGINE_BASE}${B}/export/${enc(liste)}.xlsx${q}`,
};

const money = new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 });
const unit = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const int = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const dtf = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });

export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : money.format(v));
export const fmtUnit = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${unit.format(v)} ₺`);
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int.format(v));
export const fmtKg = (v: number | null | undefined) => (v === null || v === undefined ? '—' : v >= 10_000 ? `${unit.format(v / 1000)} ton` : `${int.format(v)} kg`);
export const fmtPct = (v: number | null | undefined, sign = false) =>
  v === null || v === undefined ? '—' : `${sign && v > 0 ? '+' : ''}%${Math.round(v * 100)}`;
export const fmtDay = (iso: string | null | undefined) => (iso ? dtf.format(new Date(`${iso.slice(0, 10)}T00:00:00Z`)) : '—');

export const KIND_LABEL: Record<string, string> = { matbaa: 'Matbaa', kagit: 'Kağıtçı', diger: 'Diğer tedarikçi' };
export const STATE_LABEL: Record<CellState, string> = {
  asim: 'Kapasite aşımı',
  'referans-ustu': 'Referansın üstü',
  normal: 'Eşik altında',
  olculemedi: 'Eşik ölçülemedi',
  bos: 'İş yok',
};
