import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';
import { normalizeTrNumber } from '../components/trNumber';

/** M45 Finansal raporlar ekranının köprü uçları: /api/v1/finance/*. Rakamların hepsi köprüden gelir; ekran hesaplamaz. */

export type Freshness = {
  /** Faturalı satışın son günü (Logo kopyası donmuşsa o tarih). */
  veriSonu: string | null;
  /** Maliyeti işlenmiş son satış günü. */
  maliyetSonu: string | null;
  muhasebeSonu: string | null;
  okundu: string | null;
  /** Sorgu bilgisi (her rakamın SQL'i ve hesabı): `<SqlInfo k={…kaynaklar} alan="…" />`. */
  kaynaklar?: Kaynaklar;
};

export type Line = { kod: string; ad: string; sira: number; ust: string | null; isaret: number; tur: 'gelir' | 'gider' | 'ara_toplam' | 'eslenmemis'; formul: string[] | null };

export type Status = Freshness & {
  running: boolean;
  step: string | null;
  error: string | null;
  years: Record<string, { hesapSatir?: number; satisAy?: number; net?: number; at?: string }>;
  cash: { id?: string; asof?: string; errors?: Record<string, string>; _at?: string };
};

export type Meta = {
  months: string[];
  grains: Record<Grain, string>;
  profitBy: Record<ProfitBy, string>;
  taxStatuses: Record<TaxStatus, string>;
  lines: Line[];
  years: number[];
  defaultYear: number | null;
  defaultMonth: number | null;
  data: Status;
  me: { username: string; display: string; canCash: boolean; canMap: boolean; canClose: boolean; canTax: boolean; canNote: boolean; canExport: boolean; canComment?: boolean; canApproveComment?: boolean };
};

export type Grain = 'ay' | 'ceyrek' | 'ytd';
export type ProfitBy = 'kitap' | 'seri' | 'yayinevi' | 'kanal' | 'cari';
export type TaxStatus = 'bekliyor' | 'hazirlaniyor' | 'hazir' | 'verildi';

export type SummaryCard = {
  id: string;
  label: string;
  value: number | null;
  unit: '₺' | 'oran' | 'metin';
  compare?: number | null;
  compareLabel?: string;
  change?: number | null;
  ratio?: number | null;
  state?: string;
  note?: string | null;
  yaklasik: boolean;
  sekme?: string;
};

export type Summary = Freshness & {
  hazir: boolean;
  donem?: string;
  cards: SummaryCard[];
  dikkat: Array<{ tur: 'sapma' | 'nakit' | 'vergi'; metin: string; tutar: number | null; sekme: string }>;
};

export type PnlRow = Line & {
  values: Record<string, number | null>;
  onaysiz: number | null;
  hesap: number;
  notlar: string[];
  yaklasik: boolean;
};

export type Close = {
  durum: 'acik' | 'kapandi';
  kapatan: string | null;
  kapanisTarihi: string | null;
  ozetHash: string | null;
  not: string | null;
  acan: string | null;
  acilisTarihi: string | null;
  acilisGerekce: string | null;
  degisti?: boolean;
};

export type Pnl = Freshness & {
  year: number;
  month: number;
  grain: Grain;
  columns: Record<string, { label: string; complete?: boolean; loaded?: boolean; plan?: { title: string } | null; note?: string }>;
  rows: PnlRow[];
  dislanan: number | null;
  kurallar: Record<'yansitma' | 'kapanis', { hesap: number; borc: number | null; alacak: number | null }>;
  esleme: { onaysizTutar: number | null; eslenmemis: number; eslenmemisTutar: number | null };
  maliyet: { maliyetliPay: number | null; maliyetsizNet: number | null; maliyetsizSatir: number; satisSatir: number; yaklasik: boolean };
  faturaNetSatis: number | null;
  mutabakatFarki: number | null;
  mizan: { durum: 'denk' | 'fark' | 'okunmadi'; borc?: number; alacak?: number; fark?: number };
  kapanis: Close | null;
};

export type Mapping = {
  satir: string | null;
  durum: 'onayli' | 'dislandi' | 'oneri' | 'yok';
  kaynak: 'onay' | 'zeki' | 'hesap-plani' | null;
  kayit: string | null;
  olasilik?: number | null;
  onaylayan?: string | null;
  not?: string | null;
};

export type LineAccounts = Freshness & {
  kod: string;
  ad: string;
  donem: string;
  toplam: number | null;
  items: Array<{ hesap: string; ad: string | null; borc: number; alacak: number; etki: number; satirSayisi: number; satir: string; esleme: Mapping }>;
};

export type Entries = Freshness & {
  hesap: string;
  donem: string;
  total: number;
  page: number;
  pageSize: number;
  sql: string;
  items: Array<{ tarih: string | null; fisNo: string | null; fisTuru: number | null; hesap: string; hesapAdi: string | null; aciklama: string | null; borc: number; alacak: number; merkez: string | null; kural: 'dahil' | 'yansitma' | 'kapanis' }>;
};

export type AccountMap = Freshness & {
  year: number;
  lines: Line[];
  counts: Record<Mapping['durum'], number>;
  amounts: Record<Mapping['durum'], number>;
  suggest: { running?: boolean; count?: number; oneri?: number; belirsiz?: number; hata?: number; error?: string; _at?: string };
  items: Array<{ hesap: string; ad: string | null; grup: string; etki: number | null; hareketli: boolean; esleme: Mapping }>;
};

export type Reconciliation = Freshness & {
  donem: string;
  muhasebe: { brutSatis: number | null; satisIndirimleri: number | null; netSatis: number | null };
  fatura: { satis: number | null; iade: number | null; netSatis: number | null; iskontoOncesi: number | null; iskonto: number | null } | null;
  fark: number | null;
  olasiNedenler: string[];
};

export type ProfitRow = {
  key: string;
  ad: string;
  kanallar: string[] | null;
  adet: number | null;
  iskontoOncesi: number | null;
  iskonto: number | null;
  iskontoOrani: number | null;
  net: number | null;
  maliyetLogo: number | null;
  maliyetliNet: number | null;
  katkiKesin: number | null;
  marjKesin: number | null;
  maliyetsizNet: number | null;
  maliyetTahmini: number | null;
  maliyetBilinmeyenNet: number | null;
  telif: number | null;
  telifsizNet: number | null;
  katkiYaklasik: number | null;
  marjYaklasik: number | null;
  kapsam: number | null;
  yaklasik: boolean;
};

export type Profit = Freshness & {
  by: ProfitBy;
  byLabel: string;
  year: number;
  donem: string;
  items: ProfitRow[];
  toplam: ProfitRow;
  total: number;
  page: number;
  pageSize: number;
  telif: { hesaplandi: boolean; sozlesmeli: number; sozlesmesiz: number; kaynak: string };
};

export type CashWeek = { hafta: number; baslangic: string; bitis: string; acilis: number; giris: number; cikis: number; net: number; kapanis: number; acik: boolean; enBuyukCikis: string | null; kismi: boolean };
export type CashLine = { kalem: string; yon: 'giris' | 'cikis' | 'bilgi'; kaynak: string; yaklasik: boolean; haftalar: number[]; toplam: number; ayrinti: unknown[][] };
export type Cash = Freshness & {
  run: { id: string; at: string | null; by: string | null; veriSonu: string | null; baslangic: string } | null;
  acilisBakiye?: number;
  pozisyon?: Record<string, number>;
  vadesiGecmis?: Record<string, number>;
  dovizTelif?: Record<string, number>;
  hatalar?: Record<string, string>;
  butceDahil?: boolean;
  kalemler?: CashLine[];
  haftalar?: CashWeek[];
  acikHafta?: CashWeek | null;
  /** Olasılıklı bant (tahmin): kesin kalemler kuraldan, tahsilat/ödeme p10–p90. Kantil yoksa `var: false`. */
  bant?: CashBand;
  status: Status;
};

export type Quantiles = { p10: number; p50: number; p90: number };
export type CashBand =
  | {
      var: true;
      etiket: 'tahmin';
      gecmisHafta: number;
      not: string;
      kesinKalemler: string[];
      yerineGecen: string[];
      enKotuAcik: { hafta: number; baslangic: string; kapanis: number } | null;
      haftalar: Array<{ hafta: number; baslangic: string; kesin: number; tahsilat: Quantiles; odeme: Quantiles;
        kapanis: { kotu: number; orta: number; iyi: number }; kuralKapanis: number }>;
    }
  | { var: false; neden: string };

export type CashHistory = Freshness & {
  items: Array<{ run: string; runAt: string | null; hafta: number; baslangic: string; tahminNet: number; gercekNet: number; sapma: number }>;
  ortalamaMutlakSapma: number | null;
  not: string | null;
};

export type Note = { id: string; anahtar: string; metin: string; hazirlayan: string; tarih: string | null };

export type BudgetView = Freshness & {
  year: number;
  plan: { id: string; title: string; version: number; scenarioLabel?: string; decidedAt?: string | null; decidedBy?: string | null } | null;
  mesaj?: string;
  asof?: string | null;
  esik?: number;
  sirket?: { hedefCiro: number; beklenenCiro: number; gercekCiro: number; oran: number | null; durum: string };
  gider?: { butce: number; butceDonem: number; gercek: number; kullanim: number | null; asim: number; yaklasti: number };
  aylar?: Array<{ ay: number; hedef: number; gercek: number | null }>;
  departmanlar?: Array<{ anahtar: string; merkezKodu: string; merkezAdi: string | null; hesap: string; hesapAdi: string | null; yillik: number; butceDonem: number | null; gercek: number | null; kullanim: number | null; durum: string | null; sapma: number | null; not: Note | null }>;
  sapmalar?: Array<{ id: string; anahtar: string; kind: string; scope: string; key: string; label: string | null; ratio: number | null; expected: number | null; actual: number | null; gap: number | null; not: Note | null }>;
  sapmaToplam?: number;
};

export type TaxItem = { id: string; beyan: string; donem: string | null; sonGun: string; sorumlu: string | null; durum: TaxStatus; durumLabel: string; tutar: number | null; not: string | null; kalanGun: number; gecikti: boolean };
export type TaxList = { items: TaxItem[]; statuses: Record<TaxStatus, string>; today: string; yaklasan: TaxItem[]; geciken: TaxItem[]; kaynaklar?: Kaynaklar };

const B = '/api/v1/finance';

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
  if (res.status === 403) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  }
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new Error(msg || httpErrorText(res.status));
  }
  return (await res.json()) as T;
}

const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;

export type Period = { year: number; month: number; grain: Grain };

export const financeApi = {
  meta: () => send<Meta>('GET', '/meta'),
  status: () => send<Status>('GET', '/status'),
  refresh: () => send<Status & { started: boolean }>('POST', '/refresh', {}),
  summary: () => send<Summary>('GET', '/summary', undefined, 180_000),
  pnl: (p: Period) => send<Pnl>('GET', `/pnl${qs(p)}`, undefined, 180_000),
  lineAccounts: (kod: string, p: Period) => send<LineAccounts>('GET', `/pnl/lines/${enc(kod)}/accounts${qs(p)}`),
  entries: (hesap: string, p: Period, page: number) => send<Entries>('GET', `/pnl/accounts/${enc(hesap)}/entries${qs({ ...p, page })}`, undefined, 300_000),
  pnlExportUrl: (p: Period) => `${ENGINE_BASE}${B}/pnl/export.xlsx${qs(p)}`,
  reconciliation: (p: Period) => send<Reconciliation>('GET', `/reconciliation${qs(p)}`),
  accountMap: (year?: number) => send<AccountMap>('GET', `/account-map${qs({ year })}`),
  setMapping: (hesap: string, satir: string, not?: string) => send<{ hesap: string; satir: string }>('PATCH', `/account-map/${enc(hesap)}`, { satir, not }),
  resetMapping: (hesap: string) => send<{ hesap: string }>('DELETE', `/account-map/${enc(hesap)}`),
  approveMappings: (codes: string[]) => send<{ approved: Array<{ hesap: string; satir: string }>; skipped: Array<{ hesap: string; neden: string }> }>('POST', '/account-map/approve', { codes }),
  suggestMappings: (codes?: string[]) => send<{ started: boolean; count: number; message?: string }>('POST', '/account-map/suggest', { codes }),
  close: (year: number, month: number, not?: string) => send<Close>('POST', `/closes/${year}/${month}`, { not }),
  reopen: (year: number, month: number, reason: string) => send<Close>('DELETE', `/closes/${year}/${month}${qs({ reason })}`),
  profit: (p: { by: ProfitBy; year: number; frm: number; to: number; q?: string; sort?: string; page?: number }) =>
    send<Profit>('GET', `/profitability${qs(p)}`, undefined, 180_000),
  profitExportUrl: (p: { by: ProfitBy; year: number; frm: number; to: number; q?: string; sort?: string }) => `${ENGINE_BASE}${B}/profitability/export.csv${qs(p)}`,
  cash: (budget = false) => send<Cash>('GET', `/cash${qs({ budget: budget || undefined })}`),
  cashRebuild: () => send<Status & { started: boolean }>('POST', '/cash/rebuild', {}),
  cashHistory: () => send<CashHistory>('GET', '/cash/history'),
  budget: (year: number) => send<BudgetView>('GET', `/budget${qs({ year })}`, undefined, 180_000),
  saveNote: (b: { year: number; anahtar: string; metin: string }) => send<Note>('POST', '/notes', b),
  tax: (year?: number) => send<TaxList>('GET', `/tax-calendar${qs({ year })}`),
  taxCreate: (b: Partial<TaxItem>) => send<TaxItem>('POST', '/tax-calendar', b),
  taxUpdate: (id: string, b: Partial<TaxItem>) => send<TaxItem>('PATCH', `/tax-calendar/${enc(id)}`, b),
  taxDelete: (id: string) => send<{ ok: boolean }>('DELETE', `/tax-calendar/${enc(id)}`),
  taxCopy: (from: number, to: number) => send<{ kopyalanan: number; atlanan: number }>('POST', '/tax-calendar/copy', { from, to }),
  commentary: (year?: number, month?: number) => send<Commentary>('GET', `/commentary${qs({ year, month })}`),
  commentaryDraft: (year: number, month: number) => send<Commentary>('POST', '/commentary/draft', { year, month }, 300_000),
  commentarySave: (year: number, month: number, metin: string) => send<Commentary>('PUT', '/commentary', { year, month, metin }),
  commentaryApprove: (year: number, month: number) => send<Commentary>('POST', '/commentary/approve', { year, month }),
};

/** Aylık finansal yorum: Zeki AI taslağı (ya da model yoksa kural metni) → CFO düzeltir → açık yetkiyle onaylar. */
export type Commentary = {
  year: number;
  month: number;
  donem: string;
  id?: string;
  metin: string | null;
  durum: 'taslak' | 'onayli' | null;
  /** zeki: model metni sayı denetiminden geçti · kural: olgular olduğu gibi · insan: CFO düzeltti. */
  kaynak?: 'zeki' | 'kural' | 'insan' | null;
  neden?: string | null;
  hazirlayan?: string;
  onaylayan?: string | null;
  tarih?: string | null;
  /** Metinde geçip olgularda olmayan sayılar (insan düzeltmesinde gözden geçirme). */
  olguDisiSayilar?: string[];
};

/* ------------------------------------------------------------------ biçim */

const money0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const money2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct1 = new Intl.NumberFormat('tr-TR', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 });

export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${money0.format(v)} ₺`);
export const fmtMoney2 = (v: number | null | undefined) => (v === null || v === undefined ? '—' : money2.format(v));
export const fmtNum = (v: number | null | undefined) => (v === null || v === undefined ? '—' : money0.format(v));
export const fmtPct = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? '—' : pct1.format(v));

/** 848.110.178 → «848,1 Mn ₺». */
export function fmtShort(v: number | null | undefined, unit = ' ₺'): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  const f = (x: number, u: string) => `${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 }).format(x)} ${u}${unit}`;
  if (a >= 1e9) return f(v / 1e9, 'Mr');
  if (a >= 1e6) return f(v / 1e6, 'Mn');
  if (a >= 1e3) return f(v / 1e3, 'B');
  return `${money0.format(v)}${unit}`;
}

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
export function fmtDay(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return dayFmt.format(new Date(Date.UTC(y, m - 1, d)));
}

/** «1.234,5» ya da «1234.5» → sayı; boşsa null. */
export function parseNum(s: string): number | null {
  const t = s.trim().replace(/\s/g, '').replace(/₺|%/g, '');
  if (!t) return null;
  const norm = normalizeTrNumber(t);
  const n = Number(norm);
  return Number.isFinite(n) ? n : null;
}

export const MAP_LABEL: Record<Mapping['durum'], { label: string; tone: 'ok' | 'warn' | 'err' | 'muted' }> = {
  onayli: { label: 'Onaylı', tone: 'ok' },
  dislandi: { label: 'Dışlandı', tone: 'muted' },
  oneri: { label: 'Öneri', tone: 'warn' },
  yok: { label: 'Eşlenmemiş', tone: 'err' },
};

export const SOURCE_LABEL: Record<string, string> = { onay: 'Muhasebe kararı', zeki: 'Zeki AI önerisi', 'hesap-plani': 'Hesap planı kuralı' };

export const RULE_LABEL: Record<string, string> = { dahil: 'Rapora girer', yansitma: 'Yansıtma (sayılmaz)', kapanis: 'Kapanış fişi (sayılmaz)' };
