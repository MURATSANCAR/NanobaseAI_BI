import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';

/** Pazarlama çekirdeğinin köprü uçları: /api/v1/marketing/* (M15 yeni kitap planı). */

export type PlanStatus = 'taslak' | 'onayda' | 'onayli' | 'geri' | 'arsiv';
export type MaterialStatus = 'taslak' | 'editoryal-onayli' | 'onayli';
export type TaskStatus = 'bekliyor' | 'yapildi' | 'atlandi';

export type Meta = {
  channels: Record<string, string>;
  statuses: Record<PlanStatus, string>;
  materials: Record<string, string>;
  materialStatuses: Record<MaterialStatus, string>;
  taskStatuses: Record<TaskStatus, string>;
  dateSources: Record<string, string>;
  settings: {
    horizonDays: number;
    noPlanDays: number;
    materialDays: number;
    remindDays: number[];
    requiredMaterials: string[];
    threshold: number | null;
    thresholdSet: boolean;
    dateOrder: string[];
  };
  lastRun: { tarih?: string; eposta?: string; hata?: string; _at?: string | null } | null;
  modelReady: boolean;
  me: {
    username: string;
    display: string;
    canWrite: boolean;
    canSeeBudget: boolean;
    canApprove: boolean;
    canUpperApprove: boolean;
    canEditorial: boolean;
    canExport: boolean;
  };
};

export type Target = { year?: number | null; planId?: string | null; version?: number; adet?: number | null; ciro?: number | null; marj?: number | null; not?: string };

export type BookRow = {
  stokKodu: string;
  ad: string | null;
  yazar: string | null;
  yayinevi: string | null;
  kitaplik: string | null;
  hedefKitle: string | null;
  kapak: string | null;
  yayinTarihi: string;
  yayinKaynagi: string;
  tarihler: Record<string, string | null>;
  kalanGun: number | null;
  sorumlu: string | null;
  sorumluHesap: string | null;
  hedef: { adet: number | null; ciro: number | null; marj: number | null } | null;
  plan: null | {
    id: string;
    durum: PlanStatus;
    durumAdi: string;
    butce: number | null;
    sahip: string | null;
    gonderen: string | null;
    surum: number;
    eksikMateryal: string[];
    hedefDegisti: boolean;
    ustOnayGerekli: boolean;
  };
};

export type BookPage = {
  items: BookRow[];
  total: number;
  page: number;
  pageSize: number;
  kpi: { plansiz: number; onayda: number; materyalEksik: number; hedefDegisti: number };
  window: { from: string; to: string };
  yayinevleri: string[];
  hepsi: number;
};

export type Line = {
  id?: string;
  kanal: string;
  kanalAdi?: string;
  altKanal: string | null;
  aciklama: string | null;
  tutar: number | null;
  baslangic: string | null;
  bitis: string | null;
  kaynak?: 'zeki' | 'kullanici' | 'crm';
  gerekce?: string | null;
  elleDuzeltildi?: boolean;
};

export type Task = {
  id?: string;
  tarih: string | null;
  gunFarki: number | null;
  is: string;
  kanal: string | null;
  sorumlu: string | null;
  durum: TaskStatus;
  kanitUrl: string | null;
  materyalTur?: string | null;
  kaynak?: string | null;
};

export type Material = {
  id: string;
  tur: string;
  turAdi: string;
  crmAlani: string | null;
  metin: string;
  kaynak: string;
  durum: MaterialStatus;
  durumAdi: string;
  editoryalOnaylayan: string | null;
  editoryalOnayZamani: string | null;
  onaylayan: string | null;
  onayZamani: string | null;
  surum: number;
  dogrulama: { dusen?: Array<{ cumle: string; neden: string }>; dusenSayisi?: number } | null;
  guncelleme: string | null;
};

export type Plan = {
  id: string;
  kind: string;
  stokKodu: string | null;
  crmProjeId: string | null;
  baslik: string;
  durum: PlanStatus;
  durumAdi: string;
  surum: number;
  oncekiId: string | null;
  sahip: string | null;
  yayinTarihi: string | null;
  yayinTarihiKaynagi: string | null;
  yayinTarihiKaynakAdi: string | null;
  hedef: Target | null;
  butceCerceve: number | null;
  butceCerceveKaynak: { kaynak?: string | null; gerekce?: string; oran?: { oran: number; yil?: number; gider?: number; ciro?: number; kaynak?: string } } | null;
  butceToplam: number | null;
  zeki: {
    kanalGerekce?: string | null;
    konumlama?: string | null;
    emsal?: Array<{ stokKodu: string; ad: string | null; karar: 'emsal' | 'degil' | 'belirsiz'; olasilik: number | null }>;
    dusen?: number;
    zaman?: string;
  } | null;
  olusturan: string;
  olusturma: string | null;
  guncelleyen?: string | null;
  guncelleme?: string | null;
  gonderen: string | null;
  gonderme: string | null;
  onaylayan: string | null;
  onayZamani: string | null;
  ustOnaylayan: string | null;
  ustOnayZamani: string | null;
  gerekce: string | null;
  lines: Line[];
  tasks: Task[];
  materials: Material[];
  ustOnayGerekli?: boolean;
  eksikMateryal?: string[];
};

export type Emsal = {
  stokKodu: string;
  ad: string | null;
  yazar: string | null;
  yayinevi: string | null;
  lansman: string | null;
  ilk3: number | null;
  ilk6: number | null;
  ilk12: number | null;
  ilk6NetTutar: number | null;
  kaynak: string[];
  benzerlik: number | null;
  nedenler: string[];
};

export type Card = {
  kitap: {
    stokKodu: string;
    ad: string | null;
    yazar: string | null;
    yayinevi: string | null;
    kitaplik: string | null;
    hedefKitle: string | null;
    turler?: string | null;
    fiyat?: number | null;
    sayfa?: number | null;
    projeAdi: string | null;
    sorumlu: string | null;
  };
  yayin: { tarih: string | null; kaynak: string | null; kaynakAdi: string | null; tarihler: Record<string, string | null> };
  hedef: Target;
  emsal: {
    hazir: boolean;
    not?: string;
    items: Emsal[];
    crmEmsalSayisi?: number;
    veriSonuAy?: string;
    kaynak?: string;
    tahmin: null | { ay: string; guven: string | null; baz6: number | null; bant6: { low: number; high: number } | null; baz12: number | null; ilkBaski: number | null };
    gerceklesen: null | { lansman: string; aylar: number[] };
  };
  yazar: {
    yazar: string | null;
    items: Array<{ stokKodu: string; ad: string | null; ilkYayin: string | null; lansman: string | null; ilk12: number | null; yillik: Record<string, { adet: number; ciro: number } | null> }>;
    yillar: Array<{ yil: number; adet: number; ciro: number }>;
    kaynak?: string;
    sql?: string | null;
    not?: string;
  };
  rakipler: Array<{ ad: string | null; yayinevi: string | null; yazarlar: string | null; satisAdedi: number | null; listeFiyati: number | null; tanitim: string | null }>;
  ozelGunler: Array<{ ad: string | null; baslangic: string | null; bitis: string | null; yontem: string | null; kesinlik: string | null }>;
  crmButce: null | Record<string, number | string | null>;
  metinler: Array<{ alan: string; ad: string; metin: string }>;
  veriSonu: { logo: string | null; emsalAy: string | null };
  uyarilar: string[];
  asof?: string | null;
};

export type Job = { id: string; tur: string; durum: 'bekliyor' | 'calisiyor' | 'bitti' | 'hata'; adim: string | null; hata: string | null; sonuc: Record<string, unknown> | null; olusturma: string | null };
export type Event = { id: string; zaman: string | null; kim: string; ne: string; eski: unknown; yeni: unknown };
export type TodoItem = {
  tur: 'kitap-alani' | 'butce-satiri' | 'proje-alani';
  hedef: string;
  alan?: string;
  tip?: string;
  altTip?: string | null;
  deger?: string | number | null;
  crmDeger?: string | number | null;
  tutar?: number | null;
  baslangic?: string | null;
  bitis?: string | null;
  kitap?: string | null;
  planOnayli: boolean;
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
    if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;

export const mktApi = {
  meta: () => send<Meta>('GET', '/meta'),
  newBooks: (p: { frm?: string; to?: string; durum?: string; yayinevi?: string; sahip?: string; q?: string; page?: number; yenile?: boolean }) =>
    send<BookPage>('GET', `/new-books${qs(p)}`, undefined, 180_000),
  card: (stok: string, yenile = false) => send<Card>('GET', `/books/${enc(stok)}/card${qs({ yenile })}`, undefined, 180_000),
  create: (stokKodu: string) => send<Plan>('POST', '/plans', { kind: 'yeni', stokKodu }, 180_000),
  plan: (id: string) => send<Plan>('GET', `/plans/${enc(id)}`),
  update: (id: string, b: { baslik?: string; yayinTarihi?: string | null; sahip?: string; butceCerceve?: number | null }) =>
    send<Plan>('PATCH', `/plans/${enc(id)}`, b),
  remove: (id: string) => send<{ ok: boolean }>('DELETE', `/plans/${enc(id)}`),
  lines: (id: string, items: Line[]) => send<Plan>('PUT', `/plans/${enc(id)}/lines`, { items }),
  tasks: (id: string, items: Task[]) => send<Plan>('PUT', `/plans/${enc(id)}/tasks`, { items }),
  suggest: (id: string, materyaller?: string[]) => send<{ job: Job; plan: Plan }>('POST', `/plans/${enc(id)}/suggest`, { materyaller }, 180_000),
  jobs: (id: string) => send<{ items: Job[] }>('GET', `/plans/${enc(id)}/jobs`),
  newMaterial: (id: string, tur: string, metin?: string) => send<{ material?: Material; job?: Job }>('POST', `/plans/${enc(id)}/materials`, { tur, metin }),
  saveMaterial: (mid: string, metin: string) => send<{ material: Material }>('PUT', `/materials/${enc(mid)}`, { metin }),
  approveMaterial: (mid: string, seviye: 'editoryal' | 'pazarlama') => send<{ material: Material }>('POST', `/materials/${enc(mid)}/approve`, { seviye }),
  submit: (id: string) => send<Plan>('POST', `/plans/${enc(id)}/submit`, {}),
  withdraw: (id: string) => send<Plan>('POST', `/plans/${enc(id)}/withdraw`, {}),
  approve: (id: string, note?: string) => send<Plan>('POST', `/plans/${enc(id)}/approve`, { note }),
  upperApprove: (id: string, note?: string) => send<Plan>('POST', `/plans/${enc(id)}/upper-approve`, { note }),
  reject: (id: string, note: string) => send<Plan>('POST', `/plans/${enc(id)}/reject`, { note }),
  revise: (id: string, reason: string) => send<Plan>('POST', `/plans/${enc(id)}/revise`, { reason }),
  events: (id: string) => send<{ items: Event[] }>('GET', `/plans/${enc(id)}/events`),
  todo: (id: string) => send<{ items: TodoItem[]; planOnayli: boolean }>('GET', `/plans/${enc(id)}/crm-todo`, undefined, 180_000),
  pdfUrl: (id: string) => `${ENGINE_BASE}${B}/plans/${enc(id)}/export.pdf`,
  csvUrl: (id: string) => `${ENGINE_BASE}${B}/plans/${enc(id)}/export.csv`,
  packageUrl: (id: string) => `${ENGINE_BASE}${B}/plans/${enc(id)}/package.zip`,
  todoCsvUrl: (id: string) => `${ENGINE_BASE}${B}/plans/${enc(id)}/crm-todo.csv`,
};

/* ------------------------------------------------------------------ biçim */

const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${int0.format(v)} ₺`);
export const fmtPct = (v: number | null | undefined) =>
  v === null || v === undefined || !Number.isFinite(v) ? '—' : new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 1 }).format(v);

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
const shortFmt = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' });
const utc = (iso: string) => {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};
export const fmtDay = (iso: string | null | undefined) => (iso ? dayFmt.format(utc(iso)) : '—');
export const fmtShortDay = (iso: string | null | undefined) => (iso ? shortFmt.format(utc(iso)) : '—');
export const fmtStamp = (iso: string | null | undefined) =>
  iso ? new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso)) : '—';
export const dayTag = (g: number | null | undefined) => (g === null || g === undefined ? '' : g === 0 ? 'Yayın günü' : g < 0 ? `D${g}` : `D+${g}`);

/** «1.234,5» ya da «1234.5» → sayı; boşsa null. */
export function parseNum(s: string): number | null {
  const t = s.trim().replace(/\s/g, '').replace(/₺|%/g, '');
  if (!t) return null;
  const norm = t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : t;
  const n = Number(norm);
  return Number.isFinite(n) ? n : null;
}

export const STATUS_TONE: Record<PlanStatus, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  taslak: 'muted',
  onayda: 'warn',
  onayli: 'ok',
  geri: 'err',
  arsiv: 'muted',
};

export const MATERIAL_TONE: Record<MaterialStatus, 'ok' | 'warn' | 'muted'> = {
  taslak: 'muted',
  'editoryal-onayli': 'warn',
  onayli: 'ok',
};

export const SOURCE_LABEL = (k: string | null | undefined): string => {
  if (!k) return '—';
  if (k === 'zeki') return 'Zeki AI';
  if (k === 'kullanici') return 'Elle';
  if (k.startsWith('crm:')) return 'CRM kitap kartı';
  if (k === 'crm') return 'CRM';
  return k;
};

export const DROP_REASON: Record<string, string> = {
  'alinti-bulunamadi': 'alıntı kaynakta birebir yok',
  'kaynaksiz-rakam': 'kaynaksız rakam',
  'kanitsiz-iddia': 'kanıtsız üstünlük iddiası',
  'teknoloji-adi': 'teknoloji adı',
};
