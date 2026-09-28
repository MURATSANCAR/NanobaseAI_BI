import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../../engine';
import { httpErrorText } from '../../httpError';
import type { Meta, Plan, PlanStatus } from '../api';
import type { Kaynaklar } from '../../components/sqlInfo';

/** M18 Aylık pazarlama planı ve satış föyü: /api/v1/marketing/months/*, /api/v1/marketing/foy*. */

export type MonthlyMeta = Meta & {
  monthly?: {
    draftDay: number;
    foyRemindDay: number;
    varsayilanDonem: string;
    types: Record<string, string>;
    itemSources: Record<string, string>;
    segments: Record<string, string>;
    foyStatuses: Record<FoyStatus, string>;
    foyFields: Record<string, string>;
    foyRecipients: number;
  };
  me: Meta['me'] & {
    canMonth?: boolean;
    canFoy?: boolean;
    canFoyWrite?: boolean;
    canFoyApprove?: boolean;
    canFoySend?: boolean;
    canNewBooks?: boolean;
  };
};

export type Conflict = { kural: string; neden: string; deger?: string | null; hafta?: string; ile: string[]; ileAd: string[] };

export type MonthItem = {
  id: string;
  tur: 'yeni' | 'backlist' | 'ozel-gun' | 'b2b-kampanya' | 'set' | 'diger';
  turAdi: string;
  kaynak: string;
  kaynakAdi: string;
  kaynakRef: string | null;
  stokKodu: string | null;
  baslik: string;
  yayinevi: string | null;
  kitaplik: string | null;
  hedefKitle: string | null;
  hafta: string | null;
  baslangic: string | null;
  bitis: string | null;
  kanal: string | null;
  kanalAdi: string | null;
  butce: number | null;
  aciklama: string | null;
  elle: boolean;
  detay: {
    yazar?: string | null;
    yayinKaynagi?: string | null;
    sorumlu?: string | null;
    plan?: { id: string; durum: PlanStatus; durumAdi: string } | null;
    hedefAy?: { ciro: number | null; adet: number | null; segment: string } | null;
    crmBolgeHedefi?: { adet: number; bolge: number } | null;
    sapma?: { oran: number | null; eksik: number | null } | null;
    kitapSayisi?: number | null;
    yontem?: string | null;
    kesinlik?: string | null;
    mecra?: string | null;
    tip?: string | null;
    ekIskonto?: number | null;
    planlananCiro?: number | null;
    gerceklesenCiro?: number | null;
    urunSayisi?: number | null;
    kaynaktaYok?: boolean;
  };
  cakisma: Conflict[];
};

export type BudgetRow = {
  segment: 'yeni' | 'backlist';
  segmentAdi: string;
  kanal: string;
  kanalAdi: string;
  oneri: number | null;
  onayli: number | null;
  tutar: number | null;
  hedefPayi: number | null;
  oncekiAyOran: number | null;
  gerekce: string | null;
};

export type TaskStats = { toplam: number; bekliyor: number; yapildi: number; atlandi: number; oran: number | null };

export type MonthView = {
  donem: string;
  donemAdi: string;
  onceki: string;
  sonraki: string;
  varsayilanDonem: string;
  plan: (Plan & { ustOnayGerekli?: boolean; zeki: (Plan['zeki'] & { butceGerekce?: string | null; ozet?: string | null; notlar?: string[] }) | null }) | null;
  items: MonthItem[];
  weeks: Array<{ hafta: string; baslangic: string; bitis: string }>;
  budget: BudgetRow[];
  hedef: {
    year: number;
    planId: string | null;
    planTitle?: string;
    not?: string;
    toplamCiro: number | null;
    paylar: Record<string, number | null>;
    segment: Record<string, { ciro: number | null; adet: number; kitap: number }>;
  };
  oncekiAy: {
    donem: string;
    donemAdi: string;
    hedef: number | null;
    gercek: number | null;
    oran: number | null;
    segment: Record<string, { hedef: number | null; gercek: number | null; oran: number | null; kitap: number }>;
    sirketCiro: number | null;
    veriSonu: string | null;
    not: string | null;
    kaynak?: string | null;
    isler: TaskStats;
    plan: { id: string; durumAdi: string } | null;
  };
  cakismaSayisi: number;
  sayilar: Record<string, number>;
  foy: { toplam: number; onayli: number; eksik: number; uyumsuz: number; eski: number };
  uyari?: string | null;
  kaynaklar?: Kaynaklar;
};

export type FoyStatus = 'taslak' | 'onayda' | 'onayli';
export type FoyField = { key: string; ad: string; deger: unknown; kaynak: string | null; kim?: string };
export type Mismatch = { tur: string; ad: string; not?: string | null; bilgi?: boolean; [k: string]: unknown };

export type Foy = {
  id: string;
  stokKodu: string;
  donem: string;
  surum: number;
  durum: FoyStatus;
  durumAdi: string;
  eski: boolean;
  ayDisi: boolean;
  alanlar: FoyField[];
  eksikler: string[];
  uyumsuzluk: Mismatch[];
  engelleyen: number;
  gonderen: string | null;
  onaylayan: string | null;
  onayZamani: string | null;
  onayNotu: string | null;
  gerekce: string | null;
  guncelleyen: string | null;
  guncelleme: string | null;
  zorunlu: string[];
  kitap?: { yazar?: string | null; yayinevi?: string | null; kitaplik?: string | null; yayinTarihi?: string | null; sorumlu?: string | null; yayinKaynagi?: string | null };
  crmTodo?: Array<{ alan: string; ad: string; deger: string; kaynak: string }>;
  logo?: Mismatch | null;
  kaynaklar?: Kaynaklar;
};

export type FoyPage = {
  donem: string;
  donemAdi: string;
  items: Foy[];
  kpi: { toplam: number; onayli: number; onayda: number; eksik: number; uyumsuz: number; eski: number; hazir: number };
  notlar: string[];
  logoNotu: string | null;
  gonderimler: Array<{ id: string; alicilar: string; gonderen: string; zaman: string | null; adet: number; sonuc: string }>;
  zorunlu: string[];
  logoKaynak: string;
  kaynaklar?: Kaynaklar;
};

const B = '/api/v1/marketing';

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
  const j = res.ok ? null : ((await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null);
  const msg = j ? (typeof j.detail === 'string' ? j.detail : j.detail?.message) : undefined;
  if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  if (!res.ok) throw new Error(msg || httpErrorText(res.status));
  return (await res.json()) as T;
}

const enc = encodeURIComponent;
const q = (o: Record<string, string | boolean | undefined>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};

/** Hedef açığı ↔ ay planı boşluğu (öneri 17): liste kural (M46 açık kitap sapması − bu ay işi olan kitaplar). */
export type TargetGap = { stokKodu: string; ad: string; oran: number | null; eksik: number | null };
export type TargetGaps = {
  donem: string; donemAdi: string; items: TargetGap[]; hedefAlti: number; planli: number; plansiz: number; kaynak: string;
  kuralParagrafi: string; paragraf: string; paragrafKaynak: 'zeki' | 'kural'; paragrafDusen: number | null;
  paragrafZaman: string | null; eskiParagraf: boolean; modelVar: boolean; kaynaklar?: Kaynaklar;
};

export const monthApi = {
  meta: () => send<MonthlyMeta>('GET', '/meta'),
  targetGaps: (ay: string) => send<TargetGaps>('GET', `/months/${enc(ay)}/target-gaps`, undefined, 180_000),
  targetGapsExplain: (ay: string) => send<TargetGaps>('POST', `/months/${enc(ay)}/target-gaps/explain`, {}, 300_000),
  month: (ay: string) => send<MonthView>('GET', `/months/${enc(ay)}`, undefined, 180_000),
  build: (ay: string) => send<MonthView>('POST', `/months/${enc(ay)}/build`, {}, 300_000),
  suggest: (ay: string) => send<MonthView>('POST', `/months/${enc(ay)}/suggest`, {}, 300_000),
  budget: (ay: string, body: { items?: Array<{ segment: string; kanal: string; onayli: number | null }>; cerceve?: number | null; not?: string }) =>
    send<MonthView>('PUT', `/months/${enc(ay)}/budget`, body),
  patchItem: (ay: string, id: string, body: Partial<Pick<MonthItem, 'baslangic' | 'bitis' | 'kanal' | 'butce' | 'aciklama' | 'baslik'>>) =>
    send<{ item: MonthItem }>('PATCH', `/months/${enc(ay)}/items/${enc(id)}`, body),
  addItem: (ay: string, body: { tur: string; baslik: string; baslangic: string; bitis?: string | null; kanal?: string | null; aciklama?: string | null }) =>
    send<{ item: MonthItem }>('POST', `/months/${enc(ay)}/items`, body),
  removeItem: (ay: string, id: string) => send<{ ok: boolean }>('DELETE', `/months/${enc(ay)}/items/${enc(id)}`),
  flow: (ay: string, kind: 'submit' | 'withdraw' | 'approve' | 'upper-approve' | 'reject' | 'revise', text?: string) =>
    send<{ planId: string; durum: PlanStatus; durumAdi: string }>('POST', `/months/${enc(ay)}/${kind}`, kind === 'revise' ? { reason: text } : { note: text || undefined }),
  summaryUrl: (ay: string) => `${ENGINE_BASE}${B}/months/${enc(ay)}/summary.pdf`,

  foyList: (donem: string, durum = '', yenile = false) => send<FoyPage>('GET', `/foy${q({ donem, durum, yenile })}`, undefined, 300_000),
  foy: (stok: string, donem?: string, yenile = false) => send<Foy>('GET', `/foy/${enc(stok)}${q({ donem, yenile })}`, undefined, 180_000),
  foySave: (stok: string, donem: string, alanlar: Record<string, unknown>) => send<Foy>('PUT', `/foy/${enc(stok)}${q({ donem })}`, { alanlar }),
  foyRefresh: (stok: string, donem: string) => send<Foy>('POST', `/foy/${enc(stok)}/refresh${q({ donem })}`, {}, 180_000),
  foySubmit: (stok: string, donem: string) => send<Foy>('POST', `/foy/${enc(stok)}/submit${q({ donem })}`, {}),
  foyApprove: (stok: string, donem: string, body: { not?: string; kabul?: boolean }) => send<Foy>('POST', `/foy/${enc(stok)}/approve${q({ donem })}`, body),
  foyReject: (stok: string, donem: string, not: string) => send<Foy>('POST', `/foy/${enc(stok)}/reject${q({ donem })}`, { not }),
  foyArgs: (stok: string, donem: string) => send<Foy>('POST', `/foy/${enc(stok)}/draft-args${q({ donem })}`, {}, 300_000),
  foySend: (donem: string) => send<{ sonuc: string; alici: number; adet: number }>('POST', `/foy/paket/${enc(donem)}/send`, {}, 300_000),
  foyPdfUrl: (stok: string, donem: string) => `${ENGINE_BASE}${B}/foy/${enc(stok)}.pdf${q({ donem })}`,
  packPdfUrl: (donem: string) => `${ENGINE_BASE}${B}/foy/paket/${enc(donem)}.pdf`,
  packZipUrl: (donem: string) => `${ENGINE_BASE}${B}/foy/paket/${enc(donem)}.zip`,
};

/** «2026-11» → «2026-10» / «2026-12». */
export function shiftMonth(ay: string, n: number): string {
  const i = Number(ay.slice(0, 4)) * 12 + Number(ay.slice(5, 7)) - 1 + n;
  return `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}`;
}

export const AY = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];
export const monthLabel = (ay: string) => `${AY[Number(ay.slice(5, 7)) - 1]} ${ay.slice(0, 4)}`;
export const isMonth = (s: string | undefined | null): s is string => !!s && /^\d{4}-(0[1-9]|1[0-2])$/.test(s);

export const TYPE_TONE: Record<MonthItem['tur'], string> = {
  yeni: 'bg-canvas-violet/10 text-canvas-violet',
  backlist: 'bg-sky-50 text-sky-800',
  'ozel-gun': 'bg-amber-50 text-amber-800',
  'b2b-kampanya': 'bg-emerald-50 text-emerald-800',
  set: 'bg-slate-100 text-canvas-ink',
  diger: 'bg-slate-100 text-canvas-ink',
};

export const FOY_TONE: Record<FoyStatus, 'ok' | 'warn' | 'muted'> = { taslak: 'muted', onayda: 'warn', onayli: 'ok' };

export const fieldText = (v: unknown): string => {
  if (v === null || v === undefined || v === '') return '';
  if (Array.isArray(v)) return v.join('\n');
  return String(v);
};

export const FIELD_SOURCE = (k: string | null | undefined): string => {
  if (!k) return 'boş';
  if (k === 'elle') return 'elle';
  if (k === 'zeki') return 'Zeki AI';
  if (k === 'logo') return 'Logo';
  if (k.startsWith('crm:')) return 'CRM';
  return k;
};
