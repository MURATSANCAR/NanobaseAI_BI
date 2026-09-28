import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** Uç cevabındaki sorgu bilgisi (`<SqlInfo k={…kaynaklar} alan="…" />`). */
export type WithK = { kaynaklar?: Kaynaklar };

/** M47 Risk ve uyum ekranlarının köprü uçları: /api/v1/risk/*. */

export type Level = 'dusuk' | 'orta' | 'yuksek' | 'kritik';
export type RiskState = 'oneri' | 'acik' | 'izleniyor' | 'kabul' | 'kapandi' | 'reddedildi';
export type ValueState = 'yesil' | 'sari' | 'kirmizi' | 'esik_yok' | 'olculemedi';
export type Tone = 'ok' | 'warn' | 'err' | 'muted' | 'violet';

export type Me = {
  username: string; display: string; canWrite: boolean; seeAll: boolean; canIndicator: boolean; canIndicatorApprove: boolean;
  canReportApprove: boolean; canCompliance: boolean; canKvkk: boolean; canPolicy: boolean; canExport: boolean;
};

export type RiskMeta = {
  kategoriler: Record<string, string>; durumlar: Record<RiskState, string>; egilimler: Record<string, string>;
  kaynaklar: Record<string, string>; aksiyonDurumlari: Record<string, string>; gostergeDurumlari: Record<string, string>;
  degerDurumlari: Record<ValueState, string>; birimler: Record<string, string>; yonler: Record<string, string>;
  sikliklar: Record<string, string>; alanlar: Record<string, string>; uyumSikliklari: Record<string, string>;
  donemDurumlari: Record<string, string>; bcpDurumlari: Record<string, string>; raporDurumlari: Record<string, string>;
  seviyeler: Record<Level, string>;
  ayarlar: { scoreBands: number[]; reviewDays: number; actionWarnDays: number; complianceWarnDays: number[]; policyWarnDays: number; fileMaxMb: number };
  me: Me;
  modelVar: boolean;
};

export type Risk = {
  id: string; baslik: string; tanim: string | null; neden: string | null; sonuc: string | null; kategori: string; kategoriAdi: string;
  altKategori: string | null; sahip: string | null; sahipEposta: string | null; olasilik: number | null; etki: number | null;
  puan: number | null; seviye: Level | null; egilim: string | null; durum: RiskState; durumAdi: string; kaynak: string;
  kaynakAdi: string; kaynakRef: string | null; gozdenGecirmeGun: number | null; sonGozdenGecirme: string | null;
  sonrakiGozdenGecirme: string | null; gozdenGecirmeKalan: number | null; olusturan: string; olusturma: string | null;
  guncelleyen: string | null; guncelleme: string | null; surum: number; gostergeler: string[];
  acikAksiyon?: number; gecikenAksiyon?: number;
};

export type Action = {
  id: string; riskId: string; eylem: string; sahip: string | null; sahipEposta: string | null; termin: string | null;
  kalanGun: number | null; durum: 'acik' | 'devam' | 'tamamlandi' | 'iptal'; durumAdi: string; gecikti: boolean;
  kanitAd: string | null; kanitVar: boolean; not: string | null; olusturan: string; olusturma: string | null;
  tamamlayan: string | null; tamamlanma: string | null; riskBaslik?: string | null;
};

export type Review = {
  id: string; tarih: string | null; eskiOlasilik: number | null; eskiEtki: number | null; yeniOlasilik: number | null;
  yeniEtki: number | null; eskiPuan: number | null; yeniPuan: number | null; egilim: string | null; not: string | null;
  tetik: Array<{ kod: string; ad: string; deger: number | null; durum: string | null }>; gozdenGeciren: string;
};

export type RiskDetail = Risk & { aksiyonlar: Action[]; gozdenGecirmeler: Review[]; yazabilir: boolean };

export type Measure = {
  olcum: string | null; deger: number | null; durum: ValueState; durumAdi: string; veriSonGunu: string | null;
  kanit: Record<string, unknown>; esik: { surum?: number; sari?: number | null; kirmizi?: number | null; yon?: string };
  hata: string | null; olcen: string | null;
};

export type IndicatorDef = {
  id: string; kod: string; surum: number; ad: string; aciklama: string | null; kaynakTuru: 'sql' | 'modul'; kaynakRef: string | null;
  birim: string; birimAdi: string; yon: string; yonAdi: string; esikSari: number | null; esikKirmizi: number | null;
  sahip: string | null; sahipEposta: string | null; siklik: string; siklikAdi: string; durum: string; durumAdi: string;
  not: string | null; olusturan: string; olusturma: string | null; onaylayan: string | null; onayZamani: string | null;
};

export type Indicator = IndicatorDef & {
  son: Measure | null; gecmis: Measure[]; taslak: IndicatorDef | null; kirmiziBaslangic: string | null; riskler: string[];
  ekran: string | null; kategori: string | null; yeni?: boolean;
};

export type HeatCell = { olasilik: number; etki: number; puan: number; seviye: Level; sayi: number; riskler: Array<{ id: string; baslik: string }> };

export type QueueItem = {
  risk: Pick<Risk, 'id' | 'baslik' | 'kategori' | 'kategoriAdi' | 'sahip' | 'olasilik' | 'etki' | 'puan' | 'seviye' | 'sonGozdenGecirme'>;
  nedenler: Array<{ tur: 'gosterge' | 'tarih' | 'sahipsiz' | 'puansiz'; kod?: string; ad?: string; deger?: number | null; birim?: string; since?: string; gun?: number }>;
};

export type CompEvent = {
  id: string; itemId: string; donem: string; sonGun: string; kalanGun: number | null; durum: 'bekliyor' | 'kanit' | 'kapandi';
  durumAdi: string; gecikti: boolean; kanitAd: string | null; kanitVar: boolean; yukleyen: string | null; yukleme: string | null;
  kapatan: string | null; kapanis: string | null; not: string | null; alan?: string; alanAdi?: string; madde?: string;
  dayanak?: string | null; sorumlu?: string | null;
};

export type CompItem = {
  id: string; alan: string; alanAdi: string; madde: string; dayanak: string | null; siklik: string; siklikAdi: string;
  ilkSonGun: string; sorumlu: string | null; sorumluEposta: string | null; aktif: boolean; not: string | null;
  olusturan: string; olusturma: string | null; siradaki: CompEvent | null; kapanan: number; geciken: number;
};

export type Summary = {
  isiHaritasi: HeatCell[][]; puansiz: number; bantlar: number[]; seviyeler: Record<Level, string>; kuyruk: QueueItem[];
  gecikenAksiyon: Action[]; yaklasanAksiyon: Action[];
  kirmiziGosterge: Array<{ kod: string; ad: string; deger: number | null; birim: string; riskler: string[]; since: string | null }>;
  uyumBuAy: CompEvent[]; ilk10: Risk[]; oneriSayisi: number;
  sayilar: { canli: number; kritik: number; gosterge: number; kirmizi: number; esiksiz: number }; tumunuGorur: boolean;
};

export type Policy = {
  id: string; tur: string; sigortaci: string | null; policeNo: string | null; teminat: Array<{ ad: string; tutar: number | null }>;
  prim: number | null; bas: string | null; bit: string | null; kalanGun: number | null; yaklasti: boolean; bitti: boolean;
  sorumlu: string | null; sorumluEposta: string | null; belgeAd: string | null; belgeVar: boolean; not: string | null;
  olusturan: string; guncelleyen: string | null; guncelleme: string | null;
};

export type Bcp = {
  id: string; surec: string; kritiklik: number | null; kabulKesintiSaat: number | null; veriKaybiSaat: number | null;
  sorumlu: string | null; sorumluEposta: string | null; sonTatbikat: string | null; sonrakiTatbikat: string | null;
  tatbikatKalan: number | null; tatbikatGecikti: boolean; belgeSurum: string | null; durum: string; durumAdi: string; not: string | null;
};

export type Report = {
  id: string; donem: string; durum: 'hazirlaniyor' | 'taslak' | 'onayli' | 'hata'; durumAdi: string; kaynak: 'zeki' | 'kural' | null;
  kaynakNotu: string | null; girdiHash: string | null; olusturan: string; olusturma: string | null; duzenleyen: string | null;
  guncelleme: string | null; onaylayan: string | null; onayZamani: string | null; metin?: string | null; girdi?: Record<string, unknown>;
};

export type Job = { id: string; tur: string; durum: 'calisiyor' | 'bitti' | 'hata'; sonuc: Record<string, unknown>; hata: string | null; raporId?: string };

export type RiskInput = Partial<{
  baslik: string; tanim: string; neden: string; sonuc: string; kategori: string; altKategori: string; sahip: string;
  sahipEposta: string; olasilik: number | null; etki: number | null; egilim: string; durum: RiskState; gostergeler: string[];
  gozdenGecirmeGun: number; sonrakiGozdenGecirme: string;
}>;

const B = '/api/v1/risk';

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

async function upload<T>(path: string, file: File, params: Record<string, string> = {}): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${B}${path}${qs({ ...params, filename: file.name })}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
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

export const riskApi = {
  meta: () => send<RiskMeta>('GET', '/meta'),
  summary: () => send<Summary & WithK>('GET', '/summary', undefined, 300_000),
  risks: (p: { durum?: string; kategori?: string; q?: string; sahip?: string; hucre?: string }) =>
    send<{ items: Risk[]; total: number } & WithK>('GET', `/risks${qs(p)}`),
  risk: (id: string) => send<RiskDetail & WithK>('GET', `/risks/${enc(id)}`),
  create: (b: RiskInput) => send<Risk>('POST', '/risks', b),
  update: (id: string, b: RiskInput) => send<Risk>('PATCH', `/risks/${enc(id)}`, b),
  review: (id: string, b: { olasilik: number; etki: number; egilim?: string; not?: string; sonrakiGozdenGecirme?: string }) =>
    send<Risk>('POST', `/risks/${enc(id)}/review`, b),
  accept: (id: string, b: RiskInput) => send<Risk>('POST', `/risks/${enc(id)}/accept`, b),
  reject: (id: string, not: string) => send<Risk>('POST', `/risks/${enc(id)}/reject`, { not }),
  classify: (b: { baslik?: string; tanim?: string }) =>
    send<{ kategori: string; kategoriAdi: string; olasilik: number | null; marj: number | null; emin: boolean }>('POST', '/risks/classify', b, 120_000),
  suggest: () => send<Job>('POST', '/risks/suggest', {}),
  addAction: (id: string, b: { eylem: string; sahip?: string; sahipEposta?: string; termin?: string; not?: string }) =>
    send<Action>('POST', `/risks/${enc(id)}/actions`, b),
  updateAction: (aid: string, b: Partial<{ durum: string; not: string; eylem: string; sahip: string; termin: string }>) =>
    send<Action>('PATCH', `/actions/${enc(aid)}`, b),
  actionEvidence: (aid: string, file: File) => upload<Action>(`/actions/${enc(aid)}/evidence`, file),
  actionEvidenceUrl: (aid: string) => `${ENGINE_BASE}${B}/actions/${enc(aid)}/evidence`,
  indicators: () => send<{ items: Indicator[] } & WithK>('GET', '/indicators', undefined, 300_000),
  proposeIndicator: (b: Partial<{ kod: string; ad: string; aciklama: string; birim: string; yon: string; esikSari: number | null; esikKirmizi: number | null; sahip: string; sahipEposta: string; siklik: string; not: string }>) =>
    send<IndicatorDef>('POST', '/indicators', b),
  approveIndicator: (kod: string, not?: string) => send<IndicatorDef>('POST', `/indicators/${enc(kod)}/approve`, { not }),
  rejectIndicator: (kod: string, not: string) => send<IndicatorDef>('POST', `/indicators/${enc(kod)}/reject`, { not }),
  measure: (kod: string) => send<Measure & { kod: string; ad: string; bildirim?: string } & WithK>('POST', `/indicators/${enc(kod)}/measure`, undefined, 900_000),
  values: (kod: string) => send<{ kod: string; items: Measure[]; surumler: IndicatorDef[] } & WithK>('GET', `/indicators/${enc(kod)}/values`),
  compItems: () => send<{ items: CompItem[]; alanlar: Record<string, string>; sikliklar: Record<string, string> } & WithK>('GET', '/compliance/items'),
  saveItem: (id: string | null, b: Partial<{ alan: string; madde: string; dayanak: string; siklik: string; ilkSonGun: string; sorumlu: string; sorumluEposta: string; aktif: boolean; not: string }>) =>
    id ? send<CompItem>('PATCH', `/compliance/items/${enc(id)}`, b) : send<CompItem>('POST', '/compliance/items', b),
  calendar: (ay: string) => send<{ ay: string; items: CompEvent[]; bugun: string } & WithK>('GET', `/compliance/calendar${qs({ ay })}`),
  eventEvidence: (eid: string, file: File) => upload<CompEvent>(`/compliance/events/${enc(eid)}/evidence`, file),
  eventEvidenceUrl: (eid: string) => `${ENGINE_BASE}${B}/compliance/events/${enc(eid)}/evidence`,
  closeEvent: (eid: string, not: string) => send<CompEvent>('POST', `/compliance/events/${enc(eid)}/close`, { not }),
  policies: () => send<{ items: Policy[]; uyariGun: number } & WithK>('GET', '/policies'),
  savePolicy: (id: string | null, b: Record<string, unknown>) => (id ? send<Policy>('PATCH', `/policies/${enc(id)}`, b) : send<Policy>('POST', '/policies', b)),
  deletePolicy: (id: string) => send<{ ok: boolean }>('DELETE', `/policies/${enc(id)}`),
  policyDocument: (id: string, file: File) => upload<Policy>(`/policies/${enc(id)}/document`, file),
  policyDocumentUrl: (id: string) => `${ENGINE_BASE}${B}/policies/${enc(id)}/document`,
  bcp: () => send<{ items: Bcp[]; durumlar: Record<string, string> } & WithK>('GET', '/bcp'),
  saveBcp: (id: string | null, b: Record<string, unknown>) => (id ? send<Bcp>('PATCH', `/bcp/${enc(id)}`, b) : send<Bcp>('POST', '/bcp', b)),
  deleteBcp: (id: string) => send<{ ok: boolean }>('DELETE', `/bcp/${enc(id)}`),
  kvkk: () => send<{ available: boolean; message?: string } & Record<string, unknown>>('GET', '/kvkk'),
  reports: () => send<{ items: Report[] } & WithK>('GET', '/reports'),
  report: (id: string) => send<Report & WithK>('GET', `/reports/${enc(id)}`),
  draftReport: (donem?: string) => send<Job>('POST', '/reports/draft', donem ? { donem } : {}),
  editReport: (id: string, metin: string) => send<Report>('PATCH', `/reports/${enc(id)}`, { metin }),
  approveReport: (id: string) => send<Report>('POST', `/reports/${enc(id)}/approve`),
  reportDocxUrl: (id: string) => `${ENGINE_BASE}${B}/reports/${enc(id)}/document.docx`,
  job: (id: string) => send<Job>('GET', `/jobs/${enc(id)}`),
};

/* ------------------------------------------------------------------ biçim */

const num2 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 });
const money0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: 'short', year: 'numeric' });
const dtFmt = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });

/** Gösterge değeri birimiyle: gün, %, adet, ₺. */
export function fmtValue(v: number | null | undefined, birim: string): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  if (birim === 'yuzde') return `%${num2.format(v)}`;
  if (birim === 'tl') return `${money0.format(v)} ₺`;
  if (birim === 'gun') return `${num2.format(v)} gün`;
  return num2.format(v);
}

export const fmtNum = (v: number | null | undefined) => (v === null || v === undefined ? '—' : num2.format(v));
export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${money0.format(v)} ₺`);

export function fmtDay(v: string | null | undefined): string {
  if (!v) return '—';
  const d = new Date(v.length <= 10 ? `${v}T00:00:00` : v);
  return Number.isNaN(d.getTime()) ? v : dayFmt.format(d);
}

export function fmtTime(v: string | null | undefined): string {
  if (!v) return '—';
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : dtFmt.format(d);
}

export function fmtLeft(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  if (n === 0) return 'bugün';
  return n > 0 ? `${n} gün kaldı` : `${-n} gün geçti`;
}

export function leftTone(n: number | null | undefined, warn = 7): Tone {
  if (n === null || n === undefined) return 'muted';
  if (n < 0) return 'err';
  if (n <= warn) return 'warn';
  return 'ok';
}

/** «1.234,5» ya da «1234.5» → sayı; boşsa null. */
export function parseNum(s: string): number | null {
  const t = s.trim().replace(/\s/g, '').replace(/₺|%/g, '');
  if (!t) return null;
  const norm = t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : (t.match(/\./g) ?? []).length > 1 ? t.replace(/\./g, '') : t;
  const n = Number(norm);
  return Number.isFinite(n) ? n : null;
}

export const VALUE_TONE: Record<ValueState, Tone> = { yesil: 'ok', sari: 'warn', kirmizi: 'err', esik_yok: 'muted', olculemedi: 'muted' };

/** Isı haritası bantları: renk yanında hücrede puan yazılıdır (renk körlüğü). */
export const LEVEL_STYLE: Record<Level, { cell: string; pill: string }> = {
  dusuk: { cell: 'bg-emerald-100 text-emerald-900', pill: 'bg-emerald-50 text-emerald-700' },
  orta: { cell: 'bg-amber-100 text-amber-900', pill: 'bg-amber-50 text-amber-800' },
  yuksek: { cell: 'bg-orange-200 text-orange-950', pill: 'bg-orange-50 text-orange-800' },
  kritik: { cell: 'bg-red-200 text-red-950', pill: 'bg-red-50 text-red-700' },
};

/** Bu çeyrek: «2026-Ç3». */
export function currentQuarter(d = new Date()): string {
  return `${d.getFullYear()}-Ç${Math.floor(d.getMonth() / 3) + 1}`;
}

export function monthShift(ay: string, n: number): string {
  const [y, m] = ay.split('-').map(Number);
  const d = new Date(y, m - 1 + n, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export function monthLabel(ay: string): string {
  const [y, m] = ay.split('-').map(Number);
  return new Intl.DateTimeFormat('tr-TR', { month: 'long', year: 'numeric' }).format(new Date(y, m - 1, 1));
}

/** Arka plan işini bitene kadar yoklar (en çok ~10 dk). */
export async function waitJob(id: string, onTick?: (j: Job) => void): Promise<Job> {
  for (let i = 0; i < 300; i += 1) {
    const j = await riskApi.job(id);
    onTick?.(j);
    if (j.durum !== 'calisiyor') return j;
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error('İş uzun sürdü; birazdan listeyi yenileyin.');
}
