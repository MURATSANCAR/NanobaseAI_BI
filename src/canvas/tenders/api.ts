import type { Reading } from '../components/ReadingBadge';
import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';
import { normalizeTrNumber } from '../components/trNumber';

/** Uç cevabındaki sorgu bilgisi (`<SqlInfo k={…kaynaklar} alan="…" />`). */
export type WithK = { kaynaklar?: Kaynaklar };

/** M33 İhale takibi ekranlarının köprü uçları: /api/v1/tenders/*. */

export type TenderStatus = 'yeni' | 'inceleniyor' | 'basvurulacak' | 'basvurulmayacak' | 'teklif_verildi' | 'kazanildi' | 'kaybedildi' | 'iptal';
export type MatchState = 'bekliyor' | 'eslesti' | 'oneri' | 'belirsiz' | 'yok';
export type CheckState = 'var' | 'eksik' | 'gecersiz';

export type Me = { username: string; display: string; canEdit: boolean; canDecide: boolean; canDocs: boolean; canExport: boolean; canSource: boolean };

export type TenderMeta = {
  durumlar: Record<TenderStatus, string>;
  acikDurumlar: TenderStatus[];
  elleDurumlar: TenderStatus[];
  kurumTurleri: Record<string, string>;
  usuller: Record<string, string>;
  eslesmeDurumlari: Record<MatchState, string>;
  belgeTurleri: Record<string, string>;
  kontrolDurumlari: Record<CheckState, string>;
  sonuclar: Record<string, string>;
  kararlar: Record<string, string>;
  ayarlar: {
    autoProb: number; autoMargin: number; suggestProb: number; suggestMargin: number; candidates: number;
    priceSource: string; defaultVat: number; historyMin: number; remindDays: number[]; docWarnDays: number;
    fileMaxMb: number; publicChannel: string; watchEnabled: boolean;
    weights: Record<'eslesme' | 'stok' | 'belge' | 'sure', number>; fullDays: number;
  };
  me: Me;
  modelVar: boolean;
};

export type Score = {
  puan: number | null;
  parcalar: Record<'eslesme' | 'stok' | 'belge' | 'sure', number | null>;
  agirliklar: Record<string, number>;
  kalanGun: number | null;
};

export type Quote = { deger: string; kaynak: string; sayfa?: string; okuma?: 'metin' | 'ocr' | 'yok'; guven?: number | null };
export type Summary = {
  konu?: Quote | null; teslimSuresi?: Quote | null; teminat?: Quote | null; belgeler?: Quote[]; kosullar?: Quote[];
  atilan?: number; parca?: number; karakter?: number; dosya?: string; okuma?: Reading;
};

export type TenderRow = {
  id: string;
  kaynak: string;
  kaynakAdi: string;
  kaynakNo: string | null;
  kurum: string;
  kurumTuru: string;
  kurumTuruAdi: string;
  il: string | null;
  konu: string;
  usul: string | null;
  usulAdi: string | null;
  yaklasikTutar: number | null;
  ilanTarihi: string | null;
  sonTeklifTarihi: string | null;
  kalanGun: number | null;
  teslimSuresi: string | null;
  teminatTutari: number | null;
  teminatIadeTarihi: string | null;
  yetkili: string | null;
  durum: TenderStatus;
  durumAdi: string;
  sorumlu: string | null;
  fiyatOrani: number | null;
  fiyatOraniKaynak: string | null;
  uygunlukPuani: number | null;
  uygunluk: Partial<Score>;
  kitapIlani: { sonuc?: 'evet' | 'hayir' | 'belirsiz'; olasilik?: number | null };
  kararMetni: string | null;
  notlar: string | null;
  olusturan: string;
  olusturma: string | null;
  kalem?: number;
  eslesen?: number;
  onayBekliyor?: boolean;
};

export type Candidate = { stokKodu: string; ad: string | null; yazar: string | null; yayinevi: string | null; isbn: string | null; benzerlik: number | null };

export type Item = {
  sira: number;
  metin: string;
  ad: string | null;
  yazar: string | null;
  yayinevi: string | null;
  adet: number | null;
  isbn: string | null;
  stokKodu: string | null;
  eslesenAd: string | null;
  yontem: string | null;
  yontemAdi: string | null;
  durum: MatchState;
  durumAdi: string;
  olasilik: number | null;
  adaylar: Candidate[];
  stok: number | null;
  stokYetersiz: boolean;
  listeFiyati: number | null;
  listeFiyatiKdvHaric: number | null;
  fiyatKaynagi: string | null;
  kdvOrani: number | null;
  logoFiyati: number | null;
  logoFiyatNotu: string | null;
  onerilenFiyat: number | null;
  fiyatElle: boolean;
  tutar: number | null;
  tahminiMaliyet: number | null;
  maliyetKaynagi: string | null;
  marj: number | null;
  onaylayan: string | null;
  onayZamani: string | null;
  not: string | null;
};

export type Totals = {
  kalem: number;
  durumlar: Record<MatchState, number>;
  stokYetersiz: number;
  fiyatli: number;
  disarida: number;
  araToplam: number;
  kdv: number;
  genelToplam: number;
  listeToplami: number;
  maliyet: number | null;
  maliyetKapsam: number;
  marj: number | null;
  maliyetNotu: string | null;
};

export type CheckItem = {
  id: string; sira: number; kalem: string; belgeTuru: string | null; belgeTuruAdi: string | null; zorunlu: boolean;
  durum: CheckState; durumAdi: string; belgeId: string | null; belgeAdi: string | null; gecerlilik: string | null;
  kaynak: string | null; kaynakCumle: string | null; not: string | null;
};

export type Decision = {
  id: string; karar: 'basvur' | 'basvurma'; kararAdi: string; durum: 'onayda' | 'onaylandi' | 'reddedildi' | 'geri_cekildi';
  teklifToplami: number | null; fiyatOrani: number | null; gerekce: string | null; ozet: Partial<BriefFacts>;
  oneren: string; oneriZamani: string | null; onaylayan: string | null; onayZamani: string | null; onayNotu: string | null;
};

export type Result = {
  sonuc: 'kazanildi' | 'kaybedildi' | 'iptal'; sonucAdi: string; kazanan: string | null; kazananFiyat: number | null;
  bizimFiyat: number | null; listeToplami: number | null; kazananListeOrani: number | null; neden: string | null;
  kaynak: string | null; kaydeden: string; zaman: string | null;
};

export type HistorySummary = { sonuc: number; kazanilan: number; kaybedilen: number; kazananOranOrtanca: number | null; oranSayisi: number };

export type BriefFacts = {
  yaklasikTutar: number | null; uygunlukPuani: number | null; kalem: number; eslesen: number; katalogdaYok: number;
  stokYetersiz: number; teklifAraToplam: number; teklifGenelToplam: number; listeToplami: number; fiyatOrani: number | null;
  marj: number | null; maliyetKapsam: number; maliyetNotu: string | null; eksikBelgeler: string[]; teminatTutari: number | null;
  kalanGun: number | null; gecmis: { kurum: HistorySummary; kurumTuru: HistorySummary }; riskler: string[];
};

export type Job = {
  id: string; tur: 'ozet' | 'eslestirme' | 'risk'; durum: 'sirada' | 'calisiyor' | 'bitti' | 'hata' | 'kesildi';
  ilerleme: number; toplam: number; sonuc: Record<string, unknown>; hata: string | null; baslatan: string;
  baslangic: string | null; bitis: string | null;
};

/** Şartnamedeki riskli koşul: alıntı şartnameden birebir; kategori kapalı kümeden; karar insanın. */
export type RiskFlag = {
  id: string; sira: number; kategori: string | null; kategoriAdi: string | null; alinti: string; kaynak: 'zeki' | 'kural' | 'incele';
  ipucu: string | null; olasilik: number | null; marj: number | null; karar: 'engel' | 'engel-degil' | 'bilgi' | null;
  kararAdi: string | null; kararNotu: string | null; kararVeren: string | null; kararZamani: string | null; dosya: string | null;
};
export type RiskList = { items: RiskFlag[]; kategoriler: Record<string, string>; kararlar: Record<string, string>; engel: number; kararsiz: number };

export type FileRow = { id: string; tur: 'sartname' | 'ek' | 'belge'; ad: string; boyut: number; mime: string; yukleyen: string; zaman: string | null };

export type TenderDetail = TenderRow & {
  /** Sorgu bilgisi (her rakamın SQL'i ve hesabı). */
  kaynaklar?: Kaynaklar;
  ozet: Summary;
  kalemler: Item[];
  toplamlar: Totals;
  kontrolListesi: CheckItem[];
  dosyalar: FileRow[];
  kararlar: Decision[];
  sonuc: Result | null;
  isler: Job[];
  kararOzeti: BriefFacts;
  ayarlar: { autoProb: number; autoMargin: number; suggestProb: number; suggestMargin: number; candidates: number; priceSource: string };
};

export type DocRow = {
  id: string; ad: string; tur: string; turAdi: string; gecerlilik: string | null; kalanGun: number | null;
  durum: 'gecerli' | 'yaklasti' | 'doldu' | 'suresiz'; dosyaAdi: string | null; boyut: number | null; dosyaVar: boolean;
  not: string | null; yukleyen: string; zaman: string | null;
};

export type CalendarEvent = {
  tarih: string; tur: 'son_teklif' | 'belge' | 'ihale_belgesi' | 'teminat_iade'; baslik: string; ayrinti: string | null;
  ihaleId?: string; belgeId?: string; kalanGun: number | null; onayBekliyor?: boolean;
};

export type ResultRow = Result & { id: string; kurum: string; kurumTuru: string; kurumTuruAdi: string; konu: string; il: string | null };

export type PublicSales = {
  year: number; firm: string; kanal: string; crmKurum: number; crmLogoBagsiz: number; rolSayilari: Record<string, number>;
  rows: Array<{ ref: number; kod: string | null; unvan: string | null; il: string | null; kanal: string | null; ciro: number; adet: number; fatura: number; kaynak: 'crm' | 'kanal' | 'ikisi'; crmRol: number | null }>;
  toplamCiro: number; toplamAdet: number; cariSayisi: number; kaynakCiro: Record<'crm' | 'kanal' | 'ikisi', number>;
  iller: Array<{ il: string; ciro: number; adet: number; cari: number }>;
};

export type TenderInput = Partial<{
  kurum: string; kurumTuru: string; il: string; konu: string; usul: string; kaynakNo: string; yaklasikTutar: number | null;
  ilanTarihi: string | null; sonTeklifTarihi: string | null; teslimSuresi: string; teminatTutari: number | null;
  teminatIadeTarihi: string | null; yetkili: string; sorumlu: string; notlar: string; durum: TenderStatus; fiyatOrani: number;
}>;

const B = '/api/v1/tenders';

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

async function upload<T>(path: string, file: File | null, params: Record<string, string>): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${B}${path}${qs({ ...params, filename: file?.name ?? '' })}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file ?? new Blob([]),
    signal: AbortSignal.timeout(600_000),
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

export const tendersApi = {
  meta: () => send<TenderMeta>('GET', '/meta'),
  list: (p: { durum?: string; il?: string; kurumTuru?: string; q?: string; son?: string }) =>
    send<{ items: TenderRow[]; total: number; iller: string[]; durumSayilari: Record<string, number> } & WithK>('GET', qs(p)),
  create: (b: TenderInput) => send<TenderDetail>('POST', '', b),
  detail: (id: string) => send<TenderDetail & WithK>('GET', `/${enc(id)}`),
  update: (id: string, b: TenderInput) => send<TenderDetail>('PATCH', `/${enc(id)}`, b),
  remove: (id: string) => send<{ ok: boolean }>('DELETE', `/${enc(id)}`),
  addFile: (id: string, file: File, tur: 'sartname' | 'ek' | 'belge') => upload<FileRow>(`/${enc(id)}/files`, file, { tur }),
  deleteFile: (id: string, fid: string) => send<{ ok: boolean }>('DELETE', `/${enc(id)}/files/${enc(fid)}`),
  fileUrl: (id: string, fid: string) => `${ENGINE_BASE}${B}/${enc(id)}/files/${enc(fid)}`,
  summarize: (id: string, fileId?: string) => send<Job>('POST', `/${enc(id)}/summarize`, fileId ? { fileId } : {}),
  risks: (id: string) => send<RiskList>('GET', `/${enc(id)}/risk-flags`),
  runRisks: (id: string, fileId?: string) => send<Job>('POST', `/${enc(id)}/risk-flags`, fileId ? { fileId } : {}),
  decideRisk: (id: string, rid: string, b: { karar: string; not?: string }) => send<RiskFlag>('PATCH', `/${enc(id)}/risk-flags/${enc(rid)}`, b),
  importItems: (id: string, b: { text?: string; fileId?: string; mode: 'replace' | 'append' }) =>
    send<{ eklenen: number; okunamayan: Array<{ satir: number; metin: string; neden: string }>; baslik: string[] }>('POST', `/${enc(id)}/items/import`, b, 300_000),
  match: (id: string, b: { onlyPending?: boolean; refreshCatalog?: boolean } = {}) => send<Job>('POST', `/${enc(id)}/items/match`, b),
  job: (id: string, jid: string) => send<Job>('GET', `/${enc(id)}/jobs/${enc(jid)}`),
  updateItem: (id: string, sira: number, b: { stokKodu?: string | null; onayla?: boolean; adet?: number | null; onerilenFiyat?: number | null; not?: string }) =>
    send<Item>('PATCH', `/${enc(id)}/items/${sira}`, b, 180_000),
  catalogSearch: (id: string, q: string) => send<{ items: Candidate[] } & WithK>('GET', `/${enc(id)}/catalog-search${qs({ q })}`, undefined, 180_000),
  pricingUrl: (id: string) => `${ENGINE_BASE}${B}/${enc(id)}/pricing.xlsx`,
  checklist: (id: string) => send<{ items: CheckItem[]; turler: Record<string, string> } & WithK>('GET', `/${enc(id)}/checklist`),
  updateChecklist: (id: string, items: Array<Partial<CheckItem> & { sil?: boolean }>) =>
    send<{ items: CheckItem[] }>('PATCH', `/${enc(id)}/checklist`, { items }),
  brief: (id: string) => send<{ metin: string; kaynak: 'zeki' | 'kural'; not?: string | null }>('POST', `/${enc(id)}/brief`, {}, 180_000),
  submit: (id: string, b: { karar: 'basvur' | 'basvurma'; gerekce?: string }) => send<Decision>('POST', `/${enc(id)}/decision/submit`, b),
  withdraw: (id: string) => send<Decision>('POST', `/${enc(id)}/decision/withdraw`, {}),
  approve: (id: string, note?: string) => send<Decision>('POST', `/${enc(id)}/decision/approve`, { note }),
  reject: (id: string, note: string) => send<Decision>('POST', `/${enc(id)}/decision/reject`, { note }),
  result: (id: string, b: { sonuc: string; kazanan?: string; kazananFiyat?: number | null; bizimFiyat?: number | null; neden?: string; kaynak?: string }) =>
    send<Result>('POST', `/${enc(id)}/result`, b),
  calendar: (gun = 90) => send<{ items: CalendarEvent[]; gun: number; bugun: string } & WithK>('GET', `/calendar${qs({ gun })}`),
  results: () => send<{ items: ResultRow[]; ozet: Array<{ kurumTuru: string; kurumTuruAdi: string; sonuc: number; kazanilan: number; kazananOranOrtanca: number | null; oranSayisi: number }> } & WithK>('GET', '/results'),
  publicSales: (yil: number, yenile = false) => send<PublicSales & WithK>('GET', `/public-sales${qs({ yil, yenile: yenile || undefined })}`, undefined, 600_000),
  documents: () => send<{ items: DocRow[]; turler: Record<string, string>; uyariGun: number } & WithK>('GET', '/documents'),
  addDocument: (file: File | null, meta: { ad: string; tur: string; gecerlilik?: string; note?: string }) =>
    upload<DocRow>('/documents', file, { ad: meta.ad, tur: meta.tur, gecerlilik: meta.gecerlilik ?? '', note: meta.note ?? '' }),
  updateDocument: (id: string, b: { ad?: string; tur?: string; gecerlilik?: string | null; not?: string }) => send<DocRow>('PATCH', `/documents/${enc(id)}`, b),
  deleteDocument: (id: string) => send<{ ok: boolean }>('DELETE', `/documents/${enc(id)}`),
  documentUrl: (id: string) => `${ENGINE_BASE}${B}/documents/${enc(id)}/file`,
};

/* ------------------------------------------------------------------ biçim */

const money2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const pct1 = new Intl.NumberFormat('tr-TR', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 });
const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: 'short', year: 'numeric' });

export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${money2.format(v)} ₺`);
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export const fmtPct = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? '—' : pct1.format(v));
export function fmtDay(v: string | null | undefined): string {
  if (!v) return '—';
  const d = new Date(v.length <= 10 ? `${v}T00:00:00` : v);
  if (Number.isNaN(d.getTime())) return v;
  const base = dayFmt.format(d);
  return v.length > 10 ? `${base} ${v.slice(11, 16)}` : base;
}
export function fmtLeft(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  if (n === 0) return 'bugün';
  return n > 0 ? `${n} gün kaldı` : `${-n} gün geçti`;
}

/** «1.234,5» ya da «1234.5» → sayı; boşsa null. */
export function parseNum(s: string): number | null {
  const t = s.trim().replace(/\s/g, '').replace(/₺|%/g, '');
  if (!t) return null;
  const norm = normalizeTrNumber(t);
  const n = Number(norm);
  return Number.isFinite(n) ? n : null;
}

export const STATUS_TONE: Record<TenderStatus, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  yeni: 'violet',
  inceleniyor: 'warn',
  basvurulacak: 'ok',
  basvurulmayacak: 'muted',
  teklif_verildi: 'violet',
  kazanildi: 'ok',
  kaybedildi: 'err',
  iptal: 'muted',
};

export const MATCH_TONE: Record<MatchState, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  eslesti: 'ok',
  oneri: 'violet',
  belirsiz: 'warn',
  yok: 'err',
  bekliyor: 'muted',
};

/** Kalan güne göre renk: geçti / 2 gün / 7 gün / rahat. */
export function leftTone(n: number | null | undefined): 'ok' | 'warn' | 'err' | 'muted' {
  if (n === null || n === undefined) return 'muted';
  if (n < 0 || n <= 2) return 'err';
  if (n <= 7) return 'warn';
  return 'ok';
}
