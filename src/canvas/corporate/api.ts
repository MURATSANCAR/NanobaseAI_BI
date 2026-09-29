import type { Kaynaklar } from '../components/sqlInfo';
import { ENGINE_BASE, send } from '../engine';
import { normalizeTrNumber } from '../components/trNumber';

/** M32 Kurumsal satış ve B2B köprü istemcisi (`/api/v1/corporate/*`). Kurum listesi ve alım geçmişi Logo'dan, kurum
 *  temsilcisi ve kitap temaları CRM'den okunur; fırsat, teklif, tema onayı ve hatırlatma portal kaydıdır. Siteye, CRM'e ve
 *  Logo'ya hiçbir şey yazılmaz; teklif belgesi indirilir, gönderimi temsilci yapar. */

const B = '/api/v1/corporate';
const enc = encodeURIComponent;
const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};

export type Stage = 'aday' | 'gorusuldu' | 'teklif' | 'karar' | 'kazanildi' | 'kaybedildi';
export type QuoteStatus = 'taslak' | 'onayda' | 'hazir' | 'gonderildi' | 'kabul' | 'ret';
export const STAGE_ORDER: Stage[] = ['aday', 'gorusuldu', 'teklif', 'karar', 'kazanildi', 'kaybedildi'];
export const OPEN_STAGES: Stage[] = ['aday', 'gorusuldu', 'teklif', 'karar'];

export type Settings = {
  channel: string;
  dealerChannels: string[];
  discountApprovalPct: number | null;
  marginMinPct: number | null;
  reminderLeadDays: number;
  silentDays: number;
  b2bDays: number;
  highlightDays: number;
  alternatives: number;
  quoteValidDays: number;
  historyYears: number;
};

export type VolumeBucket = { min: number; max: number | null; n: number; indirim: number | null };

export type RefreshStatus = {
  running: boolean;
  step: string | null;
  error: string | null;
  dataEnd: string | null;
  last: { ok?: boolean; error?: string; warnings?: string[]; _at?: string; done?: Record<string, unknown> };
};

export type Meta = {
  stages: Record<Stage, string>;
  openStages: Stage[];
  segments: Record<string, string>;
  segmentSources: Record<string, string>;
  loss: Record<string, string>;
  quoteStatus: Record<QuoteStatus, string>;
  themeStatus: Record<string, string>;
  reminderStatus: Record<string, string>;
  vocabulary: string[];
  costSource: string;
  costSourceLabel: string;
  settings: Settings;
  volume: { buckets?: VolumeBucket[]; faturalar?: number; pencere?: [string, string] };
  volumeTiers: Array<[number, number]>;
  status: RefreshStatus;
  kaynaklar?: Kaynaklar;
  me: { username: string; display: string; admin: boolean; seeAll: boolean; canApprove: boolean; canQuote: boolean; canB2b: boolean; canTheme: boolean; canExport: boolean };
};

export type Summary = {
  dataEnd: string | null;
  window: { year: number; months: number; label: string } | null;
  kurumCiro: number;
  kurumCiroGecenYil: number;
  kurumSayisi: number;
  acikFirsat: number;
  acikFirsatDeger: number;
  onayBekleyen: number;
  temaOnerisi: number;
  hatirlatma: number;
  hatirlatmaTutar: number;
  sessizBayi: number;
  bayi: number;
  kaynaklar?: Kaynaklar;
};

export type Account = {
  ref: string;
  logoKod: string | null;
  crmId: string | null;
  unvan: string | null;
  il: string | null;
  kanal: string | null;
  crmRol: string | null;
  segment: string | null;
  segmentLabel: string | null;
  segmentKaynak: 'crm' | 'oneri' | 'elle' | null;
  temsilci: string | null;
  temsilciHesap: string | null;
  iskonto: number | null;
  epostaIzni: boolean | null;
  pasif: boolean;
  ilkAlim: string | null;
  sonAlim: string | null;
  buYil: number;
  gecenYilAyni: number;
  gecenYil: number;
  toplamCiro: number;
  fatura: number;
};

export type AccountDetail = Account & {
  yillar: Array<{ yil: number; ciro: number; adet: number; fatura: number; aylar: number[] }>;
  enCokAy: number | null;
  firsatlar: Opportunity[];
  hatirlatmalar: Reminder[];
  window: Summary['window'];
  dataEnd: string | null;
  kaynaklar?: Kaynaklar;
};

export type ThemeTag = { tema: string; kaynak: 'crm' | 'oneri' | 'elle'; durum: 'onerildi' | 'onayli' | 'reddedildi'; olasilik: number | null; onaylayan: string | null };

export type Book = {
  stokKodu: string;
  ad: string | null;
  yazar?: string | null;
  yayinevi?: string | null;
  kitaplik?: string | null;
  turler?: string | null;
  yaslar?: string | null;
  hedef?: string | null;
  yasMin?: number | null;
  yasMax?: number | null;
  ilkYayin?: string | null;
  stok?: number;
  yilAdet?: number;
  fiyat?: number | null;
  fiyatListe?: string | null;
  fiyatListeSayisi?: number | null;
  fiyatKdvDahil?: boolean | null;
  crmFiyat?: number | null;
  bayiSon?: number;
  bayiOnceki?: number;
  temalar: ThemeTag[];
  degisim?: number | null;
  yeni?: boolean;
};

export type QuoteLine = {
  stok: string;
  ad: string | null;
  yazar: string | null;
  adet: number;
  listeFiyati: number;
  fiyatKaynak: 'logo' | 'crm' | 'elle' | null;
  fiyatListe: string | null;
  kdvDahil: boolean | null;
  indirim: number;
  netBirim: number;
  netTutar: number;
  listeTutar: number;
  stokMiktar: number | null;
  stokYetersiz: boolean;
  maliyetBirim: number | null;
  maliyetKaynak: string;
  maliyetTahmini: boolean;
  maliyetTarih: string | null;
  gerekce?: string;
};

export type ApprovalReason = { kod: 'indirim' | 'marj'; metin: string };

export type Quote = {
  id: string;
  firsatId: string;
  surum: number;
  durum: QuoteStatus;
  durumLabel: string;
  kalemler: QuoteLine[];
  paketAdet: number | null;
  toplamListe: number;
  toplamNet: number;
  toplamMaliyet: number | null;
  marj: number | null;
  maliyetKapsami: number | null;
  indirimOrani: number | null;
  onayGerekli: boolean;
  onayNedenleri: ApprovalReason[];
  mektup: string | null;
  notlar: string | null;
  gecerlilikGun: number | null;
  gonderen: string | null;
  gonderimAt: string | null;
  onaylayan: string | null;
  onayAt: string | null;
  onayNotu: string | null;
  gonderildiAt: string | null;
  sonucNeden: string | null;
  sonucAt: string | null;
  createdBy: string;
  createdAt: string;
  firsat?: Opportunity;
  kurum?: string;
  firsatAd?: string;
  sahip?: string;
  kaynaklar?: Kaynaklar;
};

export type Opportunity = {
  id: string;
  accountRef: string | null;
  logoKod: string | null;
  kurum: string;
  ad: string;
  tema: string | null;
  asama: Stage;
  asamaLabel: string;
  deger: number | null;
  kararTarihi: string | null;
  sahip: string;
  sonrakiAdim: string | null;
  sonrakiTarih: string | null;
  kaybetmeNedeni: string | null;
  kayipSinif: string | null;
  kayipSinifLabel: string | null;
  kayipSinifKaynak: 'elle' | 'oneri' | null;
  kaynak: 'elle' | 'hatirlatma';
  notlar: string | null;
  createdAt: string;
  updatedBy: string | null;
  updatedAt: string | null;
  teklifler?: Quote[];
  sonTeklif?: { surum: number; durum: QuoteStatus; durumLabel: string; toplamNet: number } | null;
  onayBekliyor?: boolean;
  kaynaklar?: Kaynaklar;
};

export type OppInput = Partial<{
  accountRef: string | null;
  kurum: string;
  ad: string;
  tema: string | null;
  deger: number | null;
  kararTarihi: string | null;
  sonrakiAdim: string | null;
  sonrakiTarih: string | null;
  notlar: string | null;
  asama: Stage;
  kayipSinif: string;
  kaybetmeNedeni: string;
  sahip: string;
}>;

export type Pipeline = {
  items: Opportunity[];
  columns: Array<{ asama: Stage; label: string; sayi: number; deger: number }>;
  yaklasan: Opportunity[];
  kaynaklar?: Kaynaklar;
};

export type Reminder = {
  id: string;
  logoKod: string;
  unvan: string | null;
  donemAyi: string;
  gecenYilTutar: number;
  gecenYilAdet: number | null;
  durum: 'acik' | 'firsat' | 'kapandi';
  durumLabel: string;
  firsatId: string | null;
  temsilci?: string | null;
  accountRef?: string | null;
};

export type PackageRequest = {
  temalar: string[];
  kisi: number;
  kitapSayisi: number;
  butce?: number | null;
  butceTuru?: 'toplam' | 'kisi';
  yasMin?: number | null;
  yasMax?: number | null;
  indirim?: number | null;
  alternatif?: number;
};

export type PackageAlt = {
  no: number;
  kalemler: QuoteLine[];
  paketNet: number;
  paketListe: number;
  eksik: number;
  butceyeUygun: boolean;
  toplamListe: number;
  toplamNet: number;
  toplamMaliyet: number | null;
  marj: number | null;
  maliyetKapsami: number | null;
  onayGerekli: boolean;
  onayNedenleri: ApprovalReason[];
  stokUyarisi: string[];
};

export type PackageResult = {
  temalar: string[];
  kisi: number;
  kitapSayisi: number;
  paketBasiButce: number | null;
  indirim: number;
  indirimDayanak: { indirim: number; kaynak: string; aciklama: string; n?: number };
  adaySayisi: number;
  elenen: { stokYetersiz: number; fiyatYok: number; yasUymuyor: number };
  alternatifler: PackageAlt[];
  not: string | null;
  kaynaklar?: Kaynaklar;
};

export type Dealer = {
  logoKod: string;
  unvan: string | null;
  kanal: string | null;
  il: string | null;
  sonFatura: string | null;
  gun: number | null;
  durum: 'aktif' | 'sessiz';
  fatura12ay: number;
  ciro12ay: number;
  sinif: 'A' | 'B' | 'C' | null;
  b2bSiparis: number | null;
  b2bKullanici: number | null;
  segment: string;
};

export type DealerDetail = {
  logoKod: string;
  unvan: string | null;
  kanal: string | null;
  il: string | null;
  sonFatura: string | null;
  kitaplik: Array<{ kitaplik: string; adet: number; ciro: number; kitap: number }>;
  alinan: Array<{ stokKodu: string; ad: string | null; kitaplik: string; adet: number; ciro: number; son: string | null }>;
  eksik: Book[];
  dataEnd: string;
  kaynaklar?: Kaynaklar;
};

export const corporateApi = {
  meta: () => send<Meta>('GET', `${B}/meta`),
  summary: () => send<Summary>('GET', `${B}/summary`),
  status: () => send<RefreshStatus>('GET', `${B}/status`),
  refresh: () => send<RefreshStatus & { started: boolean }>('POST', `${B}/refresh`, {}),
  accounts: (p: { q?: string; segment?: string; sort?: string; page?: number }) =>
    send<{ items: Account[]; total: number; page: number; pageSize: number; segments: Record<string, number>; window: Summary['window']; dataEnd: string | null; kaynaklar?: Kaynaklar }>(
      'GET',
      `${B}/accounts${qs(p)}`,
    ),
  account: (ref: string) => send<AccountDetail>('GET', `${B}/accounts/${enc(ref)}`),
  setSegment: (ref: string, segment: string | null) => send<AccountDetail>('PATCH', `${B}/accounts/${enc(ref)}`, { segment }),
  books: (q: string) => send<{ items: Book[]; total: number; kaynaklar?: Kaynaklar }>('GET', `${B}/books${qs({ q })}`),
  themes: (p: { durum?: string; q?: string; page?: number }) =>
    send<{ items: Book[]; total: number; page: number; pageSize: number; counts: Record<string, number>; vocabulary: string[]; kaynaklar?: Kaynaklar }>('GET', `${B}/themes${qs(p)}`),
  decideTheme: (stok: string, tema: string, karar: 'onayla' | 'reddet' | 'ekle' | 'kaldir') =>
    send<{ temalar: ThemeTag[] }>('POST', `${B}/themes/${enc(stok)}/approve`, { tema, karar }),
  suggest: (b: PackageRequest) => send<PackageResult>('POST', `${B}/packages/suggest`, b, 120_000),
  opportunities: (p: { asama?: string; q?: string; acik?: boolean } = {}) => send<Pipeline>('GET', `${B}/opportunities${qs(p)}`),
  pipelineSummary: () =>
    send<{ kapanan: number; kazanilan: number; kaybedilen: number; kazanmaOrani: number | null; kazanilanDeger: number; nedenler: Array<{ kod: string; label: string; sayi: number }>; kaynaklar?: Kaynaklar }>(
      'GET',
      `${B}/pipeline/summary`,
    ),
  opportunity: (id: string) => send<Opportunity>('GET', `${B}/opportunities/${enc(id)}`),
  createOpportunity: (b: OppInput) => send<Opportunity>('POST', `${B}/opportunities`, b),
  updateOpportunity: (id: string, b: OppInput) => send<Opportunity>('PATCH', `${B}/opportunities/${enc(id)}`, b),
  createQuote: (oppId: string, b: { kalemler?: Array<{ stok: string; adet: number; indirim?: number | null; listeFiyati?: number | null }>; paketAdet?: number | null; kopya?: string }) =>
    send<Quote>('POST', `${B}/opportunities/${enc(oppId)}/quotes`, b),
  quote: (id: string) => send<Quote>('GET', `${B}/quotes/${enc(id)}`),
  updateQuote: (id: string, b: { kalemler?: Array<{ stok: string; adet: number; indirim?: number | null; listeFiyati?: number | null }>; mektup?: string | null; notlar?: string | null; paketAdet?: number | null; gecerlilikGun?: number }) =>
    send<Quote>('PATCH', `${B}/quotes/${enc(id)}`, b),
  deleteQuote: (id: string) => send<{ ok: boolean }>('DELETE', `${B}/quotes/${enc(id)}`),
  submit: (id: string) => send<Quote>('POST', `${B}/quotes/${enc(id)}/submit`, {}),
  withdraw: (id: string) => send<Quote>('POST', `${B}/quotes/${enc(id)}/withdraw`, {}),
  approve: (id: string, note?: string) => send<Quote>('POST', `${B}/quotes/${enc(id)}/approve`, { note }),
  reject: (id: string, note: string) => send<Quote>('POST', `${B}/quotes/${enc(id)}/reject`, { note }),
  sent: (id: string) => send<Quote>('POST', `${B}/quotes/${enc(id)}/sent`, {}),
  result: (id: string, sonuc: 'kabul' | 'ret', neden?: string) => send<Quote>('POST', `${B}/quotes/${enc(id)}/result`, { sonuc, neden }),
  letter: (id: string) => send<{ mektup: string }>('POST', `${B}/quotes/${enc(id)}/letter`, {}, 240_000),
  approvals: () => send<{ items: Quote[]; kaynaklar?: Kaynaklar }>('GET', `${B}/approvals`),
  reminders: (p: { ay?: string; durum?: string } = {}) =>
    send<{ items: Reminder[]; aylar: string[]; leadDays: number; toplamGecenYil: number; kaynaklar?: Kaynaklar }>('GET', `${B}/reminders${qs(p)}`),
  updateReminder: (id: string, durum: 'acik' | 'kapandi') => send<Reminder>('PATCH', `${B}/reminders/${enc(id)}`, { durum }),
  reminderToOpportunity: (id: string) => send<Opportunity>('POST', `${B}/reminders/${enc(id)}/opportunity`, {}),
  dealers: (p: { durum?: string; gun?: number; sinif?: string; q?: string }) =>
    send<{ items: Dealer[]; total: number; counts: { aktif: number; sessiz: number }; gun: number; dataEnd: string | null; b2b: { b2bGun?: number; crm?: boolean }; kaynaklar?: Kaynaklar }>(
      'GET',
      `${B}/b2b/dealers${qs(p)}`,
    ),
  dealer: (kod: string) => send<DealerDetail>('GET', `${B}/b2b/dealers/${enc(kod)}`, undefined, 180_000),
  highlights: () => send<{ items: Book[]; total: number; gun: number; dataEnd: string | null; kaynaklar?: Kaynaklar }>('GET', `${B}/b2b/highlights`),
  pdfUrl: (id: string) => `${ENGINE_BASE}${B}/quotes/${enc(id)}/document.pdf`,
  xlsxUrl: (id: string) => `${ENGINE_BASE}${B}/quotes/${enc(id)}/document.xlsx`,
  dealersCsvUrl: (p: { durum?: string; gun?: number; sinif?: string; q?: string }) => `${ENGINE_BASE}${B}/b2b/dealers.csv${qs(p)}`,
  highlightsCsvUrl: () => `${ENGINE_BASE}${B}/b2b/highlights.csv`,
};

/* ------------------------------------------------------------------ biçim */

const money0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const money2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });

export const fmtMoney = (v: number | null | undefined, cents = false) =>
  v === null || v === undefined || !Number.isFinite(v) ? '—' : `${(cents ? money2 : money0).format(v)} ₺`;
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? '—' : int0.format(v));

/** 0.305 → «%30,5»; tam sayıysa ondalıksız (0.3 → «%30»). */
export function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const x = Math.round(v * 1000) / 10;
  return `%${Number.isInteger(x) ? int0.format(x) : x.toFixed(1).replace('.', ',')}`;
}

/** 848.110.178 → «848,1 Mn ₺». */
export function fmtShort(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  const f = (x: number, u: string) => `${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 }).format(x)} ${u} ₺`;
  if (a >= 1e9) return f(v / 1e9, 'Mr');
  if (a >= 1e6) return f(v / 1e6, 'Mn');
  if (a >= 1e3) return f(v / 1e3, 'B');
  return `${money0.format(v)} ₺`;
}

const MONTHS = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];
export const monthName = (m: number) => MONTHS[m - 1] ?? '—';

/** «2026-12» → «Aralık 2026». */
export function fmtMonth(ym: string | null | undefined): string {
  if (!ym) return '—';
  const [y, m] = ym.split('-').map(Number);
  return m ? `${monthName(m)} ${y}` : '—';
}

export function fmtDay(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  if (!y || !m || !d) return '—';
  return `${d} ${monthName(m)} ${y}`;
}

/** «1.234,5» ya da «1234.5» → sayı; boşsa null. */
export function parseNum(s: string): number | null {
  const t = s.trim().replace(/\s/g, '').replace(/₺|%/g, '');
  if (!t) return null;
  const norm = normalizeTrNumber(t);
  const n = Number(norm);
  return Number.isFinite(n) ? n : null;
}

/** Bugünden karar tarihine kalan gün; geçmişse eksi. */
export function daysUntil(iso: string | null | undefined, now: Date = new Date()): number | null {
  if (!iso) return null;
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  const t = Date.UTC(y, m - 1, d);
  const n = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((t - n) / 86_400_000);
}

export function dueText(iso: string | null | undefined, now?: Date): string | null {
  const n = daysUntil(iso, now);
  if (n === null) return null;
  if (n === 0) return 'bugün';
  if (n === 1) return 'yarın';
  if (n < 0) return `${-n} gün geçti`;
  return `${n} gün kaldı`;
}

/** Bu yıl ÷ geçen yılın aynı dönemi − 1. Geçen yıl yoksa null. */
export function growth(cur: number, prev: number): number | null {
  return prev > 0 ? cur / prev - 1 : null;
}

/** Teklif marjının ekrandaki cümlesi: bilinmiyorsa uydurma yok. */
export function marginText(q: { marj: number | null; maliyetKapsami: number | null }): string {
  if (q.marj === null) return 'Maliyet bilinmiyor';
  const cov = q.maliyetKapsami ?? 0;
  return cov >= 0.999 ? fmtPct(q.marj) : `${fmtPct(q.marj)} (tutarın ${fmtPct(cov)} kadarında maliyet var)`;
}

export const QUOTE_TONE: Record<QuoteStatus, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  taslak: 'muted',
  onayda: 'warn',
  hazir: 'violet',
  gonderildi: 'violet',
  kabul: 'ok',
  ret: 'err',
};

export const STAGE_TONE: Record<Stage, string> = {
  aday: 'bg-slate-100 text-canvas-ink',
  gorusuldu: 'bg-sky-50 text-sky-800',
  teklif: 'bg-canvas-violet/10 text-canvas-violet',
  karar: 'bg-amber-50 text-amber-800',
  kazanildi: 'bg-emerald-50 text-emerald-700',
  kaybedildi: 'bg-red-50 text-red-700',
};

/** Teklif satırlarını sunucuya giden biçime çevirir (indirim yüzde). */
export const toItems = (lines: Array<Pick<QuoteLine, 'stok' | 'adet' | 'indirim' | 'fiyatKaynak' | 'listeFiyati'>>) =>
  lines.map((l) => ({ stok: l.stok, adet: l.adet, indirim: Math.round(l.indirim * 10000) / 100, ...(l.fiyatKaynak === 'elle' ? { listeFiyati: l.listeFiyati } : {}) }));
