import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** Uç cevabındaki sorgu bilgisi (köprü `shipping_kaynak.py`). */
type K = { kaynaklar?: Kaynaklar };

/** M44 Lojistik ve kargo ekranlarının köprü uçları: /api/v1/shipping/*. Maliyet ve alıcı alanları yetkisi olmayana
 *  sunucuda hiç gelmez; ekran yalnız gelen alanı gösterir. */

export type Me = {
  username: string;
  display: string;
  admin: boolean;
  maliyet: boolean;
  alici: boolean;
  karar: boolean;
  taslak: boolean;
  disaAktar: boolean;
  firmalar: boolean;
  mutabakat: boolean;
  /** Kargo maliyeti sayfası ve maliyet yetkisi birlikte. */
  maliyetSayfa: boolean;
};

export type OpsSettings = { bekleyenGun: number; kutuluGun: number; bolgeHedef: Record<string, number>; guncelleyen?: Record<string, string | null> };

export type Meta = {
  hataSiniflari: string[];
  taslakTurleri: Record<DraftType, string>;
  taslakDurumlari: Record<string, string>;
  kararTurleri: Record<DecisionType, string>;
  kirilimlar: Record<Group, string>;
  disaAktarma: Record<ExportList, string>;
  siparisDurumlari: Record<string, string>;
  ayarlar: { pencereGun: number; sevkDurumlari: number[]; takipsizDurumlar: number[]; takipsizHaricTipler: number[]; eskiGun: number; logoCariEslemesi: Record<string, string[]>; gunlukSaat: string; haftalikSaat: string };
  is: OpsSettings;
  eslemeYolu: string;
  modelVar: boolean;
  me: Me;
};

export type DraftType = 'gecikme' | 'ozur' | 'iade';
export type DecisionType = 'kurye' | 'bolge' | 'sozlesme';
export type Group = 'firma' | 'sehir' | 'sube' | 'firma-sehir';
export type ExportList = 'hatalar' | 'takipsiz' | 'kutulandi' | 'bekleyen' | 'firmalar' | 'mutabakat' | 'maliyet';

export type Freshness = {
  veriSonu: string | null;
  sonKayit: string | null;
  kayit: number;
  tarihsiz: number;
  okunamayan: Record<string, number>;
  eski: boolean;
  not: string | null;
};

export type Stages = { siparis: string | null; depoda: string | null; pusula: string | null; kutulandi: string | null; sevk: string | null; tamamlandi: string | null };

export type Failure = { entegrasyon: string; sonuc: string | null; mesaj: string | null; mesajHash: string; sinif?: string | null; sinifOlasilik?: number | null };

export type Order = {
  id: string;
  no: string | null;
  tarih: string | null;
  durum: number;
  durumAdi: string;
  tip: number | null;
  tipAdi: string | null;
  firmaId: string | null;
  firma: string | null;
  takipNo: string | null;
  takipUrl: string | null;
  etiket: boolean;
  kutu: number | null;
  odeme: string | null;
  musteri: string | null;
  cariKodu: string | null;
  il: string | null;
  asamalar: Stages;
  kutulanaliGun: number | null;
  sevkeKadarGun: number | null;
  hatalar?: Failure[];
  sinif?: string | null;
};

export type Cargo = {
  id: string;
  takipNo: string | null;
  musteriIrsNo: string | null;
  kargoIrsNo: string | null;
  firma: string;
  cikisSube: string | null;
  varisSube: string | null;
  sehir: string | null;
  teslimSaati: string | null;
  iadeDurumu: string | null;
  iade: boolean;
  tahsilatli: boolean;
  sevkAdeti: number | null;
  kanal: string | null;
  gun: number | null;
  irsTarihi: string | null;
  teslimTarihi: string | null;
  yas?: number;
  desi?: number | null;
  agirlik?: number | null;
  tutar?: number | null;
  tahsilatTutar?: number | null;
  alici?: string | null;
  teslimAlan?: string | null;
};

export type Overview = {
  pencereGun: number;
  bugun: string;
  sevk: { adet: number; bugun: number };
  hata: number;
  hataSiniflari: Array<{ sinif: string; adet: number }>;
  takipsiz: number;
  kutulandi: { toplam: number; esikUstu: number; esikGun: number; tarihsiz: number };
  bekleyen: { toplam: number; esikUstu: number; esikGun: number; kovalar: Array<{ kova: string; adet: number }> };
  kargoVeri: Freshness;
  son30: {
    baslangic: string;
    bitis: string;
    toplam: { gonderi: number; teslim: number; iade: number; ortancaGun: number | null; tutar?: number | null; desiBasi?: number | null };
    firmalar: Array<{ firma: string; gonderi: number; ortancaGun: number | null; iadeOrani: number | null; desiBasi?: number | null; tutar?: number | null }>;
  };
  kaynaklar?: Kaynaklar;
};

export type Draft = { id: string; siparisId: string; siparisNo: string | null; tur: DraftType; turAdi: string; metin: string; kaynak: 'zeki' | 'kural'; yazan: string; durum: 'taslak' | 'kullanildi'; durumAdi: string; olusturma: string | null; guncelleme: string | null };

export type TimelineStep = { asama: string; zaman: string | null; kaynak: string; oncekindenGun: number | null };

export type ShipmentCard = {
  siparis: Order;
  takip: Array<{ belgeNo: string | null; takipNo: string | null; olusturma: string | null }>;
  sevkiyatlar: Array<{ id: string; no: string | null; tarih: string | null; tur: string | null; faturaNo: string | null; logoyaAktarildi: boolean; epostaGitti: boolean | null; logo: { tarih: string | null; tur: number } | null | undefined }>;
  kargo: Cargo[];
  eslemeYolu: string;
  hatalar: Failure[];
  zamanCizelgesi: TimelineStep[];
  taslaklar: Draft[];
  kargoVeri: Freshness;
  logoNotu: string | null;
  aliciGorunur: boolean;
  maliyetGorunur: boolean;
  kaynaklar?: Kaynaklar;
};

export type Waiting = {
  toplam: number;
  esikGun: number;
  esikUstu: number;
  kovalar: Array<{ kova: string; adet: number }>;
  firmalar: Array<Record<string, number | string> & { firma: string; toplam: number; esikUstu: number }>;
  items: Cargo[];
  sayfa: number;
  sayfaBoyu: number;
  devami: boolean;
  kargoVeri: Freshness;
  sehirler: string[];
  firmaListesi: string[];
  kaynaklar?: Kaynaklar;
};

export type ScoreRow = {
  firma?: string;
  sehir?: string;
  sube?: string;
  gonderi: number;
  sevkAdeti: number | null;
  teslim: number;
  bekleyen: number;
  iade: number;
  tutarsiz: number;
  ortancaGun: number | null;
  ortalamaGun: number | null;
  p90Gun: number | null;
  tahsilatli: number;
  iadeOrani: number | null;
  hedefGun?: number;
  hedefiAsan?: number;
  hedefiAsanOrani?: number | null;
  tutar?: number | null;
  desi?: number | null;
  desiBasi?: number | null;
  sevkBasi?: number | null;
  gonderiBasi?: number | null;
  tahsilatTutar?: number | null;
};

export type Scorecard = {
  kirilim: Group;
  kirilimAdi: string;
  baslangic: string;
  bitis: string;
  items: ScoreRow[];
  toplam: { gonderi: number; teslim: number; iade: number; ortancaGun: number | null; tutar?: number | null; desi?: number | null; desiBasi?: number | null; sevkBasi?: number | null };
  sehirler: string[];
  firmalar: string[];
  kargoVeri: Freshness;
  maliyetGorunur: boolean;
  kaynaklar?: Kaynaklar;
};

export type Decision = { id: string; tur: DecisionType; turAdi: string; kapsam: Record<string, string>; gerekce: string | null; modelOzet: string | null; karar: string; kararVeren: string; tarih: string | null };

export type ReconcileRow = {
  firma: string;
  gonderi: number;
  crmTutar: number | null;
  desi: number | null;
  tutarOkunamayan: number;
  mukerrer: number;
  mukerrerTutar: number | null;
  logoEslendi: boolean;
  logoCariler: string[];
  logoFatura: number;
  logoKdvHaric: number | null;
  logoKdvDahil: number | null;
  farkKdvHaric: number | null;
  farkKdvDahil: number | null;
};

export type Reconcile = {
  ay: string;
  baslangic: string;
  bitis: string;
  items: ReconcileRow[];
  sevk: { logoIrsaliye: number; logoFaturali: number; logoSatir: number; logoAdet: number | null; crmSevkiyat: number; eslesen: number; eslesmeOrani: number | null; eslesmeyen: string[] } | null;
  notlar: string[];
  toplam: { gonderi: number; crmTutar: number | null; logoKdvHaric: number | null; eslenmeyenFirma: number };
  kargoVeri: Freshness;
  kaynaklar?: Kaynaklar;
};

export type Candidate = { cari: string | null; unvan: string | null; fatura: number; kdvHaric: number | null; son: string | null; eslenmis: boolean };

/** Kargo maliyeti tedarikçi grubu (köprü `shipping.COST_GROUPS`). */
export type CostGroup = 'kargo' | 'pazarYeri' | 'nakliye';

export type CostMonth = {
  ay: string;
  kargo: number | null;
  pazarYeri: number | null;
  nakliye: number | null;
  toplam: number | null;
  netCiro: number | null;
  oran: number | null;
  irsaliye: number;
  tasiyici: Array<{ kod: string; irsaliye: number }>;
};

export type CostSupplier = {
  cari: string;
  unvan: string | null;
  grup: CostGroup;
  grupAdi: string;
  gider: number | null;
  pay: number | null;
  fatura: number;
  hizmetler: Array<{ kod: string; ad: string | null; gider: number | null }>;
  tasiyicilar: string[];
};

export type CostCarrier = {
  kod: string;
  kodlar: string[];
  ad: string;
  crmFirma: string | null;
  irsaliye: number;
  tasiyiciYok: boolean;
  eslendi: boolean;
  eslenenCariler: Array<{ cari: string; unvan: string | null }>;
  gider: number | null;
  irsaliyeBasi: number | null;
  pazarYeriIrsaliye: number;
  pazarYerleri: Array<{ unvan: string; irsaliye: number }>;
};

export type CostMarketplace = {
  cariler: string[];
  unvan: string;
  gider: number | null;
  irsaliye: number;
  baskaTasiyici: number;
  gonderiBasi: number | null;
  /** Gönderi başı, pazar yerlerinin ortancasından 10 kat sapıyordu; gösterilmez. */
  sapma?: boolean;
  alicilar: Array<{ cari: string | null; unvan: string | null; irsaliye: number }>;
  kodlar: Array<{ kod: string; ad: string; irsaliye: number }>;
};

export type ShippingCost = {
  period: { yil: number; baslangic: string; bitis: string };
  dataEnd: string | null;
  giderSonu: string | null;
  irsaliyeSonu: string | null;
  totals: {
    gider: number | null;
    kargo: number | null;
    pazarYeri: number | null;
    nakliye: number | null;
    netCiro: number | null;
    oran: number | null;
    irsaliye: number;
    irsaliyeBasi: number | null;
    tasiyiciYok: number;
    tedarikci: number;
    fatura: number;
  };
  byMonth: CostMonth[];
  bySupplier: CostSupplier[];
  byCarrier: CostCarrier[];
  marketplaces: CostMarketplace[];
  groups: Record<CostGroup, string>;
  notes: string[];
  yillar: number[];
  hizmetKodlari: string[];
  kaynaklar?: Kaynaklar;
};

const B = '/api/v1/shipping';

async function fail(res: Response): Promise<never> {
  const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
  const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
  if (res.status === 401) throw new EngineAuthError();
  if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  throw new Error(msg || httpErrorText(res.status));
}

async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 300_000): Promise<T> {
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

export const shippingApi = {
  meta: () => send<Meta>('GET', '/meta'),
  overview: (yenile = false) => send<Overview>('GET', `/overview${qs({ yenile })}`),
  settings: () => send<OpsSettings>('GET', '/settings'),
  saveSettings: (b: Partial<Pick<OpsSettings, 'bekleyenGun' | 'kutuluGun' | 'bolgeHedef'>>) => send<OpsSettings>('PUT', '/settings', b),
  shipments: (p: { q?: string; firma?: string; durum?: string; sayfa?: number }) =>
    send<K & { items: Order[]; sayfa: number; sayfaBoyu: number; devami: boolean; kapsam: string; firmalar: Array<{ id: string; ad: string }> }>('GET', `/shipments${qs(p)}`),
  shipment: (id: string) => send<ShipmentCard>('GET', `/shipments/${enc(id)}`),
  errors: (p: { entegrasyon?: string; sinif?: string; yenile?: boolean }) =>
    send<K & { items: Order[]; toplam: number; pencereGun: number; entegrasyonlar: string[]; not: string }>('GET', `/errors${qs(p)}`),
  untracked: () => send<K & { items: Order[]; toplam: number; pencereGun: number; durumlar: number[]; haricTipler: string[] }>('GET', '/untracked'),
  boxed: (gun?: number) => send<K & { items: Order[]; toplam: number; esikUstu: number; esikGun: number; tarihsiz: number }>('GET', `/boxed${qs({ gun })}`),
  waiting: (p: { gun?: number; firma?: string; sehir?: string; sayfa?: number }) => send<Waiting>('GET', `/waiting${qs(p)}`),
  carriers: (p: { baslangic?: string; bitis?: string; sehir?: string; firma?: string; kirilim?: Group }) => send<Scorecard>('GET', `/carriers${qs(p)}`),
  decisions: () => send<{ items: Decision[]; turler: Record<DecisionType, string> }>('GET', '/decisions'),
  createDecision: (b: { tur: DecisionType; karar: string; gerekce?: string; modelOzet?: string | null; kapsam?: Record<string, string> }) =>
    send<Decision>('POST', '/decisions', b),
  deleteDecision: (id: string) => send<{ ok: boolean }>('DELETE', `/decisions/${enc(id)}`),
  decisionSummary: (b: { baslangic?: string; bitis?: string; sehir?: string }) =>
    send<{ metin: string | null; kaynak: string | null; not: string | null }>('POST', '/decisions/summary', b),
  reconcile: (ay: string) => send<Reconcile>('GET', `/reconcile${qs({ ay })}`),
  reconcileSummary: (ay: string) => send<{ metin: string | null; not: string | null }>('POST', `/reconcile/summary${qs({ ay })}`),
  candidates: () => send<K & { items: Candidate[]; ipuclari: string[]; ayar: string }>('GET', '/reconcile/candidates'),
  cost: (yil?: number, yenile = false) => send<ShippingCost>('GET', `/cost${qs({ yil, yenile })}`),
  createDraft: (siparisId: string, tur: DraftType) => send<Draft>('POST', '/drafts', { siparisId, tur }),
  updateDraft: (id: string, b: { metin?: string; durum?: 'taslak' | 'kullanildi' }) => send<Draft>('PATCH', `/drafts/${enc(id)}`, b),
  deleteDraft: (id: string) => send<{ ok: boolean }>('DELETE', `/drafts/${enc(id)}`),
  exportUrl: (liste: ExportList, p: Record<string, string | number | undefined> = {}) => `${ENGINE_BASE}${B}/export/${liste}.xlsx${qs(p)}`,
};

/* ------------------------------------------------------------------ biçim */

const money2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const num1 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const pct1 = new Intl.NumberFormat('tr-TR', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 });
const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: 'short', year: 'numeric' });

export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${money2.format(v)} ₺`);
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export const fmtNum = (v: number | null | undefined) => (v === null || v === undefined ? '—' : num1.format(v));
export const fmtPct = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? '—' : pct1.format(v));
export const fmtDays = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${num1.format(v)} gün`);

export function fmtDay(v: string | null | undefined): string {
  if (!v) return '—';
  const d = new Date(v.length <= 10 ? `${v}T00:00:00` : v);
  if (Number.isNaN(d.getTime())) return v;
  const base = dayFmt.format(d);
  return v.length > 10 ? `${base} ${v.slice(11, 16)}` : base;
}

/** Bekleyen yaşa göre ton: eşiğin altı sakin, eşik–2×eşik uyarı, üstü kırmızı. */
export function ageTone(days: number | null | undefined, threshold: number): 'ok' | 'warn' | 'err' | 'muted' {
  if (days === null || days === undefined) return 'muted';
  if (days < threshold) return 'ok';
  if (days < threshold * 2) return 'warn';
  return 'err';
}

/** Önceki ay «YYYY-AA». */
export function previousMonth(now = new Date()): string {
  const d = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}
