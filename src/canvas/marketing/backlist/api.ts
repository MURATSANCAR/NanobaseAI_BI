import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../../engine';
import { httpErrorText } from '../../httpError';
import type { Job, Material, Plan, PlanStatus } from '../api';
import type { Kaynaklar } from '../../components/sqlInfo';

/** M17 Backlist uçları: /api/v1/marketing/backlist*. Plan onayı, bütçe, takvim ve materyal onayı çekirdeğin uçlarıyla
 *  (`mktApi`); backlist planı `kind='backlist'` olarak aynı akıştan geçer. */

export type ComponentKey = 'egilim' | 'stok' | 'marj' | 'tahmin' | 'sapma';
export type Weights = Record<ComponentKey, number>;

export type RunMeta = {
  tarih?: string;
  veriSonu?: string;
  sonTamAy?: string;
  sonTamAyAdi?: string;
  son12?: [string, string];
  onceki12?: [string, string];
  seri?: [string, string];
  kume?: { kaynak: 'm46' | 'crm'; ad: string; sayi: number; haric157?: number; ilkYayinYok?: number; yil?: number };
  tahmin?: { baslangic?: string; guncelleme?: number } | null;
  notlar?: string[];
  sureMs?: number;
  _at?: string | null;
};

export type BlMeta = {
  components: Array<{ key: ComponentKey; ad: string; aciklama: string }>;
  formula: string;
  sorts: Record<string, string>;
  m46States: Record<string, string>;
  matchTypes: Record<string, string>;
  roles: Record<string, string>;
  materials: Record<string, string>;
  defaultWeights: Weights;
  teamWeights: Partial<Weights> | null;
  teamWeightsBy: string | null;
  teamWeightsAt: string | null;
  settings: { agendaWeeks: number; remindWeeks: number; topicWeeks: number; campaignYears: number; digestMin: number; minMonths: number };
  run: RunMeta | null;
  lastRun: { tarih?: string; hata?: string; _at?: string | null } | null;
  modelReady: boolean;
  me: { username: string; canWrite: boolean; canSeeBudget: boolean; canApprove: boolean; canEditorial: boolean; canSetTeamWeights: boolean; canExport: boolean };
};

export type Day = { id: string; ad: string | null; baslangic: string | null; bitis: string | null; yontem?: string | null; kesinlik?: string | null; gecenYil?: string | null };
export type PlanRef = { id: string; kind: string; durum: PlanStatus; durumAdi: string; baslik: string; baslangic: string | null; rol: string; surum: number };

export type Row = {
  stokKodu: string;
  ad: string | null;
  yazar: string | null;
  yayinevi: string | null;
  kitaplik: string | null;
  hedefKitle: string | null;
  ilkYayin: string | null;
  kapak: string | null;
  adetSon12: number;
  adetOnceki12: number;
  degisim: number | null;
  ciroSon12: number | null;
  marj: number | null;
  stok: number | null;
  tukenmeAy: number | null;
  satisYok: boolean;
  tahmin12: number | null;
  m46: { durum: string | null; durumAdi: string | null; oran: number | null; hedefAdet: number | null; hedefCiro: number | null; sapmaAcik: boolean; acikTutar: number | null };
  ozelGunler: Day[];
  yaklasanGunler?: Day[];
  dijital: { ekitapStokKodu?: string | null; ekitapIsbn?: string | null };
  detay: { yaslar?: string | null; siniflar?: string | null; turler?: string | null };
  bilesen: Record<ComponentKey, { yuzdelik: number | null; ham: number | string | null }>;
  endeks: number | null;
  endeksVarsayilan: number | null;
  planlar: PlanRef[];
};

export type ListPage = {
  items: Row[];
  total: number;
  hepsi: number;
  page: number;
  pageSize: number;
  facets: { yayinevleri: string[]; kitapliklar: string[]; hedefKitleler: string[] };
  gunler: Array<{ id: string; ad: string | null; baslangic: string | null; kitap: number }>;
  kpi: { sapmaAcik: number; stokta: number; yakinGun: number; planli: number };
  agirlik: Weights;
  run: RunMeta | null;
  kaynaklar?: Kaynaklar;
};

export type Match = {
  id: string;
  stokKodu: string;
  tur: 'ozel-gun' | 'yazar-yeni' | 'konu';
  turAdi: string;
  etiket: string | null;
  tarih: string | null;
  bitis: string | null;
  kaynak: string;
  skor: number | null;
  onay: 'bekliyor' | 'kabul' | 'red' | null;
  onaylayan: string | null;
  detay: Record<string, unknown>;
};

export type Effect = {
  kampanyaId: string;
  stokKodu: string;
  kitapAdi?: string | null;
  ad: string | null;
  mecra: string | null;
  baslangic: string | null;
  bitis: string | null;
  ekIskonto: number | null;
  netIskonto: number | null;
  planlananCiro: number | null;
  gerceklesenCiro: number | null;
  once3: number | null;
  kampanya: number | null;
  sonra2: number | null;
  kampanyaAyi: number | null;
  kapsam: 'tam' | 'suruyor' | 'veri-yok';
  aylikDegisim: number | null;
  backlist: boolean;
};

export type Detail = Row & {
  seri: Array<{ ay: string; adet: number; ciro: number | null }>;
  kampanyalar: Effect[];
  eslesmeler: Match[];
  eylemler: Array<{ eylem: string; gerekce: string }>;
  veriSonu: string | null;
  asof: string | null;
  kaynaklar?: Kaynaklar;
};

export type AgendaBook = { stokKodu: string; ad: string | null; yazar: string | null; stok: number | null; tukenmeAy: number | null; gecenYilAyAdet: number | null; planlar: PlanRef[]; sapmaAcik: boolean };
export type Agenda = {
  hafta: number;
  bugun: string;
  gunler: Array<Day & { kalanGun: number; kitaplar: AgendaBook[]; stokta: number; aktivasyonsuz: number }>;
  yazarlar: Array<{ stokKodu: string; ad: string | null; tarih: string | null; yazar: string | null; kitaplar: AgendaBook[] }>;
  konular: Array<Match & { kitap: AgendaBook }>;
  kaynaklar?: Kaynaklar;
};

export type Campaign = {
  kampanyaId: string;
  ad: string | null;
  mecra: string | null;
  baslangic: string | null;
  bitis: string | null;
  ekIskonto: number | null;
  netIskonto: number | null;
  planlananCiro: number | null;
  gerceklesenCiro: number | null;
  kampanyaAyi: number | null;
  urunler: Effect[];
  once3: number;
  kampanya: number;
  sonra2: number;
  tam: boolean;
  aylikDegisim: number | null;
  backlistUrun: number;
};

export type PlanBook = { stokKodu: string; rol: string; rolAdi: string; ad: string | null; sira: number; gerekce: string | null };
export type Activation = Plan & { kitaplar: PlanBook[] };

export type ListParams = {
  sirala?: string;
  yon?: string;
  agirlik?: string;
  yayinevi?: string;
  kitaplik?: string;
  hedef_kitle?: string;
  m46?: string;
  stokta?: boolean;
  ozel_gun?: string;
  plan?: string;
  q?: string;
  page?: number;
};

const B = '/api/v1/marketing/backlist';

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
  const detail = async () => {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    return typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
  };
  if (res.status === 403) throw new EngineForbiddenError((await detail()) || 'Bu işleme yetkiniz yok.');
  if (!res.ok) throw new Error((await detail()) || httpErrorText(res.status));
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

export const weightsText = (w: Weights, keys: ComponentKey[]) => keys.map((k) => `${k}:${w[k] ?? 1}`).join(',');

export const blApi = {
  meta: () => send<BlMeta>('GET', '/meta'),
  list: (p: ListParams) => send<ListPage>('GET', qs(p), undefined, 60_000),
  detail: (stok: string, agirlik?: string) => send<Detail>('GET', `/${enc(stok)}${qs({ agirlik })}`),
  agenda: (hafta?: number) => send<Agenda>('GET', `/agenda${qs({ hafta })}`),
  effects: (yil?: number, backlist?: boolean) => send<{ items: Campaign[]; total: number; yillar: number[]; not: string; kaynaklar?: Kaynaklar }>('GET', `/effects${qs({ yil, backlist })}`),
  activations: (arsiv = false) => send<{ items: Activation[]; total: number; kaynaklar?: Kaynaklar }>('GET', `/activations${qs({ arsiv })}`),
  saveTeamWeights: (w: Weights) => send<{ teamWeights: Weights }>('PUT', '/weights', { agirlik: w }),
  decide: (id: string, karar: 'kabul' | 'red') => send<{ match: Match }>('POST', `/matches/${enc(id)}/decide`, { karar }),
  createPlan: (kitaplar: Array<{ stokKodu: string; rol?: string }>, baslangic?: string) =>
    send<Activation>('POST', '/plans', { kitaplar, baslangic: baslangic || undefined }, 180_000),
  planBooks: (id: string) => send<{ items: PlanBook[] }>('GET', `/plans/${enc(id)}/books`),
  savePlanBooks: (id: string, kitaplar: Array<{ stokKodu: string; rol: string }>) => send<{ items: PlanBook[] }>('PUT', `/plans/${enc(id)}/books`, { kitaplar }),
  newMaterial: (id: string, tur: string, metin?: string) => send<{ material?: Material; job?: Job }>('POST', `/plans/${enc(id)}/materials`, { tur, metin }),
  csvUrl: (p: ListParams) => `${ENGINE_BASE}${B}/export.csv${qs(p)}`,
};

/** Backlist aktivasyonunun içerik türleri; M15 materyal seçicisinde görünmez, backlist planında yalnız bunlar. */
export const BACKLIST_MATERIALS = ['yeniden-kesfet', 'e-bulten-bolum', 'toplu-alim-mektubu'];

/* ------------------------------------------------------------------ biçim */

const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const one = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
export const fmtN = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export const fmtOne = (v: number | null | undefined) => (v === null || v === undefined ? '—' : one.format(v));
export const fmtChange = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 0 }).format(v)}`;
export const monthName = (ym: string | null | undefined) => {
  if (!ym) return '—';
  const [y, m] = ym.split('-').map(Number);
  return new Intl.DateTimeFormat('tr-TR', { month: 'short', year: '2-digit', timeZone: 'UTC' }).format(new Date(Date.UTC(y, m - 1, 1)));
};

export const runout = (r: Pick<Row, 'stok' | 'tukenmeAy' | 'satisYok'>) =>
  r.stok === null ? 'stok bilinmiyor' : r.stok <= 0 ? 'stok yok' : r.satisYok ? 'satış yok' : `${fmtOne(r.tukenmeAy)} ay`;

export const M46_TONE: Record<string, 'ok' | 'warn' | 'err' | 'muted'> = { iyi: 'ok', izle: 'warn', sapma: 'err', baslamadi: 'muted', yok: 'muted' };
