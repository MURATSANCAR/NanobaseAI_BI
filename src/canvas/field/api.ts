import { ENGINE_BASE, send } from '../engine';

/** M30 Saha satış ve tahsilat köprü istemcisi (`/api/v1/field/*`). Cari = Logo müşteri carisi (cari kodu); temsilci ataması
 *  CRM'den, bakiye/yaşlandırma/satış Logo'dan (gece turu), tahsilat onay akışı CRM'den okunur. Portal CRM'e ve Logo'ya yazmaz. */

export type Chip = { key: string; points: number; label: string };
export type BucketKey = 'k_1_30' | 'k_31_60' | 'k_61_90' | 'k_90p';

export type Customer = {
  code: string;
  unvan: string | null;
  il: string | null;
  kanal: string | null;
  temsilci: string | null;
  temsilciAd: string | null;
  atama: 'owner' | 'il' | 'slsman' | null;
  bakiye: number | null;
  vadesiGecmis: number | null;
  kovalar: Record<BucketKey, number | null>;
  plansiz: number | null;
  sonOdeme: string | null;
  sonFatura: string | null;
  ytd: number | null;
  gecenYil: number | null;
  hedefBeklenen: number | null;
  hedefAcigi: number | null;
  riskDoluluk: number | null;
  siparisRiskte: number | null;
  cekOlay: number;
  puan: number | null;
  gerekce: Chip[];
  sonZiyaret: string | null;
};

export type Visit = {
  id: string;
  tur: 'cari' | 'okul' | 'kurum';
  hedef: string;
  hedefAd: string | null;
  sahip: string;
  planlanan: string | null;
  gerceklesen: string | null;
  durum: 'planlandi' | 'yapildi' | 'iptal';
  durumAd: string;
  notu: string | null;
  gizli: boolean;
  /** Başkasının gizli notu: metin gelmez. */
  gizliNot: boolean;
  ton: 'olumlu' | 'notr' | 'olumsuz' | null;
  sonrakiAdim: string | null;
  sonrakiTarih: string | null;
  sozOdemeTarihi: string | null;
  sozOdemeTutari: number | null;
  eslikEdenBayi: string | null;
  olusturma: string | null;
  guncelleyen: string | null;
  guncelleme: string | null;
};

export type VisitInput = Partial<{
  tur: string;
  hedef: string;
  planlanan: string | null;
  gerceklesen: string | null;
  durum: Visit['durum'];
  notu: string;
  ton: Visit['ton'];
  sonrakiAdim: string;
  sonrakiTarih: string | null;
  sozOdemeTarihi: string | null;
  sozOdemeTutari: number | null;
  gizli: boolean;
}>;

export type FieldEvent = { id: string; tur: string; baslik: string; detay: string | null; code: string | null; zaman: string; goruldu: boolean };

export type FieldMeta = {
  me: {
    username: string;
    display: string;
    admin: boolean;
    cari: number;
    canAll: boolean;
    canNote: boolean;
    canOverride: boolean;
    canApprovePlan: boolean;
    canPerformance: boolean;
    canExport: boolean;
  };
  weights: Array<{ key: string; max: number; label: string }>;
  buckets: Array<{ key: BucketKey; label: string }>;
  tones: Array<{ key: NonNullable<Visit['ton']>; label: string }>;
  planStates: Array<{ key: string; label: string }>;
  run: {
    asof: string | null;
    dataEnd: string | null;
    year: number | null;
    agingAsof: string | null;
    portfolio: number | null;
    assigned: number | null;
    warnings: string[] | null;
    target: {
      kaynak: 'm46' | 'crm' | 'crm-tutarsiz' | null;
      plan: { title?: string } | null;
      toplamHedef: number | null;
      pay: number | null;
      /** CRM hedef toplamı ÷ aynı carilerin geçen yıl cirosu. */
      olcek?: number | null;
      uyari?: string | null;
    } | null;
    mmx: boolean | null;
    _at?: string;
  };
  reps: Array<{ hesap: string; ad: string; cari: number }>;
  zekiQuestions: string[];
  settings: { visitCycleDays: number; collectionDays: number; pendingWarnHours: number; planMaxInstallments: number; similarMin: number; newBookDays: number; agingAsof: string; targetSource: string; mmx: boolean };
};

export type Today = {
  asof: string | null;
  dataEnd: string | null;
  warning: string | null;
  kpi: { vadesiGecmis: number; k90: number; onayBekleyen: number; onayBekleyenTutar: number; hedefOrani: number | null; cari: number };
  planned: Array<Visit & { musteri: Customer | null }>;
  /** Sıralı listenin istenen sayfası; `total` aramaya uyan müşterilerin hepsi. */
  items: Customer[];
  total: number;
  offset: number;
  events: FieldEvent[];
};

export type Collection = {
  id: string | null;
  ad: string | null;
  durum: number;
  durumAd: string;
  tip: string | null;
  tutar: number | null;
  vade: string | null;
  tahsilatTarihi: string | null;
  olusturma: string | null;
  onayTarihi: string | null;
  redTarihi: string | null;
  yasSaat: number | null;
  redSebebi: string | null;
  redMetni: string | null;
  zekiEtiket: { etiket: string | null; olasilik: number | null } | null;
  temsilci: string | null;
  temsilciAd: string | null;
  musteri: string | null;
  code: string | null;
};

export type Installment = { sira: number; tarih: string; tutar: number };
export type PaymentPlan = {
  id: string;
  code: string;
  unvan: string | null;
  temsilci: string | null;
  tutar: number;
  taksitler: Installment[];
  taksitToplam: number;
  gerekce: string | null;
  durum: 'taslak' | 'onayda' | 'onayli' | 'reddedildi';
  durumAd: string;
  oneren: string;
  olusturma: string | null;
  gonderen: string | null;
  gonderim: string | null;
  onaylayan: string | null;
  zaman: string | null;
  kararNotu: string | null;
};

export type GapBook = { stok: string; ad: string | null; pay: number; hedefAdet: number; beklenen: number; gerceklesen: number; acikAdet: number; acikCiro: number };
export type Suggestion = { stok: string; ad: string | null; benzerCari: number; benzerCiro: number; yeni: boolean; ilkSatis: string | null; neden: string[] };

export type Signals = {
  bakiye: number | null;
  vadesi_gecmis: number | null;
  gelmemis: number | null;
  plansiz: number | null;
  k_1_30: number | null;
  k_31_60: number | null;
  k_61_90: number | null;
  k_90p: number | null;
  son_odeme_tarihi: string | null;
  odeme_12ay: number | null;
  karsiliksiz_olay_12ay: number | null;
  protesto_olay_12ay: number | null;
  cek_olay_tutar: number | null;
  risk_toplam: number | null;
  limit_toplam: number | null;
  risk_doluluk: number | null;
  siparis_riskte: number | null;
  siparis_riskte_sebep: string | null;
  ytd_net_ciro: number | null;
  gecen_yil_ayni_donem: number | null;
  gecen_yil_tam: number | null;
  iade_orani: number | null;
  son_fatura: string | null;
  hedef_yil: number | null;
  hedef_beklenen: number | null;
  hedef_acigi: number | null;
  hedef_kaynagi: 'm46' | 'crm' | null;
};

export type Brief = {
  code: string;
  unvan: string | null;
  il: string | null;
  kanal: string | null;
  temsilci: string | null;
  temsilciAd: string | null;
  atama: string | null;
  asof: string | null;
  dataEnd: string | null;
  agingAsof: string | null;
  signals: Signals;
  puan: number;
  gerekce: Chip[];
  faturalar: Array<{ tarih: string | null; no: string | null; tutar: number }>;
  odemeler: Array<{ tarih: string | null; tutar: number; tur: number }>;
  siparisler: Array<{ no: string | null; tarih: string | null; tutar: number; durum: string; riskte: boolean; sebep: string | null }>;
  tahsilatlar: Collection[];
  sahaTahsilat: Array<{ no: string | null; tur: string | null; tutar: number; vade: string | null; tarih: string | null }>;
  hedefKitaplar: GapBook[];
  hedefKurali: string | null;
  oneriler: Suggestion[];
  oneriKurali: string;
  ziyaretler: Visit[];
  odemePlanlari: PaymentPlan[];
  sozGecti: { tarih: string; tutar: number | null } | null;
  warnings: string[];
  ozet: { metin: string; kaynak: 'zeki' | 'kural'; zaman: string | null };
  zekiVar: boolean;
};

export type RepRow = {
  hesap: string | null;
  ad: string;
  cari: number;
  ytd: number;
  gecenYil: number;
  buyume: number | null;
  hedefBeklenen: number;
  hedefli: number;
  hedefOrani: number | null;
  vadesiGecmis: number;
  k90: number;
  cekOlay: number;
  onayBekleyen: number;
  onayBekleyenTutar: number;
  reddedilen: number;
  ziyaret: number;
  not: number;
};
export type Weekly = { start: string; end: string; items: RepRow[]; asof: string | null; dataEnd: string | null; warning: string | null };

const P = '/api/v1/field';
const enc = encodeURIComponent;
const qs = (o: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : '';
};

/** Sabah saha brifi: Bugün listesinin kapsamından 4–5 cümle. `kaynak` 'zeki' yalnız model metni sayı denetiminden
 *  geçtiyse; 'kural' iken olgular olduğu gibi yazılır. */
export type MorningBrief = { metin: string; kaynak: 'zeki' | 'kural'; neden: string | null; gun: string; dataEnd: string | null };

export const fieldApi = {
  meta: () => send<FieldMeta>('GET', `${P}/meta`, undefined, 60_000),
  today: (p: { temsilci?: string; q?: string; limit?: number }) => send<Today>('GET', `${P}/today${qs(p)}`, undefined, 120_000),
  todayBrief: (p: { temsilci?: string }) => send<MorningBrief>('GET', `${P}/today/brief${qs(p)}`, undefined, 180_000),
  portfolio: (p: { temsilci?: string; q?: string }) => send<{ items: Customer[]; count: number }>('GET', `${P}/portfolio${qs(p)}`),
  brief: (code: string) => send<Brief>('GET', `${P}/customers/${enc(code)}/brief`, undefined, 180_000),
  summary: (code: string) => send<{ metin: string; kaynak: 'zeki' | 'kural'; not: string | null }>('POST', `${P}/customers/${enc(code)}/brief/summary`, {}, 180_000),
  collections: (p: { kova?: string; temsilci?: string }) =>
    send<{ totals: Record<BucketKey, number>; count: number; total: number; items: Customer[]; note: string }>('GET', `${P}/collections${qs(p)}`),
  crmCollections: (p: { durum: 'onay-bekliyor' | 'reddedildi'; temsilci?: string; gun?: number }) =>
    send<{ items: Collection[]; count: number; total: number; reasons: Array<{ sebep: string; adet: number }>; warnHours: number }>(
      'GET',
      `${P}/collections/crm${qs(p)}`,
      undefined,
      120_000,
    ),
  events: () => send<{ items: FieldEvent[] }>('GET', `${P}/events`),
  seen: () => send<{ marked: number }>('POST', `${P}/events/seen`, {}),
  visits: (p: { musteri?: string; tarih?: string; tur?: string; sahip?: string }) => send<{ items: Visit[] }>('GET', `${P}/visits${qs(p)}`),
  addVisit: (b: VisitInput) => send<Visit>('POST', `${P}/visits`, b),
  updateVisit: (id: string, b: VisitInput) => send<Visit>('PATCH', `${P}/visits/${enc(id)}`, b),
  followup: (id: string) => send<{ taslak: string; gonderilmez: true; sayilarDogrulandi: boolean }>('POST', `${P}/visits/${enc(id)}/followup-draft`, {}, 180_000),
  plans: (p: { durum?: string; musteri?: string }) => send<{ items: PaymentPlan[] }>('GET', `${P}/payment-plans${qs(p)}`),
  addPlan: (b: { code: string; taksitSayisi?: number; baslangic?: string }) => send<PaymentPlan>('POST', `${P}/payment-plans`, b),
  editPlan: (id: string, b: { taksitler?: Array<{ tarih: string; tutar: number }>; gerekce?: string }) => send<PaymentPlan>('PATCH', `${P}/payment-plans/${enc(id)}`, b),
  submitPlan: (id: string) => send<PaymentPlan>('POST', `${P}/payment-plans/${enc(id)}/submit`, {}),
  approvePlan: (id: string, note?: string) => send<PaymentPlan>('POST', `${P}/payment-plans/${enc(id)}/approve`, { note }),
  rejectPlan: (id: string, note: string) => send<PaymentPlan>('POST', `${P}/payment-plans/${enc(id)}/reject`, { note }),
  addOverride: (b: { code: string; neden: string; bitis?: string }) => send<{ id: string }>('POST', `${P}/overrides`, b),
  deleteOverride: (id: string) => send<{ ok: boolean }>('DELETE', `${P}/overrides/${enc(id)}`),
  weekly: (p: { hafta?: string; temsilci?: string }) => send<Weekly>('GET', `${P}/report/weekly${qs(p)}`, undefined, 120_000),
  weeklyXlsxUrl: (p: { hafta?: string; temsilci?: string }) => `${ENGINE_BASE}${P}/report/weekly.xlsx${qs(p)}`,
};

/* ------------------------------------------------------------------ biçim (saf; testli) */

const money0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const pct0 = new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 0 });
const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', timeZone: 'UTC' });
const dayYearFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });

export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${money0.format(Math.round(v))} ₺`);

/** Kısa tutar: 42.350 → «42 bin ₺», 1.250.000 → «1,3 Mn ₺». Telefonda kartta sığsın diye. */
export function fmtShort(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  const a = Math.abs(v);
  if (a >= 1_000_000) return `${(v / 1_000_000).toLocaleString('tr-TR', { maximumFractionDigits: 1 })} Mn ₺`;
  if (a >= 1_000) return `${Math.round(v / 1_000).toLocaleString('tr-TR')} bin ₺`;
  return `${Math.round(v).toLocaleString('tr-TR')} ₺`;
}

/** Adet (cari, kayıt): binlik ayraçlı, «248.351». */
export const fmtCount = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));

export const fmtPct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : pct0.format(v));

/** ISO gün (YYYY-AA-GG, saat olabilir) → «19 Tem»; yıl bu yıl değilse yıl da yazılır. */
export function fmtDay(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return '—';
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.getUTCFullYear() === now.getUTCFullYear() ? dayFmt.format(d) : dayYearFmt.format(d);
}

/** Bugünden kaç gün önce (İstanbul günü karşılaştırması gerekmez: iki taraf da gün). */
export function daysAgo(iso: string | null | undefined, today: string): number | null {
  if (!iso) return null;
  const a = Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
  const b = Date.parse(`${today.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  return Math.round((b - a) / 86_400_000);
}

/** Onay bekleyen tahsilatın yaşı: saat → «5 sa», «3 gün». */
export function fmtAge(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return '—';
  if (hours < 24) return `${Math.max(1, Math.round(hours))} sa`;
  return `${Math.floor(hours / 24)} gün`;
}

/** Puanın tonu: 60+ acil, 30+ öncelikli, altı olağan. */
export function scoreTone(p: number | null | undefined): 'err' | 'warn' | 'muted' {
  if (p === null || p === undefined) return 'muted';
  return p >= 60 ? 'err' : p >= 30 ? 'warn' : 'muted';
}

/** Türkçe sayı girişi: «20.000,50» → 20000.5; boş → null; geçersiz → NaN. */
export function parseTr(v: string): number | null {
  const s = v.trim();
  if (!s) return null;
  const n = Number(s.replace(/\s/g, '').replace(/\./g, '').replace(',', '.'));
  return Number.isFinite(n) ? n : Number.NaN;
}

/** İstanbul'a göre bugünün günü (YYYY-AA-GG). */
export function istanbulToday(now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Istanbul' }).format(now);
}

export const TONE_LABEL: Record<NonNullable<Visit['ton']>, string> = { olumlu: 'Olumlu', notr: 'Nötr', olumsuz: 'Olumsuz' };
